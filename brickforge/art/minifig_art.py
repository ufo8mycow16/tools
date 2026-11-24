"""Renders BrickForge's minifigure artwork from the LDraw library (CC BY 4.0).
Build-time only: writes PNGs next to this file, which build.bat packs into the exe.

    python minifig_art.py path/to/complete.zip

Figures are built from real LDraw parts in the colours the sets used:
  knight  - Yellow Castle (375) blue knight, crown on dark pink vest + shield
  prince / princess - Knight's Tournament (383)
  lady_knight - Series 23 Knight of the Yellow Castle (her printed torso/armour
                aren't in LDraw - closest plain parts used)
"""
import math, os, re, sys, zipfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ library + colours
class Lib:
    def __init__(self, zpath):
        self.z = zipfile.ZipFile(zpath)
        self.files = {}
        for n in self.z.namelist():
            low = n.lower()
            if not low.endswith((".dat", ".ldr")):
                continue
            parts = low.split("/")
            for root, prio in (("parts", 0), ("p", 1)):
                if root in parts:
                    i = parts.index(root)
                    key = "/".join(parts[i + 1:])
                    if key not in self.files or self.files[key][0] > prio:
                        self.files[key] = (prio, n)
                    break
            if low.endswith("ldconfig.ldr"):
                self.ldconfig = n
        self.cache = {}
        self.colours = self._colours()

    def read(self, name):
        key = name.strip().replace("\\", "/").lower()
        if key not in self.files:
            return None
        if key not in self.cache:
            self.cache[key] = self.z.read(self.files[key][1]).decode("utf-8", "replace")
        return self.cache[key]

    def _colours(self):
        out = {}
        for line in self.z.read(self.ldconfig).decode("utf-8", "replace").splitlines():
            m = re.search(r"CODE\s+(\d+)\s+VALUE\s+#([0-9A-Fa-f]{6})\s+EDGE\s+#([0-9A-Fa-f]{6})(.*)", line)
            if m:
                rgb = [int(m.group(2)[i:i + 2], 16) / 255 for i in (0, 2, 4)]
                edge = [int(m.group(3)[i:i + 2], 16) / 255 for i in (0, 2, 4)]
                metal = any(w in m.group(4).upper() for w in ("CHROME", "METAL", "PEARLESCENT"))
                out[int(m.group(1))] = (np.array(rgb), np.array(edge), metal)
        return out


def flatten(lib, text, colour, M, tris, lines, depth=0):
    """Triangles (3x3 points, colour code) and edge lines under transform M (4x4)."""
    if depth > 30 or text is None:
        return
    for raw in text.splitlines():
        p = raw.split()
        if not p or p[0] == "0":
            continue
        t = p[0]
        try:
            c = int(p[1])
        except ValueError:
            continue
        c = colour if c == 16 else (-colour if c == 24 else c)   # -code = edge colour of code
        if t == "1" and len(p) >= 15:
            x, y, z, a, b, cc, d, e, f, g, h, i = map(float, p[2:14])
            S = np.array([[a, b, cc, x], [d, e, f, y], [g, h, i, z], [0, 0, 0, 1.0]])
            flatten(lib, lib.read(" ".join(p[14:])), c, M @ S, tris, lines, depth + 1)
        elif t in ("3", "4"):
            pts = np.array(list(map(float, p[2:2 + 3 * int(t)]))).reshape(-1, 3)
            P = (M[:3, :3] @ pts.T).T + M[:3, 3]
            tris.append((P[[0, 1, 2]], c))
            if t == "4":
                tris.append((P[[0, 2, 3]], c))
        elif t == "2" and len(p) >= 8:
            pts = np.array(list(map(float, p[2:8]))).reshape(2, 3)
            lines.append(((M[:3, :3] @ pts.T).T + M[:3, 3], c))


# ------------------------------------------------------------------ figure assembly
def mat(rows):
    return np.array(rows, float).reshape(3, 3)


def rx(deg):
    a = math.radians(deg)
    return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])


def ry(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])


def rz(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


ARM_R = (np.array([-15.552, 9, 0]), mat([0.985, -0.17, 0, 0.17, 0.985, 0, 0, 0, 1]))
ARM_L = (np.array([15.552, 9, 0]), mat([0.985, 0.17, 0, -0.17, 0.985, 0, 0, 0, 1]))
HAND_R = (np.array([-23.6904, 26.774, -9.8982]),
          mat([0.985, -0.1202, 0.1202, 0.17, 0.6964, -0.6964, 0, 0.707, 0.707]))
HAND_L = (np.array([23.6904, 26.774, -9.8982]),
          mat([0.985, 0.1202, -0.1202, -0.17, 0.6964, -0.6964, 0, 0.707, 0.707]))


def line1(colour, pos, R, part):
    r = R.reshape(-1)
    return (f"1 {colour} {pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f} "
            + " ".join(f"{v:.5f}" for v in r) + f" {part}")


def figure(torso, arms, hands, hips, legs, head, torso_part="973.dat", head_part="3626bp01.dat",
           hat=None, neck=None, legs_part=None, right=0.0, left=0.0, right_item=None, left_item=None,
           extra=(), turn=0.0):
    """LDraw text for a whole minifig. right/left = how far each arm swings up (degrees,
    forward). right_item/left_item = (part, colour, R, offset) held in that hand."""
    L = [line1(torso, (0, 0, 0), np.eye(3), torso_part)]
    for (o, R), (ho, HR), up, part, item in ((ARM_R, HAND_R, right, "3818.dat", right_item),
                                             (ARM_L, HAND_L, left, "3819.dat", left_item)):
        Q = rx(-up)                                   # swing forward/up about the shoulder
        L.append(line1(arms, o, Q @ R, part))
        hp = o + Q @ (ho - o)
        L.append(line1(hands, hp, Q @ HR, "3820.dat"))
        if item:
            ip, ic, IR, off = item
            L.append(line1(ic, hp + Q @ HR @ np.array(off), Q @ HR @ IR, ip))
    if legs_part:
        L.append(line1(legs, (0, 32, 0), np.eye(3), legs_part))
    else:
        L.append(line1(hips, (0, 32, 0), np.eye(3), "3815.dat"))
        L.append(line1(legs, (0, 44, 0), np.eye(3), "3816.dat"))
        L.append(line1(legs, (0, 44, 0), np.eye(3), "3817.dat"))
    L.append(line1(14, (0, -24, 0), np.eye(3), head_part))
    if hat:
        hp_, hc = hat[0], hat[1]
        L.append(line1(hc, (0, -24, 0), np.eye(3), hp_))
    for e in extra:
        L.append(line1(e[1], e[2] if len(e) > 2 else (0, -24, 0), np.eye(3), e[0]))
    if neck:
        L.append(line1(neck[1], (0, 0, 0), np.eye(3), neck[0]))
    return "\n".join(L)


# ------------------------------------------------------------------ renderer
def render(lib, ldr_text, out_png, height=420, yaw=-28, pitch=14, ss=3, outline=True):
    tris, lines = [], []
    flatten(lib, ldr_text, 16, np.eye(4), tris, lines)
    P = np.array([t[0] for t in tris])                      # (n,3,3)
    C = np.array([t[1] for t in tris])
    # LDraw: y down. View: turn, tilt.
    R = rx(pitch) @ ry(yaw)
    V = P.reshape(-1, 3) * np.array([1, -1, -1])
    V = (R @ V.T).T.reshape(-1, 3, 3)
    lo, hi = V.reshape(-1, 3).min(0), V.reshape(-1, 3).max(0)
    pad = 6
    scale = (height * ss - 2 * pad * ss) / (hi[1] - lo[1])
    W = int((hi[0] - lo[0]) * scale + 2 * pad * ss)
    H = int(height * ss)
    def to_px(Q):
        x = (Q[..., 0] - lo[0]) * scale + pad * ss
        y = (hi[1] - Q[..., 1]) * scale + pad * ss
        return x, y, Q[..., 2]
    zbuf = np.full((H, W), -1e9)
    img = np.zeros((H, W, 4))
    light = np.array([-0.45, 0.65, 0.62]); light /= np.linalg.norm(light)
    X, Y, Z = to_px(V)
    N = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    nl = np.linalg.norm(N, axis=1); nl[nl == 0] = 1
    N = N / nl[:, None]
    for k in range(len(V)):
        code = C[k]
        if code < 0:
            col = lib.colours.get(-code, lib.colours[0])[1]; metal = False
        else:
            cc = lib.colours.get(code, lib.colours[71])
            col, metal = cc[0], cc[2]
        n = N[k] if N[k][2] >= 0 else -N[k]
        diff = max(0.0, float(n @ light))
        spec = max(0.0, n[2] * 0.0 + (2 * (n @ light) * n[2] - light[2])) ** (12 if not metal else 6)
        shade = col * (0.42 + 0.62 * diff) + (0.18 if not metal else 0.35) * spec
        xs, ys, zs = X[k], Y[k], Z[k]
        x0, x1 = int(max(0, math.floor(xs.min()))), int(min(W - 1, math.ceil(xs.max())))
        y0, y1 = int(max(0, math.floor(ys.min()))), int(min(H - 1, math.ceil(ys.max())))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        a = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        b = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        c = 1 - a - b
        inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        if not inside.any():
            continue
        z = a * zs[0] + b * zs[1] + c * zs[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z > sub)
        sub[upd] = z[upd]
        img[y0:y1 + 1, x0:x1 + 1][upd] = np.append(np.clip(shade, 0, 1), 1.0)
    if outline and lines:
        Lp = np.array([l[0] for l in lines]) * np.array([1, -1, -1])
        Lp = (R @ Lp.reshape(-1, 3).T).T.reshape(-1, 2, 3)
        lx, ly, lz = to_px(Lp)
        for k in range(len(Lp)):
            n = int(max(abs(lx[k, 1] - lx[k, 0]), abs(ly[k, 1] - ly[k, 0]))) + 1
            t = np.linspace(0, 1, n)
            px = (lx[k, 0] + (lx[k, 1] - lx[k, 0]) * t).astype(int)
            py = (ly[k, 0] + (ly[k, 1] - ly[k, 0]) * t).astype(int)
            pz = lz[k, 0] + (lz[k, 1] - lz[k, 0]) * t
            ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
            px, py, pz = px[ok], py[ok], pz[ok]
            vis = pz >= zbuf[py, px] - 0.6
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    qx, qy = np.clip(px[vis] + dx, 0, W - 1), np.clip(py[vis] + dy, 0, H - 1)
                    img[qy, qx, :3] *= 0.55
    from PIL import Image
    im = Image.fromarray((img * 255).astype(np.uint8), "RGBA")
    im = im.resize((W // ss, H // ss), Image.LANCZOS)

    def project(pt):
        """LDraw point -> pixel position in the saved picture."""
        q = R @ (np.asarray(pt, float) * np.array([1, -1, -1]))
        x, y, _ = to_px(q)
        return x / ss, y / ss
    if out_png:
        im.save(out_png)
    return im, project


# ------------------------------------------------------------------ the cast
BLUE, RED, WHITE, YELLOW, BLACK, BROWN, LGRAY, LBGRAY, SANDBLUE, DPINK, GOLD, FSILVER = \
    1, 4, 15, 14, 0, 6, 7, 71, 379, 5, 297, 179
HELD = rx(-90)          # how a hand holds a shield / lance (found by eye)


def place(text, pos, yaw=0.0):
    """Move (and turn) a whole figure."""
    R = ry(yaw)
    out = []
    for l in text.splitlines():
        p = l.split()
        x, y, z = map(float, p[2:5])
        M = np.array(list(map(float, p[5:14]))).reshape(3, 3)
        out.append(line1(int(p[1]), R @ np.array([x, y, z]) + np.array(pos), R @ M, " ".join(p[14:])))
    return "\n".join(out)


def knight(right=0.0, left=0.0, lance=True, shield=True):
    """Yellow Castle (375) blue knight: crown on dark pink vest and shield."""
    return figure(BLUE, BLUE, YELLOW, BLUE, BLUE, None, hat=("3844.dat", LGRAY),
                  neck=("3840d01.dat", LGRAY), right=right, left=left,
                  left_item=("3846d01.dat", LGRAY, HELD, (0, 0, 0)) if shield else None,
                  right_item=("3849.dat", BROWN, HELD, (0, 0, 0)) if lance else None)


def prince(right=0.0, left=0.0):
    return figure(RED, RED, YELLOW, RED, RED, None, torso_part="973p4s.dat",
                  hat=("3901.dat", BROWN), right=right, left=left)


def princess(right=0.0, left=0.0):
    return figure(WHITE, WHITE, YELLOW, WHITE, WHITE, None, torso_part="973p72.dat",
                  hat=("3625.dat", RED), right=right, left=left)


def lady_knight(right=0.0, left=0.0, visor_up=85, sword=True, shield=True):
    """Series 23 Knight of the Yellow Castle. Her printed torso and armour aren't in LDraw,
    so: plain parts in her colours, plus a small copy of her crown shield (3846p4x - crown on
    lilac with gold border, the same design as her chest print) laid on the breastplate.
    Gold sword and the crown shield in her hands; visor tipped up so you can see her face."""
    t = figure(LBGRAY, SANDBLUE, YELLOW, LBGRAY, LBGRAY, None, head_part="3626bp08.dat",
               legs_part="37364.dat", hat=("30124b.dat", LBGRAY), neck=("2587.dat", FSILVER),
               right=right, left=left,
               # sword points up when the arm is raised, along the arm when it's down
               right_item=("3847.dat", GOLD, HELD @ rx(180) if right > 90 else HELD, (0, 0, 0))
               if sword else None,
               left_item=("3846p4x.dat", LBGRAY, HELD, (0, 0, 0)) if shield else None)
    pivot = np.array([0, -16, 0.7])                   # visor pins on the helmet
    Rv = rx(-visor_up)
    t += "\n" + line1(GOLD, pivot, Rv, "2594b.dat")
    t += "\n" + line1(DPINK, pivot + Rv @ (np.array([0, -36, -12]) - pivot), np.eye(3), "64647.dat")
    # chest crest: the shield shrunk flat onto the breastplate (front of the plate ~ z -20.4)
    sc = np.diag([0.30, 0.30, 0.04])
    t += "\n" + line1(LBGRAY, (0, 13 - 9.2 * 0.30, -20.4 + 10 * 0.04 - 0.35), sc, "3846p4x.dat")
    return t


def banner(lib, out_png, title="BrickForge", height=230):
    """The prince and princess (383) holding up a sign of yellow 1x16 bricks."""
    from PIL import ImageDraw, ImageFont
    up = 172
    scene = place(prince(up, up), (-125, 0, 0)) + "\n" + place(princess(up, up), (125, 0, 0))
    rows = 3
    for r in range(rows):
        scene += "\n" + line1(YELLOW, (0, -50 - 24 * r, 12), np.eye(3), "2465.dat")
    im, project = render(lib, scene, None, height=height, yaw=-10, pitch=6)
    # letter the front face of the sign
    top, bottom = -50 - 24 * (rows - 1), -50 + 24
    (x0, y0), (x1, y1) = project((-150, top + 2, -10 + 12)), project((150, bottom - 2, -10 + 12))
    draw = ImageDraw.Draw(im)
    font_path = os.path.join(HERE, "Poppins-Bold.ttf")
    size = int((y1 - y0) * 0.62)
    font = ImageFont.truetype(font_path, size)
    while draw.textlength(title, font=font) > (x1 - x0) * 0.9 and size > 8:
        size -= 2
        font = ImageFont.truetype(font_path, size)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    draw.text((cx + 2, cy + 2), title, font=font, fill=(90, 60, 0, 255), anchor="mm")
    draw.text((cx, cy), title, font=font, fill=(200, 20, 30, 255), anchor="mm")
    im.save(out_png)
    return im.size


def make_all(lib):
    """Every picture BrickForge's window uses."""
    out = {}
    out["banner"] = banner(lib, os.path.join(HERE, "banner.png"), height=130)
    # knight at the Generate button: arm resting, then arm out pressing (turned so the arm
    # points left - the app shows him mirrored, beside the button)
    for name, arm in (("knight_ready", 25), ("knight_press", 80)):
        im, _ = render(lib, place(knight(right=arm, lance=False), (0, 0, 0), yaw=30),
                       None, height=110, yaw=0, pitch=10)
        im = im.transpose(0)            # mirror: he faces right, towards the button
        im.save(os.path.join(HERE, name + ".png"))
        out[name] = im.size
    im, _ = render(lib, place(lady_knight(right=150), (0, 0, 0), yaw=-25),
                   os.path.join(HERE, "lady_knight_wave.png"), height=110, yaw=0, pitch=10)
    out["lady_knight_wave"] = im.size
    im, _ = render(lib, knight(), os.path.join(HERE, "knight_guard.png"), height=130, yaw=-28, pitch=12)
    out["knight_guard"] = im.size
    return out


if __name__ == "__main__":
    for k, v in make_all(Lib(sys.argv[1])).items():
        print(k, v)
