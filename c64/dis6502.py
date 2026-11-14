import sys
OP={}
def d(op,mn,mode): OP[op]=(mn,mode)
tbl="""
00 BRK imp|01 ORA izx|05 ORA zp|06 ASL zp|08 PHP imp|09 ORA imm|0A ASL acc|0D ORA abs|0E ASL abs|10 BPL rel|11 ORA izy|15 ORA zpx|16 ASL zpx|18 CLC imp|19 ORA aby|1D ORA abx|1E ASL abx
20 JSR abs|21 AND izx|24 BIT zp|25 AND zp|26 ROL zp|28 PLP imp|29 AND imm|2A ROL acc|2C BIT abs|2D AND abs|2E ROL abs|30 BMI rel|31 AND izy|35 AND zpx|36 ROL zpx|38 SEC imp|39 AND aby|3D AND abx|3E ROL abx
40 RTI imp|41 EOR izx|45 EOR zp|46 LSR zp|48 PHA imp|49 EOR imm|4A LSR acc|4C JMP abs|4D EOR abs|4E LSR abs|50 BVC rel|51 EOR izy|55 EOR zpx|56 LSR zpx|58 CLI imp|59 EOR aby|5D EOR abx|5E LSR abx
60 RTS imp|61 ADC izx|65 ADC zp|66 ROR zp|68 PLA imp|69 ADC imm|6A ROR acc|6C JMP ind|6D ADC abs|6E ROR abs|70 BVS rel|71 ADC izy|75 ADC zpx|76 ROR zpx|78 SEI imp|79 ADC aby|7D ADC abx|7E ROR abx
81 STA izx|84 STY zp|85 STA zp|86 STX zp|88 DEY imp|8A TXA imp|8C STY abs|8D STA abs|8E STX abs|90 BCC rel|91 STA izy|94 STY zpx|95 STA zpx|96 STX zpy|98 TYA imp|99 STA aby|9A TXS imp|9D STA abx
A0 LDY imm|A1 LDA izx|A2 LDX imm|A4 LDY zp|A5 LDA zp|A6 LDX zp|A8 TAY imp|A9 LDA imm|AA TAX imp|AC LDY abs|AD LDA abs|AE LDX abs|B0 BCS rel|B1 LDA izy|B4 LDY zpx|B5 LDA zpx|B6 LDX zpy|B8 CLV imp|B9 LDA aby|BA TSX imp|BC LDY abx|BD LDA abx|BE LDX aby
C0 CPY imm|C1 CMP izx|C4 CPY zp|C5 CMP zp|C6 DEC zp|C8 INY imp|C9 CMP imm|CA DEX imp|CC CPY abs|CD CMP abs|CE DEC abs|D0 BNE rel|D1 CMP izy|D5 CMP zpx|D6 DEC zpx|D8 CLD imp|D9 CMP aby|DD CMP abx|DE DEC abx
E0 CPX imm|E1 SBC izx|E4 CPX zp|E5 SBC zp|E6 INC zp|E8 INX imp|E9 SBC imm|EA NOP imp|EC CPX abs|ED SBC abs|EE INC abs|F0 BEQ rel|F1 SBC izy|F5 SBC zpx|F6 INC zpx|F8 SED imp|F9 SBC aby|FD SBC abx|FE INC abx
"""
for item in tbl.replace('\n','|').split('|'):
    item=item.strip()
    if item: o,mn,mo=item.split(); d(int(o,16),mn,mo)
L={'imp':1,'acc':1,'imm':2,'zp':2,'zpx':2,'zpy':2,'izx':2,'izy':2,'rel':2,'abs':3,'abx':3,'aby':3,'ind':3}
def dis(m,a,n):
    out=[]
    for _ in range(n):
        op=m[a]
        if op not in OP: out.append('%04X  %02X        ???'%(a,op)); a+=1; continue
        mn,mo=OP[op]; l=L[mo]; b=m[a+1] if l>1 else 0; w=b|(m[a+2]<<8) if l>2 else 0
        arg={'imp':'','acc':'A','imm':'#$%02X'%b,'zp':'$%02X'%b,'zpx':'$%02X,X'%b,'zpy':'$%02X,Y'%b,'izx':'($%02X,X)'%b,'izy':'($%02X),Y'%b,
             'rel':'$%04X'%((a+2+(b-256 if b>127 else b))&0xffff),'abs':'$%04X'%w,'abx':'$%04X,X'%w,'aby':'$%04X,Y'%w,'ind':'($%04X)'%w}[mo]
        out.append('%04X  %-9s %s %s'%(a,' '.join('%02X'%x for x in m[a:a+l]),mn,arg)); a+=l
    return '\n'.join(out)
if __name__=='__main__':
    m=open(sys.argv[1],'rb').read(); print(dis(m,int(sys.argv[2],16),int(sys.argv[3])))
