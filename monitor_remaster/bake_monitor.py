"""Bake the Halcyon 1084's plastics into one texture set and export the game .glb.

blender -b --python bake_monitor.py -- <out_dir> [size]
Reads <out_dir>/halcyon_1084_procedural.blend (from build_monitor.py), writes
<out_dir>/halcyon_1084.glb + halcyon_1084_baked.blend + the baked PNGs.
One UV set in the result: plastics on the baked atlas, the badge on its own picture,
CRT_Screen spanning 0..1 across the tube face.
"""
import bpy, bmesh, sys, os

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = argv[0]
SIZE = int(argv[1]) if len(argv) > 1 else 2048
bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, 'halcyon_1084_procedural.blend'))
sc = bpy.context.scene
mon = bpy.data.objects['Halcyon1084']
me = mon.data
bpy.context.view_layer.objects.active = mon
mon.select_set(True)

PLASTIC = ['Halcyon_Plastic', 'Halcyon_Trim', 'Halcyon_Label', 'Halcyon_DarkPlastic',
           'Halcyon_RCAYellow', 'Halcyon_RCAWhite']
PLASTIC = PLASTIC + [n + ' 1side' for n in PLASTIC]
names = [m.name for m in me.materials]
pidx = {names.index(n) for n in PLASTIC if n in names}

# atlas UVs for the plastic faces only
orig = me.uv_layers['UVMap']
bake_uv = me.uv_layers.new(name='bake')
me.uv_layers.active = bake_uv
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(me)
for f in bm.faces:
    f.select = f.material_index in pidx
bmesh.update_edit_mesh(me)
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004, area_weight=0.0,
                         scale_to_bounds=True)
bpy.ops.object.mode_set(mode='OBJECT')

def new_img(name, srgb=True):
    img = bpy.data.images.new(name, SIZE, SIZE, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    return img

def target(img):
    for n in PLASTIC:
        m = bpy.data.materials.get(n)
        if not m:
            continue
        nt = m.node_tree
        t = nt.nodes.get('BAKE_TARGET') or nt.nodes.new('ShaderNodeTexImage')
        t.name = 'BAKE_TARGET'; t.image = img
        uvn = nt.nodes.get('BAKE_UV') or nt.nodes.new('ShaderNodeUVMap')
        uvn.name = 'BAKE_UV'; uvn.uv_map = 'bake'; nt.links.new(uvn.outputs[0], t.inputs[0])
        for n2 in nt.nodes:
            n2.select = False
        t.select = True; nt.nodes.active = t
    # the other materials get a throwaway target so Cycles has somewhere to write
    for m in me.materials:
        if m.name in PLASTIC:
            continue
        nt = m.node_tree
        t = nt.nodes.get('BAKE_TARGET') or nt.nodes.new('ShaderNodeTexImage')
        t.name = 'BAKE_TARGET'; t.image = bpy.data.images.get('scratch') or bpy.data.images.new('scratch', 16, 16)
        nt.nodes.active = t

sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.render.bake.margin = 12
sc.render.bake.use_selected_to_active = False
# faces that aren't plastic must not paint over the atlas: they bake into 'scratch' via their own target

results = {}
for kind, srgb, samples in (('DIFFUSE', True, 64), ('ROUGHNESS', False, 16), ('NORMAL', False, 16)):
    img = new_img('Halcyon_Body_' + kind.lower(), srgb)
    target(img)
    sc.cycles.samples = samples
    kw = {}
    if kind == 'DIFFUSE':
        sc.render.bake.use_pass_direct = False; sc.render.bake.use_pass_indirect = False
        sc.render.bake.use_pass_color = True
        kw = dict(pass_filter={'COLOR'})
    if kind == 'NORMAL':
        sc.render.bake.normal_space = 'TANGENT'
    bpy.ops.object.bake(type=kind, uv_layer='bake', **kw)
    path = os.path.join(OUT, 'halcyon_1084_body_%s.png' % {'DIFFUSE': 'color', 'ROUGHNESS': 'rough', 'NORMAL': 'normal'}[kind])
    img.filepath_raw = path; img.file_format = 'PNG'; img.save()
    results[kind] = path
    print('BAKED', kind, path)

# one body material from the bakes
body = bpy.data.materials.new('Halcyon_Body'); body.use_nodes = True; body.use_backface_culling = False
nt = body.node_tree; bs = nt.nodes['Principled BSDF']
def tex(path, cs):
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(path)
    t.image.colorspace_settings.name = cs; return t
c = tex(results['DIFFUSE'], 'sRGB'); nt.links.new(c.outputs[0], bs.inputs['Base Color'])
r = tex(results['ROUGHNESS'], 'Non-Color'); nt.links.new(r.outputs[0], bs.inputs['Roughness'])
n = tex(results['NORMAL'], 'Non-Color'); nm = nt.nodes.new('ShaderNodeNormalMap')
nt.links.new(n.outputs[0], nm.inputs['Color']); nt.links.new(nm.outputs[0], bs.inputs['Normal'])
bs.inputs['Specular IOR Level'].default_value = 0.5

# final UV set: atlas for plastics, original UVs for badge/screen/others
orig = me.uv_layers['UVMap']; bake_uv = me.uv_layers['bake']
src = [tuple(d.uv) for d in orig.data]
for p in me.polygons:
    if p.material_index not in pidx:
        for li in p.loop_indices:
            bake_uv.data[li].uv = src[li]
me.uv_layers.remove(me.uv_layers['UVMap'])
me.uv_layers['bake'].name = 'UVMap'
for m in me.materials:
    nt2 = m.node_tree
    for nd in list(nt2.nodes):
        if nd.name in ('BAKE_TARGET', 'BAKE_UV'):
            nt2.nodes.remove(nd)
        elif nd.type == 'UVMAP':
            nd.uv_map = 'UVMap'

# swap plastics for the baked body
body1 = body.copy(); body1.name = 'Halcyon_Body 1side'; body1.use_backface_culling = True
keep = [m for m in me.materials if m.name not in PLASTIC]
remap = {}
for i, m in enumerate(me.materials):
    if m.name in PLASTIC:
        remap[i] = 1 if m.name.endswith(' 1side') else 0
    else:
        remap[i] = 2 + keep.index(m)
mi = [remap[p.material_index] for p in me.polygons]
me.materials.clear(); me.materials.append(body); me.materials.append(body1)
for m in keep:
    me.materials.append(m)
for p, i in zip(me.polygons, mi):
    p.material_index = i

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'halcyon_1084_baked.blend'))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'halcyon_1084.glb'), export_format='GLB',
                          use_selection=False, export_yup=True, export_apply=True,
                          export_image_format='AUTO', export_materials='EXPORT')
print('EXPORTED')
