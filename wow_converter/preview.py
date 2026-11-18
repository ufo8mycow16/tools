"""blender -b --python preview.py -- out.png a.glb [b.glb ...]   side-by-side Eevee render, same camera"""
import bpy, sys, math, mathutils
argv = sys.argv[sys.argv.index('--') + 1:]; out, files = argv[0], argv[1:]
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
objs = []
for i, f in enumerate(files):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f)
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']; objs.append(new)
# size / spacing
def bbox(ob_list):
    pts = [o.matrix_world @ mathutils.Vector(c) for o in ob_list for c in o.bound_box]
    mn = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); mx = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
    return mn, mx
mn, mx = bbox(objs[0]); size = (mx - mn).length; ctr = (mn + mx) / 2
gap = size * 1.05
for i, ol in enumerate(objs):
    for o in ol: o.location.x += i * gap - ctr.x; o.location.y -= ctr.y; o.location.z -= ctr.z
n = len(objs)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = gap * n * 1.0
mid = mathutils.Vector(((n - 1) * gap / 2, 0, 0))
d = mathutils.Vector((0.35, -1.0, 0.45)).normalized() * size * 4
cam.location = mid + d; cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler()
for rot, e in [((0.9, 0.2, -0.6), 3.0), ((1.2, 0, 2.4), 1.2)]:
    l = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); l.data.energy = e; l.rotation_euler = rot; sc.collection.objects.link(l)
sc.world = bpy.data.worlds.new('w'); sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs[0].default_value = (0.08, 0.08, 0.09, 1); sc.world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
sc.render.engine = 'BLENDER_EEVEE_NEXT'; sc.render.resolution_x = 900 * n; sc.render.resolution_y = 900
sc.render.film_transparent = False; sc.view_settings.view_transform = 'Standard'
sc.render.filepath = out; bpy.ops.render.render(write_still=True)
