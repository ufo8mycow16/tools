# smooth-shaded software preview: per-pixel interpolated normals, key + fill + rim light, 2x supersampled
import sys, os, numpy as np
sys.path[:0]=['/home/claude/vulcan-fury/tools/crew','/home/claude/vulcan-fury/tools/crew/likeness']
from rtex import load_fbx, meshes, geodata, videos
from common import rot
from PIL import Image
FBX=os.environ['FBX']; by,to=load_fbx(FBX); ms=meshes(by,to); vid=videos(by)
g,mats,texs=ms['Genesis8Male.Shape']; V,T,UV,TUV,TM=geodata(g)
if os.environ.get('XN'): V=np.load(os.environ['XN'])
FACE_TEX=os.environ.get('FACE_TEX')
keep=[i for i,m in enumerate(mats) if m in ('Face','Lips','Ears','Torso','Irises','Sclera','Pupils','EyeSocket','Arms')]
sel=np.isin(TM,keep); T,TUV,TM=T[sel],TUV[sel],TM[sel]
imgs={i:vid.get((texs.get(m) or [None])[0]) for i,m in enumerate(mats)}
if FACE_TEX:
    ft=np.asarray(Image.open(FACE_TEX).convert('RGB'),np.float32)/255
    for i,m in enumerate(mats):
        if m in ('Face','Lips','Ears'): imgs[i]=ft
def vnorm(P,T):
    n=np.cross(P[T[:,1]]-P[T[:,0]],P[T[:,2]]-P[T[:,0]]); N=np.zeros_like(P)
    for k in range(3): np.add.at(N,T[:,k],n)
    return N/(np.linalg.norm(N,axis=1,keepdims=True)+1e-12)
NV=vnorm(V,T)
hg,hm,ht=ms['Z CABELO menor_6746.Shape']; HV,HT,HUV,HTUV,HTM=geodata(hg)
HTEX=os.environ.get('HAIR_TEX')
himg=np.asarray(Image.open(HTEX).convert('RGB'),np.float32)/255 if HTEX else vid.get((ht.get(hm[0]) or [None])[0])
if himg is not None and himg.dtype==np.uint8: himg=himg.astype(np.float32)/255
top=V[:,1].max(); hmask=(HV[HT][:,:,1].min(1)>top-30); HT2=HT[hmask]; HTUV2=HTUV[hmask]
HN=vnorm(HV,HT2)
LIB=[]
if os.environ.get('LIBHAIR'):
    import json
    jp=os.environ['LIBHAIR']; meta=json.load(open(jp)); blob=open(jp[:-5]+'.bin','rb').read()
    get=lambda x: np.frombuffer(blob,dtype=x['dtype'],count=x['count'],offset=x['at'])
    capc=np.array([float(v) for v in os.environ.get('CAPCOL','0.30,0.20,0.11').split(',')])
    hc=np.array([float(v) for v in os.environ.get('HAIRCOL','0.42,0.27,0.13').split(',')])
    order=sorted(meta['surfaces'],key=lambda s:0 if 'scalp' in s['material'].lower() else 1)
    for sd in order:
        P=get(sd['pos']).reshape(-1,3).astype(np.float64); TT=get(sd['index']).reshape(-1,3); UVs=get(sd['uv']).reshape(-1,2)
        pic='/home/claude/vulcan-fury/assets/models/characters/hair/'+os.path.basename(sd['picture'])
        img=np.asarray(Image.open(pic).convert('RGBA'),np.float32)/255
        LIB.append((P,TT,UVs,img,capc if 'scalp' in sd['material'].lower() else hc))
def shade(n):
    key=np.array([-0.08,0.15,1.0]); key/=np.linalg.norm(key)
    fill=np.array([0.6,0.1,0.8]); fill/=np.linalg.norm(fill)
    d=np.clip(n@key,0,1); f=np.clip(n@fill,0,1)
    return 0.45+0.6*d+0.1*f
def shot(yaw,W=520,H=620,sc=22,SS=2):
    W2,H2,sc2=W*SS,H*SS,sc*SS
    R=rot(np.radians(yaw),0,0); c=np.array([0,top-11,2])
    img=np.zeros((H2,W2,3))+0.12; zb=np.full((H2,W2),-1e9)
    def raster(P,T,N,colfn,cull):
        Q=(P-c)@R.T; NQ=N@R.T; sx=Q[:,0]*sc2+W2/2; sy=-Q[:,1]*sc2+H2/2; z=Q[:,2]
        fn=np.cross(Q[T[:,1]]-Q[T[:,0]],Q[T[:,2]]-Q[T[:,0]])
        for t,(a,b,cc) in enumerate(T):
            if cull and fn[t,2]<=0: continue
            xs=np.array([sx[a],sx[b],sx[cc]]); ys=np.array([sy[a],sy[b],sy[cc]])
            x0,x1=int(max(0,np.floor(xs.min()))),int(min(W2-1,np.ceil(xs.max()))); y0,y1=int(max(0,np.floor(ys.min()))),int(min(H2-1,np.ceil(ys.max())))
            if x1<x0 or y1<y0: continue
            gx,gy=np.meshgrid(np.arange(x0,x1+1)+0.5,np.arange(y0,y1+1)+0.5)
            d=(ys[1]-ys[2])*(xs[0]-xs[2])+(xs[2]-xs[1])*(ys[0]-ys[2])
            if abs(d)<1e-12: continue
            l0=((ys[1]-ys[2])*(gx-xs[2])+(xs[2]-xs[1])*(gy-ys[2]))/d; l1=((ys[2]-ys[0])*(gx-xs[2])+(xs[0]-xs[2])*(gy-ys[2]))/d; l2=1-l0-l1
            m=(l0>=-0.001)&(l1>=-0.001)&(l2>=-0.001)
            zz=l0*z[a]+l1*z[b]+l2*z[cc]; sub=zb[y0:y1+1,x0:x1+1]; u=m&(zz>sub)
            if not u.any(): continue
            col,alpha=colfn(t,l0[u],l1[u],l2[u])
            if alpha is not None:
                k=alpha>0.4; u2=np.zeros_like(u); u2[u]=k; u=u2; col=col[k]
                if not u.any(): continue
                L0,L1,L2=l0[u],l1[u],l2[u]
            else: L0,L1,L2=l0[u],l1[u],l2[u]
            nn=L0[:,None]*NQ[a]+L1[:,None]*NQ[b]+L2[:,None]*NQ[cc]; nn/=np.linalg.norm(nn,axis=1,keepdims=True)+1e-9
            if not cull: nn=np.where(nn[:,2:3]<0,-nn,nn)
            sub[u]=zz[u]; img[y0:y1+1,x0:x1+1][u]=col*shade(nn)[:,None]
    def skin(t,a,b,cc):
        im=imgs.get(TM[t])
        if im is None: return np.tile([0.8,0.6,0.5],(len(a),1)),None
        if im.dtype==np.uint8: im=im.astype(np.float32)/255; imgs[TM[t]]=im
        uv=a[:,None]*UV[TUV[t,0]]+b[:,None]*UV[TUV[t,1]]+cc[:,None]*UV[TUV[t,2]]; uv=uv%1.0
        h,w=im.shape[:2]; return im[((1-uv[:,1])*(h-1)).astype(int),(uv[:,0]*(w-1)).astype(int)][:,:3],None
    def hair(t,a,b,cc):
        uv=a[:,None]*HUV[HTUV2[t,0]]+b[:,None]*HUV[HTUV2[t,1]]+cc[:,None]*HUV[HTUV2[t,2]]; uv=uv%1.0
        h,w=himg.shape[:2]; px=himg[((1-uv[:,1])*(h-1)).astype(int),(uv[:,0]*(w-1)).astype(int)]
        return px[:,:3],(px[:,3] if px.shape[1]>3 else None)
    raster(V,T,NV,skin,True)
    if not LIB and not os.environ.get('NOHAIR'): raster(HV,HT2,HN,hair,False)
    for (P,TT,UVs,himg2,col) in LIB:
        NN=vnorm(P,TT)
        def lh(t,a,b,cc,TT=TT,UVs=UVs,pim=himg2,col=col):
            uv=a[:,None]*UVs[TT[t,0]]+b[:,None]*UVs[TT[t,1]]+cc[:,None]*UVs[TT[t,2]]; uv=uv%1.0
            h,w=pim.shape[:2]; px=pim[((1-uv[:,1])*(h-1)).astype(int).clip(0,h-1),(uv[:,0]*(w-1)).astype(int).clip(0,w-1)]
            return px[:,:3]*col, px[:,3]
        # cap first, cards after (cards drawn back to front is skipped - depth test only)
        raster(P,TT,NN,lh,False)
    im=Image.fromarray((np.clip(img,0,1)*255).astype('uint8')); return im.resize((W,H),Image.LANCZOS)

import json
W,H,SC=1040,1240,44.0
im=shot(0,W=W,H=H,sc=SC); im.save('/tmp/ov_model.png')
vm=json.load(open('vmap.json')); c=np.array([0,top-11,2])
pts={k:[(V[i,0]-c[0])*SC+W/2, -(V[i,1]-c[1])*SC+H/2] for k,i in vm.items()}
json.dump(pts,open('/tmp/ov_pts.json','w'))
