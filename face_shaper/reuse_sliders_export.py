import sys, json, base64, numpy as np
sys.path[:0]=['/home/claude/vulcan-fury/tools/crew','/home/claude/vulcan-fury/tools/crew/likeness']
from rtex import load_fbx, meshes, geodata, videos
from PIL import Image
CH='/home/claude/vulcan-fury/assets/models/characters/'
def head_sel(fbx):
    by,to=load_fbx(fbx); ms=meshes(by,to); vid=videos(by)
    g,mats,texs=ms['Genesis8Male.Shape']; V,T,UV,TUV,TM=geodata(g)
    top=V[:,1].max(); neck=top-31
    groups=[('skin',['Face','Lips','Ears','EyeSocket']),('neck',['Torso']),('eyes',['Irises','Sclera','Pupils'])]
    grp=[]
    for gi,(n,ml) in enumerate(groups):
        mids=[mats.index(m) for m in ml]; sel=np.where(np.isin(TM,mids))[0]
        grp.append((gi,[t for t in sel if V[T[t],1].min()>neck]))
    return V,T,UV,TUV,grp,vid
# --- Chekov's sliders back to full-vertex deltas
Vc,Tc,_,_,gc,_=head_sel(CH+'Chekov_daz.fbx')
usedc=np.unique(np.concatenate([Tc[s].ravel() for _,s in gc]))
cm=json.load(open('chekov_src/meta.json')); print('chekov used',len(usedc),'page verts',cm['head']['pos']['n']//3)
assert len(usedc)==cm['head']['pos']['n']//3
mb=base64.b64decode(open('chekov_src/morphs.txt').read())
full={}
for s in cm['sliders']:
    nz=np.frombuffer(mb,np.uint16,s['n'],s['off']); q=np.frombuffer(mb,np.int16,s['n']*3,s['off']+2*s['n']).reshape(-1,3)
    d=np.zeros((16384,3),np.float32); d[usedc[nz]]=q*s['scale']; full[s['id']]=(d,s)
# --- Kirk
V,T,UV,TUV,grp,vid=head_sel(CH+'Kirk_daz.fbx')
key={}; pv=[]; puv=[]; idx=[]; gstart=[]
for gi,sel in grp:
    gstart.append(len(idx))
    for t in sel:
        for j in range(3):
            v=int(T[t][j]); u=UV[TUV[t][j]]%1.0; k=(v,round(float(u[0]),5),round(float(u[1]),5),gi)
            if k not in key: key[k]=len(pv); pv.append(v); puv.append(u)
            idx.append(key[k])
gstart.append(len(idx))
pv=np.array(pv); used=np.unique(pv); remap={v:i for i,v in enumerate(used)}
print('kirk used',len(used),'same set as chekov:',np.array_equal(used,usedc))
orig=np.array([remap[v] for v in pv],np.uint16)
P=V[used].astype(np.float32); UVa=np.array(puv,np.float32); I=np.array(idx,np.uint32)
mblob=bytearray(); mmeta=[]
for sid,(d0,s) in full.items():
    d=d0[used]; nz=np.where(np.abs(d).max(1)>2e-4)[0]
    sc=float(np.abs(d[nz]).max()/32000) if len(nz) else 1e-6
    q=np.round(d[nz]/sc).astype(np.int16)
    m=dict(s); m.update(off=len(mblob),n=int(len(nz)),scale=sc); mmeta.append(m)
    mblob+=nz.astype(np.uint16).tobytes()+q.tobytes()
    if len(mblob)%4: mblob+=b'\0'*(4-len(mblob)%4)
def lay(arrs):
    b=bytearray(); meta={}
    for k,a in arrs:
        meta[k]=dict(off=len(b),n=int(a.size),dtype=str(a.dtype)); b+=a.tobytes()
        if len(b)%4: b+=b'\0'*(4-len(b)%4)
    return b,meta
E=np.zeros(0,np.float32)
hb,hmeta=lay([('pos',P.ravel()),('uv',UVa.ravel()),('index',I),('orig',orig),('hair_pos',E),('hair_uv',E)])
out='kirk'
open(f'{out}/head.txt','w').write(base64.b64encode(bytes(hb)).decode())
open(f'{out}/morphs.txt','w').write(base64.b64encode(bytes(mblob)).decode())
def save(a,fn,size):
    Image.fromarray((np.clip(a,0,1)*255).astype(np.uint8)).resize((size,size),Image.LANCZOS).save(f'{out}/{fn}',quality=90)
save(vid['1heada'],'face.jpg',2048); save(vid['1torso'],'torso.jpg',1024); save(vid['eyes'],'eyes.jpg',1024)
pm=json.load(open('kirk/photo_marks.json')); vm=json.load(open('/home/claude/vulcan-fury/tools/crew/kirk_build/vmap.json'))
A=np.array([V[vm[k],0]+1j*V[vm[k],1] for k in pm]); Bp=np.array([pm[k][0]-1j*pm[k][1] for k in pm])
am,bm=A.mean(),Bp.mean(); z=np.sum((Bp-bm)*np.conj(A-am))/np.sum(abs(A-am)**2); t=bm-z*am
print('photo fit residual px',np.abs(z*A+t-Bp).round(1),'scale px/cm',abs(z).round(2))
r=30.0; x0,x1=-15.0,15.0; cy=float(V[vm['L_out'],1]); y0,y1=cy-20,cy+16
Wd,Hd=int((x1-x0)*r),int((y1-y0)*r); k=z/r; e=z*(x0+1j*y1)+t
coef=(k.real,k.imag,e.real,-k.imag,k.real,-e.imag)
Image.open('kirk/photo_src.png').convert('RGB').transform((Wd,Hd),Image.AFFINE,coef,resample=Image.BICUBIC,fillcolor=(128,128,128)).save(f'{out}/photo.jpg',quality=90)
meta=dict(head=hmeta,groups=[dict(name=n,start=gstart[i],count=gstart[i+1]-gstart[i],tex=fn) for i,(n,fn) in enumerate([('skin','face.jpg'),('neck','torso.jpg'),('eyes','eyes.jpg')])],
          sliders=mmeta,photo=dict(x0=x0,x1=x1,y0=y0,y1=y1),centre=[0.0,float(cy-4),float(V[used,2].mean())])
json.dump(meta,open(f'{out}/meta.json','w')); np.save(f'{out}/used.npy',used)
print('sliders',len(mmeta))
