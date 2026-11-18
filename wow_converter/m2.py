"""WoW M2 (MD21 chunked, Legion+) and .skin reader. Geometry, UVs, bones, textures, submeshes.
Field layouts follow WoW Model Viewer 1.1 (modelheaders.h) and wowdev.wiki."""
import struct
import numpy as np

def chunks(d):
    out = {}; p = 0
    while p + 8 <= len(d):
        tag = d[p:p+4].decode('latin1'); n = struct.unpack_from('<I', d, p+4)[0]
        out.setdefault(tag, d[p+8:p+8+n]); p += 8 + n
    return out

def arr(b, off):
    return struct.unpack_from('<II', b, off)  # count, offset

HDR_FIELDS = ['name', 'global_loops', 'sequences', 'sequence_lookups', 'bones', 'key_bone_lookup',
              'vertices']

class M2:
    def __init__(self, data):
        if data[:4] == b'MD21':
            c = chunks(data)
            self.chunks = c
            b = c['MD21']
        else:
            self.chunks = {}; b = data
        assert b[:4] == b'MD20', b[:4]
        self.b = b
        self.version = struct.unpack_from('<I', b, 4)[0]
        o = 8
        self.name_a = arr(b, o); o += 8
        self.flags = struct.unpack_from('<I', b, o)[0]; o += 4
        names = ['global_loops', 'sequences', 'sequence_lookups', 'bones', 'key_bone_lookup', 'vertices']
        self.a = {}
        for n in names: self.a[n] = arr(b, o); o += 8
        self.num_skins = struct.unpack_from('<I', b, o)[0]; o += 4
        for n in ['colors', 'textures', 'texture_weights', 'texture_transforms', 'replaceable_texture_lookup',
                  'materials', 'bone_lookup', 'texture_lookup', 'tex_unit_lookup', 'transparency_lookup',
                  'texture_transforms_lookup']:
            self.a[n] = arr(b, o); o += 8
        o += 28 + 28  # bounding box+radius, collision box+radius
        for n in ['collision_indices', 'collision_positions', 'collision_normals', 'attachments',
                  'attachment_lookup', 'events', 'lights', 'cameras', 'camera_lookup', 'ribbons', 'particles']:
            self.a[n] = arr(b, o); o += 8
        cnt, off = self.name_a
        self.name = b[off:off+cnt].split(b'\0')[0].decode('latin1')
        # chunk extras
        c = self.chunks
        self.skin_fids = list(struct.unpack('<%dI' % (len(c['SFID'])//4), c['SFID']))[:self.num_skins] if 'SFID' in c else []
        self.txids = list(struct.unpack('<%dI' % (len(c['TXID'])//4), c['TXID'])) if 'TXID' in c else []
        self.skel_fid = struct.unpack('<I', c['SKID'])[0] if 'SKID' in c else 0
        self.anim_fids = c.get('AFID', b'')
        self.bone_fids = list(struct.unpack('<%dI' % (len(c['BFID'])//4), c['BFID'])) if 'BFID' in c else []

    def verts(self):
        n, off = self.a['vertices']
        dt = np.dtype([('pos', '<f4', 3), ('bw', 'u1', 4), ('bi', 'u1', 4), ('nrm', '<f4', 3), ('uv', '<f4', 2), ('uv2', '<f4', 2)])
        return np.frombuffer(self.b, dt, n, off)

    def textures(self):
        n, off = self.a['textures']; out = []
        for i in range(n):
            ty, fl, fc, fo = struct.unpack_from('<IIII', self.b, off + 16*i)
            fname = self.b[fo:fo+fc].split(b'\0')[0].decode('latin1') if fc else ''
            fid = self.txids[i] if i < len(self.txids) else 0
            out.append(dict(type=ty, flags=fl, file=fname, fid=fid))
        return out

    def u16list(self, key):
        n, off = self.a[key]; return list(struct.unpack_from('<%dH' % n, self.b, off)) if n else []

    def materials(self):
        n, off = self.a['materials']; return [struct.unpack_from('<HH', self.b, off+4*i) for i in range(n)]

    def bones(self):
        n, off = self.a['bones']; out = []
        for i in range(n):
            o = off + 88*i
            key_id, flags, parent, submesh, crc = struct.unpack_from('<iIhHI', self.b, o)
            pivot = struct.unpack_from('<3f', self.b, o + 76)
            out.append(dict(key=key_id, flags=flags, parent=parent, pivot=pivot))
        return out


class Skin:
    def __init__(self, d):
        assert d[:4] == b'SKIN', d[:4]
        def a(o): return struct.unpack_from('<II', d, o)
        vn, vo = a(4); inn, io = a(12); bn, bo = a(20); sn, so = a(28); tn, to = a(36)
        self.vmap = np.frombuffer(d, '<u2', vn, vo).astype(np.int64)
        self.idx = np.frombuffer(d, '<u2', inn, io).astype(np.int64)
        self.subs = []
        for i in range(sn):
            sid, lvl, vs, vc, ist, ic = struct.unpack_from('<HHHHHH', d, so + 48*i)
            self.subs.append(dict(id=sid, vstart=vs + (lvl << 16), vcount=vc, istart=ist + (lvl << 16), icount=ic))
        self.batches = []
        for i in range(tn):
            f = struct.unpack_from('<BbHHHHHHHHHHH', d, to + 24*i)
            self.batches.append(dict(flags=f[0], shader=f[2], sub=f[3], geoset=f[4], color=f[5], material=f[6],
                                     layer=f[7], tcount=f[8], tcombo=f[9]))

    def faces(self, sub=None):
        """triangles as indices into the M2 vertex array"""
        subs = self.subs if sub is None else [self.subs[sub]]
        out = []
        for s in subs:
            tri = self.idx[s['istart']:s['istart'] + s['icount']]
            out.append(self.vmap[tri].reshape(-1, 3))
        return np.concatenate(out) if out else np.zeros((0, 3), int)
