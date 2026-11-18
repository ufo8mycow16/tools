"""Glen's WoW archive reader (my side). Reads CASC indexes/configs staged from Glen's PC,
plans byte-range reads for the PC-side fetcher, and decodes BLTE data.
Written from the format notes in WoW Model Viewer's CascLib source."""
import os, struct, zlib, glob

def load_idx(folder):
    """local .idx v2 files -> {ekey9: (archive, offset, size)}"""
    out = {}
    for fn in sorted(glob.glob(os.path.join(folder, '*.idx'))):
        d = open(fn, 'rb').read()
        hdr_len, hdr_hash = struct.unpack_from('<II', d, 0)
        ver, bucket, extra, size_len, off_len, key_len, off_bits, seg = struct.unpack_from('<HBBBBBBQ', d, 8)
        assert ver == 7 and size_len == 4 and off_len == 5 and key_len == 9, (fn, ver)
        pos = 8 + hdr_len
        pos = (pos + 15) & ~15
        ent_len, ent_hash = struct.unpack_from('<II', d, pos); pos += 8
        n = ent_len // 18
        for i in range(n):
            e = d[pos + i * 18: pos + i * 18 + 18]
            k = e[:9]
            so = int.from_bytes(e[9:14], 'big')
            arch = so >> off_bits; off = so & ((1 << off_bits) - 1)
            size = struct.unpack_from('<I', e, 14)[0]
            if k not in out:
                out[k] = (arch, off, size)
    return out

def parse_config(path):
    cfg = {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, v = line.split('=', 1); cfg[k.strip()] = v.split()
    return cfg

def blte_decode(data):
    """decode a BLTE blob (data may start with the 30-byte local header)"""
    if data[:4] != b'BLTE':
        i = data.find(b'BLTE')
        assert i >= 0, 'no BLTE magic'
        data = data[i:]
    hsize = struct.unpack_from('>I', data, 4)[0]
    if hsize == 0:
        chunks = [(len(data) - 8, None)]; pos = 8
    else:
        flags = data[8]; n = int.from_bytes(data[9:12], 'big')
        chunks = []
        for i in range(n):
            csize, dsize = struct.unpack_from('>II', data, 12 + i * 24)
            chunks.append((csize, dsize))
        pos = hsize
    out = bytearray()
    for csize, dsize in chunks:
        c = data[pos:pos + csize]; pos += csize
        mode = c[:1]
        if mode == b'N': out += c[1:]
        elif mode == b'Z': out += zlib.decompress(c[1:])
        elif mode == b'E': out += b'\0' * (dsize or 0)   # encrypted chunk: can't read, pad
        elif mode == b'F': out += blte_decode(c[1:])
        else: raise ValueError('unknown BLTE chunk mode %r' % mode)
    return bytes(out)

def parse_encoding(d):
    """encoding file -> {ckey(16): ekey(16)}"""
    assert d[:2] == b'EN', d[:2]
    ver, hck, hek, cpage_kb, epage_kb, ccount, ecount, _, espec_size = struct.unpack_from('>BBBHHIIBI', d, 2)
    pos = 22 + espec_size
    pos += ccount * 32           # page index (first key + md5)
    page = cpage_kb * 1024
    m = {}
    for p in range(ccount):
        base = pos + p * page; q = base
        while q < base + page:
            kc = d[q]
            if kc == 0: break
            q += 1 + 5                      # key count + 40-bit size
            ck = d[q:q + hck]; q += hck
            ek = d[q:q + hek]; q += hek * kc
            m[ck] = ek
    return m

def parse_root(d, locale=0x2):
    """WoW root (MFST / TSFM) -> {fileDataId: [ckey, ...]} (all variants; pick an installed one)"""
    out = {}
    pos = 0
    magic = d[:4]
    if magic in (b'TSFM', b'MFST'):
        a, b = struct.unpack_from('<II', d, 4)
        if a < 100 and b in (1, 2):           # 50893+: sig, headersize, version, total, named
            hdrsize, version = a, b; pos = hdrsize
        else:
            version = 0; pos = 12
    else:
        version = -1
    while pos < len(d):
        if version == 2:
            n, loc, cf1, cf2 = struct.unpack_from('<IIII', d, pos); cf3 = d[pos + 16]; pos += 17
            cflags = cf1 | cf2 | (cf3 << 17)
        else:
            n, cflags, loc = struct.unpack_from('<III', d, pos); pos += 12
        ids = struct.unpack_from('<%dI' % n, d, pos); pos += 4 * n
        if version >= 0:
            ckeys = [d[pos + 16 * i: pos + 16 * i + 16] for i in range(n)]; pos += 16 * n
            if not (cflags & 0x10000000): pos += 8 * n
        else:
            ckeys = [d[pos + 24 * i: pos + 24 * i + 16] for i in range(n)]; pos += 24 * n
        fid = -1
        take = (loc & locale) != 0 or loc == 0xFFFFFFFF or loc == 0
        for i in range(n):
            fid = fid + 1 + ids[i]
            if take:
                out.setdefault(fid, []).append(ckeys[i])
    return out
