"""Plan a fetch: ids/ckeys -> requests.txt for the PC fetcher."""
import sys, pickle, os
sys.path.insert(0, '/home/claude/wowx'); import casc
BASE = '/mnt/user-data/uploads/Games/World of Warcraft/Data/'
_idx = None; _enc = None; _root = None
def idx():
    global _idx
    if _idx is None: _idx = casc.load_idx(BASE + 'data')
    return _idx
def enc():
    global _enc
    if _enc is None: _enc = pickle.load(open('/home/claude/wowx/encoding.pkl', 'rb'))
    return _enc
def root():
    global _root
    if _root is None and os.path.exists('/home/claude/wowx/root.pkl'): _root = pickle.load(open('/home/claude/wowx/root.pkl', 'rb'))
    return _root
def loc_for_ckey(ck):
    ek = enc().get(ck)
    if ek is None: return None
    return idx().get(ek[:9])
def write_requests(items, path='/mnt/user-data/outputs/wowtools/requests.txt'):
    """items: list of (name, (arch, off, size))"""
    with open(path, 'w', newline='\r\n') as f:
        for name, (a, o, s) in items:
            f.write(f'{a} {o} {s} {name}\n')
    return path

def request_fids(fids, path='/mnt/user-data/outputs/wowtools/requests.txt'):
    """Write requests for FileDataIDs; names are <fid>.blte. Returns list missing."""
    items = []; miss = []
    for fid in fids:
        ck = root().get(fid)
        loc = plan_loc(ck) if ck else None
        if loc: items.append((f'{fid}.blte', loc))
        else: miss.append(fid)
    write_requests(items, path); return miss
def plan_loc(ck): return loc_for_ckey(ck)
def read_fid(fid, folder='/mnt/user-data/uploads/Documents/WoW Tools/out/'):
    raw = open(folder + f'{fid}.blte', 'rb').read()
    # idx entries point at a 30-byte header (ekey(16)+size(4)+flags(2)+checksums(8)) before BLTE
    return casc.blte_decode(raw)
