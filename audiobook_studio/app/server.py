"""The studio's web server (standard library only). Serves the app (web/) and a JSON API, and streams audio with
range requests so the player can jump about and phones can scrub."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import json
import mimetypes
import os
import re
import socket
import tempfile
import traceback

from . import analysis, audio, config, db, gemma, jobs, library, voices
from .tts import ENGINE

WEB = config.APP_DIR / 'web'
mimetypes.add_type('audio/mp4', '.m4a')
mimetypes.add_type('audio/mp4', '.m4b')
mimetypes.add_type('audio/flac', '.flac')
mimetypes.add_type('application/manifest+json', '.webmanifest')
mimetypes.add_type('text/javascript', '.js')

ROUTES = []


def route(method, pattern):
    rx = re.compile('^' + pattern + '$')

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


class HttpError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def lan_addresses():
    out = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        out.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.'):
                out.add(ip)
    except Exception:
        pass
    return sorted(out)


# ------------------------------------------------------------------------------------------------- helpers

def book_summary(b):
    stats = db.one("SELECT COUNT(*) total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) done, "
                   "SUM(duration) dur, SUM(words) words FROM chapters WHERE book_id=? AND include=1", (b['id'],))
    b = dict(b)
    b['chapters_total'] = stats['total'] or 0
    b['chapters_done'] = stats['done'] or 0
    b['duration'] = stats['dur'] or 0
    b['words'] = stats['words'] or 0
    b['cover_url'] = f"/files/book/{b['id']}/cover" if b['cover'] else ''
    pos = db.one('SELECT SUM(duration) d FROM chapters WHERE book_id=? AND include=1 AND idx<?',
                 (b['id'], b['pos_chapter']))
    listened = (pos['d'] or 0) + (b['pos_time'] or 0)
    b['listened'] = listened
    b['progress'] = (listened / b['duration']) if b['duration'] else 0
    return b


def chapter_detail(cid):
    ch = db.one('SELECT * FROM chapters WHERE id=?', (cid,))
    if not ch:
        raise HttpError(404, 'No such chapter')
    segs = db.q('SELECT id, idx, para, kind, display, text, quote_id, speaker, speaker_source, emotion, sound, '
                'voice, duration, start, status, audio_hash FROM segments WHERE chapter_id=? ORDER BY idx', (cid,))
    ch['segments'] = segs
    ch['audio_url'] = f"/files/chapter/{cid}.m4a?v={int(ch['duration'] * 1000)}" if ch['status'] == 'done' else ''
    return ch


# ------------------------------------------------------------------------------------------------- status

@route('GET', '/api/status')
def api_status(h, m, body):
    st = gemma.status() if config.get('use_ollama') else {'ok': False, 'models': [], 'model_ready': False,
                                                         'error': 'switched off'}
    ref = Path(config.get('reference_voices'))
    cb = config.path('chatterbox_root') / 'venv'
    return {
        'app': 'Third Moon Audiobook Studio', 'version': '1.0',
        'gemma': st, 'engine': ENGINE.status(), 'ffmpeg': audio.check_ffmpeg(),
        'reference_folder_ok': ref.is_dir(), 'chatterbox_venv_ok': cb.is_dir(),
        'port': config.get('port'), 'lan': [f"http://{ip}:{config.get('port')}" for ip in lan_addresses()]
        if config.get('listen_on_network') else [],
        'books': db.one('SELECT COUNT(*) n FROM books')['n'],
        'queue': db.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")['n'],
    }


@route('GET', '/api/settings')
def api_settings(h, m, body):
    return config.load()


@route('POST', '/api/settings')
def api_settings_save(h, m, body):
    s = config.update(body or {})
    if 'reference_voices' in (body or {}) or 'voices_dir' in (body or {}):
        voices.scan()
    return s


@route('GET', '/api/stats')
def api_stats(h, m, body):
    rows = db.q('SELECT * FROM stats ORDER BY day DESC LIMIT 60')
    tot = db.one('SELECT SUM(seconds_listened) l, SUM(seconds_generated) g FROM stats')
    return {'days': rows, 'listened': tot['l'] or 0, 'generated': tot['g'] or 0}


@route('POST', '/api/listened')
def api_listened(h, m, body):
    jobs.listened(body.get('seconds', 0))
    return {'ok': True}


# --------------------------------------------------------------------------------------------------- books

@route('GET', '/api/books')
def api_books(h, m, body):
    return [book_summary(b) for b in db.q('SELECT * FROM books ORDER BY COALESCE(opened, added) DESC')]


@route('POST', '/api/books/import')
def api_import(h, m, body):
    name = unquote(h.headers.get('X-Filename', 'book.epub'))
    data = h.raw_body
    if not data:
        raise HttpError(400, 'No file came through.')
    ext = Path(name).suffix.lower()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / ('upload' + ext)
        p.write_bytes(data)
        if ext == '.epub':
            bid = library.import_epub(p)
            db.update('books', bid, {'source_path': name})
        elif ext in ('.txt', '.md', '.text'):
            text = data.decode('utf-8', 'replace')
            bid = library.import_text(Path(name).stem, text)
        elif ext in ('.html', '.htm', '.xhtml'):
            from .epub import html_blocks
            blocks = html_blocks(data.decode('utf-8', 'replace'))
            bid = library.import_text(Path(name).stem, '\n\n'.join(b['text'] for b in blocks))
        else:
            raise HttpError(400, f'I can read .epub, .txt, .md and .html files - not {ext or "that"}.')
    if config.get('use_ollama'):
        jobs.add('analyse', bid)
    return book_summary(db.one('SELECT * FROM books WHERE id=?', (bid,)))


@route('POST', '/api/books/text')
def api_import_text(h, m, body):
    text = (body or {}).get('text', '')
    if not text.strip():
        raise HttpError(400, 'Paste some text first.')
    bid = library.import_text(body.get('title') or 'Pasted text', text, body.get('author', ''))
    db.update('books', bid, {'source_kind': 'paste'})
    if body.get('listen_now'):
        jobs.add('generate', bid)
    return book_summary(db.one('SELECT * FROM books WHERE id=?', (bid,)))


@route('POST', '/api/books/url')
def api_import_url(h, m, body):
    url = (body or {}).get('url', '').strip()
    if not re.match(r'^https?://', url):
        raise HttpError(400, 'That needs to be a web address starting with http.')
    try:
        bid = library.import_url(url)
    except Exception as e:
        raise HttpError(400, f'Could not read that page: {e}')
    if body.get('listen_now'):
        jobs.add('generate', bid)
    return book_summary(db.one('SELECT * FROM books WHERE id=?', (bid,)))


@route('GET', r'/api/books/(\d+)')
def api_book(h, m, body):
    b = db.one('SELECT * FROM books WHERE id=?', (int(m[1]),))
    if not b:
        raise HttpError(404, 'No such book')
    b = book_summary(b)
    b['chapters'] = db.q('SELECT c.id, c.idx, c.title, c.include, c.kind, c.status, c.duration, c.words, c.summary, '
                         "(SELECT COUNT(*) FROM segments s WHERE s.chapter_id=c.id AND s.kind='dialogue') dialogue, "
                         "(SELECT COUNT(*) FROM segments s WHERE s.chapter_id=c.id) lines, "
                         "(SELECT COUNT(*) FROM segments s WHERE s.chapter_id=c.id AND s.status='done') made "
                         'FROM chapters c WHERE c.book_id=? ORDER BY c.idx', (b['id'],))
    b['characters'] = library.characters(b['id'])
    b['bookmarks'] = db.q('SELECT * FROM bookmarks WHERE book_id=? ORDER BY chapter_idx, time', (b['id'],))
    b['unassigned'] = db.one("SELECT COUNT(*) n FROM segments s JOIN chapters c ON c.id=s.chapter_id WHERE "
                             "c.book_id=? AND c.include=1 AND s.kind='dialogue' AND s.speaker=''", (b['id'],))['n']
    return b


@route('PATCH', r'/api/books/(\d+)')
def api_book_update(h, m, body):
    bid = int(m[1])
    allowed = {k: v for k, v in (body or {}).items() if k in ('title', 'author', 'series', 'description',
                                                             'narrator_voice', 'pos_chapter', 'pos_time', 'speed')}
    if 'pos_time' in allowed or 'pos_chapter' in allowed:
        allowed['opened'] = db.now()
    db.update('books', bid, allowed)
    return {'ok': True}


@route('DELETE', r'/api/books/(\d+)')
def api_book_delete(h, m, body):
    jobs.cancel_book(int(m[1]))
    library.delete_book(int(m[1]))
    return {'ok': True}


@route('POST', r'/api/books/(\d+)/analyse')
def api_analyse(h, m, body):
    return {'job': jobs.add('analyse', int(m[1]))}


@route('POST', r'/api/books/(\d+)/rules')
def api_rules(h, m, body):
    library.run_rule_attribution(int(m[1]), keep_existing=not (body or {}).get('reset'))
    library.auto_cast(int(m[1]))
    return {'ok': True}


@route('POST', r'/api/books/(\d+)/generate')
def api_generate(h, m, body):
    chapters = (body or {}).get('chapters') or None
    return {'job': jobs.add('generate', int(m[1]), chapters=chapters)}


@route('POST', r'/api/books/(\d+)/stop')
def api_stop(h, m, body):
    jobs.cancel_book(int(m[1]))
    return {'ok': True}


@route('POST', r'/api/books/(\d+)/export')
def api_export(h, m, body):
    return {'job': jobs.add('export', int(m[1]), format=(body or {}).get('format', 'm4b'))}


@route('GET', r'/api/books/(\d+)/exports')
def api_exports(h, m, body):
    out = []
    for j in db.q("SELECT * FROM jobs WHERE kind='export' AND book_id=? AND status='done' ORDER BY id DESC",
                  (int(m[1]),)):
        f = db.jload(j['args'], {}).get('file')
        if f and Path(f).exists():
            out.append({'file': Path(f).name, 'format': db.jload(j['args'], {}).get('format'),
                        'size': Path(f).stat().st_size, 'url': '/files/export?path=' + f, 'when': j['finished']})
    return out


@route('POST', r'/api/books/(\d+)/recap')
def api_recap(h, m, body):
    upto = int((body or {}).get('upto', 0))
    return {'job': jobs.add('summary', int(m[1]), recap=True, upto=upto)}


@route('GET', r'/api/books/(\d+)/search')
def api_search(h, m, body):
    q = (h.query.get('q') or [''])[0].strip()
    if len(q) < 2:
        return []
    rows = db.q("SELECT s.id, s.display, s.start, s.speaker, c.idx chapter_idx, c.title chapter_title, c.id chapter_id "
                "FROM segments s JOIN chapters c ON c.id=s.chapter_id WHERE c.book_id=? AND s.display LIKE ? "
                "ORDER BY c.idx, s.idx LIMIT 200", (int(m[1]), f'%{q}%'))
    return rows


# --------------------------------------------------------------------------------------------- characters

@route('GET', r'/api/books/(\d+)/characters')
def api_chars(h, m, body):
    return library.characters(int(m[1]))


@route('POST', r'/api/books/(\d+)/characters')
def api_char_add(h, m, body):
    name = (body or {}).get('name', '').strip()
    if not name:
        raise HttpError(400, 'A character needs a name.')
    library.save_characters(int(m[1]), [{'name': name, 'gender': body.get('gender', ''),
                                         'aliases': body.get('aliases', [])}])
    return library.characters(int(m[1]))


@route('PATCH', r'/api/characters/(\d+)')
def api_char_update(h, m, body):
    c = db.one('SELECT * FROM characters WHERE id=?', (int(m[1]),))
    if not c:
        raise HttpError(404, 'No such character')
    vals = {k: v for k, v in (body or {}).items() if k in ('voice', 'gender', 'description', 'hidden')}
    if 'aliases' in (body or {}):
        vals['aliases'] = json.dumps([a.strip() for a in body['aliases'] if a.strip()])
    if body.get('name') and body['name'] != c['name']:
        new = body['name'].strip()
        vals['name'] = new
        db.run('UPDATE segments SET speaker=? WHERE speaker=? AND chapter_id IN (SELECT id FROM chapters WHERE book_id=?)',
               (new, c['name'], c['book_id']))
    db.update('characters', c['id'], vals)
    return {'ok': True}


@route('POST', r'/api/characters/(\d+)/merge')
def api_char_merge(h, m, body):
    c = db.one('SELECT * FROM characters WHERE id=?', (int(m[1]),))
    into = db.one('SELECT * FROM characters WHERE id=?', (int(body['into']),))
    if not c or not into:
        raise HttpError(404, 'No such character')
    db.run('UPDATE segments SET speaker=? WHERE speaker=? AND chapter_id IN (SELECT id FROM chapters WHERE book_id=?)',
           (into['name'], c['name'], c['book_id']))
    al = set(db.jload(into['aliases'], [])) | set(db.jload(c['aliases'], [])) | {c['name']}
    db.update('characters', into['id'], {'aliases': json.dumps(sorted(al))})
    db.run('DELETE FROM characters WHERE id=?', (c['id'],))
    library.count_lines(c['book_id'])
    return {'ok': True}


@route('DELETE', r'/api/characters/(\d+)')
def api_char_delete(h, m, body):
    c = db.one('SELECT * FROM characters WHERE id=?', (int(m[1]),))
    if c:
        db.run("UPDATE segments SET speaker='', speaker_source='' WHERE speaker=? AND chapter_id IN "
               "(SELECT id FROM chapters WHERE book_id=?)", (c['name'], c['book_id']))
        db.run('DELETE FROM characters WHERE id=?', (c['id'],))
    return {'ok': True}


@route('GET', r'/api/characters/(\d+)/lines')
def api_char_lines(h, m, body):
    c = db.one('SELECT * FROM characters WHERE id=?', (int(m[1]),))
    return db.q("SELECT s.id, s.display, c.idx chapter_idx, c.title chapter_title FROM segments s JOIN chapters c "
                "ON c.id=s.chapter_id WHERE c.book_id=? AND s.speaker=? AND s.kind='dialogue' ORDER BY c.idx, s.idx "
                "LIMIT 60", (c['book_id'], c['name']))


# ------------------------------------------------------------------------------------------- chapters/lines

@route('GET', r'/api/chapters/(\d+)')
def api_chapter(h, m, body):
    return chapter_detail(int(m[1]))


@route('PATCH', r'/api/chapters/(\d+)')
def api_chapter_update(h, m, body):
    vals = {k: v for k, v in (body or {}).items() if k in ('include', 'title')}
    if 'include' in vals:
        vals['include'] = 1 if vals['include'] else 0
    db.update('chapters', int(m[1]), vals)
    return {'ok': True}


@route('POST', r'/api/chapters/(\d+)/summary')
def api_chapter_summary(h, m, body):
    ch = db.one('SELECT book_id FROM chapters WHERE id=?', (int(m[1]),))
    return {'job': jobs.add('summary', ch['book_id'], int(m[1]))}


@route('PATCH', r'/api/segments/(\d+)')
def api_segment_update(h, m, body):
    s = db.one('SELECT * FROM segments WHERE id=?', (int(m[1]),))
    if not s:
        raise HttpError(404, 'No such line')
    vals = {}
    for k in ('speaker', 'emotion', 'sound', 'voice', 'text', 'kind'):
        if k in (body or {}):
            vals[k] = body[k] or ''
    if 'speaker' in vals or 'emotion' in vals or 'sound' in vals:
        vals['speaker_source'] = 'manual'
    whole = (body or {}).get('whole_quote')
    if whole and s['quote_id'] and ('speaker' in vals):
        db.run("UPDATE segments SET speaker=?, speaker_source='manual' WHERE chapter_id=? AND quote_id=?",
               (vals['speaker'], s['chapter_id'], s['quote_id']))
    db.update('segments', s['id'], vals)
    ch = db.one('SELECT book_id FROM chapters WHERE id=?', (s['chapter_id'],))
    if 'speaker' in vals:
        library.count_lines(ch['book_id'])
    return {'ok': True}


@route('POST', r'/api/segments/(\d+)/regenerate')
def api_segment_regen(h, m, body):
    s = db.one('SELECT chapter_id FROM segments WHERE id=?', (int(m[1]),))
    ch = db.one('SELECT book_id FROM chapters WHERE id=?', (s['chapter_id'],))
    return {'job': jobs.add('segment', ch['book_id'], s['chapter_id'], segment=int(m[1]))}


# --------------------------------------------------------------------------------------------------- voices

@route('GET', '/api/voices')
def api_voices(h, m, body):
    vs = voices.scan()
    for v in vs:
        v['preview_url'] = f"/files/voice/{v['key']}/preview.mp3" if v['preview'] and Path(v['preview']).exists() else ''
        v['reference_url'] = f"/files/voice/{v['key']}/reference"
        v['used_by'] = [r['name'] for r in db.q('SELECT name FROM characters WHERE voice=?', (v['key'],))]
    return vs


@route('POST', '/api/voices/upload')
def api_voice_upload(h, m, body):
    name = unquote(h.headers.get('X-Filename', 'voice.wav'))
    return voices.add_upload(name, h.raw_body)


@route('PATCH', r'/api/voices/([\w\-]+)')
def api_voice_update(h, m, body):
    vals = {k: v for k, v in (body or {}).items() if k in ('name', 'gender', 'notes', 'favourite')}
    db.update('voices', m[1], vals, key='key')
    return {'ok': True}


@route('POST', r'/api/voices/([\w\-]+)/preview')
def api_voice_preview(h, m, body):
    return {'job': jobs.add('preview', voice=m[1], text=(body or {}).get('text') or None)}


# ---------------------------------------------------------------------------------------------- pronunciation

@route('GET', '/api/pronunciations')
def api_pron(h, m, body):
    book = int((h.query.get('book') or ['0'])[0])
    return db.q('SELECT * FROM pronunciations WHERE book_id IN (0, ?) ORDER BY book_id DESC, pattern', (book,))


@route('POST', '/api/pronunciations')
def api_pron_add(h, m, body):
    if not (body or {}).get('pattern'):
        raise HttpError(400, 'Say which word to change.')
    pid = db.insert('pronunciations', {'book_id': int(body.get('book_id', 0)), 'pattern': body['pattern'],
                                       'replacement': body.get('replacement', ''),
                                       'whole_word': 1 if body.get('whole_word', True) else 0,
                                       'match_case': 1 if body.get('match_case') else 0,
                                       'is_regex': 1 if body.get('is_regex') else 0})
    return db.one('SELECT * FROM pronunciations WHERE id=?', (pid,))


@route('PATCH', r'/api/pronunciations/(\d+)')
def api_pron_update(h, m, body):
    vals = {k: v for k, v in (body or {}).items() if k in ('pattern', 'replacement', 'whole_word', 'match_case',
                                                           'is_regex', 'enabled')}
    db.update('pronunciations', int(m[1]), vals)
    return {'ok': True}


@route('DELETE', r'/api/pronunciations/(\d+)')
def api_pron_delete(h, m, body):
    db.run('DELETE FROM pronunciations WHERE id=?', (int(m[1]),))
    return {'ok': True}


# ------------------------------------------------------------------------------------------------- bookmarks

@route('POST', '/api/bookmarks')
def api_bm_add(h, m, body):
    bid = db.insert('bookmarks', {'book_id': int(body['book_id']), 'chapter_idx': int(body.get('chapter_idx', 0)),
                                  'time': float(body.get('time', 0)), 'segment_id': int(body.get('segment_id') or 0),
                                  'label': body.get('label', ''), 'note': body.get('note', ''),
                                  'colour': body.get('colour', 'gold'), 'created': db.now()})
    return db.one('SELECT * FROM bookmarks WHERE id=?', (bid,))


@route('PATCH', r'/api/bookmarks/(\d+)')
def api_bm_update(h, m, body):
    db.update('bookmarks', int(m[1]), {k: v for k, v in (body or {}).items() if k in ('label', 'note', 'colour')})
    return {'ok': True}


@route('DELETE', r'/api/bookmarks/(\d+)')
def api_bm_delete(h, m, body):
    db.run('DELETE FROM bookmarks WHERE id=?', (int(m[1]),))
    return {'ok': True}


# ------------------------------------------------------------------------------------------------------ jobs

@route('GET', '/api/jobs')
def api_jobs(h, m, body):
    return jobs.state()


@route('POST', r'/api/jobs/(\d+)/cancel')
def api_job_cancel(h, m, body):
    jobs.cancel(int(m[1]))
    return {'ok': True}


@route('POST', '/api/queue/pause')
def api_pause(h, m, body):
    jobs.pause((body or {}).get('on', True))
    return {'paused': jobs.state()['paused']}


@route('POST', '/api/engine/unload')
def api_unload(h, m, body):
    ENGINE.unload()
    return {'ok': True}


# ------------------------------------------------------------------------------------------------- the server

class Handler(BaseHTTPRequestHandler):
    server_version = 'ThirdMoonAudiobookStudio/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, data, ctype='application/json; charset=utf-8', extra=None):
        if not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _file(self, path, download_name=None, cache=False):
        path = Path(path)
        if not path.is_file():
            return self._send(404, {'error': 'Not found'})
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        start, end = 0, size - 1
        rng = self.headers.get('Range')
        code = 200
        if rng:
            mm = re.match(r'bytes=(\d*)-(\d*)', rng)
            if mm:
                if mm[1]:
                    start = int(mm[1])
                    end = int(mm[2]) if mm[2] else size - 1
                elif mm[2]:
                    start = max(0, size - int(mm[2]))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                code = 206
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'max-age=86400' if cache else 'no-cache')
        if code == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if download_name:
            self.send_header('Content-Disposition', f'attachment; filename="{download_name}"')
        self.end_headers()
        if self.command == 'HEAD':
            return
        with open(path, 'rb') as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _files(self, path):
        m = re.match(r'^/files/book/(\d+)/cover$', path)
        if m:
            b = db.one('SELECT cover FROM books WHERE id=?', (int(m[1]),))
            return self._file(config.book_dir(int(m[1])) / b['cover'], cache=True) if b and b['cover'] else \
                self._send(404, {'error': 'No cover'})
        m = re.match(r'^/files/chapter/(\d+)\.m4a$', path)
        if m:
            c = db.one('SELECT audio FROM chapters WHERE id=?', (int(m[1]),))
            return self._file(c['audio']) if c and c['audio'] else self._send(404, {'error': 'Not made yet'})
        m = re.match(r'^/files/segment/(\d+)\.flac$', path)
        if m:
            s = db.one('SELECT audio FROM segments WHERE id=?', (int(m[1]),))
            return self._file(s['audio']) if s and s['audio'] else self._send(404, {'error': 'Not made yet'})
        m = re.match(r'^/files/voice/([\w\-]+)/(preview\.mp3|reference)$', path)
        if m:
            v = voices.get(m[1])
            if not v:
                return self._send(404, {'error': 'No such voice'})
            return self._file(v['preview'] if m[2] == 'preview.mp3' else v['file'])
        if path == '/files/export':
            p = Path((self.query.get('path') or [''])[0]).resolve()
            root = config.export_dir().resolve()
            if root not in p.parents and p != root:
                return self._send(403, {'error': 'Only exported audiobooks can be downloaded.'})
            return self._file(p, download_name=p.name)
        return self._send(404, {'error': 'Not found'})

    def _static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        p = (WEB / path.lstrip('/')).resolve()
        if WEB.resolve() not in p.parents or not p.is_file():
            p = WEB / 'index.html'
        return self._file(p)

    def _dispatch(self):
        u = urlparse(self.path)
        self.query = parse_qs(u.query)
        path = u.path
        try:
            if path.startswith('/api/'):
                length = int(self.headers.get('Content-Length') or 0)
                raw = self.rfile.read(length) if length else b''
                self.raw_body = raw
                body = {}
                if raw and 'json' in (self.headers.get('Content-Type') or ''):
                    body = json.loads(raw.decode('utf-8'))
                for method, rx, fn in ROUTES:
                    if method != self.command:
                        continue
                    m = rx.match(path)
                    if m:
                        return self._send(200, fn(self, m, body))
                return self._send(404, {'error': 'No such API call: ' + path})
            if path.startswith('/files/'):
                return self._files(path)
            return self._static(path)
        except HttpError as e:
            return self._send(e.code, {'error': str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {'error': f'{type(e).__name__}: {e}'})

    do_GET = do_POST = do_PATCH = do_DELETE = do_HEAD = _dispatch


def serve():
    db.init()
    voices.scan()
    jobs.start()
    host = '0.0.0.0' if config.get('listen_on_network') else '127.0.0.1'
    port = int(config.get('port'))
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f'\n  Third Moon Audiobook Studio is running.\n  On this PC:   http://localhost:{port}')
    if config.get('listen_on_network'):
        for ip in lan_addresses():
            print(f'  On the phone: http://{ip}:{port}  (same Wi-Fi)')
    print('  Close this window to stop it.\n', flush=True)
    if config.get('open_browser') and not os.environ.get('AUDIOBOOK_NO_BROWSER'):
        import webbrowser
        try:
            webbrowser.open(f'http://localhost:{port}')
        except Exception:
            pass
    httpd.serve_forever()
