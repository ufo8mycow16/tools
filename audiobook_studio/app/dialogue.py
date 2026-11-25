"""Splitting a chapter into narration and dialogue, finding the characters, and the rules that work out who
says each line (used on their own when Gemma is off, and to check/fill in Gemma's answers).
"""
from collections import Counter, defaultdict
import re

from . import cast
from .textproc import split_sentences, chunk

SAID = ('said', 'says', 'asked', 'asks', 'replied', 'replies', 'answered', 'answers', 'whispered', 'whispers',
        'shouted', 'shouts', 'yelled', 'yells', 'muttered', 'mutters', 'murmured', 'murmurs', 'snapped', 'snaps',
        'added', 'adds', 'continued', 'continues', 'began', 'begins', 'went on', 'cried', 'cries', 'called',
        'calls', 'demanded', 'demands', 'insisted', 'insists', 'observed', 'observes', 'noted', 'notes',
        'remarked', 'remarks', 'agreed', 'agrees', 'protested', 'protests', 'growled', 'growls', 'barked',
        'snarled', 'hissed', 'breathed', 'sighed', 'laughed', 'chuckled', 'grinned', 'smiled', 'grunted',
        'retorted', 'interrupted', 'conceded', 'admitted', 'explained', 'suggested', 'ordered', 'commanded',
        'told', 'tells', 'responded', 'responds', 'stated', 'states', 'declared', 'announced', 'repeated',
        'pointed out', 'offered', 'drawled', 'sneered', 'groaned', 'mumbled', 'stammered', 'pleaded', 'begged',
        'warned', 'reminded', 'corrected', 'countered', 'acknowledged', 'confirmed', 'reported', 'wondered',
        'mused', 'queried', 'inquired', 'enquired', 'exclaimed', 'gasped', 'whimpered', 'screamed', 'roared',
        'rumbled', 'purred', 'spat', 'shot back', 'put in', 'cut in', 'chimed in', 'concluded', 'persisted')
SAID_RX = '|'.join(sorted((re.escape(s) for s in SAID), key=len, reverse=True))
NAME_RX = r"(?:[A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){0,2})"
PRONOUN_RX = r'(?:he|she|He|She)'

OPEN = '“'
CLOSE = '”'


# ------------------------------------------------------------------------------------------------ segmentation

def quote_style(paragraphs):
    text = '\n'.join(paragraphs[:400])
    curly = text.count(OPEN) + text.count(CLOSE)
    single = len(re.findall(r'(^|[\s(—])‘\S', text))
    straight = text.count('"')
    if single > curly and single > straight:
        return 'single'
    if straight > curly:
        return 'straight'
    return 'curly'


def _runs(text, style, carry_open):
    """[(is_dialogue, text)] for one paragraph. carry_open = the previous paragraph's quote never closed."""
    runs = []
    if style == 'single':
        o, c = '‘', '’'
    elif style == 'straight':
        o, c = '"', '"'
    else:
        o, c = OPEN, CLOSE
    inside = False
    buf = ''
    i = 0
    starts_with_open = text.lstrip().startswith(o)
    if carry_open and not starts_with_open:
        inside = True  # unusual; most books re-open the quote
    while i < len(text):
        ch = text[i]
        if style == 'single' and ch == c and inside:
            # an apostrophe inside a word is not a closing quote
            nxt = text[i + 1:i + 2]
            if nxt.isalpha():
                buf += ch
                i += 1
                continue
        if style == 'straight':
            if ch == '"':
                if inside:
                    buf += ch
                    runs.append((True, buf))
                    buf, inside = '', False
                else:
                    if buf.strip():
                        runs.append((False, buf))
                    buf, inside = ch, True
                i += 1
                continue
        elif ch == o and not inside:
            if style == 'single' and i > 0 and text[i - 1].isalpha():
                buf += ch
                i += 1
                continue
            if buf.strip():
                runs.append((False, buf))
            buf, inside = ch, True
            i += 1
            continue
        elif ch == c and inside:
            buf += ch
            runs.append((True, buf))
            buf, inside = '', False
            i += 1
            continue
        buf += ch
        i += 1
    unclosed = inside
    if buf.strip():
        runs.append((inside, buf))
    return runs, unclosed


def segment_chapter(blocks, style, limit):
    """Blocks from the EPUB -> segment rows (without ids).

    Each row: para, kind (heading/narration/dialogue/break), display (as printed), text (what's spoken, before
    pronunciations), quote_id (dialogue runs counted through the chapter; runs of one unclosed multi-paragraph
    speech share an id).
    """
    rows = []
    para = 0
    qid = 0
    carry = False
    for b in blocks:
        if b['kind'] == 'break':
            rows.append({'para': para, 'kind': 'break', 'display': '* * *', 'text': '', 'quote_id': 0})
            para += 1
            carry = False
            continue
        if b['kind'] == 'h':
            rows.append({'para': para, 'kind': 'heading', 'display': b['text'], 'text': b['text'], 'quote_id': 0})
            para += 1
            continue
        runs, unclosed = _runs(b['text'], style, carry)
        for ri, (is_dlg, t) in enumerate(runs):
            t = t.strip()
            if not t:
                continue
            if is_dlg:
                # a speech carried on from an unclosed quote in the paragraph before keeps its id
                if not (ri == 0 and carry and qid):
                    qid += 1
                pieces = chunk(t, limit)
                for p in pieces:
                    rows.append({'para': para, 'kind': 'dialogue', 'display': p, 'text': p, 'quote_id': qid})
            else:
                # narration: sentence by sentence (nice highlighting), short ones glued together
                sents = []
                for s in split_sentences(t):
                    sents.extend(chunk(s, limit))
                merged = []
                for s in sents:
                    if merged and len(merged[-1]) + 1 + len(s) <= min(limit, 170) and \
                            (len(s) < 60 or len(merged[-1]) < 60):
                        merged[-1] += ' ' + s
                    else:
                        merged.append(s)
                for s in merged:
                    rows.append({'para': para, 'kind': 'narration', 'display': s, 'text': s, 'quote_id': 0})
        carry = unclosed
        para += 1
    return rows


# --------------------------------------------------------------------------------------------- characters

def discover_characters(paragraph_texts, limit=40):
    """Rules-only character list: the Star Trek table plus names seen next to speech verbs or titles."""
    text = '\n'.join(paragraph_texts)
    counts = Counter()
    gender_hint = defaultdict(Counter)

    # known Star Trek people
    for name, (g, aliases) in cast.TREK.items():
        n = 0
        for a in [name] + aliases:
            if len(a) < 3 and a != 'Q':
                continue
            n += len(re.findall(r'(?<![\w])' + re.escape(a) + r'(?![\w])', text))
        if n:
            counts[name] += n + 2  # a known Star Trek name counts from its first mention
            gender_hint[name][g] += 5

    # "said Ossek", "Ossek said", "Captain Ossek"
    for m in re.finditer(r'(?:' + SAID_RX + r')\s+(' + NAME_RX + r')', text):
        counts[m.group(1)] += 3
    for m in re.finditer(r'(' + NAME_RX + r')\s+(?:' + SAID_RX + r')\b', text):
        counts[m.group(1)] += 3
    for t in cast.TITLES:
        for m in re.finditer(re.escape(t) + r'\s+([A-Z][\w\'’\-]+)', text):
            counts[m.group(1)] += 2
            if t in cast.FEMALE_TITLES:
                gender_hint[m.group(1)]['female'] += 3

    found = {}
    alias_of = {}
    for name, (g, aliases) in cast.TREK.items():
        for a in aliases:
            alias_of[a] = name
    for raw, n in counts.most_common():
        if n < 3:
            continue
        name = raw.strip()
        first = name.split()[0]
        if first in cast.NOT_NAMES or name in cast.NOT_NAMES:
            # "Captain Kirk" style - keep the part after the title
            parts = [p for p in name.split() if p not in cast.NOT_NAMES]
            if not parts:
                continue
            name = ' '.join(parts)
        canon = alias_of.get(name, name)
        tk, entry = cast.trek_entry(canon)
        if tk:
            canon = tk
        if canon in found:
            found[canon]['score'] += n
            continue
        g = ''
        if entry:
            g = entry[0]
        elif gender_hint[canon]:
            g = gender_hint[canon].most_common(1)[0][0]
        else:
            g = guess_gender(canon, text)
        found[canon] = {'name': canon, 'aliases': list(entry[1]) if entry else [], 'gender': g, 'score': n,
                        'description': ''}
    chars = sorted(found.values(), key=lambda c: -c['score'])[:limit]
    return chars


def guess_gender(name, text):
    he = she = 0
    for m in re.finditer(re.escape(name) + r'\b', text):
        window = text[m.end():m.end() + 160]
        he += len(re.findall(r'\b(he|him|his)\b', window, re.I))
        she += len(re.findall(r'\b(she|her|hers)\b', window, re.I))
    if he > she * 1.5:
        return 'male'
    if she > he * 1.5:
        return 'female'
    return ''


# ------------------------------------------------------------------------------------------------- speakers

def _find_name(fragment, aliases, prefer_last=False):
    """The character named in a bit of narration (longest alias wins), or None."""
    best = None
    for alias, canon in aliases.items():
        if len(alias) < 2:
            continue
        for m in re.finditer(r'(?<![\w])' + re.escape(alias) + r'(?![\w])', fragment, re.I):
            # skip lowercase hits of names that are also words ("data", "q", "number one")
            if fragment[m.start():m.end()][0].islower():
                continue
            key = (m.start() if not prefer_last else -m.start(), -len(alias))
            if best is None or key < best[0]:
                best = (key, canon)
    return best[1] if best else None


def attribute_rules(segments, characters, gender_of):
    """Fill speaker on dialogue segments in one chapter. segments: list of dicts (para, kind, display, quote_id,
    speaker, speaker_source). Only segments whose speaker_source isn't 'manual'/'gemma' are changed."""
    aliases = cast.alias_table(characters)
    by_para = defaultdict(list)
    for s in segments:
        by_para[s['para']].append(s)
    paras = sorted(by_para)

    last_named = {'male': None, 'female': None, 'any': None}
    history = []  # speakers of the last dialogue paragraphs, newest last
    qid_speaker = {}
    for p in paras:
        segs = by_para[p]
        if all(s['kind'] in ('break', 'heading') for s in segs):
            if any(s['kind'] == 'break' for s in segs):
                history.clear()
            continue
        narr = ' '.join(s['display'] for s in segs if s['kind'] == 'narration')
        dlg = [s for s in segs if s['kind'] == 'dialogue']
        speaker, how = None, ''

        if dlg:
            # 1. a speech tag right after or before a quote
            for i, s in enumerate(segs):
                if s['kind'] != 'dialogue':
                    continue
                after = ' '.join(x['display'] for x in segs[i + 1:i + 2] if x['kind'] == 'narration')
                before = ' '.join(x['display'] for x in segs[max(0, i - 1):i] if x['kind'] == 'narration')
                m = re.match(r'^\W*(?:' + SAID_RX + r')\s+(' + NAME_RX + r'|' + PRONOUN_RX + r')', after)
                m = m or re.match(r'^\W*(' + NAME_RX + r'|' + PRONOUN_RX + r')(?:\s+\w+ly)?\s+(?:' + SAID_RX + r')\b', after)
                m = m or re.search(r'(' + NAME_RX + r'|' + PRONOUN_RX + r')(?:\s+\w+ly)?\s+(?:' + SAID_RX + r')\b[^.!?]{0,40}[,:]?\s*$', before)
                if m:
                    who = m.group(1)
                    if who.lower() in ('he', 'she'):
                        speaker = last_named['male' if who.lower() == 'he' else 'female']
                        how = 'pronoun'
                    else:
                        speaker = _find_name(who, aliases)
                        how = 'tag'
                    if speaker:
                        break
            # 2. a character doing something in the same paragraph ("Kirk leaned forward.")
            if not speaker and narr:
                first_sentence = re.split(r'(?<=[.!?])\s', narr)[0]
                speaker = _find_name(first_sentence, aliases)
                how = 'action' if speaker else ''
                if not speaker:
                    m = re.match(r'^\W*(He|She)\b', narr)
                    if m:
                        speaker = last_named['male' if m.group(1) == 'He' else 'female']
                        how = 'pronoun' if speaker else ''
            # a speech that runs over several paragraphs is the same person all the way
            if not speaker and qid_speaker.get(dlg[0]['quote_id']):
                speaker, how = qid_speaker[dlg[0]['quote_id']], 'continued'
            # 3. back-and-forth conversation: the one before last
            if not speaker and len(history) >= 2 and history[-1] != history[-2]:
                speaker = history[-2]
                how = 'turns'
            # vocative check: "Jim, ..." can't be said by Kirk
            spoken = ' '.join(s['display'] for s in dlg)
            addressed = None
            vm = re.match(r'^\W*(' + NAME_RX + r')\s*[,!?]', spoken) or \
                re.search(r',\s*(' + NAME_RX + r')\s*[.!?]["”’]*$', spoken)
            if vm:
                addressed = _find_name(vm.group(1), aliases)
            if speaker and addressed and speaker == addressed:
                alt = [h for h in reversed(history) if h != addressed]
                speaker, how = (alt[0], 'turns') if alt else (None, '')
            for s in dlg:
                s['rule_speaker'], s['rule_how'] = speaker or '', how or ''
                if s.get('speaker_source') in ('manual', 'gemma'):
                    continue
                s['speaker'] = speaker or ''
                s['speaker_source'] = how or 'unknown'
            final = next((s['speaker'] for s in dlg if s['speaker']), None)
            for s in dlg:
                if s['speaker']:
                    qid_speaker[s['quote_id']] = s['speaker']
            if final and how == 'continued':
                final = None  # the same speech, not a new turn in the conversation
            if final:
                history.append(final)
                history[:] = history[-6:]
            # who did the talking is who the next "he/she" most likely means
            if final and gender_of.get(final):
                last_named[gender_of[final]] = final

        # names in narration move the pronoun pointers along
        for alias, canon in aliases.items():
            if re.search(r'(?<![\w])' + re.escape(alias) + r'(?![\w])', narr):
                g = gender_of.get(canon)
                if g in ('male', 'female'):
                    last_named[g] = canon
                last_named['any'] = canon
    return segments


# -------------------------------------------------------------------------------------------- sound effects

SOUND_RULES = [
    (r'\b(laughed|laughing|laughs)\b', '[laugh]'),
    (r'\b(chuckled|chuckling|chuckles)\b', '[chuckle]'),
    (r'\b(sighed|sighing|sighs)\b', '[sigh]'),
    (r'\b(gasped|gasping|gasps)\b', '[gasp]'),
    (r'\b(groaned|groaning|groans)\b', '[groan]'),
    (r'\b(coughed|coughing|coughs)\b', '[cough]'),
    (r'\b(sniffed|sniffing|sniffled)\b', '[sniff]'),
    (r'\bcleared (his|her|their) throat\b', '[clear throat]'),
]

EMOTION_RULES = [
    (r'\b(whisper(ed|ing)?|murmur(ed|ing)?|breathed|hushed|under (his|her) breath)\b', 'whispering'),
    (r'\b(shout(ed|ing)?|yell(ed|ing)?|roar(ed)?|snarl(ed)?|bark(ed)?|furious|angrily|snapped|growled|thundered)\b',
     'angry'),
    (r'\b(sob(bed|bing)?|wept|weeping|tears|crying|cried softly)\b', 'crying'),
    (r'\b(dryly|sarcastic(ally)?|sardonic(ally)?|wryly|drawled)\b', 'sarcastic'),
    (r'\b(afraid|terrified|fear(fully)?|trembl(ed|ing)|panicked|nervously)\b', 'fear'),
    (r'\b(grinn?(ed|ing)|smil(ed|ing)|laugh(ed|ing)|cheerfully|delighted|happily)\b', 'happy'),
    (r'\b(astonish(ed|ment)|surprised|startled|stunned|amazed|blinked)\b', 'surprised'),
]


def rule_emotion(narr_near):
    for rx, emo in EMOTION_RULES:
        if re.search(rx, narr_near, re.I):
            return emo
    return ''


def rule_sound(narr_near):
    for rx, tag in SOUND_RULES:
        if re.search(rx, narr_near, re.I):
            return tag
    return ''
