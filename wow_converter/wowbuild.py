"""Blender: build a WoW mesh from dump.py output, optionally run the HD smoothing pass, save .blend + .glb.
blender -b --python wowbuild.py -- <dumpdir> <outbase> [levels=2] [crease_deg=55] [raw]

Smoothing pass ("HD pass"):
  1. weld the UV-seam splits so the surface is one piece (UVs stay per corner)
  2. edges sharper than crease_deg become creases (stay crisp but get a rounded bevel),
     open borders stay as they are
  3. Catmull-Clark subdivision, then solve the cage so the smooth surface still passes
     through every original vertex - it rounds off between the points without shrinking
     or changing the silhouette
  4. apply, smooth shading
"""
import bpy, bmesh, sys, os, json, math
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
src, outbase = argv[0], argv[1]
levels = int(argv[2]) if len(argv) > 2 else 2
crease_deg = float(argv[3]) if len(argv) > 3 else 55.0
raw = 'raw' in argv
CMIN = float(argv[4]) if len(argv) > 4 and argv[4] != 'raw' else 0.8
UVSEAM = True

bpy.ops.wm.read_factory_settings(use_empty=True)
d = np.load(os.path.join(src, 'mesh.npz')); info = json.load(open(os.path.join(src, 'info.json')))
pos, uv, faces, mat = d['pos'], d['uv'], d['faces'], d['mat']

# --- materials
mat_ids = sorted(set(int(m) for m in mat)); slot = {m: i for i, m in enumerate(mat_ids)}
def make_mat(fid):
    m = bpy.data.materials.new(f'tex_{fid}'); m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.45
    if fid and str(fid) in info['textures']:
        t = m.node_tree.nodes.new('ShaderNodeTexImage')
        t.image = bpy.data.images.load(os.path.join(src, info['textures'][str(fid)]))
        t.interpolation = 'Cubic'
        m.node_tree.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    return m

# --- mesh (WoW: X fwd, Y left, Z up -> same handedness as Blender)
me = bpy.data.meshes.new(info['name'] or 'wow')
me.from_pydata([tuple(p) for p in pos], [], [tuple(int(i) for i in f) for f in faces])
uvl = me.uv_layers.new(name='UVMap')
lu = np.array([uv[me.loops[i].vertex_index] for i in range(len(me.loops))])
lu[:, 1] = 1.0 - lu[:, 1]
uvl.data.foreach_set('uv', lu.ravel())
for fid in mat_ids: me.materials.append(make_mat(fid))
me.polygons.foreach_set('material_index', [slot[int(m)] for m in mat])
ob = bpy.data.objects.new(me.name, me); bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob; ob.select_set(True)

# weld seam duplicates (WoW splits verts at UV seams / hard normals)
bm = bmesh.new(); bm.from_mesh(me)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()
nv0, nf0 = len(me.vertices), len(me.polygons)

if not raw:
    # creases on sharp edges
    bm = bmesh.new(); bm.from_mesh(me)
    cl = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    lim = math.radians(crease_deg)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            a = e.calc_face_angle(0.0)
            if a > lim: e[cl] = min(1.0, CMIN + (1.0 - CMIN) * (a - lim) / (math.radians(75) - lim + 1e-6))
        elif len(e.link_faces) != 2: e[cl] = 1.0
    uvl_b = bm.loops.layers.uv.active
    for e in bm.edges:
        if len(e.link_faces) == 2 and e[cl] < 1.0:
            uvs = []
            for f in e.link_faces:
                for l in f.loops:
                    if l.edge == e: uvs.append((tuple(l[uvl_b].uv), tuple(l.link_loop_next[uvl_b].uv)))
            (a0, a1), (b0, b1) = uvs
            if max(abs(a0[0]-b1[0]), abs(a0[1]-b1[1]), abs(a1[0]-b0[0]), abs(a1[1]-b0[1])) > 1e-4:
                e[cl] = max(e[cl], 0.9)
    bm.to_mesh(me); bm.free()

    sub = ob.modifiers.new('HD', 'SUBSURF')
    sub.levels = sub.render_levels = levels
    sub.uv_smooth = 'PRESERVE_CORNERS_AND_JUNCTIONS'; sub.boundary_smooth = 'PRESERVE_CORNERS'
    sub.use_limit_surface = True; sub.quality = 3; sub.use_creases = True

    # solve cage so the limit surface interpolates the original vertices
    target = np.zeros(nv0 * 3); me.vertices.foreach_get('co', target); target = target.reshape(-1, 3)
    cage = target.copy()
    dg = bpy.context.evaluated_depsgraph_get()
    for it in range(25):
        ev = ob.evaluated_get(dg).to_mesh()
        lim_pos = np.zeros(len(ev.vertices) * 3); ev.vertices.foreach_get('co', lim_pos)
        lim_pos = lim_pos.reshape(-1, 3)[:nv0]
        ob.evaluated_get(dg).to_mesh_clear()
        err = target - lim_pos
        cage += 0.9 * err
        me.vertices.foreach_set('co', cage.ravel()); me.update(); dg.update()
        if np.abs(err).max() < 1e-5 * (np.ptp(target) + 1e-9): break
    print('HD pass: iterations', it + 1, 'max error', float(np.abs(err).max()), flush=True)
    bpy.ops.object.modifier_apply(modifier='HD')

for p in me.polygons: p.use_smooth = True
print('faces', nf0, '->', len(me.polygons), flush=True)

os.makedirs(os.path.dirname(outbase) or '.', exist_ok=True)
for img in bpy.data.images: img.pack()
bpy.ops.wm.save_as_mainfile(filepath=outbase + '.blend')
bpy.ops.export_scene.gltf(filepath=outbase + '.glb', export_format='GLB', use_selection=False)
