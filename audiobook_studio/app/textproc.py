"""Text cleaning, sentence splitting, chunking for Chatterbox, and the pronunciation list."""
import re
import unicodedata

from . import db

# Words that end with a full stop but don't end a sentence.
ABBREVIATIONS = {
    'mr', 'mrs', 'ms', 'dr', 'st', 'lt', 'cmdr', 'capt', 'adm', 'ens', 'sgt', 'col', 'gen', 'maj', 'prof',
    'jr', 'sr', 'vs', 'etc', 'e.g', 'i.e', 'no', 'vol', 'fig', 'approx', 'u.s.s', 'u.s', 'i.k.s', 'a.m', 'p.m',
    'inc', 'ltd', 'co', 'mt', 'ft',
}

SCENE_BREAK = re.compile(r'^\s*(?:[*•·#~\-=_]\s*){1,}$')


def normalise(text):
    """Tidy text from a book: unicode forms, odd spaces, soft hyphens, dashes and ellipses."""
    t = unicodedata.normalize('NFKC', text)
    t = t.replace('­', '').replace('​', '').replace('﻿', '')
    t = t.replace(' ', ' ').replace(' ', ' ').replace(' ', ' ')
    t = t.replace('…', '...')
    t = re.sub(r'\.\s\.\s\.', '...', t)
    t = t.replace('―', '—').replace('--', '—')
    t = re.sub(r'[ \t\r\f\v]+', ' ', t)
    return t.strip()


def is_scene_break(text):
    t = text.strip()
    return bool(t) and len(t) <= 12 and bool(SCENE_BREAK.match(t))


_SENT_END = re.compile(r'([.!?…]+["”’\')\]]*)(\s+)(?=["“‘(\[]?[A-Z0-9])')


def split_sentences(text):
    """Split into sentences, keeping abbreviations (Dr. McCoy, U.S.S. Enterprise) in one piece."""
    out, start = [], 0
    for m in _SENT_END.finditer(text):
        end = m.end(1)
        before = text[start:end]
        word = re.search(r'([A-Za-z.]+)\.["”’\')\]]*$', before)
        if word and word.group(1).lower().strip('.') in ABBREVIATIONS:
            continue
        if re.search(r'\b[A-Z]\.["”’]*$', before) and m.group(1).startswith('.') and len(m.group(1)) == 1:
            continue  # an initial: "James T. Kirk"
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        start = m.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


def chunk(text, limit):
    """Break text Chatterbox would choke on (longer than `limit`) at the most natural points."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    parts = []
    for s in split_sentences(text):
        if len(s) <= limit:
            parts.append(s)
            continue
        # a very long sentence: break at ; : em dash, then commas, then spaces
        pieces = [s]
        for pat in (r'(?<=[;:—])\s*', r'(?<=,)\s+', r'\s+'):
            nxt = []
            for p in pieces:
                if len(p) <= limit:
                    nxt.append(p)
                    continue
                bits = [b for b in re.split(pat, p) if b]
                cur = ''
                for b in bits:
                    if cur and len(cur) + 1 + len(b) > limit:
                        nxt.append(cur)
                        cur = b
                    else:
                        cur = (cur + ' ' + b).strip() if cur else b
                if cur:
                    nxt.append(cur)
            pieces = nxt
        parts.extend(pieces)
    # glue tiny leftovers onto their neighbour so Turbo never gets a two-word line on its own
    merged = []
    for p in parts:
        if merged and (len(p) < 25 or len(merged[-1]) < 25) and len(merged[-1]) + 1 + len(p) <= limit:
            merged[-1] = merged[-1] + ' ' + p
        else:
            merged.append(p)
    return merged


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9’']+", text))


# ---------------------------------------------------------------------------------------------- pronunciations

def pronunciation_rules(book_id=0):
    rows = db.q('SELECT * FROM pronunciations WHERE enabled=1 AND book_id IN (0, ?) ORDER BY book_id DESC, '
                'length(pattern) DESC', (book_id,))
    rules = []
    for r in rows:
        flags = 0 if r['match_case'] else re.IGNORECASE
        try:
            if r['is_regex']:
                rx = re.compile(r['pattern'], flags)
            else:
                p = re.escape(r['pattern'])
                if r['whole_word']:
                    left = r'(?<![\w])' if r['pattern'][:1].isalnum() else ''
                    right = r'(?![\w])' if r['pattern'][-1:].isalnum() else ''
                    p = left + p + right
                rx = re.compile(p, flags)
        except re.error:
            continue
        rules.append((rx, r['replacement']))
    return rules


def apply_pronunciations(text, rules):
    for rx, rep in rules:
        text = rx.sub(rep, text)
    return text


def speakable(text):
    """What Turbo is actually given: no curly quotes round dialogue, no stray symbols it would read out."""
    t = text.strip()
    t = t.strip('"“”').strip()
    t = t.replace('“', '').replace('”', '').replace('"', '')
    t = t.replace('‘', "'").replace('’', "'")
    t = re.sub(r'\s*—\s*', ', ', t)          # em dash -> a comma pause
    t = re.sub(r'(^|\s)[*_~#]+|[*_~#]+(\s|$)', r'\1\2', t)
    t = re.sub(r'\s+([,.!?;:])', r'\1', t)
    t = re.sub(r',\s*,', ',', t)
    t = re.sub(r'^[,;:]\s*', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    if t and t[-1] not in '.!?':
        t = t.rstrip(',;:') + '.'
    return t
