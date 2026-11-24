"""Atiesh charms (from the game's charm string: silver disc, gem in a gold ring, gold beads, two bound claws).
blender -b --python charms.py -- <outdir>
Every piece is its own watertight solid, sized in mm, with a 3 mm cord hole. Laid flat for printing."""
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector, Matrix

out = sys.argv[sys.argv.index('--') + 1:][0]; os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
def log(*a): print('[charms]', *a, flush=True)

def new_obj(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); SC.collection.objects.link(ob); return ob

def lathe(profile, name, seg=96, axis='Z'):
    bm = bmesh.new(); rings = []
    for k in range(seg):
        a = 2 * math.pi * k / seg; ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((r * ca, r * sa, z)) for r, z in profile])
    n = len(profile)
    for k in range(seg):
        A, B = rings[k], rings[(k + 1) % seg]
        for i in range(n):
            j = (i + 1) % n; bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm)

def torus(name, R, r, loc=(0, 0, 0), rot=(0, 0, 0), seg=64, mseg=24):
    bm = bmesh.new()
    bmesh.ops.create_cone  # noqa (keeps bmesh ops import obvious)
    vs = []
    for i in range(seg):
        a = 2 * math.pi * i / seg; row = []
        for j in range(mseg):
            b = 2 * math.pi * j / mseg
            row.append(bm.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
        vs.append(row)
    for i in range(seg):
        for j in range(mseg):
            bm.faces.new((vs[i][j], vs[(i + 1) % seg][j], vs[(i + 1) % seg][(j + 1) % mseg], vs[i][(j + 1) % mseg]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = new_obj(name, bm); ob.location = loc; ob.rotation_euler = rot; return ob

def sphere(name, r, loc=(0, 0, 0)):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=r)
    ob = new_obj(name, bm); ob.location = loc; return ob

def cyl(name, r, h, loc=(0, 0, 0), rot=(0, 0, 0), seg=48):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=h)
    ob = new_obj(name, bm); ob.location = loc; ob.rotation_euler = rot; return ob

def box(name, size, loc):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    ob = new_obj(name, bm); ob.scale = size; ob.location = loc; return ob

def apply_tf(ob):
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

def fuse(name, parts, vox=0.1):
    for p in parts: apply_tf(p)
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts: p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]; bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = name
    m = ob.modifiers.new('r', 'REMESH'); m.mode = 'VOXEL'; m.voxel_size = vox; m.adaptivity = 0.0
    bpy.ops.object.modifier_apply(modifier='r')
    sm = ob.modifiers.new('s', 'SMOOTH'); sm.factor = 0.5; sm.iterations = 2
    bpy.ops.object.modifier_apply(modifier='s')
    return ob

def cut(ob, cutter):
    apply_tf(cutter)
    b = ob.modifiers.new('cut', 'BOOLEAN'); b.operation = 'DIFFERENCE'; b.object = cutter; b.solver = 'EXACT'
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.modifier_apply(modifier='cut')
    bpy.data.objects.remove(cutter)

def dec(ob, target=120000):
    n = len(ob.data.polygons)
    if n > target:
        d = ob.modifiers.new('d', 'DECIMATE'); d.ratio = target / n
        bpy.context.view_layer.objects.active = ob; bpy.ops.object.modifier_apply(modifier='d')

HOLE = 1.6   # 3.2 mm cord hole

# ---- 1. silver disc (coin with rings, loop on top; lies flat, face up)
R = 12.0
disc = lathe([(0.01, 0), (R - 0.6, 0), (R, 0.6), (R, 2.8), (R - 0.6, 3.6), (R - 1.6, 3.6), (R - 2.0, 3.0),
              (8.4, 3.0), (8.0, 3.5), (7.2, 3.5), (6.8, 3.0), (4.6, 3.0), (4.2, 3.5), (3.6, 4.4), (2.0, 4.9), (0.01, 5.0)], 'disc_body')
loop = torus('disc_loop', 3.4, 1.6, loc=(0, R + 2.2, 1.8))
disc = fuse('Disc (silver)', [disc, loop], 0.08)
dec(disc)

# ---- 2. gem in a gold ring: ring + two half-gems that glue in from either side
ring = torus('ring', 8.6, 1.9, loc=(0, 0, 1.9))                       # flat on the bed
bail = torus('bail', 2.8, 1.3, loc=(0, 8.6 + 1.9 + 2.0, 1.9))
ring = fuse('Gem ring (gold)', [ring, bail], 0.08)
dec(ring)
GR = 7.6
gem = lathe([(0.01, 0)] + [(GR * math.cos(t), GR * math.sin(t)) for t in np.linspace(0.0, math.pi / 2, 24)[:-1]] + [(0.01, GR)], 'Gem half (class colour)', seg=96)
gem2 = gem.copy(); gem2.data = gem.data.copy(); gem2.name = 'Gem half 2 (class colour)'; SC.collection.objects.link(gem2)

# ---- 3. gold beads (9 mm, bored, small flats top and bottom so they print standing)
beads = []
for i in range(3):
    t0 = math.acos(1 - 0.7 / 4.5)
    prof = [(0.01, 0.7)] + [(4.5 * math.sin(t), 4.5 - 4.5 * math.cos(t)) for t in np.linspace(t0, math.pi - t0, 40)] + [(0.01, 8.3)]
    b = lathe(prof, f'Bead {i + 1} (gold)', seg=64)
    cut(b, cyl('h', HOLE, 30, loc=(0, 0, 4)))
    beads.append(b)

# ---- 4. claws: curved tapering fang swept on an arc, bound base with wraps, cord hole through the base
def claw(name, mirror=False):
    bm = bmesh.new()
    Rarc = 34.0; ang = math.radians(62); n = 40; m = 28
    rings = []
    for i in range(n + 1):
        t = i / n
        a = ang * t
        c = Vector((Rarc * (1 - math.cos(a)), Rarc * math.sin(a), 0))         # arc in XY, starts at origin heading +Y
        tang = Vector((math.sin(a), math.cos(a), 0)); nrm = Vector((math.cos(a), -math.sin(a), 0)); bi = Vector((0, 0, 1))
        rad = 5.2 * (1 - t) ** 0.85 + 0.35
        flat = 0.72                                                            # fangs are a bit flattened
        row = []
        for j in range(m):
            b = 2 * math.pi * j / m
            row.append(bm.verts.new(c + nrm * (rad * math.cos(b)) + bi * (rad * flat * math.sin(b))))
        rings.append(row)
    for i in range(n):
        for j in range(m):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % m], rings[i + 1][(j + 1) % m], rings[i + 1][j]))
    tip = bm.verts.new(Vector((Rarc * (1 - math.cos(ang)), Rarc * math.sin(ang), 0)) + Vector((math.sin(ang), math.cos(ang), 0)) * 0.6)
    for j in range(m): bm.faces.new((rings[n][j], rings[n][(j + 1) % m], tip))
    base = bm.verts.new((0, 0, 0))
    for j in range(m): bm.faces.new((rings[0][(j + 1) % m], rings[0][j], base))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    fang = new_obj(name + '_fang', bm)
    stub = cyl('stub', 5.6, 12, loc=(0, -5.0, 0), rot=(math.pi / 2, 0, 0))   # bound base, back along -Y
    wraps = [torus(f'w{k}', 5.6, 1.0, loc=(0, -1.8 - 3.0 * k, 0), rot=(math.pi / 2, 0, 0)) for k in range(4)]
    knob = sphere('knob', 4.2, loc=(0, -11.5, 0))
    ob = fuse(name, [fang, stub, knob] + wraps, 0.08)
    cut(ob, cyl('h', HOLE, 30, loc=(0, -8.6, 0)))                          # hole across the binding (vertical when lying flat)
    if mirror:
        ob.scale.x = -1; apply_tf(ob)
        bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.reverse_faces(bm, faces=bm.faces); bm.to_mesh(ob.data); bm.free()
    # lie flat: lowest point on z=0
    zmin = min(v.co.z for v in ob.data.vertices)
    for v in ob.data.vertices: v.co.z -= zmin
    dec(ob)
    return ob

c1 = claw('Claw 1 (ivory, red binding)'); c2 = claw('Claw 2 (ivory, red binding)', mirror=True)
# cord hole in the disc / ring loops already exists (torus); everything to z>=0
for ob in [disc, ring, gem, gem2] + beads:
    zmin = min(v.co.z for v in ob.data.vertices)
    for v in ob.data.vertices: v.co.z -= zmin

report = []
for ob in [disc, ring, gem, gem2] + beads + [c1, c2]:
    bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.triangulate(bm, faces=bm.faces)
    bad = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bm.verts.ensure_lookup_table()
    V = np.array([v.co[:] for v in bm.verts]); F = np.array([[v.index for v in f.verts] for f in bm.faces]); bm.free()
    np.savez(os.path.join(out, ob.name + '.npz'), V=V, F=F)
    log(ob.name, 'tris', len(F), 'bad edges', bad, 'size', (V.max(0) - V.min(0)).round(1))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'charms.blend'))
