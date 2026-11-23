"""6x16 plate with studs on the edges only (LEGO-compatible part 6205 replacement).
Builds a single watertight STL with numpy only. Plain studs, no logos."""
import numpy as np, struct, sys

# ---- dimensions (mm) ----
PITCH = 8.0
NX, NY = 16, 6
GAP = 0.1                 # each outer face sits 0.1 inside the nominal grid
H = 3.2                   # plate height
TOP = 1.0                 # top thickness
WALL = 1.2                # side wall thickness
STUD_R = 2.4              # 4.8 dia
STUD_H = 1.7
TUBE_RO = 6.51 / 2
TUBE_RI = 4.8 / 2
N = 32                    # segments per circle (multiple of 8)

CEIL = H - TOP
LX, LY = NX * PITCH, NY * PITCH

verts, vidx, tris = [], {}, []

def V(x, y, z):
    # snap nominal outer edge onto the real (inset) outer face
    if abs(x) < 1e-9: x = GAP
    if abs(x - LX) < 1e-9: x = LX - GAP
    if abs(y) < 1e-9: y = GAP
    if abs(y - LY) < 1e-9: y = LY - GAP
    k = (round(x, 4) + 0.0, round(y, 4) + 0.0, round(z, 4) + 0.0)
    if k not in vidx:
        vidx[k] = len(verts); verts.append(k)
    return vidx[k]

def T(a, b, c, n):
    pa, pb, pc = (np.array(verts[i]) for i in (a, b, c))
    nn = np.cross(pb - pa, pc - pa)
    if np.linalg.norm(nn) < 1e-12: return
    tris.append((a, b, c) if np.dot(nn, n) > 0 else (a, c, b))

ang = [2 * np.pi * j / N for j in range(N)]
def sq(cx, cy, h, t):
    c, s = np.cos(t), np.sin(t); m = max(abs(c), abs(s))
    return cx + h * c / m, cy + h * s / m
def circ(cx, cy, r, t):
    return cx + r * np.cos(t), cy + r * np.sin(t)

def ring_face(cx, cy, h, r, z, n):
    """square cell minus circle, horizontal"""
    S = [V(*sq(cx, cy, h, t), z) for t in ang]
    C = [V(*circ(cx, cy, r, t), z) for t in ang]
    for j in range(N):
        k = (j + 1) % N
        T(S[j], S[k], C[k], n); T(S[j], C[k], C[j], n)
    return C

def full_face(cx, cy, h, z, n):
    S = [V(*sq(cx, cy, h, t), z) for t in ang]; c = V(cx, cy, z)
    for j in range(N): T(c, S[j], S[(j + 1) % N], n)

def disc(cx, cy, r, z, n):
    C = [V(*circ(cx, cy, r, t), z) for t in ang]; c = V(cx, cy, z)
    for j in range(N): T(c, C[j], C[(j + 1) % N], n)

def cyl(cx, cy, r, z0, z1, outward):
    for j in range(N):
        t0, t1 = ang[j], ang[(j + 1) % N]
        a, b = V(*circ(cx, cy, r, t0), z0), V(*circ(cx, cy, r, t1), z0)
        c, d = V(*circ(cx, cy, r, t1), z1), V(*circ(cx, cy, r, t0), z1)
        tm = t0 + np.pi / N; n = np.array([np.cos(tm), np.sin(tm), 0]) * (1 if outward else -1)
        T(a, b, c, n); T(a, c, d, n)

def edge_studs():
    for i in range(NX):
        for j in range(NY):
            if i in (0, NX - 1) or j == NY - 1: yield i, j   # open along one long side

studs = set(edge_studs())
UP, DOWN = np.array([0, 0, 1.]), np.array([0, 0, -1.])

# ---- top face + studs ----
for i in range(NX):
    for j in range(NY):
        cx, cy = 4 + 8 * i, 4 + 8 * j
        if (i, j) in studs:
            ring_face(cx, cy, 4, STUD_R, H, UP)
            cyl(cx, cy, STUD_R, H, H + STUD_H, True)
            disc(cx, cy, STUD_R, H + STUD_H, UP)
        else:
            full_face(cx, cy, 4, H, UP)

# outer boundary sample positions (match top-face cell edges)
def side_samples(n_cells):
    offs = [4 * np.tan(t) for t in np.linspace(-np.pi/4, np.pi/4, N // 4 + 1)]
    d = {}
    for k in range(n_cells):
        for o in offs: d.setdefault(round(4 + 8 * k + o, 4), 4 + 8 * k + o)
    return [d[k] for k in sorted(d)]
xs, ys = side_samples(NX), side_samples(NY)

# outer perimeter loop (counter-clockwise, nominal coords)
loop = [(x, 0) for x in xs] + [(LX, y) for y in ys[1:]] + \
       [(x, LY) for x in reversed(xs[:-1])] + [(0, y) for y in reversed(ys[1:-1])]

# ---- outer side walls ----
for k in range(len(loop)):
    p, q = loop[k], loop[(k + 1) % len(loop)]
    a, b, c, d = V(*p, 0), V(*q, 0), V(*q, H), V(*p, H)
    mid = np.array([(p[0] + q[0]) / 2 - LX / 2, (p[1] + q[1]) / 2 - LY / 2])
    dvec = np.array(q) - np.array(p); n = np.array([dvec[1], -dvec[0], 0.])
    if np.dot(n[:2], mid) < 0: n = -n
    T(a, b, c, n); T(a, c, d, n)

# ---- bottom rim (z=0) between outer loop and inner wall rectangle ----
ix0, iy0, ix1, iy1 = GAP + WALL, GAP + WALL, LX - GAP - WALL, LY - GAP - WALL
def trap_fan(inner_a, inner_b, outer_pts, z, n):
    a, b = V(*inner_a, z), V(*inner_b, z)
    O = [V(*p, z) for p in outer_pts]
    for k in range(len(O) - 1): T(a, O[k], O[k + 1], n)
    T(a, O[-1], b, n)
sides_outer = [
    ((ix0, iy0), (ix1, iy0), [(x, 0) for x in xs]),
    ((ix1, iy0), (ix1, iy1), [(LX, y) for y in ys]),
    ((ix1, iy1), (ix0, iy1), [(x, LY) for x in reversed(xs)]),
    ((ix0, iy1), (ix0, iy0), [(0, y) for y in reversed(ys)]),
]
for a, b, pts in sides_outer: trap_fan(a, b, pts, 0, DOWN)

# ---- inner walls (face into cavity) ----
rect = [(ix0, iy0), (ix1, iy0), (ix1, iy1), (ix0, iy1)]
for k in range(4):
    p, q = rect[k], rect[(k + 1) % 4]
    a, b, c, d = V(*p, 0), V(*q, 0), V(*q, CEIL), V(*p, CEIL)
    mid = np.array([(p[0] + q[0]) / 2 - LX / 2, (p[1] + q[1]) / 2 - LY / 2])
    dvec = np.array(q) - np.array(p); n = np.array([dvec[1], -dvec[0], 0.])
    if np.dot(n[:2], mid) > 0: n = -n
    T(a, b, c, n); T(a, c, d, n)

# ---- cavity ceiling + tubes ----
tx = [8 * k for k in range(1, NX)]
ty = [8 * k for k in range(1, NY)]
for cx in tx:
    for cy in ty:
        ring_face(cx, cy, 4, TUBE_RO, CEIL, DOWN)
        cyl(cx, cy, TUBE_RO, 0, CEIL, True)
        cyl(cx, cy, TUBE_RI, 0, CEIL, False)
        disc(cx, cy, TUBE_RI, CEIL, DOWN)
        # tube bottom annulus
        for j in range(N):
            t0, t1 = ang[j], ang[(j + 1) % N]
            a, b = V(*circ(cx, cy, TUBE_RO, t0), 0), V(*circ(cx, cy, TUBE_RO, t1), 0)
            c, d = V(*circ(cx, cy, TUBE_RI, t1), 0), V(*circ(cx, cy, TUBE_RI, t0), 0)
            T(a, b, c, DOWN); T(a, c, d, DOWN)

# ceiling frame between inner wall and tube-cell block
def uniq(vals):
    d = {}
    for v in vals: d.setdefault(round(v, 4), v)
    return [d[k] for k in sorted(d)]
gx = uniq(sq(cx, 0, 4, t)[0] for cx in tx for t in ang)
gy = uniq(sq(0, cy, 4, t)[1] for cy in ty for t in ang)
bx0, bx1, by0, by1 = gx[0], gx[-1], gy[0], gy[-1]
frame = [
    ((ix0, iy0), (ix1, iy0), [(x, by0) for x in gx]),
    ((ix1, iy0), (ix1, iy1), [(bx1, y) for y in gy]),
    ((ix1, iy1), (ix0, iy1), [(x, by1) for x in reversed(gx)]),
    ((ix0, iy1), (ix0, iy0), [(bx0, y) for y in reversed(gy)]),
]
# each trapezoid: wall edge a-b, block edge pts; corners of block connect to wall corners
for a, b, pts in frame:
    A, B = V(*a, CEIL), V(*b, CEIL)
    P = [V(*p, CEIL) for p in pts]
    for k in range(len(P) - 1): T(A, P[k], P[k + 1], DOWN)
    T(A, P[-1], B, DOWN)

# ---- check watertight ----
from collections import Counter
ec = Counter()
for a, b, c in tris:
    for e in ((a, b), (b, c), (c, a)): ec[e] += 1
bad = [e for e, n in ec.items() if n != 1 or ec.get((e[1], e[0]), 0) != 1]
print("verts", len(verts), "tris", len(tris), "bad edges", len(bad))

# ---- write binary STL ----
out = sys.argv[1] if len(sys.argv) > 1 else "plate_6x16_edge_studs_6205.stl"
P = np.array(verts)
with open(out, "wb") as f:
    f.write(b"6x16 edge-stud plate (6205 replacement)".ljust(80, b" "))
    f.write(struct.pack("<I", len(tris)))
    for a, b, c in tris:
        n = np.cross(P[b] - P[a], P[c] - P[a]); n = n / np.linalg.norm(n)
        f.write(struct.pack("<12fH", *n, *P[a], *P[b], *P[c], 0))
print("wrote", out)

