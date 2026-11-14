import sys,os
d=open(sys.argv[1],'rb').read()
SPT=[21]*17+[19]*7+[18]*6+[17]*5
def off(t,s): return (sum(SPT[:t-1])+s)*256
bam=d[off(18,0):off(18,0)+256]
print('disk name:', bytes(bam[0x90:0xa0]).replace(b'\xa0',b'').decode('latin1'), 'id', bytes(bam[0xa2:0xa4]), 'size',len(d))
t,s=18,1; files=[]
while t:
    sec=d[off(t,s):off(t,s)+256]
    for i in range(8):
        e=sec[i*32:i*32+32]
        typ=e[2]
        if typ==0: continue
        name=bytes(e[5:21]).replace(b'\xa0',b'').decode('latin1')
        ft,fs=e[3],e[4]; blocks=e[30]|e[31]<<8
        data=b''; tt,ss=ft,fs; n=0
        while tt and n<800:
            b=d[off(tt,ss):off(tt,ss)+256]
            if b[0]==0: data+=b[2:b[1]+1]; break
            data+=b[2:]; tt,ss=b[0],b[1]; n+=1
        kinds={0:'DEL',1:'SEQ',2:'PRG',3:'USR',4:'REL'}
        la=data[0]|data[1]<<8 if len(data)>1 else 0
        print(f'{blocks:4d} "{name}" {kinds.get(typ&7,typ)} bytes={len(data)} load=${la:04x}')
        files.append((name,data))
    t,s=sec[0],sec[1]
for i,(n,dt) in enumerate(files):
    safe=''.join(c if c.isalnum() else '_' for c in n) or 'noname'
    open(f'files/{i:02d}_{safe}.prg','wb').write(dt)
