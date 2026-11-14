import bpy, mathutils
from collections import defaultdict
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath='/home/claude/skpconv/out/monitor_1084s.glb')
agg=defaultdict(lambda:[0,0.0,[9,9,9],[-9,-9,-9]])
for o in bpy.data.objects:
    if o.type!='MESH': continue
    mw=o.matrix_world
    for p in o.data.polygons:
        m=o.data.materials[p.material_index].name.replace(' (one side)','')
        c=mw@p.center; a=agg[(o.name,m)]; a[0]+=1; a[1]+=p.area
        for i in range(3): a[2][i]=min(a[2][i],c[i]); a[3][i]=max(a[3][i],c[i])
for k,v in sorted(agg.items()):
    print(k, v[0], round(v[1]*1e4,1),'cm2', [round(x,3) for x in v[2]],[round(x,3) for x in v[3]])
o=bpy.data.objects['Mesh_11']; print('glass uv', [l.name for l in o.data.uv_layers])
o=bpy.data.objects['Mesh_13']; print('bezel uv', [l.name for l in o.data.uv_layers])
