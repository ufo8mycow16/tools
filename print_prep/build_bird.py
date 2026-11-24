"""Atiesh bird topper - stage A (Blender).
blender -b --python build_bird.py -- <found.npz> <found_fl.npy> <outdir> [scale_mm_per_unit=15.5] [voxel_mm=0.4]

1. Takes Glen's Sketchfab Atiesh (Victor Guebel, CC-BY 4.0), keeps only the bird
   (drops shaft, post, medallions and their cords).
2. Seals each piece, smooths the low-poly facets (HD pass: creased Catmull-Clark,
   cage solved so the surface still passes through the original points).
3. Saves the smoothed, UV-mapped bird as uvsrc (feather lookup for stage B).
4. Adds a straight post for the talons and a 25 mm dowel ferrule (socket bored 50 mm deep),
   fuses everything into one watertight solid with a voxel remesh. All units in mm.
"""
import bpy, bmesh, sys, os, math
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
npz, flpath, out = argv[0], argv[1], argv[2]
S = float(argv[3]) if len(argv) > 3 else 15.5
VOX = float(argv[4]) if len(argv) > 4 else 0.4
os.makedirs(out, exist_ok=True)

DROP = {9, 1, 7, 23, 5, 16, 24, 4, 15, 25, 8, 11}   # shaft, medallions, cords, hangers, old post, ring
NODISP = {13, 21}                                   # eyeballs stay glossy-smooth

bpy.ops.wm.read_factory_settings(use_empty=True)
d = np.load(npz); pos = d['pos'] * S; uv = d['uv']; F = d['faces']; fl = np.load(flpath)

def log(*a): print('[bird]', *a, flush=True)

def hd_pass(ob, levels=2, crease_deg=40.0, cmin=0.9):
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    cl = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    lim = math.radians(crease_deg)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            a = e.calc_face_angle(0.0)
            if a > lim: e[cl] = min(1.0, cmin + (1.0 - cmin) * (a - lim) / (math.radians(75) - lim + 1e-6))
    bm.to_mesh(me); bm.free()
    nv0 = len(me.vertices)
    sub = ob.modifiers.new('HD', 'SUBSURF')
    sub.levels = sub.render_levels = levels
    sub.uv_smooth = 'PRESERVE_CORNERS_AND_JUNCTIONS'; sub.boundary_smooth = 'PRESERVE_CORNERS'
    sub.use_limit_surface = True; sub.quality = 3; sub.use_creases = True
    target = np.zeros(nv0 * 3); me.vertices.foreach_get('co', target); target = target.reshape(-1, 3)
    cage = target.copy(); dg = bpy.context.evaluated_depsgraph_get()
    for it in range(25):
        ev = ob.evaluated_get(dg).to_mesh()
        lp = np.zeros(len(ev.vertices) * 3); ev.vertices.foreach_get('co', lp); lp = lp.reshape(-1, 3)[:nv0]
        ob.evaluated_get(dg).to_mesh_clear()
        err = target - lp; cage += 0.9 * err
        me.vertices.foreach_set('co', cage.ravel()); me.update(); dg.update()
        if np.abs(err).max() < 1e-3: break
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier='HD')
    return it + 1, float(np.abs(err).max())

pieces = []
for c in sorted(set(np.unique(fl)) - DROP):
    sel = fl == c
    vs = np.unique(F[sel]); rm = -np.ones(len(pos), int); rm[vs] = np.arange(len(vs))
    me = bpy.data.meshes.new(f'p{c}')
    me.from_pydata([tuple(p) for p in pos[vs]], [], [tuple(int(i) for i in f) for f in rm[F[sel]]])
    uvl = me.uv_layers.new(name='UVMap')
    lu = np.array([uv[vs][me.loops[i].vertex_index] for i in range(len(me.loops))], dtype=float)
    uvl.data.foreach_set('uv', lu.ravel())          # raw glTF uv (v down) - stage B samples it the same way
    ob = bpy.data.objects.new(f'p{c}', me); bpy.context.scene.collection.objects.link(ob)
    # weld, seal holes, consistent normals
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    holes = [e for e in bm.edges if len(e.link_faces) == 1]
    if holes: bmesh.ops.holes_fill(bm, edges=holes, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    open_left = sum(1 for e in me.edges if e.use_seam and False)
    me['piece'] = int(c)
    it, er = hd_pass(ob)
    pa = me.attributes.new('piece', 'INT', 'FACE'); pa.data.foreach_set('value', [int(c)] * len(me.polygons))
    nd = me.attributes.new('nodisp', 'INT', 'FACE'); nd.data.foreach_set('value', [1 if c in NODISP else 0] * len(me.polygons))
    log('piece', c, 'faces', len(me.polygons), 'hd iters', it, 'err %.4f mm' % er)
    pieces.append(ob)

# join smoothed bird -> uvsrc
bpy.ops.object.select_all(action='DESELECT')
for o in pieces: o.select_set(True)
bpy.context.view_layer.objects.active = pieces[0]
bpy.ops.object.join()
bird = bpy.context.view_layer.objects.active; bird.name = 'uvsrc'
for p in bird.data.polygons: p.use_smooth = True
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'uvsrc.blend'))
co = np.zeros(len(bird.data.vertices) * 3); bird.data.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
log('bird bounds mm', co.min(0).round(1), co.max(0).round(1))

# ---- post + ferrule (lathe), mm, z up
def lathe(profile, name, seg=160):
    """profile: list of (r, z) going round a closed loop (r>0). Revolved into a closed solid."""
    bm = bmesh.new()
    rings = []
    for k in range(seg):
        a = 2 * math.pi * k / seg; ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((r * ca, r * sa, z)) for r, z in profile])
    n = len(profile)
    for k in range(seg):
        A, B = rings[k], rings[(k + 1) % seg]
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob

DOW = 25.0; BORE_R = (DOW + 0.6) / 2      # 25.6 mm bore: slides on a 25 mm dowel, glue fills the gap
FER_R = 16.5; BAND_R = 17.6
POST_R = 12.75
z_top_fer = 6.0                          # ferrule top (just under the tail tip)
z_bot = z_top_fer - 56.0                 # ferrule bottom
depth = 50.0
z_post_top = 66.0                        # up inside the talons/body

# ferrule profile (outer top -> bottom, then up the bore), closed loop
fer = [
    (POST_R, z_top_fer + 1.0),
    (BAND_R - 0.6, z_top_fer + 0.2), (BAND_R, z_top_fer - 0.6), (BAND_R, z_top_fer - 4.0), (FER_R, z_top_fer - 5.0),
    (FER_R, z_bot + 7.0), (BAND_R, z_bot + 6.0), (BAND_R, z_bot + 1.2), (BAND_R - 1.2, z_bot),
    (BORE_R + 1.0, z_bot), (BORE_R, z_bot + 1.0),           # 1 mm lead-in chamfer
    (BORE_R, z_bot + depth - 0.8), (BORE_R - 0.8, z_bot + depth),
    (0.05, z_bot + depth),
    (0.05, z_top_fer + 1.0),
]
# make the loop go outward-first consistently: it's fine as a closed polygon in (r,z)
F_ob = lathe(fer, 'ferrule')
P_ob = lathe([(POST_R, z_top_fer), (POST_R, z_post_top), (0.05, z_post_top), (0.05, z_top_fer)], 'post')

for o in (F_ob, P_ob): o.select_set(False)
bpy.ops.object.select_all(action='DESELECT')
# copy of bird for fusing (keep uvsrc untouched)
fuse = bird.copy(); fuse.data = bird.data.copy(); fuse.name = 'fused'; bpy.context.scene.collection.objects.link(fuse)
for o in (fuse, F_ob, P_ob): o.select_set(True)
bpy.context.view_layer.objects.active = fuse
bpy.ops.object.join()
fuse = bpy.context.view_layer.objects.active
log('joined faces', len(fuse.data.polygons), '- remeshing at', VOX, 'mm')
rem = fuse.modifiers.new('fuse', 'REMESH'); rem.mode = 'VOXEL'; rem.voxel_size = VOX; rem.adaptivity = 0.0
rem.use_smooth_shade = True
bpy.ops.object.modifier_apply(modifier='fuse')
log('fused faces', len(fuse.data.polygons), 'verts', len(fuse.data.vertices))
bpy.data.objects.remove(bird)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'fused.blend'))
log('done')
