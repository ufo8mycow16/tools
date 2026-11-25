"""Adding books to the library (EPUB, text, a web page) and the book-level helpers the rest of the app uses."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import shutil
import urllib.request

from . import config, db, dialogue, cast, voices
from .epub import read_epub, html_blocks
from .textproc import normalise, is_scene_break, word_count


def _store(meta, source_path='', source_kind='epub'):
    limit = int(config.get('max_chunk_chars'))
    book_id = db.insert('books', {
        'title': meta['title'] or 'Untitled', 'author': meta.get('author', ''), 'series': meta.get('series', ''),
        'description': meta.get('description', ''), 'language': meta.get('language', 'en'),
        'source_path': str(source_path), 'source_kind': source_kind, 'added': db.now(), 'status': 'imported',
    })
    folder = config.book_dir(book_id)
    if meta.get('cover'):
        data, ext = meta['cover']
        p = folder / ('cover' + (ext if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp') else '.jpg'))
        p.write_bytes(data)
        db.update('books', book_id, {'cover': p.name})
    if source_path and Path(source_path).exists():
        try:
            shutil.copy2(source_path, folder / ('source' + Path(source_path).suffix.lower()))
        except Exception:
            pass

    all_paras = [b['text'] for c in meta['chapters'] for b in c['blocks'] if b['kind'] == 'p']
    style = dialogue.quote_style(all_paras)
    with db.connect() as con:
        for i, ch in enumerate(meta['chapters']):
            words = sum(word_count(b['text']) for b in ch['blocks'])
            cur = con.execute('INSERT INTO chapters (book_id, idx, title, include, kind, words) VALUES (?,?,?,?,?,?)',
                              (book_id, i, ch['title'], 1 if ch['kind'] == 'chapter' else 0, ch['kind'], words))
            cid = cur.lastrowid
            rows = dialogue.segment_chapter(ch['blocks'], style, limit)
            con.executemany('INSERT INTO segments (chapter_id, idx, para, kind, text, display, quote_id) '
                            'VALUES (?,?,?,?,?,?,?)',
                            [(cid, j, r['para'], r['kind'], r['text'], r['display'], r['quote_id'])
                             for j, r in enumerate(rows)])
        con.commit()

    # a first cast straight away (rules + the Star Trek table) so the Cast screen isn't empty
    chars = dialogue.discover_characters(all_paras)
    save_characters(book_id, chars)
    run_rule_attribution(book_id)
    auto_cast(book_id)
    return book_id


def save_characters(book_id, chars, replace=False):
    existing = {c['name'].lower(): c for c in db.q('SELECT * FROM characters WHERE book_id=?', (book_id,))}
    if replace:
        db.run("DELETE FROM characters WHERE book_id=? AND voice=''", (book_id,))
        existing = {c['name'].lower(): c for c in db.q('SELECT * FROM characters WHERE book_id=?', (book_id,))}
    for c in chars:
        name = (c.get('name') or '').strip()
        if not name or name in cast.NOT_NAMES:
            continue
        cur = existing.get(name.lower())
        aliases = [a for a in (c.get('aliases') or []) if a and a.lower() != name.lower()]
        if cur:
            old = db.jload(cur['aliases'], [])
            merged = sorted(set(old) | set(aliases))
            vals = {'aliases': json.dumps(merged)}
            if c.get('gender') and not cur['gender']:
                vals['gender'] = c['gender']
            if c.get('description') and not cur['description']:
                vals['description'] = c['description']
            db.update('characters', cur['id'], vals)
        else:
            cid = db.insert('characters', {'book_id': book_id, 'name': name, 'aliases': json.dumps(aliases),
                                           'gender': c.get('gender', ''), 'description': c.get('description', '')})
            existing[name.lower()] = db.one('SELECT * FROM characters WHERE id=?', (cid,))


def characters(book_id):
    rows = db.q('SELECT * FROM characters WHERE book_id=? ORDER BY lines DESC, name', (book_id,))
    for r in rows:
        r['aliases'] = db.jload(r['aliases'], [])
    return rows


def run_rule_attribution(book_id, keep_existing=True):
    """Rules-only speakers for every chapter (Gemma's and Glen's own choices are kept)."""
    chars = characters(book_id)
    gender_of = {c['name']: c['gender'] for c in chars}
    for ch in db.q('SELECT id FROM chapters WHERE book_id=? ORDER BY idx', (book_id,)):
        segs = db.q('SELECT id, para, kind, display, quote_id, speaker, speaker_source FROM segments '
                    'WHERE chapter_id=? ORDER BY idx', (ch['id'],))
        if not keep_existing:
            for s in segs:
                if s['speaker_source'] != 'manual':
                    s['speaker_source'] = ''
        dialogue.attribute_rules(segs, chars, gender_of)
        rows, overrides = [], []
        for i, s in enumerate(segs):
            if s['kind'] != 'dialogue':
                continue
            near = ' '.join(x['display'] for x in segs[max(0, i - 1):i + 2]
                            if x['kind'] == 'narration' and x['para'] == s['para'])
            if s['speaker_source'] == 'manual':
                continue
            if s['speaker_source'] == 'gemma':
                # a plain speech tag ("Kirk asked") beats Gemma when they disagree
                if s.get('rule_how') == 'tag' and s.get('rule_speaker') and s['rule_speaker'] != s['speaker']:
                    overrides.append((s['rule_speaker'], s['id']))
                continue
            rows.append((s['speaker'], s['speaker_source'], dialogue.rule_emotion(near), dialogue.rule_sound(near),
                         s['id']))
        with db.connect() as con:
            con.executemany('UPDATE segments SET speaker=?, speaker_source=?, emotion=?, sound=? WHERE id=?', rows)
            con.executemany("UPDATE segments SET speaker=?, speaker_source='tag' WHERE id=?", overrides)
            con.commit()
    count_lines(book_id)


def count_lines(book_id):
    counts = {r['speaker']: r['n'] for r in db.q(
        "SELECT s.speaker, COUNT(DISTINCT s.quote_id || '-' || s.chapter_id) n FROM segments s "
        "JOIN chapters c ON c.id=s.chapter_id WHERE c.book_id=? AND s.kind='dialogue' AND s.speaker!='' "
        "GROUP BY s.speaker", (book_id,))}
    for c in db.q('SELECT id, name FROM characters WHERE book_id=?', (book_id,)):
        db.update('characters', c['id'], {'lines': counts.get(c['name'], 0)})
    # anyone Gemma or Glen gave lines to who isn't on the list yet
    names = {c['name'] for c in db.q('SELECT name FROM characters WHERE book_id=?', (book_id,))}
    for n, k in counts.items():
        if n not in names:
            db.insert('characters', {'book_id': book_id, 'name': n, 'aliases': '[]', 'lines': k})


def auto_cast(book_id):
    """Give characters a voice when one obviously fits: same name as a reference voice (kirk.mp3 -> Kirk)."""
    vs = voices.scan()
    by_key = {v['key'].lower(): v['key'] for v in vs}
    by_name = {v['name'].lower(): v['key'] for v in vs}
    for c in db.q("SELECT * FROM characters WHERE book_id=? AND voice=''", (book_id,)):
        names = [c['name']] + db.jload(c['aliases'], [])
        hit = None
        for n in names:
            k = n.lower().replace(' ', '_')
            hit = by_key.get(k) or by_name.get(n.lower()) or by_key.get(n.split()[-1].lower())
            if hit:
                break
        if c['name'] == 'Scott' and not hit:
            hit = by_key.get('scotty') or by_key.get('scott')
        if hit:
            db.update('characters', c['id'], {'voice': hit})
    book = db.one('SELECT narrator_voice FROM books WHERE id=?', (book_id,))
    if book and not book['narrator_voice']:
        pick = by_key.get('narrator') or by_key.get('shatner') or by_key.get('kirk_narrator') or by_key.get('kirk')
        if pick:
            db.update('books', book_id, {'narrator_voice': pick})


# ------------------------------------------------------------------------------------------------- importers

def import_epub(path):
    return _store(read_epub(path), path, 'epub')


def import_text(title, text, author=''):
    text = text.replace('\r\n', '\n')
    lines = [normalise(l) for l in re.split(r'\n\s*\n|\n(?=\s{2,})', text)]
    chapters, cur = [], {'title': title or 'Text', 'blocks': [], 'kind': 'chapter'}
    for l in lines:
        if not l:
            continue
        if re.match(r'^(chapter|part|book|prologue|epilogue)\b[^\n]{0,60}$', l, re.I) and len(l) < 70:
            if cur['blocks']:
                chapters.append(cur)
            cur = {'title': l, 'blocks': [{'kind': 'h', 'text': l}], 'kind': 'chapter'}
        elif is_scene_break(l):
            cur['blocks'].append({'kind': 'break', 'text': ''})
        else:
            for p in l.split('\n'):
                p = normalise(p)
                if p:
                    cur['blocks'].append({'kind': 'p', 'text': p})
    if cur['blocks']:
        chapters.append(cur)
    if not chapters:
        raise ValueError('There was no text to read.')
    return _store({'title': title or chapters[0]['title'], 'author': author, 'chapters': chapters}, '', 'text')


class _Article(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self._in_title = True
        a = dict(attrs)
        if tag == 'meta' and a.get('property') == 'og:title' and a.get('content'):
            self.title = a['content']

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False

    def handle_data(self, d):
        if self._in_title and not self.title:
            self.title = d.strip()


def import_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Third Moon Audiobook Studio)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        ctype = r.headers.get('Content-Type', '')
    enc = 'utf-8'
    m = re.search(r'charset=([\w-]+)', ctype)
    if m:
        enc = m.group(1)
    html = raw.decode(enc, 'replace')
    t = _Article()
    try:
        t.feed(html)
    except Exception:
        pass
    # keep the main body: the biggest run of paragraphs, dropping menus and footers
    body = re.sub(r'(?is)<(nav|header|footer|aside|form|script|style|noscript)\b.*?</\1>', ' ', html)
    m = re.search(r'(?is)<article\b.*?</article>', body) or re.search(r'(?is)<main\b.*?</main>', body)
    if m:
        body = m.group(0)
    blocks = [b for b in html_blocks(body) if b['kind'] != 'p' or word_count(b['text']) >= 6 or
              b['text'].endswith(('.', '!', '?', '"', '”'))]
    if not blocks:
        raise ValueError('No readable text found on that page.')
    title = t.title or url
    return _store({'title': title, 'author': re.sub(r'^https?://(www\.)?', '', url).split('/')[0],
                   'chapters': [{'title': title, 'blocks': [{'kind': 'h', 'text': title}] + blocks,
                                 'kind': 'chapter'}]}, url, 'web')


def delete_book(book_id):
    for ch in db.q('SELECT id FROM chapters WHERE book_id=?', (book_id,)):
        db.run('DELETE FROM segments WHERE chapter_id=?', (ch['id'],))
    for t in ('chapters', 'characters', 'bookmarks'):
        db.run(f'DELETE FROM {t} WHERE book_id=?', (book_id,))
    db.run('DELETE FROM pronunciations WHERE book_id=?', (book_id,))
    db.run("UPDATE jobs SET status='cancelled' WHERE book_id=? AND status IN ('queued','running')", (book_id,))
    db.run('DELETE FROM books WHERE id=?', (book_id,))
    shutil.rmtree(config.library_dir() / str(book_id), ignore_errors=True)
