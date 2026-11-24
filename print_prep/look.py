"""Blender: quick clay render of one object from a .blend, several angles side by side.
blender -b <file.blend> --python look.py -- <objname> <out.png> [res=600] [views=front,side,back,34] [zoom box: zmin,zmax]"""
import bpy, sys, math, mathutils
argv = sys.argv[sys.argv.index('--') + 1:]
name, outp = argv[0], argv[1]
res = int(argv[2]) if len(argv) > 2 else 600
views = (argv[3] if len(argv) > 3 else 'front,side,back,34').split(',')
zbox = [float(v) for v in argv[4].split(',')] if len(argv) > 4 else None
sc = bpy.context.scene
for o in list(sc.objects):
    if o.name != name: o.hide_render = True
ob = bpy.data.objects[name]; ob.hide_render = False
for p in ob.data.polygons: p.use_smooth = True
bb = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
lo = mathutils.Vector([min(v[i] for v in bb) for i in range(3)]); hi = mathutils.Vector([max(v[i] for v in bb) for i in range(3)])
if zbox: lo.z, hi.z = zbox
ctr = (lo + hi) / 2; size = max(hi - lo)
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'MATCAP'
sc.display.shading.studio_light = 'basic_1.exr' if 'basic_1.exr' in [l.name for l in bpy.context.preferences.studio_lights] else sc.display.shading.studio_light
sc.display.shading.color_type = 'SINGLE'; sc.display.shading.single_color = (0.85, 0.72, 0.45)
sc.display.shading.show_cavity = True; sc.display.shading.cavity_type = 'BOTH'
sc.render.resolution_x = res; sc.render.resolution_y = int(res * 1.4)
sc.render.film_transparent = False
cam_d = bpy.data.cameras.new('c'); cam_d.type = 'ORTHO'; cam_d.ortho_scale = size * 1.08
cam = bpy.data.objects.new('c', cam_d); sc.collection.objects.link(cam); sc.camera = cam
ang = {'front': (0, 0), 'side': (90, 0), 'back': (180, 0), '34': (35, 15), 'side2': (270, 0), 'top': (0, 80), 'under': (0, -80)}
import os
paths = []
for v in views:
    yaw, pitch = ang[v]
    # front = looking along +y toward -y? model faces -y (beak toward -y) -> camera at -y
    y, p = math.radians(yaw), math.radians(pitch)
    dirv = mathutils.Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
    cam.location = ctr + dirv * size * 3
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    pth = outp.replace('.png', f'_{v}.png'); sc.render.filepath = pth
    bpy.ops.render.render(write_still=True); paths.append(pth)
print('VIEWS', ';'.join(paths))
