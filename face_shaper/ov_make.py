import json, numpy as np
from PIL import Image, ImageFilter, ImageChops, ImageDraw
P=Image.open('/mnt/user-data/uploads/a0f2ab08-image.png').convert('RGB'); M=Image.open('/tmp/ov_model.png').convert('RGB')
pts=json.load(open('/tmp/ov_pts.json'))
ph={'R_out':(360,607),'R_in':(492,610),'L_in':(632,610),'L_out':(760,600)}
A=np.array([pts[k] for k in ph]); B=np.array([ph[k] for k in ph],float)
# similarity B = s R A + t, via complex least squares
a=A[:,0]+1j*A[:,1]; b=B[:,0]+1j*B[:,1]; am,bm=a.mean(),b.mean()
z=np.sum((b-bm)*np.conj(a-am))/np.sum(abs(a-am)**2); t=bm-z*am
# inverse map photo px -> model px for PIL affine
zi=1/z; ti=-t/z
coef=(zi.real,-zi.imag,ti.real, zi.imag,zi.real,ti.imag)
W=P.size; Mw=M.transform(W,Image.AFFINE,coef,resample=Image.BICUBIC,fillcolor=(30,30,30))
mask=Image.fromarray(((np.asarray(Mw).sum(2)>3*40)*255).astype('uint8'))
blend=Image.composite(Image.blend(P,Mw,0.5),P,mask)
edge=mask.filter(ImageFilter.FIND_EDGES)
# model feature lines (eyes/lips/brows) from luminance edges of the model render
fl=Mw.convert('L').filter(ImageFilter.FIND_EDGES).point(lambda v:255 if v>40 else 0)
fl=ImageChops.multiply(fl,mask.filter(ImageFilter.MinFilter(9)))
lines=P.copy(); green=Image.new('RGB',W,(0,255,80)); lines.paste(green,(0,0),ImageChops.lighter(edge,fl))
d=ImageDraw.Draw(lines)
for k,v in pts.items():
    q=z*(v[0]+1j*v[1])+t; d.ellipse([q.real-4,q.imag-4,q.real+4,q.imag+4],outline=(255,40,40),width=2)
print('scale',abs(z),'resid',np.abs(z*a+t-b).round(1))
row=Image.new('RGB',(W[0]*3+20,W[1]),'black')
for i,im in enumerate([Mw,blend,lines]): row.paste(im,(i*(W[0]+10),0))
row.resize((row.size[0]//2,row.size[1]//2),Image.LANCZOS).save('/mnt/user-data/outputs/chekov_overlay_sheet.png')
blend.save('/mnt/user-data/outputs/chekov_overlay_blend.png'); lines.save('/mnt/user-data/outputs/chekov_overlay_lines.png')
