"""Halcyon 1084 monitor: SketchUp conversion -> real-looking game prop.

blender -b --python build_monitor.py -- <in.glb> <out_dir> [bake_size]

1. imports the converted SketchUp model, drops the doubled-up screen glass and LED lens
2. sorts the SketchUp colours into real materials (aged beige plastic, darker trim, dark plastic,
   nickel connectors, coloured RCA rings, power LED, the CRT screen, the Halcyon badge)
3. bakes the plastics (colour with grime/dust, roughness, surface grain) into one texture set
4. writes halcyon_1084.blend (full procedural version) and halcyon_1084.glb (baked, for Godot)

Materials in the .glb: Halcyon_Body (baked atlas), Halcyon_Metal, Halcyon_Badge, Halcyon_LED,
CRT_Screen (its own 0..1 UVs across the tube face, so the game can put any picture on it).
"""
import bpy, bmesh, sys, os, math

argv = sys.argv[sys.argv.index('--') + 1:]
SRC, OUT = argv[0], argv[1]
BAKE = int(argv[2]) if len(argv) > 2 else 2048
HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, 'tex')
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)

# -- 1. tidy ---------------------------------------------------------------------------
for n in ('Mesh_11', 'Mesh_12'):          # glass pane over the tube, lens over the LED
    bpy.data.objects.remove(bpy.data.objects[n])
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in meshes:
    o.data = o.data.copy()                 # instanced parts -> own data before joining
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
mon = bpy.context.view_layer.objects.active
mon.name = mon.data.name = 'Halcyon1084'
for o in [o for o in bpy.data.objects if o.type == 'EMPTY']:
    bpy.data.objects.remove(o)
mon.parent = None
# sit it on the ground, centred
me = mon.data
zs = [v.co.z for v in me.vertices]
xs = [v.co.x for v in me.vertices]
ys = [v.co.y for v in me.vertices]
off = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs))
for v in me.vertices:
    v.co.x -= off[0]; v.co.y -= off[1]; v.co.z -= off[2]

# -- 2. materials ------------------------------------------------------------------------
GROUP = {
    '[0010_Snow]': 'body', 'Default': 'body', '[0035_Tan]': 'trim',
    '[0136_Charcoal]': 'dark', '[0137_Black]': 'dark', '_Black_1': 'dark', 'Color_006': 'dark',
    '[0070_SpringGreen]': 'dark',
    'Metal_Corrogated_Shiny': 'metal', '_6': 'metal', '_12': 'metal', '_5': 'metal',
    '[0056_Yellow]': 'rca_yellow', '[Color_000]': 'rca_white', '[0128_White]': 'label',
    '[0065_Lime]': 'led', 'Screen-LotusII': 'screen', 'Badge-1084': 'badge',
}

def nodes_of(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (900, 0)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (600, 0)
    nt.links.new(bs.outputs[0], out.inputs[0])
    return nt, bs

def plastic(name, rgb, rough, grain=1.0, grime=0.7, yellow=0.08):
    """Moulded ABS: fine speckle grain, faint sun-yellowing blotches, grime in the creases,
    a little dust on top faces."""
    m = bpy.data.materials.new(name); nt, bs = nodes_of(m); L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    # yellowing blotches (big, soft)
    nb = nt.nodes.new('ShaderNodeTexNoise'); nb.inputs['Scale'].default_value = 6.0
    nb.inputs['Detail'].default_value = 3.0; L.new(tc.outputs['Object'], nb.inputs['Vector'])
    base = nt.nodes.new('ShaderNodeRGB'); base.outputs[0].default_value = (*rgb, 1)
    yel = nt.nodes.new('ShaderNodeRGB')
    yel.outputs[0].default_value = (rgb[0] * 1.0, rgb[1] * 0.93, rgb[2] * 0.74, 1)
    mixy = nt.nodes.new('ShaderNodeMix'); mixy.data_type = 'RGBA'
    ramp = nt.nodes.new('ShaderNodeMapRange'); ramp.inputs['From Min'].default_value = 0.45
    ramp.inputs['From Max'].default_value = 0.75; ramp.inputs['To Max'].default_value = yellow * 6
    L.new(nb.outputs['Fac'], ramp.inputs['Value']); L.new(ramp.outputs[0], mixy.inputs['Factor'])
    L.new(base.outputs[0], mixy.inputs[6]); L.new(yel.outputs[0], mixy.inputs[7])
    # grime in creases (ambient occlusion), brown-grey
    ao = nt.nodes.new('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = 0.012
    ao.samples = 16
    inv = nt.nodes.new('ShaderNodeMapRange'); inv.inputs['From Min'].default_value = 0.35
    inv.inputs['From Max'].default_value = 1.0; inv.inputs['To Min'].default_value = grime
    inv.inputs['To Max'].default_value = 0.0
    L.new(ao.outputs['AO'], inv.inputs['Value'])
    dirt = nt.nodes.new('ShaderNodeMix'); dirt.data_type = 'RGBA'
    L.new(inv.outputs[0], dirt.inputs['Factor']); L.new(mixy.outputs[2], dirt.inputs[6])
    dirt.inputs[7].default_value = (rgb[0] * 0.42, rgb[1] * 0.38, rgb[2] * 0.32, 1)
    # dust on upward faces
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); L.new(geo.outputs['Normal'], sep.inputs[0])
    nd = nt.nodes.new('ShaderNodeTexNoise'); nd.inputs['Scale'].default_value = 140
    L.new(tc.outputs['Object'], nd.inputs['Vector'])
    up = nt.nodes.new('ShaderNodeMath'); up.operation = 'MULTIPLY'
    L.new(sep.outputs['Z'], up.inputs[0]); L.new(nd.outputs['Fac'], up.inputs[1])
    upc = nt.nodes.new('ShaderNodeMapRange'); upc.inputs['From Min'].default_value = 0.45
    upc.inputs['From Max'].default_value = 0.8; upc.inputs['To Max'].default_value = 0.18
    L.new(up.outputs[0], upc.inputs['Value'])
    dust = nt.nodes.new('ShaderNodeMix'); dust.data_type = 'RGBA'
    L.new(upc.outputs[0], dust.inputs['Factor']); L.new(dirt.outputs[2], dust.inputs[6])
    dust.inputs[7].default_value = (0.55, 0.53, 0.5, 1)
    L.new(dust.outputs[2], bs.inputs['Base Color'])
    # roughness: satin, rougher where grimy/dusty
    rn = nt.nodes.new('ShaderNodeTexNoise'); rn.inputs['Scale'].default_value = 40
    L.new(tc.outputs['Object'], rn.inputs['Vector'])
    rr = nt.nodes.new('ShaderNodeMapRange'); rr.inputs['To Min'].default_value = rough - 0.06
    rr.inputs['To Max'].default_value = rough + 0.08; L.new(rn.outputs['Fac'], rr.inputs['Value'])
    radd = nt.nodes.new('ShaderNodeMath'); radd.operation = 'ADD'; radd.use_clamp = True
    L.new(rr.outputs[0], radd.inputs[0]); L.new(upc.outputs[0], radd.inputs[1])
    L.new(radd.outputs[0], bs.inputs['Roughness'])
    # moulded speckle grain
    ng = nt.nodes.new('ShaderNodeTexNoise'); ng.inputs['Scale'].default_value = 2600
    ng.inputs['Detail'].default_value = 2.0; L.new(tc.outputs['Object'], ng.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.12 * grain
    bump.inputs['Distance'].default_value = 0.0004
    L.new(ng.outputs['Fac'], bump.inputs['Height']); L.new(bump.outputs[0], bs.inputs['Normal'])
    bs.inputs['Specular IOR Level'].default_value = 0.5
    return m

def simple(name, rgb, rough, metal=0.0, emit=None, strength=0.0):
    m = bpy.data.materials.new(name); nt, bs = nodes_of(m)
    bs.inputs['Base Color'].default_value = (*rgb, 1)
    bs.inputs['Roughness'].default_value = rough; bs.inputs['Metallic'].default_value = metal
    if emit:
        bs.inputs['Emission Color'].default_value = (*emit, 1)
        bs.inputs['Emission Strength'].default_value = strength
    return m

def image_mat(name, path, rough, emit_strength=0.0, base_rgb=None):
    m = bpy.data.materials.new(name); nt, bs = nodes_of(m)
    img = bpy.data.images.load(path); tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
    uv = nt.nodes.new('ShaderNodeUVMap'); uv.uv_map = 'UVMap'
    nt.links.new(uv.outputs[0], tex.inputs[0])
    if base_rgb:
        bs.inputs['Base Color'].default_value = (*base_rgb, 1)
    else:
        nt.links.new(tex.outputs[0], bs.inputs['Base Color'])
    bs.inputs['Roughness'].default_value = rough
    if emit_strength:
        nt.links.new(tex.outputs[0], bs.inputs['Emission Color'])
        bs.inputs['Emission Strength'].default_value = emit_strength
    return m

BEIGE = (0.60, 0.515, 0.365)     # linear; reads as the classic warm computer beige
MATS = {
    'body': plastic('Halcyon_Plastic', BEIGE, 0.46),
    'trim': plastic('Halcyon_Trim', (0.53, 0.45, 0.32), 0.42),
    'label': plastic('Halcyon_Label', (0.74, 0.72, 0.66), 0.55, grain=0.3, grime=0.3),
    'dark': plastic('Halcyon_DarkPlastic', (0.028, 0.027, 0.026), 0.55, grain=0.6, grime=0.2, yellow=0.0),
    'rca_yellow': plastic('Halcyon_RCAYellow', (0.75, 0.55, 0.03), 0.4, grain=0.2, grime=0.2, yellow=0),
    'rca_white': plastic('Halcyon_RCAWhite', (0.7, 0.7, 0.68), 0.4, grain=0.2, grime=0.2, yellow=0),
    'metal': simple('Halcyon_Metal', (0.62, 0.6, 0.56), 0.32, metal=1.0),
    'led': simple('Halcyon_LED', (0.05, 0.5, 0.08), 0.2, emit=(0.15, 1.0, 0.2), strength=6.0),
    'badge': image_mat('Halcyon_Badge', os.path.join(TEX, 'halcyon_badge.png'), 0.3),
}
# CRT: dark glossy glass; until the game draws on it, a dim placeholder BBS screen glows through
crt = image_mat('CRT_Screen', os.path.join(TEX, 'crt_placeholder.png'), 0.06, emit_strength=1.6,
                base_rgb=(0.012, 0.014, 0.014))
crt.node_tree.nodes['Principled BSDF'].inputs['Coat Weight'].default_value = 1.0
crt.node_tree.nodes['Principled BSDF'].inputs['Coat Roughness'].default_value = 0.03
MATS['screen'] = crt

old = [m.name.replace(' (one side)', '') for m in me.materials]
final = []
for g in ['body', 'trim', 'label', 'dark', 'rca_yellow', 'rca_white', 'metal', 'led', 'badge', 'screen']:
    final.append(MATS[g])
index = {}
for i, n in enumerate(old):
    g = GROUP.get(n)
    if g is None:
        print('UNMAPPED material', n, '-> body'); g = 'body'
    index[i] = [m.name for m in final].index(MATS[g].name)
raw = [m.name for m in me.materials]
one = [raw[p.material_index].endswith(' (one side)') for p in me.polygons]
mi = [index[p.material_index] for p in me.polygons]
me.materials.clear()
twins = []
for m in final:
    m.use_backface_culling = False
    me.materials.append(m)
for m in final:                      # culled twin for faces SketchUp painted per side
    t = m.copy(); t.name = m.name + ' 1side'; t.use_backface_culling = True
    me.materials.append(t); twins.append(t)
NF = len(final)
for p, i, o in zip(me.polygons, mi, one):
    p.material_index = i + (NF if o else 0)
print('one-sided faces', sum(one), 'of', len(one))
# weld the converter's loose triangles back into surfaces (keeps hard edges)
# per material slot, so SketchUp's back-to-back face pairs (different slots) never merge
bpy.ops.object.mode_set(mode='EDIT')
for slot in range(len(me.materials)):
    bpy.ops.mesh.select_all(action='DESELECT')
    mon.active_material_index = slot
    bpy.ops.object.material_slot_select()
    bpy.ops.mesh.split()
    bpy.ops.mesh.remove_doubles(threshold=0.00003, use_sharp_edge_from_normals=True)
bpy.ops.object.mode_set(mode='OBJECT')
# fresh normals: smooth across gentle curves, hard at real edges
bpy.ops.mesh.customdata_custom_splitnormals_clear()
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30), keep_sharp_edges=False)
print('after weld verts', len(me.vertices), 'faces', len(me.polygons))

# screen UVs: normalise the tube face's own UVs to 0..1 (Godot puts its picture there)
uvl = me.uv_layers['UVMap'] if 'UVMap' in me.uv_layers else me.uv_layers[0]
uvl.name = 'UVMap'
scr = [m.name for m in final].index('CRT_Screen')
loops = [li for p in me.polygons if p.material_index in (scr, scr + NF) for li in p.loop_indices]
us = [uvl.data[i].uv[0] for i in loops]; vs = [uvl.data[i].uv[1] for i in loops]
print('screen uv range', min(us), max(us), min(vs), max(vs))
# rebuild from geometry instead (planar from the front: x across, z up) - always clean
xs = [me.vertices[me.loops[i].vertex_index].co.x for i in loops]
zs = [me.vertices[me.loops[i].vertex_index].co.z for i in loops]
x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
for i in loops:
    co = me.vertices[me.loops[i].vertex_index].co
    uvl.data[i].uv = ((co.x - x0) / (x1 - x0), (co.z - z0) / (z1 - z0))
print('screen size cm', round((x1 - x0) * 100, 1), round((z1 - z0) * 100, 1))
# (normals: the converter's smoothing comes through the glTF as custom normals - kept as is)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'halcyon_1084_procedural.blend'))
print('PROCEDURAL SAVED')
