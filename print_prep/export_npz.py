"""Blender: dump an object as triangles (mm) + a watertight report.
blender -b file.blend --python export_npz.py -- <obj> <out.npz>"""
import bpy, bmesh, sys, numpy as np
a = sys.argv[sys.argv.index('--') + 1:]
ob = bpy.data.objects[a[0]]
bm = bmesh.new(); bm.from_mesh(ob.data)
bmesh.ops.triangulate(bm, faces=bm.faces)
bad_e = sum(1 for e in bm.edges if len(e.link_faces) != 2)
bad_v = sum(1 for v in bm.verts if not v.is_manifold)
bm.verts.ensure_lookup_table()
V = np.array([v.co[:] for v in bm.verts]); F = np.array([[v.index for v in f.verts] for f in bm.faces])
vol = bm.calc_volume(signed=True)
bm.free()
np.savez(a[1], V=V, F=F)
print('[export] tris', len(F), 'open/non-manifold edges', bad_e, 'non-manifold verts', bad_v, 'volume cm3 %.1f' % (vol / 1000), 'size mm', (V.max(0) - V.min(0)).round(1), flush=True)
