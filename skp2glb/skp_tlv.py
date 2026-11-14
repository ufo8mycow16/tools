"""Minimal SketchUp (2021+) .skp reader: ZIP container + model.dat TLV tree. Written from skppy's format notes."""
import struct, zipfile, io, json, os
_T = json.load(open(os.path.join(os.path.dirname(__file__), 'tags.json')))
CONT = set(_T['containers']) | {0x05DD}
NAMES = {int(k): v for k, v in _T['names'].items()}

class Node:
    __slots__ = ('tag', 'data', 'kids')
    def __init__(s, tag, data, kids): s.tag, s.data, s.kids = tag, data, kids
    def all(s, tag): return [k for k in (s.kids or []) if k.tag == tag]
    def first(s, *path):
        n = s
        for t in path:
            if n is None or n.kids is None: return None
            n = next((k for k in n.kids if k.tag == t), None)
        return n
    def __repr__(s): return f"<{s.tag:#06x} {NAMES.get(s.tag)} {'%d kids' % len(s.kids) if s.kids is not None else '%dB' % len(s.data)}>"

def _scan(buf, a, b):
    """Return list of (tag, start, end) if [a,b) is exactly a sequence of TLV records, else None."""
    out = []; p = a
    while p < b:
        if p + 6 > b: return None
        tag, ln = struct.unpack_from('<HI', buf, p)
        q = p + 6 + ln
        if q > b: return None
        out.append((tag, p + 6, q)); p = q
    return out

def parse(buf, a=0, b=None):
    b = len(buf) if b is None else b
    recs = _scan(buf, a, b)
    nodes = []
    for tag, s, e in recs:
        kids = None
        if tag in CONT and e > s:
            sub = _scan(buf, s, e)
            if sub is not None: kids = parse(buf, s, e)
        elif tag in CONT and e == s:
            kids = []
        nodes.append(Node(tag, buf[s:e] if kids is None else b'', kids))
    return nodes

def load(path):
    raw = open(path, 'rb').read()
    z = zipfile.ZipFile(io.BytesIO(raw[raw.find(b'PK\x03\x04'):]))
    md = z.read('model.dat')
    root = Node(-1, b'', parse(md))
    return z, root

def cint(b):
    return int.from_bytes(b, 'little') if b else 0
def idof(node):
    w = node.first(0x05DC, 0x05DE) if node else None
    return cint(w.data) if w is not None else None
