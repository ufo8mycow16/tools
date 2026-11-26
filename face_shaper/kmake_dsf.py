"""Chekov: final head (final_X.npy, export space) -> FHMChekovLikeness.dsf for g8_head_swap --figure Genesis8Male."""
import json, sys, numpy as np
sys.path.insert(0,'/home/claude/vulcan-fury/tools/crew'); sys.path.insert(0,'/home/claude/vulcan-fury/tools/crew/likeness')
from scipy.spatial import cKDTree
from g9_build_character import load
import kfit
from bindbody import bp
blank = load('/home/claude/kyle/g8m/Content/data/DAZ 3D/Genesis 8/Male/Genesis8Male.dsf')
Bv = np.array(blank['geometry_library'][0]['vertices']['values'], np.float64)
bcen = {n['id']: np.array([c['value'] for c in n['center_point']]) for n in blank['node_library'] if 'center_point' in n}
E = kfit.X0; X = np.load('final_X.npy')
top_y = E[:,1].max(); lo = 0.845*top_y
sel = np.where(E[:,1] > lo - 6)[0]
H = Bv.copy(); H[sel] = X[sel]
ring = (E[:,1] > lo) & (E[:,1] < lo + 1.0); t = (E[ring] - H[ring]).mean(0); print('neck nudge', np.round(t,3))
bind = bp('/home/claude/vulcan-fury/assets/models/characters/Chekov_daz.fbx', b'Genesis8Male_BindPose'); print(len(bind), 'bind nodes')
change = X - E
comp = kfit.comp; skin = np.where(kfit.skin)[0]; kd = cKDTree(E[skin])
# eyeballs: the two components whose centres sit at the eye corners' height, either side
cands = [c for c in np.unique(comp) if c != kfit.skin_id and 100 < (comp==c).sum() < 3000]
eyes = {}
for c in cands:
    m = comp == c; cen = E[m].mean(0)
    if abs(cen[1]-E[kfit.vm['L_out'],1]) < 1.5 and 1.5 < abs(cen[0]) < 5 and cen[2] > 4:
        k='lEye' if cen[0] > 0 else 'rEye'; eyes[k] = eyes.get(k, np.zeros_like(m)) | m
print('eyes', {k:int(v.sum()) for k,v in eyes.items()})
moves = {}
for b, c in bcen.items():
    if b not in bind: continue
    cb = np.asarray(bind[b], float)
    if cb[1] < lo: continue
    if b in eyes: loc = change[eyes[b]].mean(0)
    else:
        d, nn = kd.query(cb, k=12); w = 1/(d+0.5)**2; w /= w.sum(); loc = (change[skin[nn]]*w[:,None]).sum(0)
    moves[b] = (cb + loc - t) - c
D = H - Bv; idx = np.where(np.abs(D).max(1) > 1e-4)[0]
print(len(moves), 'joints, deltas on', len(idx))
mid = 'FHMChekovLikeness'
def formula(b, ax, k):
    return {"output": f"{b}:#{b}?center_point/{ax}", "operations": [{"op":"push","url":f"Genesis8Male:#{mid}?value"},{"op":"push","val":float(k)},{"op":"mult"}]}
dsf = {"file_version":"0.6.0.0","asset_info":{"id":f"/data/ThirdMoon/Chekov/{mid}.dsf","type":"modifier","contributor":{"author":"Third Moon Interactive (Claude)"},"revision":"1.0","modified":"2026-11-20"},
       "modifier_library":[{"id":mid,"name":mid,"parent":"/data/DAZ%203D/Genesis%208/Male/Genesis8Male.dsf#Genesis8Male",
          "presentation":{"type":"Modifier/Shape","label":"Chekov Likeness"},
          "channel":{"id":"value","type":"float","name":"Chekov Likeness","value":0,"min":0,"max":1,"clamped":True},
          "region":"Head","group":"/Head/Real World",
          "formulas":[formula(b,ax,m[i]) for b,m in moves.items() for i,ax in enumerate('xyz') if abs(m[i])>1e-4],
          "morph":{"vertex_count":len(Bv),"deltas":{"count":len(idx),"values":[[int(i)]+[round(float(v),5) for v in D[i]] for i in idx]}}}]}
json.dump(dsf, open(f'{mid}.dsf','w')); print('wrote', mid)
