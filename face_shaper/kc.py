import sys, json, numpy as np
sys.path.insert(0,'/home/claude/vulcan-fury/tools/crew'); sys.path.insert(0,'/home/claude/vulcan-fury/tools/crew/likeness')
from extract_face_shapes import geometry
import common
from common import rot
K='/home/claude/vulcan-fury/assets/models/characters/Chekov_daz.fbx'
def tris_of(f, name='Genesis8Male'):
    v, pvi = geometry(f, name); out=[]; poly=[]; quads=[]
    for i in pvi:
        if i < 0:
            poly.append(~i)
            for k in range(1,len(poly)-1): out.append((poly[0],poly[k],poly[k+1]))
            quads.append(tuple(poly)); poly=[]
        else: poly.append(i)
    return v, np.array(out,np.int64), quads
V0, T, POLYS = tris_of(K)
common._tri = T
def render(P, yaw=0, pitch=0, size=(500,560), scale=19, cy=None, ids=False):
    R = rot(np.radians(yaw), np.radians(pitch), 0)
    top = P[:,1].max(); c = np.array([0, top-12.5 if cy is None else cy, 0])
    img, vid, sxy = common.render(P, R, c, scale, size, head_only_y=top-30)
    return (img, vid, sxy) if ids else img
