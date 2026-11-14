import bpy, math, sys, mathutils
out=sys.argv[sys.argv.index('--')+1]; src=sys.argv[sys.argv.index('--')+2]
bpy.ops.wm.read_factory_settings(use_empty=True)
if src.endswith('.blend'): bpy.ops.wm.open_mainfile(filepath=src)
else: bpy.ops.import_scene.gltf(filepath=src)
sc=bpy.context.scene
for o in [o for o in sc.objects if o.type in ('CAMERA','LIGHT')]: bpy.data.objects.remove(o)
sc.render.engine='CYCLES'; sc.cycles.samples=48; sc.cycles.device='CPU'; sc.cycles.use_denoising=True
sc.render.resolution_x=900; sc.render.resolution_y=700
w=bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True; w.node_tree.nodes['Background'].inputs[0].default_value=(0.25,0.27,0.3,1); w.node_tree.nodes['Background'].inputs[1].default_value=0.6
def light(loc,e,s=0.6):
    l=bpy.data.lights.new('l','AREA'); l.energy=e; l.size=s; o=bpy.data.objects.new('l',l); sc.collection.objects.link(o); o.location=loc
    d=mathutils.Vector((0,0.12,0.18))-o.location; o.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
light((-0.6,-0.8,0.8),60); light((0.8,-0.4,0.5),25); light((0.3,0.9,0.9),30)
c=bpy.data.cameras.new('c'); c.lens=50; co=bpy.data.objects.new('c',c); sc.collection.objects.link(co); sc.camera=co
import os
V=os.environ.get('VIEW','34')
if V=='front': co.location=(0.0,-0.95,0.2); tgt=(0,0,0.17)
elif V=='badge': co.location=(-0.18,-0.42,0.12); tgt=(-0.09,-0.18,0.07)
elif V=='back': co.location=(0.5,0.8,0.4); tgt=(0,0,0.15)
else: co.location=(-0.6,-0.85,0.45); tgt=(0,0,0.17)
d=mathutils.Vector(tgt)-co.location; co.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
sc.render.filepath=out; bpy.ops.render.render(write_still=True)
