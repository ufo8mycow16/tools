"""The library database (SQLite, one file: data/studio.db).

Small helpers only - every module talks to the database through q()/one()/run()/insert().
Each call opens its own short connection so the web server threads and the generation worker never share one.
"""
import json
import sqlite3
import threading
import time

from . import config

DB_FILE = config.DATA_DIR / 'studio.db'
_init_lock = threading.Lock()
_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT DEFAULT '',
    series TEXT DEFAULT '',
    description TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    source_path TEXT DEFAULT '',
    source_kind TEXT DEFAULT 'epub',
    cover TEXT DEFAULT '',
    narrator_voice TEXT DEFAULT '',
    status TEXT DEFAULT 'imported',
    analysed INTEGER DEFAULT 0,
    analysis_method TEXT DEFAULT '',
    added REAL,
    opened REAL,
    pos_chapter INTEGER DEFAULT 0,
    pos_time REAL DEFAULT 0,
    speed REAL DEFAULT 0,
    summary TEXT DEFAULT '',
    recap TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    title TEXT DEFAULT '',
    include INTEGER DEFAULT 1,
    kind TEXT DEFAULT 'chapter',
    status TEXT DEFAULT 'new',
    duration REAL DEFAULT 0,
    audio TEXT DEFAULT '',
    words INTEGER DEFAULT 0,
    summary TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS chapters_book ON chapters(book_id, idx);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    para INTEGER DEFAULT 0,
    kind TEXT DEFAULT 'narration',
    text TEXT DEFAULT '',
    display TEXT DEFAULT '',
    quote_id INTEGER DEFAULT 0,
    speaker TEXT DEFAULT '',
    speaker_source TEXT DEFAULT '',
    emotion TEXT DEFAULT '',
    sound TEXT DEFAULT '',
    voice TEXT DEFAULT '',
    audio TEXT DEFAULT '',
    audio_hash TEXT DEFAULT '',
    duration REAL DEFAULT 0,
    start REAL DEFAULT 0,
    gap_after INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    locked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS segments_chapter ON segments(chapter_id, idx);
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    gender TEXT DEFAULT '',
    description TEXT DEFAULT '',
    lines INTEGER DEFAULT 0,
    voice TEXT DEFAULT '',
    hidden INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS characters_book ON characters(book_id);
CREATE TABLE IF NOT EXISTS voices (
    key TEXT PRIMARY KEY,
    name TEXT,
    file TEXT,
    origin TEXT DEFAULT 'reference',
    gender TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    favourite INTEGER DEFAULT 0,
    preview TEXT DEFAULT '',
    added REAL
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    chapter_idx INTEGER DEFAULT 0,
    time REAL DEFAULT 0,
    segment_id INTEGER DEFAULT 0,
    label TEXT DEFAULT '',
    note TEXT DEFAULT '',
    colour TEXT DEFAULT 'gold',
    created REAL
);
CREATE TABLE IF NOT EXISTS pronunciations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER DEFAULT 0,
    pattern TEXT NOT NULL,
    replacement TEXT NOT NULL,
    whole_word INTEGER DEFAULT 1,
    match_case INTEGER DEFAULT 0,
    is_regex INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    book_id INTEGER DEFAULT 0,
    chapter_id INTEGER DEFAULT 0,
    args TEXT DEFAULT '{}',
    status TEXT DEFAULT 'queued',
    progress REAL DEFAULT 0,
    message TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created REAL,
    started REAL,
    finished REAL
);
CREATE TABLE IF NOT EXISTS stats (
    day TEXT PRIMARY KEY,
    seconds_listened REAL DEFAULT 0,
    seconds_generated REAL DEFAULT 0
);
"""

# Pronunciations every book starts with (global, book_id 0). Glen can change or switch any of them off.
DEFAULT_PRONUNCIATIONS = [
    ('Dr.', 'Doctor', 1, 1, 0),
    ('Mr.', 'Mister', 1, 1, 0),
    ('Mrs.', 'Missus', 1, 1, 0),
    ('Ms.', 'Mizz', 1, 1, 0),
    ('Lt.', 'Lieutenant', 1, 1, 0),
    ('Lt. Cmdr.', 'Lieutenant Commander', 1, 1, 0),
    ('Cmdr.', 'Commander', 1, 1, 0),
    ('Capt.', 'Captain', 1, 1, 0),
    ('Adm.', 'Admiral', 1, 1, 0),
    ('Ens.', 'Ensign', 1, 1, 0),
    ('Sgt.', 'Sergeant', 1, 1, 0),
    ('St.', 'Saint', 1, 1, 0),
    ('NCC-1701-A', 'N C C seventeen oh one A', 1, 1, 0),
    ('NCC-1701', 'N C C seventeen oh one', 1, 1, 0),
    ('U.S.S.', 'U S S', 1, 1, 0),
    ('USS', 'U S S', 1, 1, 0),
    ('I.K.S.', 'I K S', 1, 1, 0),
    ('IKS', 'I K S', 1, 1, 0),
    ('Starfleet', 'Starfleet', 1, 0, 0),
    ('Pon farr', 'pon far', 1, 0, 0),
    ('Kal-if-fee', 'kal if fee', 1, 0, 0),
    ('Koon-ut-kal-if-fee', 'koon ut kal if fee', 1, 0, 0),
    ('T’Pring', 'Tee Pring', 1, 0, 0),
    ("T'Pring", 'Tee Pring', 1, 0, 0),
    ('T’Pau', 'Tee Pow', 1, 0, 0),
    ("T'Pau", 'Tee Pow', 1, 0, 0),
    ('Qo’noS', 'Kronos', 1, 0, 0),
    ("Qo'noS", 'Kronos', 1, 0, 0),
    ('Kobayashi', 'Koh-bah-yah-shee', 1, 0, 0),
    ('Sulu', 'Soo-loo', 1, 1, 0),
    ('Uhura', 'Oo-hoo-rah', 1, 1, 0),
]


def connect():
    init()
    c = sqlite3.connect(str(DB_FILE), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def init():
    global _ready
    if _ready:
        return
    with _init_lock:
        if _ready:
            return
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(DB_FILE), timeout=30)
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript(SCHEMA)
        if not c.execute('SELECT 1 FROM pronunciations LIMIT 1').fetchone():
            c.executemany('INSERT INTO pronunciations (book_id, pattern, replacement, whole_word, match_case, is_regex) '
                          'VALUES (0, ?, ?, ?, ?, ?)', DEFAULT_PRONUNCIATIONS)
        # anything that was running when the app last closed goes back in the queue
        c.execute("UPDATE jobs SET status='queued', message='Restarted' WHERE status='running'")
        c.commit()
        c.close()
        _ready = True


def q(sql, args=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    with connect() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def run(sql, args=()):
    with connect() as c:
        cur = c.execute(sql, args)
        c.commit()
        return cur.rowcount


def many(sql, rows):
    with connect() as c:
        c.executemany(sql, rows)
        c.commit()


def insert(table, values):
    keys = list(values)
    with connect() as c:
        cur = c.execute(f'INSERT INTO {table} ({",".join(keys)}) VALUES ({",".join("?" * len(keys))})',
                        [values[k] for k in keys])
        c.commit()
        return cur.lastrowid


def update(table, row_id, values, key='id'):
    if not values:
        return
    keys = list(values)
    with connect() as c:
        c.execute(f'UPDATE {table} SET {",".join(k + "=?" for k in keys)} WHERE {key}=?',
                  [values[k] for k in keys] + [row_id])
        c.commit()


def now():
    return time.time()


def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default
