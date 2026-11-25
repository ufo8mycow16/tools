"""The 'Read the book' job: Gemma finds the characters, then who says every line and how; the rules fill in
anything she misses (or do the whole job when she's not available)."""
from . import cast, config, db, gemma, library

PASSAGE_CHARS = 7000


def chapter_paragraphs(chapter_id):
    """[(para, [segments])] in order."""
    segs = db.q('SELECT * FROM segments WHERE chapter_id=? ORDER BY idx', (chapter_id,))
    paras, cur, cur_p = [], [], None
    for s in segs:
        if s['para'] != cur_p and cur:
            paras.append((cur_p, cur))
            cur = []
        cur_p = s['para']
        cur.append(s)
    if cur:
        paras.append((cur_p, cur))
    return paras


def _para_text(segs, mark=True):
    out, last_q = [], None
    for s in segs:
        if s['kind'] == 'break':
            return '* * *'
        if s['kind'] == 'dialogue' and mark and s['quote_id'] != last_q:
            out.append(f"[Q{s['quote_id']}]" + s['display'])
            last_q = s['quote_id']
        else:
            out.append(s['display'])
    return ' '.join(out)


def analyse(book_id, progress, cancelled, log):
    chapters = db.q('SELECT * FROM chapters WHERE book_id=? AND include=1 ORDER BY idx', (book_id,))
    use_gemma = bool(config.get('use_ollama'))
    st = gemma.status() if use_gemma else {'ok': False}
    if use_gemma and not st['ok']:
        log(f"Gemma isn't answering at {config.get('ollama_url')} - using the rules only. ({st.get('error', '')})")
        use_gemma = False
    elif use_gemma and not st['model_ready']:
        log(f"Ollama is running but {config.get('ollama_model')} isn't installed there - using the rules only. "
            f"Models it has: {', '.join(st['models']) or 'none'}")
        use_gemma = False

    total_steps = max(1, len(chapters) * (2 if use_gemma else 1))
    step = 0
    method = 'gemma' if use_gemma else 'rules'

    if use_gemma:
        # 1. characters, chapter by chapter
        for ch in chapters:
            if cancelled():
                return
            progress(step / total_steps, f'Finding characters - {ch["title"]}')
            text = '\n'.join(_para_text(segs, mark=False) for _, segs in chapter_paragraphs(ch['id']))
            for start in range(0, min(len(text), PASSAGE_CHARS * 3), PASSAGE_CHARS):
                try:
                    found = gemma.find_characters(text[start:start + PASSAGE_CHARS], library.characters(book_id))
                    library.save_characters(book_id, _canonicalise(found, book_id))
                except gemma.GemmaUnavailable as e:
                    log(f'Gemma stopped answering ({e}) - finishing with the rules.')
                    use_gemma = False
                    break
            step += 1
            if not use_gemma:
                break

    if use_gemma:
        # 2. speakers and emotions
        for ch in chapters:
            if cancelled():
                return
            progress(step / total_steps, f'Who says what - {ch["title"]}')
            chars = library.characters(book_id)
            aliases = cast.alias_table(chars)
            paras = chapter_paragraphs(ch['id'])
            batch, size = [], 0
            batches = []
            for p, segs in paras:
                t = _para_text(segs)
                if size + len(t) > PASSAGE_CHARS and batch:
                    batches.append(batch)
                    batch, size = batch[-2:], sum(len(_para_text(s)) for _, s in batch[-2:])  # overlap for context
                batch.append((p, segs))
                size += len(t)
            if batch:
                batches.append(batch)
            for b in batches:
                if not any(s['kind'] == 'dialogue' for _, segs in b for s in segs):
                    continue
                passage = '\n\n'.join(_para_text(segs) for _, segs in b)
                try:
                    answers = gemma.attribute(passage, chars)
                except gemma.GemmaUnavailable as e:
                    log(f'Gemma stopped answering ({e}) - finishing with the rules.')
                    use_gemma = False
                    break
                rows = []
                for _, segs in b:
                    for s in segs:
                        if s['kind'] != 'dialogue' or s['speaker_source'] == 'manual':
                            continue
                        a = answers.get(s['quote_id'])
                        if not a or not a['speaker']:
                            continue
                        name = a['speaker']
                        if name.lower() in ('narrator', 'none', 'unknown', ''):
                            name = 'Narrator'
                        else:
                            name = aliases.get(name.lower()) or _match(name, aliases) or name
                        rows.append((name, 'gemma', '' if a['emotion'] == 'neutral' else a['emotion'],
                                     ('[' + a['sound'] + ']') if a['sound'] else '', s['id']))
                if rows:
                    db.many('UPDATE segments SET speaker=?, speaker_source=?, emotion=?, sound=? WHERE id=?', rows)
            step += 1
            if not use_gemma:
                method = 'gemma+rules'
                break
        gemma_lines = db.one("SELECT COUNT(*) n FROM segments s JOIN chapters c ON c.id=s.chapter_id "
                             "WHERE c.book_id=? AND s.speaker_source='gemma'", (book_id,))['n']
        log(f'Gemma placed {gemma_lines} lines.')
        if config.get('unload_ollama_after_analysis'):
            gemma.unload()

    progress(0.97, 'Filling any gaps with the rules')
    library.run_rule_attribution(book_id, keep_existing=True)
    library.count_lines(book_id)
    library.auto_cast(book_id)
    db.update('books', book_id, {'analysed': 1, 'analysis_method': method, 'status': 'ready'})
    unknown = db.one("SELECT COUNT(*) n FROM segments s JOIN chapters c ON c.id=s.chapter_id WHERE c.book_id=? "
                     "AND c.include=1 AND s.kind='dialogue' AND s.speaker=''", (book_id,))['n']
    log(f'Done. Lines still without a speaker (they get the narrator): {unknown}.')


def _match(name, aliases):
    low = name.lower()
    for a, canon in aliases.items():
        if low == a or low.split()[-1] == a or a.split()[-1] == low:
            return canon
    return None


def _canonicalise(found, book_id):
    """Gemma sometimes calls Kirk 'Captain Kirk' or 'Jim' - fold those into the existing character."""
    chars = library.characters(book_id)
    aliases = cast.alias_table(chars)
    out = []
    for c in found:
        canon = aliases.get(c['name'].lower()) or _match(c['name'], aliases)
        tk, entry = cast.trek_entry(c['name'])
        if not canon and tk:
            canon = tk
            c['aliases'] = list(set(c['aliases']) | set(entry[1]))
            c['gender'] = c['gender'] or entry[0]
        if canon and canon != c['name']:
            c['aliases'] = list(set(c['aliases']) | {c['name']})
            c['name'] = canon
        out.append(c)
    return out


def summarise_chapter(chapter_id):
    ch = db.one('SELECT * FROM chapters WHERE id=?', (chapter_id,))
    text = '\n'.join(_para_text(segs, mark=False) for _, segs in chapter_paragraphs(chapter_id))
    if len(text) > 30000:
        text = text[:15000] + '\n[...]\n' + text[-15000:]
    s = gemma.summarise(text, 'chapter', ch['title'])
    db.update('chapters', chapter_id, {'summary': s})
    return s


def recap(book_id, up_to_idx):
    chs = db.q('SELECT * FROM chapters WHERE book_id=? AND include=1 AND idx<=? ORDER BY idx', (book_id, up_to_idx))
    missing = [c for c in chs if not c['summary']]
    for c in missing:
        summarise_chapter(c['id'])
    chs = db.q('SELECT * FROM chapters WHERE book_id=? AND include=1 AND idx<=? ORDER BY idx', (book_id, up_to_idx))
    text = '\n'.join(f"{c['title']}: {c['summary']}" for c in chs)
    r = gemma.summarise(text, 'recap')
    db.update('books', book_id, {'recap': r})
    return r
