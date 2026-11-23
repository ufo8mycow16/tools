"""Turns an LDraw part's overlapping surfaces into one sealed, printable solid.

LDraw parts are built for display: studs sit on top of plates with open bottoms,
tubes butt against ceilings, big faces meet small ones mid-edge. This module:
  1. builds an inside/outside test for the part (counts surface crossings along
     rays, so overlapping pieces still read as solid),
  2. rebuilds every flat surface that has loose edges on it: all edges on that
     plane are split where they cross, triangulated, and each little triangle is
     kept only if it really separates inside from outside,
  3. drops curved faces buried inside the part,
  4. stitches seams where one edge meets another mid-way.
"""
import numpy as np
from collections import defaultdict

EPS = 2e-3      # mm, how far off a surface we probe inside/outside
TOL = 1e-4      # mm, "same point / on the plane" tolerance
MIN_PLANE_AREA = 1.0   # mm^2


# ------------------------------------------------------------------ inside test
class Occupancy:
    """inside(points) -> bool array. Majority vote of rays along +x, +y, +z."""

    def __init__(self, V, F, bins=64):
        self.tri = V[F]
        n = np.cross(self.tri[:, 1] - self.tri[:, 0], self.tri[:, 2] - self.tri[:, 0])
        self.n = n
        self.axes = []
        lo, hi = V.min(0) - 1, V.max(0) + 1
        self.lo, self.hi = lo, hi
        for a in range(3):
            u, w = [k for k in range(3) if k != a]
            sel = np.nonzero(np.abs(n[:, a]) > 1e-12)[0]
            T = self.tri[sel]
            # 2D bins over the (u, w) plane
            nb = bins
            cu = (hi[u] - lo[u]) / nb
            cw = (hi[w] - lo[w]) / nb
            tu0 = np.floor((T[:, :, u].min(1) - lo[u]) / cu).astype(int)
            tu1 = np.floor((T[:, :, u].max(1) - lo[u]) / cu).astype(int)
            tw0 = np.floor((T[:, :, w].min(1) - lo[w]) / cw).astype(int)
            tw1 = np.floor((T[:, :, w].max(1) - lo[w]) / cw).astype(int)
            buckets = defaultdict(list)
            for i in range(len(sel)):
                for bu in range(tu0[i], tu1[i] + 1):
                    for bw in range(tw0[i], tw1[i] + 1):
                        buckets[bu * nb + bw].append(i)
            buckets = {k: np.array(v) for k, v in buckets.items()}
            self.axes.append((a, u, w, sel, T, cu, cw, nb, buckets))

    def winding(self, Q, axis_index):
        a, u, w, sel, T, cu, cw, nb, buckets = self.axes[axis_index]
        out = np.zeros(len(Q), dtype=np.int32)
        bu = np.floor((Q[:, u] - self.lo[u]) / cu).astype(int)
        bw = np.floor((Q[:, w] - self.lo[w]) / cw).astype(int)
        key = bu * nb + bw
        order = np.argsort(key, kind="stable")
        ks = key[order]
        starts = np.nonzero(np.r_[True, ks[1:] != ks[:-1]])[0]
        ends = np.r_[starts[1:], len(ks)]
        sign_all = np.sign(self.n[sel, a]).astype(np.int32)
        for s, e in zip(starts, ends):
            tris = buckets.get(int(ks[s]))
            if tris is None:
                continue
            qi = order[s:e]
            q = Q[qi]
            t = T[tris]                                    # (m,3,3)
            # 2D barycentric of q in each triangle (u, w plane)
            x0, y0 = t[:, 0, u], t[:, 0, w]
            x1, y1 = t[:, 1, u] - x0, t[:, 1, w] - y0
            x2, y2 = t[:, 2, u] - x0, t[:, 2, w] - y0
            det = x1 * y2 - x2 * y1
            px = q[:, None, u] - x0[None]
            py = q[:, None, w] - y0[None]
            with np.errstate(divide="ignore", invalid="ignore"):
                b1 = (px * y2[None] - x2[None] * py) / det[None]
                b2 = (x1[None] * py - px * y1[None]) / det[None]
            b0 = 1 - b1 - b2
            hit = (b0 >= 0) & (b1 >= 0) & (b2 >= 0) & (det[None] != 0)
            ha = b0 * t[None, :, 0, a] + b1 * t[None, :, 1, a] + b2 * t[None, :, 2, a]
            hit &= ha > q[:, None, a]
            out[qi] = (hit * sign_all[tris][None]).sum(1)
        return out

    def inside(self, Q):
        Q = np.asarray(Q, dtype=float)
        if len(Q) == 0:
            return np.zeros(0, bool)
        # tiny fixed jitter so rays don't run exactly along edges of the LDraw grid
        J = np.array([3.1e-6, 4.7e-6, 2.3e-6])
        votes = np.zeros(len(Q), dtype=np.int32)
        for k in range(3):
            votes += (self.winding(Q + J * (k + 1), k) > 0)
        return votes >= 2


# ------------------------------------------------------------------ helpers
def open_edges(F):
    """Directed edges with no matching reverse edge (mesh holes/seams)."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = e[:, 0].astype(np.int64) * (1 << 32) + e[:, 1]
    rkey = e[:, 1].astype(np.int64) * (1 << 32) + e[:, 0]
    uk, cnt = np.unique(key, return_counts=True)
    ruk, rcnt = np.unique(rkey, return_counts=True)
    # count of reverse occurrences for each key
    pos = np.searchsorted(ruk, uk)
    pos[pos >= len(ruk)] = 0
    rc = np.where(ruk[pos] == uk, rcnt[pos], 0)
    bad = uk[cnt != rc]
    return np.stack([bad >> 32, bad & 0xFFFFFFFF], 1)


def face_normals(V, F):
    t = V[F]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return n / ln


def plane_keys(N, D):
    """Canonical (normal, offset) per face so coplanar faces share a key."""
    s = np.where(np.abs(N[:, 0]) > 1e-9, np.sign(N[:, 0]),
                 np.where(np.abs(N[:, 1]) > 1e-9, np.sign(N[:, 1]), np.sign(N[:, 2])))
    s[s == 0] = 1
    Nc = N * s[:, None]
    Dc = D * s
    k = np.round(np.c_[Nc * 1e4, Dc * 1e3]).astype(np.int64)
    return k, Nc, Dc


def basis(n):
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v


# ------------------------------------------------------------------ 2D splitting
def split_segments(P2, segs, tol=1e-6):
    """Split 2D segments where they cross or where a point lies on them.
    P2: (n,2) points, segs: (m,2) index pairs. Returns (P2_new, segs_new, new_points_info)
    where new points carry (seg_a, seg_b, t_a) so callers can build 3D positions."""
    segs = np.unique(np.sort(segs, axis=1), axis=0)
    segs = segs[segs[:, 0] != segs[:, 1]]
    m = len(segs)
    if m == 0:
        return P2, segs, []
    A, B = P2[segs[:, 0]], P2[segs[:, 1]]
    lo = np.minimum(A, B)
    hi = np.maximum(A, B)
    span = (P2.max(0) - P2.min(0)).max() + 1e-9
    nb = int(min(256, max(8, np.sqrt(m) * 2)))
    cell = span / nb
    base = P2.min(0)
    c0 = np.floor((lo - base) / cell - 1e-9).astype(int)
    c1 = np.floor((hi - base) / cell + 1e-9).astype(int)
    c0 = np.clip(c0, 0, nb)
    c1 = np.clip(c1, 0, nb)
    cells = defaultdict(list)
    for i in range(m):
        for x in range(c0[i, 0], c1[i, 0] + 1):
            for y in range(c0[i, 1], c1[i, 1] + 1):
                cells[x * (nb + 1) + y].append(i)
    pairs = set()
    for lst in cells.values():
        if len(lst) > 1:
            L = np.array(lst)
            ii, jj = np.triu_indices(len(L), 1)
            for p in zip(L[ii], L[jj]):
                pairs.add(p)
    splits = defaultdict(list)            # seg -> [(t, point_index)]
    newpts = []
    newinfo = []
    if pairs:
        pr = np.array(list(pairs))
        i, j = pr[:, 0], pr[:, 1]
        p, r = A[i], B[i] - A[i]
        q, s = A[j], B[j] - A[j]
        rxs = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
        qp = q - p
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / rxs
            u = (qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]) / rxs
        Lr = np.linalg.norm(r, axis=1)
        Ls = np.linalg.norm(s, axis=1)
        et = tol / np.maximum(Lr, 1e-12)
        eu = tol / np.maximum(Ls, 1e-12)
        cross = (np.abs(rxs) > 1e-14) & (t > et) & (t < 1 - et) & (u > eu) & (u < 1 - eu)
        # shared endpoints are not crossings
        shared = (segs[i, 0] == segs[j, 0]) | (segs[i, 0] == segs[j, 1]) | \
                 (segs[i, 1] == segs[j, 0]) | (segs[i, 1] == segs[j, 1])
        cross &= ~shared
        idx = np.nonzero(cross)[0]
        if len(idx):
            X = p[idx] + t[idx, None] * r[idx]
            key = np.round(X / (tol * 10)).astype(np.int64)
            _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
            inv = inv.reshape(-1)
            base_id = len(P2)
            for k, ix in enumerate(idx):
                pid = base_id + inv[k]
                splits[i[ix]].append((t[ix], pid))
                splits[j[ix]].append((u[ix], pid))
            for f in first:
                ix = idx[f]
                newpts.append(X[f])
                newinfo.append((segs[i[ix]], t[ix]))
    P2n = np.vstack([P2, np.array(newpts).reshape(-1, 2)]) if newpts else P2
    # points lying on segments (T-junctions), using grid of points
    for s_i in range(m):
        a, b = segs[s_i]
        pa, pb = P2n[a], P2n[b]
        d = pb - pa
        L2 = d @ d
        if L2 < 1e-20:
            continue
        cand = set()
        for x in range(c0[s_i, 0], c1[s_i, 0] + 1):
            for y in range(c0[s_i, 1], c1[s_i, 1] + 1):
                cand.update(cells.get(x * (nb + 1) + y, ()))
        pts = set()
        for o in cand:
            pts.add(segs[o, 0]); pts.add(segs[o, 1])
        pts.discard(a); pts.discard(b)
        if not pts:
            continue
        pi = np.array(list(pts))
        w = P2n[pi] - pa
        tt = (w @ d) / L2
        dist = np.abs(w[:, 0] * d[1] - w[:, 1] * d[0]) / np.sqrt(L2)
        ok = (tt > 1e-9) & (tt < 1 - 1e-9) & (dist < tol * 10)
        for k in np.nonzero(ok)[0]:
            splits[s_i].append((tt[k], pi[k]))
    out = []
    for s_i in range(m):
        a, b = segs[s_i]
        if s_i in splits:
            lst = sorted(set(splits[s_i]))
            chain = [a] + [pid for _, pid in lst] + [b]
            chain = [c for k, c in enumerate(chain) if k == 0 or c != chain[k - 1]]
            out += [(chain[k], chain[k + 1]) for k in range(len(chain) - 1)]
        else:
            out.append((a, b))
    out = np.array(out, dtype=np.int64).reshape(-1, 2)
    out = np.unique(np.sort(out, axis=1), axis=0)
    out = out[out[:, 0] != out[:, 1]]
    return P2n, out, newinfo


# ------------------------------------------------------------------ plane rebuild
def conforming_triangulation(P2, segs, max_rounds=14):
    """Delaunay triangulation that contains every segment as an edge
    (missing segments get split at their midpoint until they show up)."""
    from scipy.spatial import Delaunay
    P2 = P2.copy()
    segs = [tuple(s) for s in segs]
    for _ in range(max_rounds):
        try:
            tri = Delaunay(P2, qhull_options="Qbb Qc Qz Q12")
        except Exception:
            return P2, None
        S = tri.simplices
        e = np.concatenate([S[:, [0, 1]], S[:, [1, 2]], S[:, [2, 0]]])
        e = np.sort(e, axis=1)
        have = set(map(tuple, e))
        missing = [s for s in segs if (min(s), max(s)) not in have]
        if not missing:
            return P2, S
        newpts = []
        keep = [s for s in segs if (min(s), max(s)) in have]
        for a, b in missing:
            mid = len(P2) + len(newpts)
            newpts.append((P2[a] + P2[b]) / 2)
            keep += [(a, mid), (mid, b)]
        P2 = np.vstack([P2, newpts])
        segs = keep
    return P2, S


def rebuild_plane(V, seg_ids, n, d, occ, id_offset):
    """Returns (new_points_3d, triangles as 3D index lists into [V | new])."""
    u, v = basis(n)
    ids = np.unique(seg_ids)
    origin = n * d
    P3 = V[ids]
    P2 = np.c_[(P3 - origin) @ u, (P3 - origin) @ v]
    remap = {g: k for k, g in enumerate(ids)}
    segs = np.array([[remap[a], remap[b]] for a, b in seg_ids])
    P2, segs, _ = split_segments(P2, segs)
    P2, S = conforming_triangulation(P2, segs)
    if S is None or len(S) == 0:
        return None
    T = P2[S]
    area = (T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1]) - \
           (T[:, 2, 0] - T[:, 0, 0]) * (T[:, 1, 1] - T[:, 0, 1])
    S = S[np.abs(area) > 1e-12]
    area = area[np.abs(area) > 1e-12]
    S[area < 0] = S[area < 0][:, ::-1]           # all counter-clockwise (normal +n)
    C2 = P2[S].mean(1)
    C3 = origin + C2[:, :1] * u + C2[:, 1:] * v
    below = occ.inside(C3 - EPS * n)
    above = occ.inside(C3 + EPS * n)
    face_up = below & ~above        # solid under, air above -> face points +n
    face_dn = above & ~below
    # 3D positions of every 2D point (old ones keep their vertex ids)
    allP3 = origin + P2[:, :1] * u + P2[:, 1:] * v
    gid = np.empty(len(P2), dtype=np.int64)
    gid[:len(ids)] = ids
    nnew = len(P2) - len(ids)
    gid[len(ids):] = id_offset + np.arange(nnew)
    tris = np.vstack([gid[S[face_up]], gid[S[face_dn]][:, ::-1]])
    return allP3[len(ids):], tris


# ------------------------------------------------------------------ stitching
def weld(V, F, tol=1e-4):
    q = np.round(V / tol).astype(np.int64)
    uq, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    F = inv[F]
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    return V[first], F[ok]


def drop_duplicates(V, F):
    """Same triangle twice -> keep one; same triangle facing both ways -> drop both."""
    srt = np.sort(F, axis=1)
    i = np.argmin(F, axis=1)
    r = np.arange(len(F))
    rot = np.stack([F[r, i], F[r, (i + 1) % 3], F[r, (i + 2) % 3]], 1)
    fwd = rot[:, 1] == srt[:, 1]
    key = srt[:, 0] * (1 << 42) + srt[:, 1] * (1 << 21) + srt[:, 2]
    order = np.lexsort((~fwd, key))
    key_s, fwd_s = key[order], fwd[order]
    keep = []
    s = 0
    n = len(order)
    while s < n:
        e = s
        while e < n and key_s[e] == key_s[s]:
            e += 1
        nf = int(fwd_s[s:e].sum())
        nb = (e - s) - nf
        if nf > nb:
            keep.append(order[s])            # first forward one
        elif nb > nf:
            keep.append(order[e - 1])        # a backward one
        s = e
    return F[np.sort(np.array(keep, dtype=np.int64))] if keep else F[:0]


def fix_tjunctions(V, F, tol=1e-4, rounds=6):
    """Where a vertex sits on another triangle's open edge, split that triangle."""
    for _ in range(rounds):
        oe = open_edges(F)
        if len(oe) == 0:
            break
        cell = 1.0
        keys = np.floor(V / cell).astype(np.int64)
        grid = defaultdict(list)
        for i, k in enumerate(map(tuple, keys)):
            grid[k].append(i)
        splits = {}
        for a, b in oe:
            pa, pb = V[a], V[b]
            dv = pb - pa
            L2 = dv @ dv
            if L2 < 1e-16:
                continue
            lo = np.floor(np.minimum(pa, pb) / cell).astype(int)
            hi = np.floor(np.maximum(pa, pb) / cell).astype(int)
            if np.prod(hi - lo + 1) > 4000:
                continue
            cand = []
            for x in range(lo[0], hi[0] + 1):
                for y in range(lo[1], hi[1] + 1):
                    for z in range(lo[2], hi[2] + 1):
                        cand += grid.get((x, y, z), [])
            if not cand:
                continue
            c = np.array(cand)
            w = V[c] - pa
            t = (w @ dv) / L2
            dist = np.linalg.norm(w - np.outer(t, dv), axis=1)
            m = (t > 1e-7) & (t < 1 - 1e-7) & (dist < tol)
            if m.any():
                o = np.argsort(t[m])
                splits[(int(a), int(b))] = list(c[m][o])
        if not splits:
            break
        newF = []
        for f in F:
            for k in range(3):
                a, b, c = int(f[k]), int(f[(k + 1) % 3]), int(f[(k + 2) % 3])
                if (a, b) in splits:
                    chain = [a] + splits[(a, b)] + [b]
                    newF += [(chain[i], chain[i + 1], c) for i in range(len(chain) - 1)]
                    break
            else:
                newF.append(tuple(f))
        F = np.array(newF, dtype=np.int64)
    return F


# ------------------------------------------------------------------ main
def seal(V, F, log=None):
    """Returns (V, F, open_edge_count) for a sealed version of the mesh."""
    V = np.asarray(V, float)
    F = np.asarray(F, np.int64)
    V, F = weld(V, F)
    F = drop_duplicates(V, F)
    F = fix_tjunctions(V, F)
    occ = Occupancy(V, F)
    N = face_normals(V, F)
    D = np.einsum("ij,ij->i", N, V[F[:, 0]])
    keys, Nc, Dc = plane_keys(N, D)
    uk, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    PN, PD = Nc[first], Dc[first]
    nplanes = len(uk)
    # which planes need rebuilding: loose edges lying on them, or faces facing both ways
    oe = open_edges(F)
    need = np.zeros(nplanes, bool)
    if len(oe):
        # which face owns each loose edge, and which plane that face is on
        e_all = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        f_all = np.tile(np.arange(len(F)), 3)
        ek = e_all[:, 0].astype(np.int64) * (1 << 32) + e_all[:, 1]
        ok_ = oe[:, 0].astype(np.int64) * (1 << 32) + oe[:, 1]
        srt = np.argsort(ek)
        pos = np.searchsorted(ek[srt], ok_)
        owner_plane = inv[f_all[srt[np.clip(pos, 0, len(srt) - 1)]]]
        A, B = V[oe[:, 0]], V[oe[:, 1]]
        for s0 in range(0, nplanes, 256):
            pn, pd = PN[s0:s0 + 256], PD[s0:s0 + 256]
            on = (np.abs(A @ pn.T - pd) < TOL * 10) & (np.abs(B @ pn.T - pd) < TOL * 10)
            # only loose edges from *other* surfaces count (e.g. a stud wall resting on a plate top)
            on &= owner_plane[:, None] != (np.arange(s0, s0 + len(pn)))[None, :]
            need[s0:s0 + 256] |= on.any(0)
    facing = np.einsum("ij,ij->i", N, Nc) > 0
    both = np.zeros(nplanes, bool)
    np.logical_or.at(both, inv, facing)
    allf = np.ones(nplanes, bool)
    np.logical_and.at(allf, inv, facing)
    need |= both & ~allf
    # only flat surfaces of a decent size - small facets of curved surfaces are
    # left alone (rebuilding them can't close curved seams and just makes a mess)
    tri = V[F]
    farea = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    parea = np.zeros(nplanes)
    np.add.at(parea, inv, farea)
    need &= parea >= MIN_PLANE_AREA
    E = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1), axis=0)
    newV = [V]
    nv = len(V)
    out_tris = []
    rebuilt = np.zeros(len(F), bool)
    planes = np.nonzero(need)[0]
    for pi, p in enumerate(planes):
        n, d = PN[p], PD[p]
        onv = np.abs(V @ n - d) < TOL * 10
        segs = E[onv[E[:, 0]] & onv[E[:, 1]]]
        fsel = inv == p
        if len(segs) < 3:
            continue
        res = rebuild_plane(V, segs, n, d, occ, nv)
        if res is None:
            continue
        pts, tris = res
        # rebuild_plane numbers new points after len(Vcur)
        newV.append(pts)
        nv += len(pts)
        out_tris.append(tris)
        rebuilt |= fsel
        if log and pi % 20 == 0:
            log(f"    sealing flat surfaces {pi + 1}/{len(planes)}")
    # faces we didn't rebuild: keep only real outside surface, facing outwards
    rest = F[~rebuilt]
    if len(rest):
        Nr = N[~rebuilt]
        C = V[rest].mean(1)
        a = occ.inside(C + EPS * Nr)
        b = occ.inside(C - EPS * Nr)
        keep_fwd = b & ~a
        keep_rev = a & ~b
        rest = np.vstack([rest[keep_fwd], rest[keep_rev][:, ::-1]])
        out_tris.append(rest)
    V2 = np.vstack(newV)
    F2 = np.vstack(out_tris) if out_tris else F[:0]
    V2, F2 = weld(V2, F2)
    F2 = drop_duplicates(V2, F2)
    F2 = fix_tjunctions(V2, F2)
    F2 = drop_duplicates(V2, F2)
    used = np.unique(F2)
    remap = -np.ones(len(V2), np.int64)
    remap[used] = np.arange(len(used))
    V2, F2 = V2[used], remap[F2]
    return V2, F2, len(open_edges(F2))
