"""BLP2 -> PIL image. Palette (with 0/1/4/8-bit alpha) done here; DXT and raw via Pillow."""
import io, struct, numpy as np
from PIL import Image
def decode(d, keep_alpha=True):
    assert d[:4] == b'BLP2', d[:4]
    enc, ad = d[8], d[9]
    w, h = struct.unpack_from('<II', d, 12)
    if enc != 1:
        im = Image.open(io.BytesIO(d)); im.load(); return im
    off = struct.unpack_from('<I', d, 20)[0]
    pal = np.frombuffer(d, '<u4', 256, 148)
    idx = np.frombuffer(d, 'u1', w*h, off)
    rgb = np.stack([(pal >> 16) & 255, (pal >> 8) & 255, pal & 255], -1)[idx].reshape(h, w, 3).astype('u1')
    if not keep_alpha or ad == 0: return Image.fromarray(rgb)
    ao = off + w*h
    if ad == 8: a = np.frombuffer(d, 'u1', w*h, ao)
    elif ad == 4: b = np.frombuffer(d, 'u1', (w*h+1)//2, ao); a = (np.stack([b & 15, b >> 4], -1).ravel()[:w*h] * 17)
    else: b = np.frombuffer(d, 'u1', (w*h+7)//8, ao); a = np.unpackbits(b, bitorder='little')[:w*h] * 255
    return Image.fromarray(np.dstack([rgb, a.reshape(h, w).astype('u1')]))
