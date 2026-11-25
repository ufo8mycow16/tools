"""Gemma (through Ollama) reading the book: characters, who says each line, how they say it, and summaries.

Everything here degrades gracefully: if Ollama isn't running, or Gemma's answer can't be read, the rules in
dialogue.py stay in charge and the job carries on.
"""
import json
import re
import urllib.error
import urllib.request

from . import config

EMOTIONS = ('neutral', 'angry', 'crying', 'dramatic', 'fear', 'happy', 'sarcastic', 'surprised', 'whispering')
SOUNDS = ('', 'laugh', 'chuckle', 'gasp', 'cough', 'sigh', 'groan', 'sniff', 'shush', 'clear throat')


class GemmaUnavailable(Exception):
    pass


def _post(path, body, timeout=600):
    url = config.get('ollama_url').rstrip('/') + path
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise GemmaUnavailable(str(e))


def status():
    """{'ok': bool, 'models': [...], 'model_ready': bool, 'error': str}"""
    url = config.get('ollama_url').rstrip('/') + '/api/tags'
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            models = [m['name'] for m in json.loads(r.read()).get('models', [])]
        want = config.get('ollama_model')
        ready = want in models or any(m.split(':')[0] == want.split(':')[0] and ':' not in want for m in models)
        return {'ok': True, 'models': models, 'model_ready': ready, 'error': ''}
    except Exception as e:
        return {'ok': False, 'models': [], 'model_ready': False, 'error': str(e)}


def chat(system, user, as_json=True, temperature=0.1):
    body = {
        'model': config.get('ollama_model'),
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        'stream': False,
        'options': {'temperature': temperature, 'num_ctx': int(config.get('ollama_context'))},
        'keep_alive': '10m',
    }
    if as_json:
        body['format'] = 'json'
    r = _post('/api/chat', body)
    text = (r.get('message') or {}).get('content', '')
    if not as_json:
        return text.strip()
    return parse_json(text)


def parse_json(text):
    text = text.strip()
    text = re.sub(r'^```(?:json)?|```$', '', text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


def unload():
    try:
        _post('/api/generate', {'model': config.get('ollama_model'), 'keep_alive': 0}, timeout=20)
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------- characters

CHAR_SYSTEM = (
    "You are casting an audiobook. You read a passage of a novel and list the characters who SPEAK or are "
    "likely to speak. Answer only with JSON."
)


def find_characters(passage, known):
    prompt = (
        "Characters already known (name: aliases): " + ('; '.join(f"{k['name']}: {', '.join(k['aliases'])}" for k in known)
                                                        or 'none') + "\n\n"
        "From the passage below, list every character who speaks, plus important named characters. "
        "Use the SAME name as the known list when it is the same person (e.g. 'Bones' is McCoy, 'Jim' is Kirk). "
        "For each give: name (short, how the book usually refers to them), aliases (other names, nicknames, titles "
        "used for them), gender (male/female/unknown), description (under 12 words: who they are and how they "
        "sound, for choosing a voice).\n"
        'Reply as {"characters":[{"name":"","aliases":[],"gender":"","description":""}]}\n\nPASSAGE:\n' + passage
    )
    data = chat(CHAR_SYSTEM, prompt) or {}
    out = []
    for c in data.get('characters', []) if isinstance(data, dict) else []:
        if not isinstance(c, dict) or not str(c.get('name', '')).strip():
            continue
        g = str(c.get('gender', '')).lower()
        out.append({'name': str(c['name']).strip(), 'aliases': [str(a).strip() for a in c.get('aliases') or [] if str(a).strip()],
                    'gender': g if g in ('male', 'female') else '', 'description': str(c.get('description', ''))[:160]})
    return out


# ---------------------------------------------------------------------------------------------------- speakers

ATTR_SYSTEM = (
    "You are an expert audiobook director. For each numbered quotation in the passage you decide WHO speaks it "
    "and HOW it is said. You use the narration around it, speech tags, who is in the scene, and the back-and-forth "
    "of conversation. A quotation can be a thought, a sign or a ship's computer - name the source as the book "
    "would. Answer only with JSON."
)


def attribute(passage, characters, previous_summary=''):
    """passage: narration with quotes marked [Q12]"..."  -> {12: {'speaker','emotion','sound'}}"""
    cast_list = '\n'.join(f"- {c['name']}" + (f" (also: {', '.join(c['aliases'][:6])})" if c['aliases'] else '') +
                          (f" - {c['description']}" if c.get('description') else '') for c in characters)
    prompt = (
        "CHARACTERS:\n" + (cast_list or '(none known yet)') + "\n\n" +
        (f"WHAT JUST HAPPENED: {previous_summary}\n\n" if previous_summary else '') +
        "For EVERY [Qn] in the passage give:\n"
        "- speaker: a name from CHARACTERS (exactly as written there), or a new short name if it is someone else, "
        "or 'Narrator' if it isn't speech at all (a title, a quoted word, a sign).\n"
        "- emotion: one of " + ', '.join(EMOTIONS) + " (most lines are neutral; use the others only when the text "
        "makes it clear).\n"
        "- sound: one of laugh, chuckle, gasp, cough, sigh, groan, sniff, shush, clear throat, or empty - only when "
        "the narration says the speaker does it as they speak.\n"
        'Reply as {"quotes":[{"id":1,"speaker":"","emotion":"neutral","sound":""}]}\n\nPASSAGE:\n' + passage
    )
    data = chat(ATTR_SYSTEM, prompt) or {}
    out = {}
    for q in data.get('quotes', []) if isinstance(data, dict) else []:
        try:
            qid = int(str(q.get('id')).strip('Q'))
        except (TypeError, ValueError):
            continue
        emo = str(q.get('emotion', '')).lower().strip()
        snd = str(q.get('sound', '')).lower().strip().strip('[]')
        out[qid] = {'speaker': str(q.get('speaker', '')).strip(),
                    'emotion': emo if emo in EMOTIONS else 'neutral',
                    'sound': snd if snd in SOUNDS else ''}
    return out


def summarise(text, kind='chapter', title=''):
    if kind == 'recap':
        system = ("You write short, spoiler-careful 'previously on' recaps for someone listening to an audiobook in "
                  "the car. Warm, clear, plain English, no headings, no lists.")
        prompt = ("Write a recap (about 150 words) of the story so far, from these chapter summaries, so the "
                  "listener remembers where they are:\n\n" + text)
    else:
        system = "You summarise chapters of novels in plain, vivid English. No headings, no lists."
        prompt = (f"Summarise this chapter{(' (' + title + ')') if title else ''} in 3-5 sentences: who, where, what "
                  "happens, and how it ends.\n\n" + text)
    return chat(system, prompt, as_json=False, temperature=0.4)
