"""Atiesh bird - stage B (Blender): carve the feathers into the fused solid.
blender -b fused.blend --python feathers.py -- <uvsrc.blend> <height.npy> <out.blend> [amp_mm=0.7]

Each point on the fused bird looks up the nearest point on the smoothed, UV-mapped bird,
reads the feather relief there (height map integrated from the model's own normal map)
and moves the surface in or out by up to amp_mm. Eyeballs, post and ferrule stay smooth."""
import bpy, sys, numpy as np
from mathutils.bvhtree import BVHTree
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
uvsrc_path, hpath, outp = argv[0], argv[1], argv[2]
AMP = float(argv[3]) if len(argv) > 3 else 0.7
MAXD = 0.7                                   # mm: further than this from the bird skin -> not feathered

def log(*a): print('[feathers]', *a, flush=True)

with bpy.data.libraries.load(uvsrc_path) as (src, dst): dst.objects = ['uvsrc']
src_ob = dst.objects[0]; sm = src_ob.data
sm.calc_loop_triangles()
nv = len(sm.vertices); co = np.zeros(nv * 3); sm.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
nt = len(sm.loop_triangles)
tv = np.zeros(nt * 3, int); sm.loop_triangles.foreach_get('vertices', tv); tv = tv.reshape(-1, 3)
tl = np.zeros(nt * 3, int); sm.loop_triangles.foreach_get('loops', tl); tl = tl.reshape(-1, 3)
tp = np.zeros(nt, int); sm.loop_triangles.foreach_get('polygon_index', tp)
luv = np.zeros(len(sm.loops) * 2); sm.uv_layers['UVMap'].data.foreach_get('uv', luv); luv = luv.reshape(-1, 2)
nod = np.zeros(len(sm.polygons), int); sm.attributes['nodisp'].data.foreach_get('value', nod)
bvh = BVHTree.FromPolygons([tuple(c) for c in co], [tuple(t) for t in tv])
log('source tris', nt)

H = np.load(hpath); Hh, Hw = H.shape
def sample(u, v):
    x = np.mod(u, 1.0) * (Hw - 1); y = np.mod(v, 1.0) * (Hh - 1)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); x1 = np.minimum(x0 + 1, Hw - 1); y1 = np.minimum(y0 + 1, Hh - 1)
    fx = x - x0; fy = y - y0
    return (H[y0, x0] * (1 - fx) * (1 - fy) + H[y0, x1] * fx * (1 - fy) + H[y1, x0] * (1 - fx) * fy + H[y1, x1] * fx * fy)

ob = bpy.data.objects['fused']; me = ob.data
n = len(me.vertices)
P = np.zeros(n * 3); me.vertices.foreach_get('co', P); P = P.reshape(-1, 3)
N = np.zeros(n * 3); me.vertex_normals.foreach_get('vector', N); N = N.reshape(-1, 3)
disp = np.zeros(n)
U = np.zeros(n); V = np.zeros(n); ok = np.zeros(n, bool)
for i in range(n):
    loc, nrm, idx, dist = bvh.find_nearest(Vector(P[i]), MAXD)
    if idx is None: continue
    if nod[tp[idx]]: continue
    a, b, c = co[tv[idx]]
    v0, v1, v2 = b - a, c - a, np.array(loc) - a
    d00 = v0 @ v0; d01 = v0 @ v1; d11 = v1 @ v1; d20 = v2 @ v0; d21 = v2 @ v1
    den = d00 * d11 - d01 * d01
    if den == 0: continue
    w1 = (d11 * d20 - d01 * d21) / den; w2 = (d00 * d21 - d01 * d20) / den; w0 = 1 - w1 - w2
    uv = w0 * luv[tl[idx, 0]] + w1 * luv[tl[idx, 1]] + w2 * luv[tl[idx, 2]]
    U[i], V[i] = uv; ok[i] = True
    if i % 100000 == 0: log('looked up', i, '/', n)
disp[ok] = sample(U[ok], V[ok])

# light smoothing of the relief over the surface (kills voxel-step noise, keeps feather shapes)
ne = len(me.edges); E = np.zeros(ne * 2, int); me.edges.foreach_get('vertices', E); E = E.reshape(-1, 2)
deg = np.bincount(E.ravel(), minlength=n).astype(float)
for _ in range(2):
    s = np.bincount(E[:, 0], weights=disp[E[:, 1]], minlength=n) + np.bincount(E[:, 1], weights=disp[E[:, 0]], minlength=n)
    disp = 0.5 * disp + 0.5 * np.where(deg > 0, s / np.maximum(deg, 1), disp)
disp[~ok] = 0.0
# fade the relief out over ~1 mm where feathered skin meets unfeathered parts (no cliffs)
w = ok.astype(float)
for _ in range(3):
    s = np.bincount(E[:, 0], weights=w[E[:, 1]], minlength=n) + np.bincount(E[:, 1], weights=w[E[:, 0]], minlength=n)
    w = np.minimum(w, np.where(deg > 0, s / np.maximum(deg, 1), w))
disp *= w
# keep sharp edges crisp (beak rim, wing edges, eye ring): no relief where the surface folds sharply
dots = np.einsum('ij,ij->i', N[E[:, 0]], N[E[:, 1]])
mind = np.ones(n)
np.minimum.at(mind, E[:, 0], dots); np.minimum.at(mind, E[:, 1], dots)
for _ in range(3):   # spread ~3 rings (~1.2 mm)
    m2 = mind.copy(); np.minimum.at(m2, E[:, 0], mind[E[:, 1]]); np.minimum.at(m2, E[:, 1], mind[E[:, 0]]); mind = m2
ang = np.degrees(np.arccos(np.clip(mind, -1, 1)))
t = np.clip((ang - 12.0) / (30.0 - 12.0), 0, 1)
disp *= 1 - t * t * (3 - 2 * t)
log('edge-faded verts', int((t > 0).sum()))

P2 = P + N * (disp * AMP)[:, None]
me.vertices.foreach_set('co', P2.ravel()); me.update()
log('feathered verts', int(ok.sum()), 'of', n, 'relief range mm', float(disp.min() * AMP), float(disp.max() * AMP))
bpy.data.objects.remove(src_ob)
bpy.ops.wm.save_as_mainfile(filepath=outp)
log('saved', outp)
