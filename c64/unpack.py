import sys
sys.path.insert(0,'.')
from cpu6502 import CPU
prg=open(sys.argv[1],'rb').read(); start=int(sys.argv[2],16)
la=prg[0]|prg[1]<<8
m=bytearray(65536); m[la:la+len(prg)-2]=prg[2:]
m[1]=0x37
c=CPU(m); c.pc=start
writes01=[]
c.on_write=lambda a,v: writes01.append((c.pc,v)) if a==1 else None
seen=set(); n=0
last_page=None
while n<60_000_000:
    pc=c.pc
    if pc>=0xA000 and (pc<0xC000 or pc>=0xE000) and m[1]&3: print('ROM call at $%04x after %d, $01=%02x'%(pc,n,m[1])); break
    pg=pc>>8
    if pg not in seen:
        seen.add(pg); print('new page $%02x00 at step %d (pc $%04x) $01=%02x'%(pg,n,pc,m[1]))
    try: c.step()
    except Exception as e: print('stop',e); break
    n+=1
print('steps',n,'pc $%04x'%c.pc, '$01 writes', [(hex(a),hex(v)) for a,v in writes01][:8])
open(sys.argv[3],'wb').write(bytes(m))
