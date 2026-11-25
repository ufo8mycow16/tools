"""The background worker: one queue, one job at a time (the graphics card does one thing well at once).

Job kinds:
    analyse     read the book with Gemma + rules (characters, speakers, emotions)
    generate    make audio for chapters (args: chapters=[ids] or all included); only lines that changed are redone
    segment     redo one line (args: segment=id), then rebuild its chapter
    preview     a short sample of a voice (args: voice=key)
    export      build the audiobook (args: format='m4b'|'mp3')
    summary     Gemma summary of a chapter (chapter_id) / recap (args: recap=True, upto=idx)
"""
from pathlib import Path
import hashlib
import json
import threading
import time
import traceback

from . import analysis, audio, config, db, library, textproc, voices
from .tts import ENGINE, EngineError, build_prompt

_wake = threading.Event()
_state = {'paused': False, 'current': None, 'log': [], 'eta': None, 'rate': None}
LOG_MAX = 300


def log(msg, job_id=None):
    line = {'t': time.time(), 'msg': msg, 'job': job_id}
    _state['log'].append(line)
    del _state['log'][:-LOG_MAX]
    print(time.strftime('%H:%M:%S'), msg, flush=True)


def add(kind, book_id=0, chapter_id=0, **args):
    # don't queue the same thing twice
    same = db.one("SELECT id FROM jobs WHERE kind=? AND book_id=? AND chapter_id=? AND args=? "
                  "AND status IN ('queued','running')", (kind, book_id, chapter_id, json.dumps(args, sort_keys=True)))
    if same:
        return same['id']
    jid = db.insert('jobs', {'kind': kind, 'book_id': book_id, 'chapter_id': chapter_id,
                             'args': json.dumps(args, sort_keys=True), 'created': db.now(), 'status': 'queued'})
    _wake.set()
    return jid


def cancel(job_id):
    db.run("UPDATE jobs SET status='cancelled', finished=? WHERE id=? AND status IN ('queued','running')",
           (db.now(), job_id))


def cancel_book(book_id):
    db.run("UPDATE jobs SET status='cancelled', finished=? WHERE book_id=? AND status IN ('queued','running')",
           (db.now(), book_id))


def pause(on):
    _state['paused'] = bool(on)
    if not on:
        _wake.set()


def state():
    jobs = db.q("SELECT * FROM jobs WHERE status IN ('queued','running') OR finished>? ORDER BY "
                "CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, id DESC LIMIT 40",
                (db.now() - 6 * 3600,))
    titles = {b['id']: b['title'] for b in db.q('SELECT id, title FROM books')}
    for j in jobs:
        j['book_title'] = titles.get(j['book_id'], '')
        j['args'] = db.jload(j['args'], {})
    return {'paused': _state['paused'], 'jobs': jobs, 'log': _state['log'][-80:], 'engine': ENGINE.status(),
            'eta': _state['eta']}


# --------------------------------------------------------------------------------------------- the worker loop

def start():
    t = threading.Thread(target=_loop, name='studio-worker', daemon=True)
    t.start()
    return t


def _loop():
    while True:
        _wake.wait(timeout=5)
        _wake.clear()
        while not _state['paused']:
            job = db.one("SELECT * FROM jobs WHERE status='queued' ORDER BY "
                         "CASE kind WHEN 'preview' THEN 0 WHEN 'segment' THEN 1 WHEN 'summary' THEN 2 ELSE 3 END, id LIMIT 1")
            if not job:
                break
            _run(job)
        # let the graphics card go after a quiet quarter of an hour
        if ENGINE.model is not None and time.time() - ENGINE.last_used > 900:
            ENGINE.unload()
            log('Chatterbox unloaded after 15 quiet minutes (it reloads by itself when needed).')


def _run(job):
    jid = job['id']
    db.update('jobs', jid, {'status': 'running', 'started': db.now(), 'progress': 0, 'message': 'Starting'})
    _state['current'] = jid
    args = db.jload(job['args'], {})

    def progress(frac, msg=''):
        db.update('jobs', jid, {'progress': max(0.0, min(1.0, frac)), 'message': msg})

    def cancelled():
        r = db.one('SELECT status FROM jobs WHERE id=?', (jid,))
        return (not r) or r['status'] == 'cancelled'

    try:
        kind = job['kind']
        if kind == 'analyse':
            analysis.analyse(job['book_id'], progress, cancelled, lambda m: log(m, jid))
        elif kind == 'generate':
            generate_book(job['book_id'], args.get('chapters'), progress, cancelled, jid)
        elif kind == 'segment':
            regenerate_segment(args['segment'], jid)
        elif kind == 'preview':
            make_preview(args['voice'], args.get('text'))
        elif kind == 'export':
            export_book(job['book_id'], args.get('format', 'm4b'), progress, jid)
        elif kind == 'summary':
            if args.get('recap'):
                analysis.recap(job['book_id'], int(args.get('upto', 0)))
            else:
                analysis.summarise_chapter(job['chapter_id'])
        else:
            raise ValueError('Unknown job ' + kind)
        if not cancelled():
            db.update('jobs', jid, {'status': 'done', 'progress': 1, 'finished': db.now()})
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, flush=True)
        db.update('jobs', jid, {'status': 'failed', 'error': f'{e}', 'finished': db.now(),
                                'message': f'Stopped: {e}'})
        log(f'Job {jid} ({job["kind"]}) stopped: {e}', jid)
    finally:
        _state['current'] = None
        _state['eta'] = None


# ------------------------------------------------------------------------------------------------- generation

def voice_for(seg, book, chars):
    if seg['voice']:
        return seg['voice']
    if seg['kind'] == 'dialogue' and seg['speaker'] and seg['speaker'] != 'Narrator':
        c = chars.get(seg['speaker'])
        if c and c['voice']:
            return c['voice']
    return book['narrator_voice']


def tags_for(seg, is_narrator):
    tags = []
    if seg['kind'] == 'dialogue' and not is_narrator:
        if config.get('use_sound_tags') and seg['sound']:
            tags.append(seg['sound'])
        if config.get('use_emotion_tags') and seg['emotion']:
            tags.append('[' + seg['emotion'] + ']')
    elif config.get('narration_tag'):
        tags.append('[narration]')
    return tags


def prompt_for(seg, book, chars, rules):
    v = voice_for(seg, book, chars)
    is_narr = v == book['narrator_voice'] and not (seg['kind'] == 'dialogue' and seg['speaker'] and
                                                   seg['speaker'] != 'Narrator' and chars.get(seg['speaker']) and
                                                   chars[seg['speaker']]['voice'])
    words = textproc.speakable(textproc.apply_pronunciations(seg['text'], rules))
    prompt = build_prompt(words, tags_for(seg, is_narr))
    stamp = '|'.join([prompt, v or '', voices.voice_hash(v) if v else '', str(config.get('temperature')),
                      str(config.get('top_p')), str(config.get('top_k')), str(config.get('repetition_penalty'))])
    return v, prompt, hashlib.sha1(stamp.encode()).hexdigest()[:16]


def gap_after(segs, i):
    s = segs[i]
    if i + 1 >= len(segs):
        return 0
    n = segs[i + 1]
    if s['kind'] == 'break' or n['kind'] == 'break':
        return int(config.get('gap_scene_break')) // 2
    if s['kind'] == 'heading':
        return int(config.get('gap_paragraph')) + 300
    if n['para'] != s['para']:
        return int(config.get('gap_paragraph'))
    if n['kind'] != s['kind'] or n['speaker'] != s['speaker']:
        return int(config.get('gap_speaker_change'))
    return int(config.get('gap_sentence'))


def _book_ctx(book_id):
    book = db.one('SELECT * FROM books WHERE id=?', (book_id,))
    chars = {c['name']: c for c in library.characters(book_id)}
    rules = textproc.pronunciation_rules(book_id)
    return book, chars, rules


def generate_chapter(chapter_id, book, chars, rules, progress=None, cancelled=lambda: False, jid=None,
                     done_before=0, total=1, started=None):
    ch = db.one('SELECT * FROM chapters WHERE id=?', (chapter_id,))
    segs = db.q('SELECT * FROM segments WHERE chapter_id=? ORDER BY idx', (chapter_id,))
    folder = config.book_dir(book['id']) / 'segments' / str(chapter_id)
    made = 0
    for i, s in enumerate(segs):
        if cancelled():
            return False
        if s['kind'] == 'break' or not s['text'].strip():
            continue
        v, prompt, h = prompt_for(s, book, chars, rules)
        if not v:
            raise EngineError('No narrator voice picked for this book - choose one on the Cast page.')
        f = folder / f'{s["id"]}.flac'
        if s['audio_hash'] == h and f.exists():
            continue
        if progress:
            n = done_before + i
            msg = f'{ch["title"]}: line {i + 1} of {len(segs)}'
            if started and n > 0:
                rate = (time.time() - started) / max(1, n)
                left = rate * (total - n)
                _state['eta'] = left
            progress(n / max(1, total), msg)
        samples, sr = ENGINE.speak(prompt, v, seed_text=f'{s["id"]}|{h}')
        d = audio.save_segment(f, samples, sr)
        db.update('segments', s['id'], {'audio': str(f), 'audio_hash': h, 'duration': d, 'voice': s['voice'],
                                        'status': 'done'})
        made += 1
        _add_stat('seconds_generated', d)
    # assemble the chapter
    segs = db.q('SELECT * FROM segments WHERE chapter_id=? ORDER BY idx', (chapter_id,))
    parts = []
    for i, s in enumerate(segs):
        g = gap_after(segs, i)
        if s['kind'] == 'break':
            parts.append((None, 0, int(config.get('gap_scene_break'))))
        elif s['audio'] and Path(s['audio']).exists():
            parts.append((s['audio'], s['duration'], g))
        else:
            parts.append((None, 0, 0))
    out = config.book_dir(book['id']) / 'chapters' / f'{ch["idx"]:03d}.m4a'
    if made or not out.exists() or ch['status'] != 'done':
        starts, total_len = audio.build_chapter(parts, out)
        db.many('UPDATE segments SET start=?, gap_after=? WHERE id=?',
                [(starts[i], parts[i][2], s['id']) for i, s in enumerate(segs)])
        db.update('chapters', chapter_id, {'audio': str(out), 'duration': total_len, 'status': 'done'})
    return True


def generate_book(book_id, chapter_ids, progress, cancelled, jid):
    book, chars, rules = _book_ctx(book_id)
    if not book['narrator_voice']:
        raise EngineError('Pick a narrator voice on the Cast page first.')
    if chapter_ids:
        chs = [db.one('SELECT * FROM chapters WHERE id=?', (c,)) for c in chapter_ids]
        chs = [c for c in chs if c]
    else:
        chs = db.q('SELECT * FROM chapters WHERE book_id=? AND include=1 ORDER BY idx', (book_id,))
    total = sum(db.one('SELECT COUNT(*) n FROM segments WHERE chapter_id=?', (c['id'],))['n'] for c in chs)
    done = 0
    started = time.time()
    db.update('books', book_id, {'status': 'generating'})
    log(f'Generating {len(chs)} chapter(s) of {book["title"]} ({total} lines).', jid)
    for c in chs:
        db.update('chapters', c['id'], {'status': 'generating'})
        ok = generate_chapter(c['id'], book, chars, rules, progress, cancelled, jid, done, total, started)
        if not ok:
            db.update('chapters', c['id'], {'status': 'partial'})
            db.update('books', book_id, {'status': 'ready'})
            return
        done += db.one('SELECT COUNT(*) n FROM segments WHERE chapter_id=?', (c['id'],))['n']
        log(f'Chapter done: {c["title"]}', jid)
    left = db.one("SELECT COUNT(*) n FROM chapters WHERE book_id=? AND include=1 AND status!='done'", (book_id,))['n']
    db.update('books', book_id, {'status': 'complete' if not left else 'ready'})


def regenerate_segment(seg_id, jid):
    s = db.one('SELECT * FROM segments WHERE id=?', (seg_id,))
    ch = db.one('SELECT * FROM chapters WHERE id=?', (s['chapter_id'],))
    book, chars, rules = _book_ctx(ch['book_id'])
    # a new take: change the seed by clearing the hash and bumping a counter in the seed text
    db.update('segments', seg_id, {'audio_hash': ''})
    v, prompt, h = prompt_for(s, book, chars, rules)
    takes = int(time.time())
    samples, sr = ENGINE.speak(prompt, v, seed_text=f'{s["id"]}|{h}|take{takes}')
    f = config.book_dir(book['id']) / 'segments' / str(ch['id']) / f'{s["id"]}.flac'
    d = audio.save_segment(f, samples, sr)
    db.update('segments', seg_id, {'audio': str(f), 'audio_hash': h, 'duration': d, 'status': 'done'})
    if ch['status'] == 'done' or Path(ch['audio'] or '').exists():
        db.update('chapters', ch['id'], {'status': 'stale'})
        generate_chapter(ch['id'], book, chars, rules)


def make_preview(key, text=None):
    v = voices.get(key)
    line = text or voices.preview_line(v)
    samples, sr = ENGINE.speak(line, key, seed_text='preview|' + line)
    out = voices.preview_file(key)
    tmp = out.with_suffix('.flac')
    audio.save_segment(tmp, samples, sr)
    import subprocess
    subprocess.run(audio.FF + ['-i', str(tmp), '-c:a', 'libmp3lame', '-b:a', '128k', str(out)], check=True)
    tmp.unlink(missing_ok=True)
    db.update('voices', key, {'preview': str(out)}, key='key')


def export_book(book_id, fmt, progress, jid):
    book = db.one('SELECT * FROM books WHERE id=?', (book_id,))
    chs = db.q('SELECT * FROM chapters WHERE book_id=? AND include=1 ORDER BY idx', (book_id,))
    missing = [c['title'] for c in chs if c['status'] != 'done' or not Path(c['audio'] or '').exists()]
    if missing:
        raise ValueError('These chapters have no audio yet: ' + ', '.join(missing[:6]) +
                         (' ...' if len(missing) > 6 else ''))
    cover = config.book_dir(book_id) / book['cover'] if book['cover'] else None
    name = audio.safe_name(f"{book['title']}" + (f" - {book['author']}" if book['author'] else ''))
    progress(0.1, 'Joining the chapters')
    if fmt == 'mp3':
        folder, z = audio.export_mp3s(book, chs, cover, config.export_dir() / name)
        log(f'Exported MP3s: {folder} (and {z.name} for the phone)', jid)
        db.update('jobs', jid, {'message': f'Saved to {folder}', 'args': json.dumps({'format': fmt, 'file': str(z)})})
    else:
        out = audio.export_m4b(book, chs, cover, config.export_dir() / (name + '.m4b'))
        log(f'Exported audiobook: {out}', jid)
        db.update('jobs', jid, {'message': f'Saved to {out}', 'args': json.dumps({'format': fmt, 'file': str(out)})})


def _add_stat(field, secs):
    day = time.strftime('%Y-%m-%d')
    db.run(f'INSERT INTO stats (day, {field}) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET {field}={field}+?',
           (day, secs, secs))


def listened(secs):
    _add_stat('seconds_listened', max(0, min(600, float(secs))))
