"""SketchUp (.skp, 2021+) -> glTF binary (.glb), written for Glen's Klingon Challenge / Vulcan Fury sets.

Own implementation, based on the format notes published with skppy (docs/format, MIT):
  * ZIP container after a text header; model.dat is a nested tag-length-value stream (skp_tlv.py).
  * Vertices/edges/faces per entities block; faces are edge-use loops (first loop outer, rest holes).
  * Components / groups / images are instances (13-double transform) of definitions.
  * Materials: TLV records give id + name; colour, opacity and texture come from materials/<name>/material.xml.
  * UVs: per-face 3x3 projection from the face's attribute payload, else planar by texture size.
Output: metres, Y up (SketchUp inches, Z up), one mesh per material, textures embedded, both face sides emitted
(SketchUp faces are two-sided: front material on the front, back material - or the front's - on the back).

usage: python3 skp2glb.py in.skp out.glb
"""
import sys, os, struct, json, math, io, re, collections
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skp_tlv as T

INCH = 0.0254
SMOOTH_DEG = 40.0

def f64s(b): return struct.unpack('<%dd' % (len(b) // 8), b)
def cint(n): return T.cint(n.data) if n is not None else None


# ---------------------------------------------------------------- materials
class Mat:
    def __init__(s, name):
        s.name = name; s.rgb = (0.8, 0.8, 0.8); s.alpha = 1.0; s.tex = None; s.tex_name = None; s.sx = s.sy = 1.0

def read_materials(z, root):
    by_id = {}
    xml_by_name = {}
    for n in z.namelist():
        if n.endswith('material.xml'):
            x = ET.fromstring(z.read(n))
            m = x.find('{*}material')
            if m is None: continue
            xml_by_name[m.get('name')] = (os.path.dirname(n), m)
    lst = root.first(0x01F7, 0x30D4, 0x30D5)
    for rec in (lst.all(0x32C8) if lst else []):
        mid = T.idof(rec); nm = rec.first(0x32CC)
        name = nm.data.decode('utf-8', 'replace') if nm is not None else 'mat%d' % mid
        mt = Mat(name)
        if name in xml_by_name:
            folder, m = xml_by_name[name]
            mt.rgb = tuple(int(m.get(c, 200)) / 255.0 for c in ('colorRed', 'colorGreen', 'colorBlue'))
            if m.get('useTrans') == '1':
                mt.alpha = float(m.get('trans', 1))
            if m.get('hasTexture') == '1':
                t = m.find('{*}texture')
                if t is not None:
                    mt.sx = float(t.get('xScale', 1)) or 1.0; mt.sy = float(t.get('yScale', 1)) or 1.0
                    im = t.find('.//{*}image')
                    cands = []
                    if im is not None:
                        cands += [im.get('file_name'), os.path.basename((im.get('path') or '').replace('\\', '/'))]
                    cands.append(os.path.basename((t.get('textureFilename') or '').replace('\\', '/')))
                    names = z.namelist()
                    cands += [n[len(folder) + 1:] for n in names if n.startswith(folder + '/') and n.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'))]
                    p = next((folder + '/' + c for c in cands if c and folder + '/' + c in names), None)
                    fn = p.rsplit('/', 1)[1] if p else None
                    if p is not None:
                        mt.tex = z.read(p); mt.tex_name = fn
                        if 'type="1"' and m.get('colorizeType', '0') == '0':
                            mt.rgb = (1.0, 1.0, 1.0)     # plain texture: don't tint
        by_id[mid] = mt
    return by_id


# ---------------------------------------------------------------- geometry per definition
class Face:
    __slots__ = ('loops', 'plane', 'front', 'back', 'proj_f', 'proj_b', 'hidden', 'edges')

def proj_of(base, side):
    p = base.first(0x05DC, 0x05DD, 0x36B1) if base is not None else None
    if p is None: return None
    for d in p.all(0x36B2):
        pair = d.first(0x2710)
        if pair is None: continue
        s = pair.first(side, 0x2713)
        if s is None: continue
        en = s.first(0x2714); m = s.first(0x2715)
        if m is not None and (en is None or cint(en) != 0):
            return np.array(f64s(m.data)).reshape(3, 3)
    return None

def read_entities(ents):
    """-> (faces, instances) for one entities block (0x1388)."""
    verts = {}; edges = {}; eflag = {}
    vb = ents.first(0x1389)
    for v in (vb.all(0x09C4) if vb else []):
        p = v.first(0x09C5)
        if p is not None: verts[T.idof(v)] = np.array(f64s(p.data))
    eb = ents.first(0x138A)
    for e in (eb.all(0x0BB8) if eb else []):
        base = e.first(0x07D0); eid = T.idof(base)
        edges[eid] = (cint(e.first(0x0BB9)), cint(e.first(0x0BBA)))
        fl = base.first(0x07D3) if base else None
        eflag[eid] = cint(fl) or 0
    faces = []
    fb = ents.first(0x138B)
    for f in (fb.all(0x0DAC) if fb else []):
        base = f.first(0x07D0)
        F = Face()
        F.front = cint(base.first(0x07D1)) if base is not None else None
        F.back = cint(f.first(0x0DAF))
        fl = cint(base.first(0x07D3)) if base is not None else 0
        F.hidden = bool((fl or 0) & 1)
        pl = f.first(0x0DAD); F.plane = np.array(f64s(pl.data)) if pl is not None else None
        F.loops = []; F.edges = []
        lc = f.first(0x0DAE)
        for lr in (lc.all(0x1194) if lc else []):
            loop = []; les = []
            uses = lr.first(0x1195)
            for u in (uses.all(0x0FA0) if uses else []):
                eid = cint(u.first(0x0FA1)); rv = cint(u.first(0x0FA2))
                if eid not in edges: continue
                a, b = edges[eid]
                loop.append(b if rv else a); les.append(eid)
            if len(loop) >= 3 and all(i in verts for i in loop):
                F.loops.append([verts[i] for i in loop]); F.edges.append([(eid, eflag.get(eid, 0)) for eid in les])
        F.proj_f = proj_of(base, 0x2711); F.proj_b = proj_of(base, 0x2712)
        if F.loops: faces.append(F)
    insts = []
    def add_inst(rec):
        base = rec.first(0x07D0)
        fl = cint(base.first(0x07D3)) if base is not None else 0
        if (fl or 0) & 1: return
        tr = rec.first(0x1966); did = cint(rec.first(0x1967))
        mat = cint(base.first(0x07D1)) if base is not None else None
        insts.append((np.array(f64s(tr.data)) if tr is not None else None, did, mat))
    ib = ents.first(0x138C)
    for r in (ib.all(0x1964) if ib else []): add_inst(r)
    gb = ents.first(0x138D)
    for g in (gb.all(0x1D4C) if gb else []):
        r = g.first(0x1964)
        if r is not None: add_inst(r)
    imb = ents.first(0x1390)
    for g in (imb.all(0x1F40) if imb else []):
        r = g.first(0x1964)
        if r is not None: add_inst(r)
    return faces, insts

def xform(t13):
    """13 doubles -> 4x4 acting on column points: three axis vectors, translation, w."""
    if t13 is None: return np.eye(4)
    M = np.eye(4)
    M[:3, 0] = t13[0:3]; M[:3, 1] = t13[3:6]; M[:3, 2] = t13[6:9]; M[:3, 3] = t13[9:12]
    w = t13[12] if len(t13) > 12 and t13[12] not in (0.0,) else 1.0
    if w != 1.0: M[:3, :] /= w
    return M


# ---------------------------------------------------------------- triangulation (ear clipping, holes bridged)
def _area2(p):
    x, y = p[:, 0], p[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))

def _in_tri(p, a, b, c):
    d1 = (p[0]-b[0])*(a[1]-b[1]) - (a[0]-b[0])*(p[1]-b[1])
    d2 = (p[0]-c[0])*(b[1]-c[1]) - (b[0]-c[0])*(p[1]-c[1])
    d3 = (p[0]-a[0])*(c[1]-a[1]) - (c[0]-a[0])*(p[1]-a[1])
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0); pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)

def _seg_x(a, b, c, d):
    def o(p, q, r): return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    d1, d2, d3, d4 = o(c, d, a), o(c, d, b), o(a, b, c), o(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 * d2 < 0 and d3 * d4 < 0

def triangulate(loops2d):
    """loops2d: list of (N,2) arrays, outer first. Returns list of index triples into the concatenated points."""
    pts = []; rings = []; off = 0
    for i, l in enumerate(loops2d):
        idx = list(range(off, off + len(l))); off += len(l); pts.extend(l)
        a = _area2(np.asarray(l))
        if (i == 0) != (a > 0): idx.reverse()           # outer CCW, holes CW
        rings.append(idx)
    P = np.asarray(pts, float)
    poly = rings[0][:]
    # bridge holes, rightmost first
    holes = sorted(rings[1:], key=lambda r: -max(P[i, 0] for i in r))
    for h in holes:
        hi = max(h, key=lambda i: P[i, 0]); hp = P[hi]
        best = None; bd = 1e300
        for k, oi in enumerate(poly):
            op = P[oi]
            d = (op[0]-hp[0])**2 + (op[1]-hp[1])**2
            if d >= bd: continue
            ok = True
            for j in range(len(poly)):
                a, b = poly[j], poly[(j+1) % len(poly)]
                if oi in (a, b): continue
                if _seg_x(hp, op, P[a], P[b]): ok = False; break
            if ok:
                for j in range(len(h)):
                    a, b = h[j], h[(j+1) % len(h)]
                    if hi in (a, b): continue
                    if _seg_x(hp, op, P[a], P[b]): ok = False; break
            if ok: bd = d; best = k
        if best is None: best = min(range(len(poly)), key=lambda k: ((P[poly[k]]-hp)**2).sum())
        s = h.index(hi); hr = h[s:] + h[:s]
        poly = poly[:best+1] + hr + [hi, poly[best]] + poly[best+1:]
    tris = []
    V = poly[:]; guard = 0
    while len(V) > 3 and guard < 10 * len(poly) + 100:
        guard += 1; n = len(V); found = False
        for i in range(n):
            a, b, c = V[i-1], V[i], V[(i+1) % n]
            pa, pb, pc = P[a], P[b], P[c]
            cr = (pb[0]-pa[0])*(pc[1]-pa[1]) - (pb[1]-pa[1])*(pc[0]-pa[0])
            if cr <= 1e-12: continue
            bad = False
            for q in V:
                if q in (a, b, c): continue
                if (P[q] == pa).all() or (P[q] == pb).all() or (P[q] == pc).all(): continue
                if _in_tri(P[q], pa, pb, pc): bad = True; break
            if bad: continue
            tris.append((a, b, c)); del V[i]; found = True; break
        if not found:                                         # degenerate leftovers: fan them
            for i in range(1, len(V) - 1): tris.append((V[0], V[i], V[i+1]))
            V = []; break
    if len(V) == 3: tris.append(tuple(V))
    return P, tris


# ---------------------------------------------------------------- face -> triangles with uv/normals
def face_basis(n):
    if abs(n[2]) > 0.999999: return np.array([1., 0, 0]), np.array([0., 1, 0])
    s = np.cross([0., 0, 1], n); s /= np.linalg.norm(s); t = np.cross(n, s)
    return s, t

def uvs_for(pts, n, proj, mat):
    if mat is None or mat.tex is None:
        return np.zeros((len(pts), 2))
    s, t = face_basis(n)
    sx = pts @ s; sy = pts @ t
    if proj is not None:
        try:
            Mi = np.linalg.inv(proj)
            r = np.stack([sx, sy, np.ones_like(sx)], 1) @ Mi
            q = r[:, 2]; q[np.abs(q) < 1e-12] = 1.0
            return np.stack([r[:, 0] / (q * mat.sx), r[:, 1] / (q * mat.sy)], 1)
        except np.linalg.LinAlgError:
            pass
    a = np.abs(n)
    if a[2] >= a[0] and a[2] >= a[1]: u, v = pts[:, 0], pts[:, 1]
    elif a[0] >= a[1]: u, v = pts[:, 1], pts[:, 2]
    else: u, v = pts[:, 0], pts[:, 2]
    return np.stack([u / mat.sx, v / mat.sy], 1)


class Out:
    def __init__(s): s.buckets = collections.defaultdict(lambda: [[], [], []])   # mat -> pos, nrm, uv

def build_def_mesh(faces):
    """Triangulate a definition once (local inches). Returns list of (front_mat, back_mat, pts(N,3), tris, normal, uvf, uvb, smooth_normals)."""
    out = []
    # smoothing: vertex-normal accumulation over smooth edges with small dihedral angles
    for F in faces:
        if F.hidden: continue
        n = F.plane[:3] if F.plane is not None else None
        allp = np.concatenate([np.asarray(l) for l in F.loops])
        if n is None or np.linalg.norm(n) < 1e-9:
            n = np.cross(allp[1] - allp[0], allp[2] - allp[0])
        n = n / (np.linalg.norm(n) or 1.0)
        s, t = face_basis(n)
        loops2d = [np.stack([np.asarray(l) @ s, np.asarray(l) @ t], 1) for l in F.loops]
        try:
            P2, tris = triangulate(loops2d)
        except Exception:
            continue
        pts3 = allp
        out.append((F, pts3, tris, n))
    return out

def smooth_normals(items):
    """items from build_def_mesh -> per-face per-point normals (smoothed across flagged edges under the angle)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3), round(p[2], 3))
    # edge -> faces using it
    edge_faces = collections.defaultdict(list)
    for fi, (F, pts, tris, n) in enumerate(items):
        for les in F.edges:
            for eid, fl in les:
                if fl & 0x10 or fl & 0x08: edge_faces[eid].append(fi)
    # union faces across smooth edges within angle
    parent = list(range(len(items)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    cosmax = math.cos(math.radians(SMOOTH_DEG))
    for eid, fl in edge_faces.items():
        for a in range(len(fl)):
            for b in range(a + 1, len(fl)):
                i, j = fl[a], fl[b]
                if abs(float(np.dot(items[i][3], items[j][3]))) >= cosmax:
                    parent[find(i)] = find(j)
    acc = collections.defaultdict(lambda: np.zeros(3))
    for fi, (F, pts, tris, n) in enumerate(items):
        g = find(fi)
        if g == fi and not any(find(k) == g for k in range(fi)) and parent.count(fi) <= 1 and False: pass
        for p in pts: acc[(g, key(p))] += n
    res = []
    for fi, (F, pts, tris, n) in enumerate(items):
        g = find(fi)
        nn = []
        for p in pts:
            v = acc[(g, key(p))]; L = np.linalg.norm(v)
            vn = v / L if L > 1e-9 else n
            if float(np.dot(vn, n)) < 0.5: vn = n
            nn.append(vn)
        res.append(np.asarray(nn))
    return res


def convert(src, dst, verbose=True):
    z, root = T.load(src)
    R = root.kids[0]
    mats = read_materials(z, R)
    defs = {}
    dl = R.first(0x01F9, 0x1770, 0x1771)
    for d in (dl.all(0x157C) if dl else []):
        ents = d.first(0x1388)
        did = T.idof(d.first(0x07D0)) or (T.idof(ents.first(0x07D0)) if ents is not None else None)
        if ents is not None and did is not None: defs[did] = ents
    cache = {}
    def def_geo(did):
        if did not in cache:
            faces, insts = read_entities(defs[did])
            items = build_def_mesh(faces)
            cache[did] = (items, smooth_normals(items), insts)
        return cache[did]
    root_ents = R.first(0x01F6, 0x1388)
    faces, insts = read_entities(root_ents)
    items = build_def_mesh(faces); root_geo = (items, smooth_normals(items), insts)

    G = Gltf(mats)
    C = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], float)   # Z up -> Y up
    Ci = np.linalg.inv(C)
    mesh_cache = {}

    def side_list(F, inh):
        """SketchUp's paint rules -> [(material, is_back, projection)]: one two-sided face, or two one-sided faces."""
        f = F.front if F.front in mats else None
        b = F.back if F.back in mats else None
        if f is not None and b is not None and f != b:
            return [(f, False, F.proj_f, False), (b, True, F.proj_b, False)]
        if f is not None: return [(f, False, F.proj_f if F.proj_f is not None else F.proj_b, True)]
        if b is not None: return [(b, False, F.proj_b if F.proj_b is not None else F.proj_f, True)]
        e = inh if inh in mats else -1
        return [(e, False, F.proj_f if F.proj_f is not None else F.proj_b, True)]

    def mesh_for(geo, inh, key):
        """One glTF mesh for a definition's own faces (local inches), per inherited material."""
        if key in mesh_cache: return mesh_cache[key]
        items, norms, _ = geo
        prims = collections.defaultdict(lambda: [[], [], []])
        for (F, pts, tris, n), nn in zip(items, norms):
            for mid, back, proj, two in side_list(F, inh):
                mat = mats.get(mid)
                uv = uvs_for(pts, n, proj, mat)
                pb = prims[(mid, two)]
                for (i, j, k) in tris:
                    for q in ((i, k, j) if back else (i, j, k)):
                        pb[0].append(pts[q]); pb[1].append(-nn[q] if back else nn[q]); pb[2].append(uv[q])
                G.stats += len(tris)
        mesh_cache[key] = G.add_mesh(prims, C) if prims else None
        return mesh_cache[key]

    def node_for(geo, inh, key, depth):
        node = {}
        m = mesh_for(geo, inh, key)
        if m is not None: node["mesh"] = m
        kids = []
        for t13, did, imat in geo[2]:
            if did not in defs or depth > 24: continue
            ii = imat if imat in mats else inh
            child = node_for(def_geo(did), ii, (did, ii), depth + 1)
            if child is None: continue
            M = C @ xform(t13) @ Ci
            M[:3, 3] *= INCH
            G.nodes[child]["matrix"] = [float(x) for x in M.T.ravel()]
            kids.append(child)
        if kids: node["children"] = kids
        if "mesh" not in node and not kids: return None
        G.nodes.append(node); return len(G.nodes) - 1

    top = node_for(root_geo, None, ('root', None), 0)
    G.write(dst, [top] if top is not None else [])
    if verbose:
        print(f"{os.path.basename(src)}: {G.stats} unique triangles, {len(G.meshes)} meshes, {len(G.nodes)} nodes, "
              f"{len(G.materials)} materials -> {dst} ({os.path.getsize(dst) / 1e6:.1f} MB)")


# ---------------------------------------------------------------- glb writer
class Gltf:
    def __init__(s, mats):
        s.mats = mats; s.bin = bytearray(); s.views = []; s.accs = []; s.meshes = []; s.materials = []
        s.images = []; s.textures = []; s.nodes = []; s.mat_index = {}; s.tex_index = {}; s.stats = 0

    def view(s, data, target=None):
        while len(s.bin) % 4: s.bin.append(0)
        off = len(s.bin); s.bin.extend(data)
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target: v["target"] = target
        s.views.append(v); return len(s.views) - 1

    def material(s, mid, two):
        key = (mid, two)
        if key in s.mat_index: return s.mat_index[key]
        mat = s.mats.get(mid)
        m = {"name": (mat.name if mat else "Default") + ("" if two else " (one side)"), "doubleSided": bool(two),
             "pbrMetallicRoughness": {"baseColorFactor": [*(mat.rgb if mat else (0.8, 0.8, 0.8)), mat.alpha if mat else 1.0],
                                      "metallicFactor": 0.0, "roughnessFactor": 0.8}}
        if mat and mat.alpha < 0.999: m["alphaMode"] = "BLEND"
        if mat and mat.tex is not None:
            if mat.name not in s.tex_index:
                mime = 'image/png' if mat.tex[:4] == b'\x89PNG' else 'image/jpeg'
                s.images.append({"bufferView": s.view(mat.tex), "mimeType": mime, "name": mat.tex_name})
                s.textures.append({"source": len(s.images) - 1, "sampler": 0}); s.tex_index[mat.name] = len(s.textures) - 1
            m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": s.tex_index[mat.name]}
        s.materials.append(m); s.mat_index[key] = len(s.materials) - 1
        return s.mat_index[key]

    def add_mesh(s, prims, C):
        out = []
        for (mid, two), (P, N, U) in prims.items():
            if not P: continue
            P = (np.asarray(P, np.float64) @ C[:3, :3].T * INCH).astype(np.float32)
            N = (np.asarray(N, np.float64) @ C[:3, :3].T).astype(np.float32)
            Uv = np.asarray(U, np.float32).copy(); Uv[:, 1] = 1.0 - Uv[:, 1]
            attrs = {}
            for key, arr, typ in (("POSITION", P, "VEC3"), ("NORMAL", N, "VEC3"), ("TEXCOORD_0", Uv, "VEC2")):
                a = {"bufferView": s.view(arr.tobytes(), 34962), "componentType": 5126, "count": len(arr), "type": typ}
                if key == "POSITION": a["min"] = P.min(0).tolist(); a["max"] = P.max(0).tolist()
                s.accs.append(a); attrs[key] = len(s.accs) - 1
            out.append({"attributes": attrs, "material": s.material(mid, two)})
        if not out: return None
        s.meshes.append({"primitives": out}); return len(s.meshes) - 1

    def write(s, dst, roots):
        gl = {"asset": {"version": "2.0", "generator": "skp2glb (Claude, for Glen)"}, "scene": 0,
              "scenes": [{"nodes": roots}], "nodes": s.nodes, "meshes": s.meshes, "materials": s.materials,
              "accessors": s.accs, "bufferViews": s.views, "buffers": [{"byteLength": len(s.bin)}]}
        if s.images: gl.update(images=s.images, textures=s.textures, samplers=[{"wrapS": 10497, "wrapT": 10497}])
        js = json.dumps(gl, separators=(',', ':')).encode(); js += b' ' * ((4 - len(js) % 4) % 4)
        while len(s.bin) % 4: s.bin.append(0)
        with open(dst, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(s.bin)))
            f.write(struct.pack('<II', len(js), 0x4E4F534A)); f.write(js)
            f.write(struct.pack('<II', len(s.bin), 0x004E4942)); f.write(s.bin)


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
