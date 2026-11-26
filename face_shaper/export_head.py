"""Face Shaper data export: a Daz G8 head (from its game FBX), its pictures, chosen face sliders, and a lined-up photo.
usage: python3 export_head.py <fbx> <basis.npy> <basis.json> <sliders.json> <photo> <photo_marks.json> <outdir>"""
import sys, json, struct, numpy as np
sys.path[:0]=['/home/claude/vulcan-fury/tools/crew','/home/claude/vulcan-fury/tools/crew/likeness']
from rtex import load_fbx, meshes, geodata, videos
from PIL import Image
fbx, bpath, bnpath, spath, photo, pmarks, out = sys.argv[1:8]
by,to=load_fbx(fbx); ms=meshes(by,to); vid=videos(by)
g,mats,texs=ms['Genesis8Male.Shape']; V,T,UV,TUV,TM=geodata(g)
top=V[:,1].max(); neck=top-31
groups=[('skin',['Face','Lips','Ears','EyeSocket'],'face.jpg','1head'),('neck',['Torso'],'torso.jpg','1torso'),
        ('eyes',['Irises','Sclera','Pupils'],'eyes.jpg','eyes1')]
corner_v=[]; corner_uv=[]; grp_tris=[]
for gi,(name,ml,fn,tex) in enumerate(groups):
    mids=[mats.index(m) for m in ml]
    sel=np.where(np.isin(TM,mids))[0]
    sel=[t for t in sel if V[T[t],1].min()>neck]
    grp_tris.append((gi,sel))
# unique (vert, uv) pairs
key={}; pv=[]; puv=[]; idx=[]; gstart=[]
for gi,sel in grp_tris:
    gstart.append(len(idx))
    for t in sel:
        for j in range(3):
            v=int(T[t][j]); u=UV[TUV[t][j]]%1.0; k=(v,round(float(u[0]),5),round(float(u[1]),5),gi)
            if k not in key: key[k]=len(pv); pv.append(v); puv.append(u)
            idx.append(key[k])
gstart.append(len(idx))
pv=np.array(pv); used=np.unique(pv); remap={v:i for i,v in enumerate(used)}
orig=np.array([remap[v] for v in pv],np.uint16)       # render vert -> topology vert
P=V[used].astype(np.float32); UVa=np.array(puv,np.float32); I=np.array(idx,np.uint32)
print('topology verts',len(used),'render verts',len(pv),'tris',len(I)//3)
# hair (does not follow sliders)
hg,hm,ht=ms['Z CABELO menor_6746.Shape']; HV,HT,HUV,HTUV,HTM=geodata(hg)
hm_=HV[HT][:,:,1].min(1)>top-30; HT2=HT[hm_]; HTUV2=HTUV[hm_]
hp=HV[HT2].reshape(-1,3).astype(np.float32); huv=(HUV[HTUV2].reshape(-1,2)%1.0).astype(np.float32)
# sliders
names=json.load(open(bnpath)); B=np.load(bpath,mmap_mode='r'); spec=json.load(open(spath))
mblob=bytearray(); mmeta=[]
for grp in spec:
    for s in grp['sliders']:
        d=np.asarray(B[names.index(s['id'])])[used].astype(np.float32)
        nz=np.where(np.abs(d).max(1)>2e-4)[0]
        sc=float(np.abs(d[nz]).max()/32000) if len(nz) else 1e-6
        q=np.round(d[nz]/sc).astype(np.int16)
        mmeta.append(dict(id=s['id'],label=s['label'],group=grp['group'],min=s.get('min',-1),max=s.get('max',1),
                          tip=s.get('tip',''),flip=s.get('flip',False),off=len(mblob),n=int(len(nz)),scale=sc))
        mblob+=nz.astype(np.uint16).tobytes()+q.tobytes()
        if len(mblob)%4: mblob+=b'\0'*(4-len(mblob)%4)
open(f'{out}/morphs.bin','wb').write(mblob)
def lay(arrs):
    b=bytearray(); meta={}
    for k,a in arrs:
        meta[k]=dict(off=len(b),n=int(a.size),dtype=str(a.dtype)); b+=a.tobytes()
        if len(b)%4: b+=b'\0'*(4-len(b)%4)
    return b,meta
hb,hmeta=lay([('pos',P.ravel()),('uv',UVa.ravel()),('index',I),('orig',orig),('hair_pos',hp.ravel()),('hair_uv',huv.ravel())])
open(f'{out}/head.bin','wb').write(hb)
def save(arr,fn,size,rgba=None):
    a=(np.clip(arr,0,1)*255).astype(np.uint8); im=Image.fromarray(a)
    if rgba is not None: im.putalpha(Image.fromarray((np.clip(rgba,0,1)*255).astype(np.uint8)).convert('L')); im=im.resize((size,size),Image.LANCZOS); im.save(f'{out}/{fn}'); return
    im.resize((size,size),Image.LANCZOS).save(f'{out}/{fn}',quality=90)
import os
FT=os.environ.get('FACE_TEX')
save(np.asarray(Image.open(FT).convert('RGB'),np.float32)/255 if FT else vid['1head'],'face.jpg',2048)
save(vid['1torso'],'torso.jpg',1024); save(vid['eyes1'],'eyes.jpg',1024)
save(vid['texture_actor_chekov_tos_skin_diffuseout'],'hair.png',1024,rgba=vid['texture_actor_chekov_tos_skin_diffuseout alpha'][...,0])
# photo lined up to the model's front view by the eye corners: write it covering a model-space rectangle
pm=json.load(open(pmarks)); vm=json.load(open('/home/claude/chekov/work/vmap.json'))
A=np.array([V[vm[k],0]+1j*V[vm[k],1] for k in pm]); Bp=np.array([pm[k][0]-1j*pm[k][1] for k in pm])  # photo y down -> up
am,bm=A.mean(),Bp.mean(); z=np.sum((Bp-bm)*np.conj(A-am))/np.sum(abs(A-am)**2); t=bm-z*am
res=np.abs(z*A+t-Bp); print('photo fit residual px',res.round(1))
r=30.0; x0,x1=-15.0,15.0; cy=float(V[vm['L_out'],1]); y0,y1=cy-20,cy+16
Wd,Hd=int((x1-x0)*r),int((y1-y0)*r)
# output (u,v) -> model (x0+u/r, y1-v/r) -> photo complex p = z*m + t (y up) -> photo px (Re, -Im)
k=z/r; e=z*(x0+1j*y1)+t
# p = e + k*(u - i v): px = Re(e)+kr*u + ki*v ; py = -(Im(e)+ki*u - kr*v)
coef=(k.real, k.imag, e.real, -k.imag, k.real, -e.imag)
ph=Image.open(photo).convert('RGB').transform((Wd,Hd),Image.AFFINE,coef,resample=Image.BICUBIC,fillcolor=(128,128,128))
ph.save(f'{out}/photo.jpg',quality=90)
meta=dict(head=hmeta,groups=[dict(name=n,start=gstart[i],count=gstart[i+1]-gstart[i],tex=fn) for i,(n,ml,fn,tx) in enumerate(groups)],
          sliders=mmeta,photo=dict(x0=x0,x1=x1,y0=y0,y1=y1),centre=[0.0,float(cy-4),float(V[used,2].mean())])
json.dump(meta,open(f'{out}/meta.json','w'))
print('morph bytes',len(mblob),'head bytes',len(hb))
