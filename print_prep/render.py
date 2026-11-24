"""Tiny textured software renderer (numpy z-buffer) for looking at a model from any angle."""
import numpy as np
from PIL import Image

def rot(yaw, pitch):
    y, p = np.radians(yaw), np.radians(pitch)
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    return Rx @ Ry

def render(pos, faces, uv=None, tex=None, R=np.eye(3), size=700, pad=0.06, bg=(235, 235, 235), wire=False):
    P = pos @ R.T
    lo, hi = P[:, :2].min(0), P[:, :2].max(0)
    sc = (1 - 2 * pad) * size / (hi - lo).max()
    c = (lo + hi) / 2
    sx = (P[:, 0] - c[0]) * sc + size / 2
    sy = size / 2 - (P[:, 1] - c[1]) * sc
    sz = P[:, 2]
    img = np.zeros((size, size, 3)); img[:] = bg
    zb = np.full((size, size), -np.inf)
    T = None
    if tex is not None:
        T = np.asarray(tex.convert('RGB'), dtype=float); th, tw = T.shape[:2]
    L = np.array([0.4, 0.6, 0.7]); L /= np.linalg.norm(L)
    for f in faces:
        a, b, cc = f
        x = np.array([sx[a], sx[b], sx[cc]]); y = np.array([sy[a], sy[b], sy[cc]]); z = np.array([sz[a], sz[b], sz[cc]])
        n = np.cross(P[b] - P[a], P[cc] - P[a]); nn = np.linalg.norm(n)
        if nn == 0: continue
        n /= nn
        shade = 0.35 + 0.65 * abs(n @ L)
        x0, x1 = int(max(0, np.floor(x.min()))), int(min(size - 1, np.ceil(x.max())))
        y0, y1 = int(max(0, np.floor(y.min()))), int(min(size - 1, np.ceil(y.max())))
        if x1 < x0 or y1 < y0: continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(d) < 1e-12: continue
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any(): continue
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        m &= zz > sub
        if not m.any(): continue
        sub[m] = zz[m]
        if T is not None and uv is not None:
            u = w0 * uv[a, 0] + w1 * uv[b, 0] + w2 * uv[cc, 0]
            v = w0 * uv[a, 1] + w1 * uv[b, 1] + w2 * uv[cc, 1]
            tx = (np.mod(u, 1) * (tw - 1)).astype(int); ty = (np.mod(v, 1) * (th - 1)).astype(int)
            col = T[ty, tx]
        else:
            col = np.array([200, 170, 110.0])[None, None, :] * np.ones(gx.shape + (1,))
        img[y0:y1 + 1, x0:x1 + 1][m] = col[m] * shade
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if wire:
        from PIL import ImageDraw
        dr = ImageDraw.Draw(im)
        for f in faces:
            pts = [(sx[i], sy[i]) for i in f] + [(sx[f[0]], sy[f[0]])]
            dr.line(pts, fill=(40, 40, 40), width=1)
    return im
