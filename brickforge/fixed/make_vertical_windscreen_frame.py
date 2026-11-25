"""How fixed/windscreen_2x6x2_vertical_frame.npz was made (Nov 2026, Dave's train windscreen 17454).
LDraw 17454 frame + 17457 glass match Dave's real glass (46.7 x 14.5 mm, 2 mm sides) but are drawn touching
with zero gap (even 5.7 mm3 overlapping), so the printed frame was too tight. Fix: frame minus the glass
grown by 0.2 mm, via distance fields on a 0.1 mm grid + marching cubes (scipy, scikit-image).
Run in order: prep -> sdf -> cut -> mesh."""

# ===== v2_prep.py =====
import sys, numpy as np
sys.path.insert(0,'/home/claude/tools/brickforge')
from ldraw_core import Library, Flattener, part_to_mesh, make_printable, LDU
lib=Library('/mnt/user-data/uploads/complete.zip'); fl=Flattener(lib)
def conv(T):
    t=np.empty_like(T); t[...,0]=T[...,0]; t[...,1]=T[...,2]; t[...,2]=-T[...,1]; return t*LDU
for num in ('17454','17457'):
    raw=conv(fl.flatten(num+'.dat')).reshape(-1,3); mn,mx=raw.min(0),raw.max(0)
    off=np.array([(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]])
    V,F,oe,_=part_to_mesh(lib,num); V2,F2,oe2,how=make_printable(V,F,oe)
    print(num,len(F),oe,'->',len(F2),oe2,how)
    np.save(f'/tmp/ws/{num}_V.npy',V2+off); np.save(f'/tmp/ws/{num}_F.npy',F2)
    np.save(f'/tmp/ws/{num}_Vraw.npy',V+off); np.save(f'/tmp/ws/{num}_Fraw.npy',F)

# ===== v2_sdf.py =====
import sys, numpy as np, time
sys.path.insert(0,'/home/claude/tools/brickforge')
from scipy.spatial import cKDTree
from scipy import ndimage
t0=time.time()
H=0.1
FV,FF=np.load('/tmp/ws/17454_V.npy'),np.load('/tmp/ws/17454_F.npy')
GV,GF=np.load('/tmp/ws/17457_Vraw.npy'),np.load('/tmp/ws/17457_Fraw.npy')
lo=np.minimum(FV.min(0),GV.min(0))-0.6; hi=np.maximum(FV.max(0),GV.max(0))+0.6
xs=[np.arange(lo[i],hi[i]+H,H)+[1.3e-4,2.9e-4,0.7e-4][i] for i in range(3)]
shape=tuple(len(a) for a in xs); print(shape,flush=True)
def parity(V,F,ax):
    o=[k for k in range(3) if k!=ax]+[ax]          # u,w,axis
    sh=tuple(shape[k] for k in o); X,Y,Z=(xs[k] for k in o)
    cnt=np.zeros(sh,np.int16)
    for t in V[F][:,:,o]:
        p=t[:,:2]; d=(p[1,0]-p[0,0])*(p[2,1]-p[0,1])-(p[2,0]-p[0,0])*(p[1,1]-p[0,1])
        if abs(d)<1e-12: continue
        i0=max(0,int(np.ceil((p[:,0].min()-X[0])/H))); i1=min(sh[0]-1,int(np.floor((p[:,0].max()-X[0])/H)))
        j0=max(0,int(np.ceil((p[:,1].min()-Y[0])/H))); j1=min(sh[1]-1,int(np.floor((p[:,1].max()-Y[0])/H)))
        if i1<i0 or j1<j0: continue
        gx,gy=np.meshgrid(X[i0:i1+1],Y[j0:j1+1],indexing='ij')
        px=gx-p[0,0]; py=gy-p[0,1]
        b1=(px*(p[2,1]-p[0,1])-(p[2,0]-p[0,0])*py)/d
        b2=((p[1,0]-p[0,0])*py-px*(p[1,1]-p[0,1]))/d
        m=(b1>=0)&(b2>=0)&(b1+b2<=1)
        if not m.any(): continue
        z=t[0,2]+b1*(t[1,2]-t[0,2])+b2*(t[2,2]-t[0,2])
        ii,jj=np.nonzero(m); k=np.ceil((z[m]-Z[0])/H).astype(int); ok=(k>=0)&(k<sh[2])
        # orientation sign flips with axis permutation parity
        np.add.at(cnt,(ii[ok]+i0,jj[ok]+j0,k[ok]),-int(np.sign(d)))
    w=np.cumsum(cnt,axis=2)!=0
    inv=np.argsort(o); return w.transpose(inv)
def inside(V,F):
    a=[parity(V,F,ax) for ax in range(3)]
    return (a[0].astype(int)+a[1]+a[2])>=2, a
def samples(V,F,step=0.04):
    out=[]
    for t in V[F]:
        a,b,c=t; e1=b-a; e2=c-a
        n=int(max(np.linalg.norm(e1),np.linalg.norm(e2),np.linalg.norm(c-b))/step)+2
        u,v=np.meshgrid(np.linspace(0,1,n),np.linspace(0,1,n)); m=u+v<=1+1e-9
        out.append(a+u[m,None]*e1+v[m,None]*e2)
    return np.concatenate(out)
def sdf(V,F,band,name):
    ins,parts=inside(V,F)
    agree=[(p==ins).mean() for p in parts]; print(name,'inside vol',ins.sum()*H**3,'axis agreement',agree,time.time()-t0,flush=True)
    ed=np.where(ins,ndimage.distance_transform_edt(ins),ndimage.distance_transform_edt(~ins))*H
    bandm=ed<=band
    idx=np.nonzero(bandm)
    Q=np.stack([xs[k][idx[k]] for k in range(3)],1)
    kd=cKDTree(samples(V,F)); d,_=kd.query(Q,workers=-1)
    s=np.full(shape,band+H,np.float32); s=np.where(ins,-s,s)
    s[idx]=np.where(ins[idx],-d,d)
    print(name,'band pts',len(Q),time.time()-t0,flush=True)
    return s
sF=sdf(FV,FF,0.8,'frame'); sG=sdf(GV,GF,1.2,'glass')
np.save('/tmp/ws/v_sF.npy',sF); np.save('/tmp/ws/v_sG.npy',sG); np.save('/tmp/ws/v_lo.npy',np.array([x[0] for x in xs]))
print('done',time.time()-t0)

# ===== cut =====
# S = np.maximum(sF, -(sG - 0.2))

# ===== mesh =====
import sys, numpy as np
sys.path.insert(0,'/home/claude/tools/brickforge')
from skimage.measure import marching_cubes
from ldraw_core import write_stl
from ldraw_seal import open_edges
S=np.load('/tmp/ws/v_S.npy'); lo=np.load('/tmp/ws/v_lo.npy'); H=0.1
S=np.pad(S,1,constant_values=5.0)
v,f,_,_=marching_cubes(S,0.0,spacing=(H,H,H))
v=v+lo-H
f=f[:,::-1]   # outward
mn,mx=v.min(0),v.max(0)
v=v-[(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]]
# check orientation via signed volume
t=v[f]; vol=np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6
if vol<0: f=f[:,::-1]; vol=-vol
print('tris',len(f),'size',v.max(0)-v.min(0),'vol',vol,'open',len(open_edges(f)))
write_stl('/tmp/ws/17454_glass_fit.stl',v,f,'BrickForge 17454 frame with room for real glass')
np.save('/tmp/ws/v_outV.npy',v); np.save('/tmp/ws/v_outF.npy',f)
