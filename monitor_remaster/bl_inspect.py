import bpy, mathutils
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath='/home/claude/skpconv/out/monitor_1084s.glb')
for o in bpy.data.objects:
    if o.type!='MESH': print('EMPTY',o.name, tuple(round(x,3) for x in o.matrix_world.translation)); continue
    bb=[o.matrix_world@mathutils.Vector(c) for c in o.bound_box]
    lo=[min(v[i] for v in bb) for i in range(3)]; hi=[max(v[i] for v in bb) for i in range(3)]
    mats=[m.name for m in o.data.materials]
    print(o.name, len(o.data.polygons), [round(x,3) for x in lo],[round(x,3) for x in hi], mats)
for m in bpy.data.materials:
    n=m.node_tree.nodes.get('Principled BSDF')
    tex=[x.image.name for x in m.node_tree.nodes if x.type=='TEX_IMAGE' and x.image]
    print('MAT',m.name, tuple(round(c,2) for c in n.inputs['Base Color'].default_value) if n else '', tex)
