"""Third Moon Audiobook Studio - settings.

Everything lives beside the app (APP_DIR) unless Settings says otherwise:
    data/studio.db        the library database
    data/settings.json    these settings
    library/<book id>/    the book's cover, chapter audio and segment audio
    voices/               voices added from inside the app (the Reference Voices folder is read, never written)
    exports/              finished .m4b / .mp3 audiobooks
"""
from pathlib import Path
import json
import threading

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / 'data'
SETTINGS_FILE = DATA_DIR / 'settings.json'

DEFAULTS = {
    # Chatterbox Turbo (Glen's install - the same one the Vulcan Fury voice scripts use)
    'chatterbox_root': r'C:\Users\Glen\ChatterboxTurbo',
    'reference_voices': r'C:\Users\Glen\Documents\Vulcan Fury\Reference Voices',
    'device': 'auto',                 # auto / cuda / cpu
    'temperature': 0.8,
    'top_p': 0.95,
    'top_k': 1000,
    'repetition_penalty': 1.2,
    'narration_tag': False,           # put Turbo's [narration] tag on narrator lines
    'use_emotion_tags': True,         # dialogue gets [angry] [whispering] ... from the analysis
    'use_sound_tags': True,           # [laugh] [sigh] [gasp] ... when the text says so
    'max_chunk_chars': 260,           # longest piece of text Turbo is given in one go

    # Gemma (Ollama) for characters, speakers, emotions and summaries
    'ollama_url': 'http://localhost:11434',
    'ollama_model': 'gemma4:12b',
    'ollama_context': 16384,
    'use_ollama': True,
    'unload_ollama_after_analysis': True,   # frees the graphics card for Chatterbox

    # Pauses (milliseconds)
    'gap_sentence': 220,
    'gap_speaker_change': 420,
    'gap_paragraph': 650,
    'gap_scene_break': 1600,
    'gap_chapter_start': 900,
    'gap_chapter_end': 1800,

    # Audio out
    'chapter_bitrate': '96k',
    'export_bitrate': '96k',
    'export_dir': str(APP_DIR / 'exports'),
    'library_dir': str(APP_DIR / 'library'),
    'voices_dir': str(APP_DIR / 'voices'),

    # Server
    'port': 8765,
    'listen_on_network': True,        # so the phone can use it over home Wi-Fi
    'open_browser': True,

    # Player defaults
    'default_speed': 1.0,
    'skip_seconds': 15,
}

_lock = threading.Lock()
_settings = None


def load():
    global _settings
    with _lock:
        if _settings is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            s = dict(DEFAULTS)
            if SETTINGS_FILE.exists():
                try:
                    s.update(json.loads(SETTINGS_FILE.read_text(encoding='utf-8')))
                except Exception:
                    pass
            _settings = s
        return dict(_settings)


def get(key):
    return load().get(key, DEFAULTS.get(key))


def update(changes):
    global _settings
    load()
    with _lock:
        for k, v in changes.items():
            if k not in DEFAULTS:
                continue
            d = DEFAULTS[k]
            try:
                if isinstance(d, bool):
                    v = v if isinstance(v, bool) else str(v).lower() in ('1', 'true', 'yes', 'on')
                elif isinstance(d, int):
                    v = int(float(v))
                elif isinstance(d, float):
                    v = float(v)
                else:
                    v = str(v)
            except (TypeError, ValueError):
                continue
            _settings[k] = v
        SETTINGS_FILE.write_text(json.dumps(_settings, indent=2), encoding='utf-8')
        return dict(_settings)


def path(key):
    return Path(get(key))


def library_dir():
    p = path('library_dir')
    p.mkdir(parents=True, exist_ok=True)
    return p


def book_dir(book_id):
    p = library_dir() / str(book_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def voices_dir():
    p = path('voices_dir')
    p.mkdir(parents=True, exist_ok=True)
    return p


def export_dir():
    p = path('export_dir')
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir():
    p = DATA_DIR / 'cache'
    p.mkdir(parents=True, exist_ok=True)
    return p
