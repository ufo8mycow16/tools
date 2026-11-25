"""How fixed/windscreen_2x6x2_frame.npz was made (Nov 2026, for Dave's train windscreen).
LDraw draws 6567/13760 with the glass melted into the frame, 1.07-1.6 mm thick and 48 mm wide.
Dave's real glass (13756): 2 mm thick edges, 46 mm wide, 14 mm tall. So: frame 13760 minus the
library glass swept inward (1.0 mm on the front, up to 1.45 mm on the sides) plus 0.15 mm all round,
done as distance fields on a 0.1 mm grid and meshed with marching cubes. Needs scipy + scikit-image.
Steps below were run in order (build2 -> build3 -> build4 -> mesh)."""

# ===== build2.py =====
import sys, numpy as np, time
sys.path.insert(0,'/home/claude/tools/brickforge')
from ldraw_core import Library, part_to_mesh, make_printable
from ldraw_seal import Occupancy
t0=time.time()
lib=Library('/mnt/user-data/uploads/complete.zip')
fr_raw=np.load('/tmp/ws/fr.npy'); gl_raw=np.load('/tmp/ws/gl.npy')
from ldraw_core import LDU
def conv(T):
    t=np.empty_like(T); t[...,0]=T[...,0]; t[...,1]=T[...,2]; t[...,2]=-T[...,1]; return t*LDU
def offset(raw):
    p=conv(raw).reshape(-1,3); mn,mx=p.min(0),p.max(0); return np.array([(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]])
out={}
for num,raw in (('13760',fr_raw),('13756',gl_raw)):
    V,F,oe,_=part_to_mesh(lib,num)
    V,F,oe,how=make_printable(V,F,oe)
    V=V+offset(raw)   # back to shared coordinates
    print(num,len(F),oe,how)
    np.save(f'/tmp/ws/{num}_V.npy',V); np.save(f'/tmp/ws/{num}_F.npy',F)
print(time.time()-t0)

# ===== build3.py =====
import sys, numpy as np, time
sys.path.insert(0,'/home/claude/tools/brickforge')
from scipy.spatial import cKDTree
from scipy import ndimage
t0=time.time()
H=0.1
FV,FF=np.load('/tmp/ws/13760_V.npy'),np.load('/tmp/ws/13760_F.npy')
GV,GF=np.load('/tmp/ws/13756_V.npy'),np.load('/tmp/ws/13756_F.npy')
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
np.save('/tmp/ws/sF.npy',sF); np.save('/tmp/ws/sG.npy',sG); np.save('/tmp/ws/lo.npy',np.array([x[0] for x in xs]))
print('done',time.time()-t0)

# ===== build4.py =====
import sys, numpy as np, time
from scipy.spatial import cKDTree
from scipy import ndimage
t0=time.time(); H=0.1
sF=np.load('/tmp/ws/sF.npy'); sG=np.load('/tmp/ws/sG.npy'); lo=np.load('/tmp/ws/lo.npy')
GV,GF=np.load('/tmp/ws/13756_V.npy'),np.load('/tmp/ws/13756_F.npy')
shape=sF.shape
CLR=0.15
# pane faces (not top/bottom edges) and their normals
T=GV[GF]; n=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]); n/=np.linalg.norm(n,axis=1)[:,None]
keep=np.abs(n[:,2])<0.95
pts=[];nrm=[]
for t,nn in zip(T[keep],n[keep]):
    a,b,c=t; k=8
    u,v=np.meshgrid(np.linspace(0,1,k),np.linspace(0,1,k)); m=u+v<=1
    p=a+u[m,None]*(b-a)+v[m,None]*(c-a); pts.append(p); nrm.append(np.repeat(nn[None],len(p),0))
pts=np.concatenate(pts); nrm=np.concatenate(nrm)
kd=cKDTree(pts)
glass=sG<0
cand=ndimage.binary_dilation(glass,iterations=16)&(sF<0.3)   # only where frame material could be removed
idx=np.nonzero(cand); P=np.stack([lo[k]+idx[k]*H for k in range(3)],1)
_,j=kd.query(P,workers=-1); nn=nrm[j]
# inward = toward cab interior: +y for front, toward x=0 for sides
d=np.stack([-np.sign(P[:,0])*0.6,np.ones(len(P)),np.zeros(len(P))],1)
s=np.sign((nn*d).sum(1)); s[s==0]=1; nin=nn*s[:,None]
Tmax=1.0+0.45*np.abs(nin[:,0])
best=np.full(len(P),np.inf)
for t in np.arange(0,1.46,0.05):
    Q=P-t*nin
    g=ndimage.map_coordinates(sG,((Q-lo)/H).T,order=1,mode='nearest')
    g=np.where(t<=Tmax,g,np.inf)
    best=np.minimum(best,g)
pocket=np.full(shape,np.inf,np.float32); pocket[idx]=best
# S = frame minus (pocket grown by CLR)
S=sF.copy()
S[idx]=np.maximum(sF[idx],-(best-CLR))
np.save('/tmp/ws/S.npy',S)
print('removed voxels',((sF<0)&(S>=0)).sum(),'cand',len(P),time.time()-t0)
from PIL import Image
def sl(i,name):
  im=np.zeros(shape[1:]+(3,),np.uint8)+255
  im[sF[i]<0]=[180,180,255]; im[S[i]<0]=[0,0,200]; im[sG[i]<0]=[255,0,0]
  Image.fromarray(np.flipud(im.transpose(1,0,2))).resize((shape[1]*3,shape[2]*3),0).save(name)
for x,nm in [(8.0,'q_x8.png'),(22.0,'q_x22.png')]: sl(int(round((x-lo[0])/H)),'/tmp/ws/'+nm)
for z,nm in [(-12,'q_zm12.png'),(-0.6,'q_zm06.png'),(-18.8,'q_zm188.png')]:
  k=int(round((z-lo[2])/H)); im=np.zeros((shape[0],shape[1],3),np.uint8)+255
  im[sF[:,:,k]<0]=[180,180,255]; im[S[:,:,k]<0]=[0,0,200]; im[sG[:,:,k]<0]=[255,0,0]
  Image.fromarray(np.flipud(im.transpose(1,0,2))).resize((shape[0]*2,shape[1]*2),0).save('/tmp/ws/'+nm)

# ===== mesh.py =====
import sys, numpy as np
sys.path.insert(0,'/home/claude/tools/brickforge')
from skimage.measure import marching_cubes
from ldraw_core import write_stl
from ldraw_seal import open_edges
S=np.load('/tmp/ws/S.npy'); lo=np.load('/tmp/ws/lo.npy'); H=0.1
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
write_stl('/tmp/ws/13760_glass_fit.stl',v,f,'BrickForge 13760 frame fitted for real glass')
np.save('/tmp/ws/outV.npy',v); np.save('/tmp/ws/outF.npy',f)
