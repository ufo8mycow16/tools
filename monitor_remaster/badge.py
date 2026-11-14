from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
W,H=1890,360; S=2
w,h=W*S,H*S
img=Image.new('RGB',(w,h),(206,204,198))
# brushed silver plate
rng=np.random.default_rng(3)
a=np.array(img).astype(float)
streak=rng.normal(0,1,(1,w)).repeat(h,0)
streak=np.array(Image.fromarray(((streak*0.5+0.5).clip(0,1)*255).astype('uint8')).filter(ImageFilter.GaussianBlur(1.5))).astype(float)/255-0.5
a+= streak[...,None]*14
grad=np.linspace(10,-10,h)[:,None,None]; a+=grad
img=Image.fromarray(a.clip(0,255).astype('uint8'))
d=ImageDraw.Draw(img)
# emblem: striped setting sun in a rounded square
OFF=265
cx,cy,r=(190+OFF)*S,180*S,130*S
sun=Image.new('L',(w,h),0); sd=ImageDraw.Draw(sun); sd.ellipse([cx-r,cy-r,cx+r,cy+r],fill=255)
# cut horizontal stripes in the lower half, getting thicker downward
y=cy+6*S; gap=6*S; band=10*S
while y<cy+r:
    sd.rectangle([cx-r,y,cx+r,y+gap],fill=0); y+=gap+band; band=max(4*S,band-2*S); gap+=3*S
sd.rectangle([cx-r,cy+r-6*S,cx+r,cy+r],fill=0)
col=np.zeros((h,w,3)); t=np.clip((np.arange(h)-(cy-r))/(2*r),0,1)[:,None]
top=np.array([248,186,48]); bot=np.array([214,52,52])
col[:]=(top*(1-t)+bot*t)[:, :, ] if False else (top[None,None,:]*(1-t[...,None])+bot[None,None,:]*t[...,None])
img.paste(Image.fromarray(col.astype('uint8')),(0,0),sun)
d=ImageDraw.Draw(img)
ink=(34,40,52)
f=ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-ExtraBoldItalic.otf',190*S)
d.text(((380+OFF)*S,-14*S),"Halcyon",font=f,fill=ink)
tw=d.textlength("Halcyon",font=f)
x0=(380+OFF)*S; x1=x0+tw+40*S
for i,c in enumerate([(214,52,52),(236,120,50),(248,186,48)]):
    yy=(232+i*12)*S; d.rectangle([x0+i*30*S,yy,x1+i*30*S,yy+6*S],fill=c)
f2=ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-SemiBold.otf',74*S)
d.text((x0+6*S,268*S),"1084   COLOUR MONITOR",font=f2,fill=ink)
img=img.resize((W,H),Image.LANCZOS)
img.save('tex/halcyon_badge.png')
