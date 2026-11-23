"""BrickForge core: turns an LDraw part into a printable STL.

Reads the LDraw parts library straight out of a zip file, flattens a part
into triangles (following the library's face-direction rules), applies the
stud/tube fit adjustments, cleans the mesh and writes a binary STL in mm.
"""
import io, os, re, struct, zipfile
import numpy as np

LDU = 0.4  # 1 LDraw unit = 0.4 mm

# Primitives whose width gets adjusted by the fit settings
STUD_NAMES = re.compile(r"^(stud|stud2|stud2a|stud-logo\d*|stud2-logo\d*)\.dat$")
TUBE_NAMES = re.compile(r"^stud4[a-z0-9]*\.dat$")
STUD_DIA = 4.8   # mm, LDraw stud.dat (radius 6 LDU)
TUBE_DIA = 6.4   # mm, LDraw stud4.dat outer (radius 8 LDU)


class Library:
    """The LDraw library, read from a zip (or a folder) containing ldraw/parts and ldraw/p."""

    def __init__(self, path):
        self.path = path
        self.files = {}      # lookup name -> archive member / file path
        self._text = {}
        self._zip = None
        if os.path.isdir(path):
            self._scan_dir(path)
        else:
            self._zip = zipfile.ZipFile(path)
            self._scan_zip()
        self.index = None

    # ---- file lookup ----
    def _add(self, rel, member):
        rel = rel.lower()
        parts = rel.split("/")
        # roots in priority order: parts/ then p/
        for root, prio in (("parts", 0), ("p", 1)):
            if root in parts:
                i = parts.index(root)
                key = "/".join(parts[i + 1:])
                if key and (key not in self.files or self.files[key][0] > prio):
                    self.files[key] = (prio, member)
                return

    def _scan_zip(self):
        for name in self._zip.namelist():
            if name.lower().endswith(".dat"):
                self._add(name, name)
            elif name.lower().endswith("parts_index.tsv"):
                self._index_member = name

    def _scan_dir(self, root):
        for dp, _, fns in os.walk(root):
            for fn in fns:
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if fn.lower().endswith(".dat"):
                    self._add(rel, full)

    def read(self, name):
        key = name.strip().replace("\\", "/").lower()
        if key in self._text:
            return self._text[key]
        hit = self.files.get(key)
        if hit is None:
            return None
        member = hit[1]
        if self._zip:
            data = self._zip.read(member)
        else:
            with open(member, "rb") as f:
                data = f.read()
        text = data.decode("utf-8", errors="replace")
        self._text[key] = text
        return text

    def has_part(self, number):
        return number.lower() in self.files and self.files[number.lower()][0] == 0

    # ---- part list / search ----
    def load_index(self):
        """List of (number, description) for every top-level part."""
        if self.index is not None:
            return self.index
        idx = []
        member = getattr(self, "_index_member", None)
        if member:
            for line in self._zip.read(member).decode("utf-8").splitlines():
                if "\t" in line:
                    n, d = line.split("\t", 1)
                    idx.append((n, d))
        else:
            for key, (prio, _) in self.files.items():
                if prio == 0 and "/" not in key:
                    text = self.read(key) or ""
                    first = text.split("\n", 1)[0].strip()
                    desc = first[1:].strip() if first.startswith("0") else ""
                    idx.append((key[:-4], desc))
            idx.sort(key=lambda x: _natural(x[0]))
        self.index = idx
        return idx

    def search(self, words, limit=500):
        phrase = " ".join(words.lower().split())
        words = phrase.split()
        if not words:
            return []
        exact, rest = [], []
        for num, desc in self.load_index():
            hay = " ".join((num + " " + desc).lower().split())
            toks = set(re.findall(r"[a-z0-9.]+", hay))
            # numbers must match a whole number (so "6" doesn't match "16"); words can match part
            if all((w in toks) if w.isdigit() else (w in hay) for w in words):
                (exact if phrase in hay or num == phrase else rest).append((num, desc))
        def rank(item):
            num, desc = item
            d = " ".join(desc.lower().split())
            return (desc.startswith("~"), not d.startswith(phrase), len(d))
        out = sorted(exact, key=rank) + sorted(rest, key=rank)
        return out[:limit]

    def description(self, number):
        text = self.read(number + ".dat") or ""
        first = text.split("\n", 1)[0].strip()
        return first[1:].strip() if first.startswith("0") else ""

    def resolve(self, number):
        """Part number as typed -> library file name, or list of suggestions."""
        n = number.strip().lower()
        if n.endswith(".dat"):
            n = n[:-4]
        if self.has_part(n + ".dat"):
            return n, []
        # suggestions: same number with a mould letter / suffix
        sugg = [k[:-4] for k, (p, _) in self.files.items()
                if p == 0 and "/" not in k and re.match(re.escape(n) + r"[a-z]?[0-9]*\.dat$", k)]
        return None, sorted(sugg, key=_natural)[:20]


def _natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class Flattener:
    def __init__(self, lib, stud_adjust=0.0, tube_adjust=0.0):
        self.lib = lib
        self.stud_scale = (STUD_DIA + stud_adjust) / STUD_DIA
        self.tube_scale = (TUBE_DIA + tube_adjust) / TUBE_DIA
        self.cache = {}
        self.missing = set()

    def flatten(self, name, depth=0):
        """Triangles of a file in its own coordinates, facing outward. (N,3,3) array."""
        key = name.strip().replace("\\", "/").lower()
        if key in self.cache:
            return self.cache[key]
        text = self.lib.read(key)
        if text is None:
            self.missing.add(key)
            self.cache[key] = np.zeros((0, 3, 3))
            return self.cache[key]
        if depth > 40:
            return np.zeros((0, 3, 3))

        own = []          # triangles from this file
        kids = []         # transformed child triangle arrays
        ccw = True
        invert_next = False
        for raw in text.splitlines():
            tok = raw.split()
            if not tok:
                continue
            t = tok[0]
            if t == "0":
                if len(tok) >= 3 and tok[1] == "BFC":
                    rest = [x.upper() for x in tok[2:]]
                    if "INVERTNEXT" in rest:
                        invert_next = True
                    if "CW" in rest:
                        ccw = False
                    if "CCW" in rest:
                        ccw = True
                continue
            if t == "1" and len(tok) >= 15:
                try:
                    v = [float(x) for x in tok[2:14]]
                except ValueError:
                    invert_next = False
                    continue
                sub = " ".join(tok[14:])
                pos = np.array(v[0:3])
                M = np.array(v[3:12]).reshape(3, 3)
                base = sub.replace("\\", "/").lower().split("/")[-1]
                if STUD_NAMES.match(base) and self.stud_scale != 1.0:
                    M = M @ np.diag([self.stud_scale, 1.0, self.stud_scale])
                elif TUBE_NAMES.match(base) and self.tube_scale != 1.0:
                    M = M @ np.diag([self.tube_scale, 1.0, self.tube_scale])
                child = self.flatten(sub, depth + 1)
                if len(child):
                    tr = child @ M.T + pos
                    flip = invert_next ^ (np.linalg.det(M) < 0)
                    if flip:
                        tr = tr[:, ::-1, :]
                    kids.append(tr)
                invert_next = False
                continue
            if t == "3" and len(tok) >= 11:
                try:
                    p = np.array([float(x) for x in tok[2:11]]).reshape(3, 3)
                except ValueError:
                    continue
                own.append(p if ccw else p[::-1])
            elif t == "4" and len(tok) >= 14:
                try:
                    p = np.array([float(x) for x in tok[2:14]]).reshape(4, 3)
                except ValueError:
                    continue
                a, b = p[[0, 1, 2]], p[[0, 2, 3]]
                if not ccw:
                    a, b = a[::-1], b[::-1]
                own.extend([a, b])
            invert_next = False if t in "2345" else invert_next

        parts = ([np.array(own)] if own else []) + kids
        res = np.concatenate(parts) if parts else np.zeros((0, 3, 3))
        self.cache[key] = res
        return res


def clean_mesh(tris_mm, weld=1e-3):
    """Weld vertices, drop degenerate/duplicate/back-to-back faces.
    Returns (vertices, faces, open_edge_count)."""
    pts = tris_mm.reshape(-1, 3)
    q = np.round(pts / weld).astype(np.int64)
    uq, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    verts = np.zeros((len(uq), 3))
    np.add.at(verts, inv, pts)
    cnt = np.bincount(inv, minlength=len(uq))[:, None]
    verts /= cnt
    F = inv.reshape(-1, 3)
    # degenerate (repeated index or zero area)
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F = F[ok]
    a = verts[F[:, 1]] - verts[F[:, 0]]
    b = verts[F[:, 2]] - verts[F[:, 0]]
    area = np.linalg.norm(np.cross(a, b), axis=1)
    F = F[area > 1e-9]
    # duplicates: same vertex set. Same direction -> keep one; opposite -> internal wall, drop both
    srt = np.sort(F, axis=1)
    # canonical rotation to detect direction
    def canon(f):
        i = np.argmin(f, axis=1)
        r = np.stack([f[np.arange(len(f)), i], f[np.arange(len(f)), (i + 1) % 3],
                      f[np.arange(len(f)), (i + 2) % 3]], axis=1)
        return r
    c = canon(F)
    direction = (c[:, 1] == srt[:, 1])  # True if ascending order after min
    keys = {}
    for k, (s, d) in enumerate(zip(map(tuple, srt), direction)):
        keys.setdefault(s, [0, 0, None, None])
        e = keys[s]
        if d:
            e[0] += 1; e[2] = k if e[2] is None else e[2]
        else:
            e[1] += 1; e[3] = k if e[3] is None else e[3]
    keep = []
    for s, (nf, nb, kf, kb) in keys.items():
        m = min(nf, nb)
        nf -= m; nb -= m
        if nf > 0:
            keep.append(kf)
        elif nb > 0:
            keep.append(kb)
    F = F[sorted(keep)]
    # open edges
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    es = np.sort(e, axis=1)
    _, ecount = np.unique(es, axis=0, return_counts=True)
    open_edges = int(np.sum(ecount == 1))
    # drop unused vertices
    used = np.unique(F)
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[F], open_edges


def part_to_mesh(lib, number, stud_adjust=0.0, tube_adjust=0.0):
    fl = Flattener(lib, stud_adjust, tube_adjust)
    tris = fl.flatten(number + ".dat")
    if len(tris) == 0:
        raise ValueError("part has no solid faces")
    # LDraw: y points down. Convert to mm, Z up (a proper rotation, so faces keep their direction)
    t = np.empty_like(tris)
    t[..., 0] = tris[..., 0]
    t[..., 1] = tris[..., 2]
    t[..., 2] = -tris[..., 1]
    t *= LDU
    verts, faces, open_edges = clean_mesh(t)
    # sit it on the bed, centred
    mn, mx = verts.min(axis=0), verts.max(axis=0)
    verts = verts - [(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, mn[2]]
    return verts, faces, open_edges, sorted(fl.missing)


def write_stl(path, verts, faces, title="BrickForge"):
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    n = n / ln
    rec = np.zeros(len(faces), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = np.stack([v0, v1, v2], axis=1)
    with open(path, "wb") as f:
        f.write(title.encode("ascii", "replace")[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(faces)))
        f.write(rec.tobytes())


def safe_filename(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:120] or "part"


def generate(lib, number, out_dir, stud_adjust=0.0, tube_adjust=0.0):
    """Make one STL. Returns dict with info for the log."""
    resolved, sugg = lib.resolve(number)
    if resolved is None:
        return {"ok": False, "number": number, "suggest": sugg}
    desc = lib.description(resolved)
    verts, faces, open_edges, missing = part_to_mesh(lib, resolved, stud_adjust, tube_adjust)
    size = verts.max(axis=0) - verts.min(axis=0)
    name = safe_filename(f"{resolved} - {desc.lstrip('~=_|')}") + ".stl"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    write_stl(path, verts, faces, f"{resolved} {desc}")
    return {"ok": True, "number": resolved, "desc": desc, "path": path,
            "faces": len(faces), "size": size, "open_edges": open_edges, "missing": missing}
