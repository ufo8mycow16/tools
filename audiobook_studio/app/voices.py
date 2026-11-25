"""The voice library: every audio file in Glen's Reference Voices folder, plus voices added from the app.

A voice's key is its file name without the extension, in lower case (kirk.mp3 -> 'kirk'). Reference files are
only ever read; Chatterbox gets a cleaned 24 kHz mono copy kept in data/cache/voices.
"""
from pathlib import Path
import hashlib
import re
import subprocess

from . import config, db

AUDIO = ('.wav', '.mp3', '.voc', '.flac', '.ogg', '.m4a', '.aac', '.opus', '.wma', '.aiff', '.aif')

PREVIEW_LINES = {
    'default': 'Space. The final frontier. These are the voyages of the starship Enterprise.',
    'male': 'I have been, and always shall be, your friend. Now, shall we get on with it?',
    'female': 'Hailing frequencies open, Captain. I think you had better hear this yourself.',
}

GENDER_GUESS = {
    'kirk': 'male', 'spock': 'male', 'mccoy': 'male', 'scotty': 'male', 'scott': 'male', 'sulu': 'male',
    'chekov': 'male', 'kyle': 'male', 'sarek': 'male', 'ullus': 'male', 'uhura': 'female', 'chapel': 'female',
    'amanda': 'female', 'tuvall': 'female', 'rand': 'female', 'computer': 'female', 'tiffany': 'female',
}


def _key(stem, taken):
    k = re.sub(r'[^a-z0-9_\-]+', '_', stem.lower()).strip('_') or 'voice'
    base, n = k, 2
    while k in taken:
        k = f'{base}_{n}'
        n += 1
    return k


def scan():
    """Bring the voices table in line with the folders on disk."""
    known = {r['key']: r for r in db.q('SELECT * FROM voices')}
    seen_files = {r['file']: r['key'] for r in known.values()}
    found = set()
    for origin, folder in (('reference', Path(config.get('reference_voices'))), ('added', config.voices_dir())):
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.suffix.lower() not in AUDIO:
                continue
            fs = str(f)
            if fs in seen_files:
                found.add(seen_files[fs])
                continue
            k = _key(f.stem, set(known) | found)
            db.insert('voices', {'key': k, 'name': f.stem.replace('_', ' ').title(), 'file': fs, 'origin': origin,
                                 'gender': GENDER_GUESS.get(f.stem.lower(), ''), 'added': db.now()})
            known[k] = {'key': k}
            found.add(k)
    # voices whose file has gone are kept (characters may still point at them) but marked missing in the list
    return all_voices()


def all_voices():
    rows = db.q('SELECT * FROM voices ORDER BY favourite DESC, name')
    for r in rows:
        r['missing'] = not Path(r['file']).is_file()
    return rows


def get(key):
    return db.one('SELECT * FROM voices WHERE key=?', (key,)) if key else None


def conditioning_wav(key):
    """A clean 24 kHz mono WAV of the voice (max 20 s, loudness levelled) for Chatterbox. Made once, cached."""
    v = get(key)
    if not v:
        raise ValueError(f'No voice called {key}')
    src = Path(v['file'])
    if not src.is_file():
        raise FileNotFoundError(f'The file for voice {v["name"]} is missing: {src}')
    out_dir = config.cache_dir() / 'voices'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'{key}.wav'
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(src), '-t', '20',
                        '-af', 'silenceremove=start_periods=1:start_threshold=-45dB,loudnorm=I=-20:TP=-2',
                        '-ar', '24000', '-ac', '1', str(out)], check=True)
    return out


def add_upload(filename, data):
    folder = config.voices_dir()
    stem = re.sub(r'[^\w\- ]+', '', Path(filename).stem).strip() or 'voice'
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO:
        raise ValueError('That is not an audio file I know.')
    dest = folder / (stem + ext)
    n = 2
    while dest.exists():
        dest = folder / f'{stem}_{n}{ext}'
        n += 1
    dest.write_bytes(data)
    scan()
    return db.one('SELECT * FROM voices WHERE file=?', (str(dest),))


def preview_file(key):
    return config.cache_dir() / 'previews' / f'{key}.mp3'


def preview_line(voice):
    return PREVIEW_LINES.get(voice.get('gender') or 'default', PREVIEW_LINES['default'])


def voice_hash(key):
    v = get(key)
    if not v or not Path(v['file']).is_file():
        return ''
    st = Path(v['file']).stat()
    return hashlib.sha1(f'{v["file"]}|{st.st_size}|{st.st_mtime}'.encode()).hexdigest()[:10]
