import bpy, sys, math, mathutils
outp = sys.argv[sys.argv.index('--') + 1:][0]
sc = bpy.context.scene
obs = [o for o in sc.objects if o.type == 'MESH']
cols = {'silver': (0.75, 0.76, 0.8), 'gold': (0.85, 0.65, 0.25), 'class': (0.2, 0.35, 0.85), 'ivory': (0.92, 0.88, 0.78)}
x = 0
for o in obs:
    for p in o.data.polygons: p.use_smooth = True
    bb = [mathutils.Vector(c) for c in o.bound_box]; w = max(v.x for v in bb) - min(v.x for v in bb)
    o.location.x = x - min(v.x for v in bb); x += w + 6
    k = next((k for k in cols if k in o.name.lower()), 'gold'); o.color = cols[k] + (1,)
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'OBJECT'
sc.display.shading.show_cavity = True
sc.render.resolution_x = 1800; sc.render.resolution_y = 700
cd = bpy.data.cameras.new('c'); cd.type = 'ORTHO'; cd.ortho_scale = x * 1.02
cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (x / 2, -60, 70); cam.rotation_euler = (math.radians(42), 0, 0)
sc.render.filepath = outp; bpy.ops.render.render(write_still=True)
