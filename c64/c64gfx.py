from PIL import Image
PAL=[(0,0,0),(255,255,255),(129,51,56),(117,206,200),(142,60,151),(86,172,77),(46,44,155),(237,241,113),
     (142,80,41),(85,56,0),(196,108,113),(74,74,74),(123,123,123),(169,255,159),(112,109,235),(178,178,178)]
def char_mc(img,x,y,data,bg,c1,c2,col):
    """multicolour char: col<8 -> hires in colour col; col>=8 -> mc, 4th colour col&7"""
    for r in range(8):
        b=data[r]
        if col & 8:
            for i in range(4):
                v=(b>>(6-2*i))&3; c=[bg,c1,c2,col&7][v]
                for k in range(2): img.putpixel((x+i*2+k,y+r),PAL[c])
        else:
            for i in range(8):
                img.putpixel((x+i,y+r),PAL[col&15 if (b>>(7-i))&1 else bg])
def sprite(img,x,y,data,mc,col,m1,m2,bg=(30,30,30)):
    for r in range(21):
        row=data[r*3:r*3+3]; bits=row[0]<<16|row[1]<<8|row[2]
        if mc:
            for i in range(12):
                v=(bits>>(22-2*i))&3
                c=None if v==0 else PAL[[0,m1,col,m2][v]]
                for k in range(2): img.putpixel((x+i*2+k,y+r),c or bg)
        else:
            for i in range(24):
                img.putpixel((x+i,y+r),PAL[col] if (bits>>(23-i))&1 else bg)
