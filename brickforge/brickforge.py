"""BrickForge - pick a LEGO part, see it, get a printable STL.

Part shapes come from the LDraw Parts Library (www.ldraw.org), CC BY 4.0.
Plain studs, no logos.
"""
import json, math, os, queue, re, sys, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import ldraw_core as core
import sets_core

APP = "BrickForge"
VERSION = "1.4"
ALL = "All categories"


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def default_out():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "BrickForge STLs")


def find_library():
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    for cand in (resource("ldraw_lib.zip"), os.path.join(here, "ldraw_lib.zip"),
                 os.path.join(here, "complete.zip")):
        if os.path.exists(cand):
            return cand
    return None


# ---------------------------------------------------------------- preview
def sample_surface(verts, faces, spacing, cap=2_500_000):
    """Evenly spaced points over every triangle (for the depth-sorted preview)."""
    tri = verts[faces]
    e = np.stack([tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 1], tri[:, 0] - tri[:, 2]], 1)
    longest = np.linalg.norm(e, axis=2).max(1)
    k = np.maximum(1, np.ceil(longest / spacing)).astype(int)
    est = ((k + 1) * (k + 2) // 2).sum()
    if est > cap:
        k = np.maximum(1, np.ceil(longest / (spacing * math.sqrt(est / cap)))).astype(int)
    pts, tid = [], []
    for kk in np.unique(k):
        sel = np.nonzero(k == kk)[0]
        i, j = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1), indexing="ij")
        m = i + j <= kk
        a, b = i[m] / kk, j[m] / kk
        c = 1 - a - b
        T = tri[sel]
        P = a[None, :, None] * T[:, None, 0] + b[None, :, None] * T[:, None, 1] + c[None, :, None] * T[:, None, 2]
        pts.append(P.reshape(-1, 3))
        tid.append(np.repeat(sel, len(a)))
    return np.concatenate(pts), np.concatenate(tid)


def png_base64(img):
    import base64, struct, zlib
    H, W, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(H))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))
    return base64.b64encode(data)


class Preview(ttk.Frame):
    """Spinnable 3D view of a part. Drag = spin, wheel = zoom, double-click = reset."""
    BASE = np.array([70.0, 125.0, 205.0])   # LEGO-ish blue
    BG = np.array([244, 245, 247], dtype=np.uint8)

    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg="#f4f5f7", highlightthickness=0, height=320)
        self.canvas.pack(fill="both", expand=True)
        self.verts = None
        self.message = "Pick a part to see it here"
        self._photo = None
        self._pending = False
        self._samples = {}
        self.reset_view()
        c = self.canvas
        c.bind("<Configure>", lambda e: self._schedule(full=True))
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", lambda e: self._schedule(full=True))
        c.bind("<Double-Button-1>", lambda e: (self.reset_view(), self._schedule(full=True)))
        c.bind("<MouseWheel>", lambda e: self._zoom(1.15 if e.delta > 0 else 1 / 1.15))
        c.bind("<Button-4>", lambda e: self._zoom(1.15))
        c.bind("<Button-5>", lambda e: self._zoom(1 / 1.15))

    def reset_view(self):
        self.yaw, self.pitch, self.zoom = math.radians(-35), math.radians(28), 1.0

    def show_picture(self, pil_image):
        self.verts = None
        self.picture = pil_image
        self._draw(full=True)

    def show_message(self, text):
        self.picture = None
        self.verts = None
        self.message = text
        self._draw(full=True)

    def set_mesh(self, verts, faces, rgb=None):
        self.picture = None
        self.colour = np.array([int(rgb[i:i + 2], 16) for i in (0, 2, 4)], float) if rgb else self.BASE
        v = verts - (verts.min(axis=0) + verts.max(axis=0)) / 2
        self.verts, self.faces = v, faces
        self.radius = float(np.max(np.linalg.norm(v, axis=1))) or 1.0
        t = v[faces]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        ln[ln == 0] = 1
        self.normals = n / ln
        self._samples = {}
        self.reset_view()
        self._draw(full=True)

    def _press(self, e):
        self._last = (e.x, e.y)

    def _drag(self, e):
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        self.yaw += dx * 0.01
        self.pitch = max(-1.55, min(1.55, self.pitch + dy * 0.01))
        self._schedule(full=False)

    def _zoom(self, f):
        self.zoom = max(0.3, min(10.0, self.zoom * f))
        self._schedule(full=True)

    def _schedule(self, full):
        self._want_full = full
        if not self._pending:
            self._pending = True
            self.after(10, lambda: self._draw(self._want_full))

    def _points(self, scale, level):
        """Surface points dense enough for this zoom (cached, rebuilt when zoom changes a lot)."""
        spacing = 1.3 / scale
        key = level
        hit = self._samples.get(key)
        if hit and 0.75 < hit[0] / spacing < 1.34:
            return hit[1], hit[2]
        P, tid = sample_surface(self.verts, self.faces, spacing)
        self._samples[key] = (spacing, P, tid)
        return P, tid

    def _draw(self, full=True):
        self._pending = False
        c = self.canvas
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        c.delete("all")
        if self.verts is None and getattr(self, "picture", None) is not None:
            im = self.picture.copy()
            im.thumbnail((w - 10, h - 10))
            from PIL import ImageTk
            self._photo = ImageTk.PhotoImage(im)
            c.create_image(w / 2, h / 2, image=self._photo)
            return
        if self.verts is None:
            c.create_text(w / 2, h / 2, text=self.message, fill="#888", font=("Segoe UI", 11))
            return
        step = 1 if full else 2                    # half resolution while dragging
        W, H = w // step, h // step
        scale = 0.42 * min(W, H) / self.radius * self.zoom
        P, tid = self._points(scale, step)
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        R = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        n = self.normals @ R.T
        keep = (n[:, 1] < 0.05)[tid]               # only faces turned towards us
        Q = P[keep] @ R.T
        t = tid[keep]
        px = (W / 2 + Q[:, 0] * scale).astype(np.int32)
        py = (H / 2 - Q[:, 2] * scale).astype(np.int32)
        light = np.array([-0.4, -0.8, 0.6])
        light /= np.linalg.norm(light)
        sh = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
        base = getattr(self, "colour", self.BASE)
        lift = 40 if base.max() < 60 else 0          # keep black parts readable
        col = np.clip((base[None] + lift) * sh[:, None] + 30 * sh[:, None] ** 4, 0, 255).astype(np.uint8)
        xs = np.concatenate([px, px + 1, px, px + 1])
        ys = np.concatenate([py, py, py + 1, py + 1])
        ds = np.tile(Q[:, 1], 4)
        ts = np.tile(t, 4)
        ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
        xs, ys, ds, ts = xs[ok], ys[ok], ds[ok], ts[ok]
        img = np.empty((H * W, 3), np.uint8)
        img[:] = self.BG
        if len(xs):
            pix = ys * W + xs
            o = np.lexsort((ds, pix))              # nearest point wins each pixel
            ps = pix[o]
            first = np.ones(len(o), bool)
            first[1:] = ps[1:] != ps[:-1]
            win = o[first]
            img[pix[win]] = col[ts[win]]
        photo = tk.PhotoImage(data=png_base64(img.reshape(H, W, 3)), format="png")
        if step > 1:
            photo = photo.zoom(step, step)
        self._photo = photo
        c.create_image(0, 0, anchor="nw", image=photo)
        c.create_text(8, h - 8, anchor="sw", fill="#999", font=("Segoe UI", 8),
                      text="drag to spin  ·  wheel to zoom  ·  double-click to reset")


# ---------------------------------------------------------------- app
class App:
    def __init__(self, root):
        self.root = root
        self.lib = None
        self.sdb = None
        self.q = queue.Queue()
        self.busy = False
        self.preview_req = 0
        self.mesh_cache = {}
        self._search_job = None
        self.settings = {"out": default_out(), "stud": 0.0, "tube": 0.0}
        try:
            with open(settings_path()) as f:
                self.settings.update(json.load(f))
        except Exception:
            pass

        root.title(f"{APP} {VERSION} - LEGO part to STL")
        root.geometry("1180x800")
        root.minsize(980, 680)
        self._build()
        self.log("Loading parts library...")
        threading.Thread(target=self._load_lib, daemon=True).start()
        root.after(100, self._poll)
        root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- layout ----------
    def _build(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=5)
        main.columnconfigure(1, weight=4)
        main.rowconfigure(0, weight=1)

        # ---- left: browser
        self.nb = ttk.Notebook(main)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left = ttk.Frame(self.nb, padding=2)
        self.nb.add(left, text="  Parts  ")
        sets_tab = ttk.Frame(self.nb, padding=2)
        self.nb.add(sets_tab, text="  Sets  ")
        self._build_sets_tab(sets_tab)
        left.columnconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)

        ttk.Label(left, text="Category:").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 3))
        self.cat_var = tk.StringVar(value=ALL)
        self.cat_box = ttk.Combobox(left, textvariable=self.cat_var, state="readonly", height=30)
        self.cat_box.grid(row=0, column=1, columnspan=2, sticky="ew", padx=6, pady=(6, 3))
        self.cat_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_list())

        ttk.Label(left, text="Search:").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        self.search_var = tk.StringVar()
        ent = ttk.Entry(left, textvariable=self.search_var, font=("Segoe UI", 11))
        ent.grid(row=1, column=1, sticky="ew", padx=6, pady=3)
        ent.bind("<KeyRelease>", lambda e: self._search_soon())
        ttk.Button(left, text="Clear", width=6,
                   command=lambda: (self.search_var.set(""), self.refresh_list())).grid(row=1, column=2, padx=6)

        self.all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="Also show printed, sticker, duplicate and old parts",
                        variable=self.all_var, command=self._toggle_all).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 3))

        tf = ttk.Frame(left)
        tf.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=6)
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tf, columns=("num", "desc", "cat"), show="headings", selectmode="extended")
        for col, txt, wd, st in (("num", "Part", 85, False), ("desc", "Description", 330, True),
                                 ("cat", "Category", 120, False)):
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=wd, stretch=st)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Double-1>", lambda e: self.add_selected())
        self.tree.bind("<Return>", lambda e: self.add_selected())

        bot = ttk.Frame(left)
        bot.grid(row=4, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        self.count_lbl = ttk.Label(bot, foreground="#666", text="")
        self.count_lbl.pack(side="left")
        ttk.Button(bot, text="Add to make list  >>", command=self.add_selected).pack(side="right")

        # ---- right: preview + make list
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=2)

        pv = ttk.LabelFrame(right, text="Preview")
        pv.grid(row=0, column=0, sticky="nsew")
        pv.columnconfigure(0, weight=1)
        pv.rowconfigure(1, weight=1)
        self.pv_title = ttk.Label(pv, text="", font=("Segoe UI", 10, "bold"), wraplength=420)
        self.pv_title.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))
        self.preview = Preview(pv)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self.pv_info = ttk.Label(pv, text="", foreground="#555")
        self.pv_info.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 6))

        mk = ttk.LabelFrame(right, text="Make list (you can also type part numbers here)")
        mk.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        mk.columnconfigure(0, weight=1)
        mk.rowconfigure(0, weight=1)
        self.parts_txt = tk.Text(mk, height=6, width=30, font=("Consolas", 11), undo=True)
        self.parts_txt.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        ttk.Button(mk, text="Clear list", command=lambda: self.parts_txt.delete("1.0", "end")).grid(
            row=1, column=0, sticky="w", padx=6, pady=(0, 6))
        self.gen_btn = ttk.Button(mk, text="Generate STLs", command=self.generate)
        self.gen_btn.grid(row=1, column=1, sticky="e", padx=6, pady=(0, 6))

        # ---- fit / output
        opts = ttk.LabelFrame(main, text="Fit and output")
        opts.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        opts.columnconfigure(5, weight=1)
        ttk.Label(opts, text="Stud size (mm):").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.stud_var = tk.DoubleVar(value=self.settings["stud"])
        ttk.Spinbox(opts, from_=-0.5, to=0.5, increment=0.05, textvariable=self.stud_var,
                    width=7, format="%.2f").grid(row=0, column=1, padx=4)
        ttk.Label(opts, text="Tube size (mm):").grid(row=0, column=2, sticky="w", padx=(16, 6))
        self.tube_var = tk.DoubleVar(value=self.settings["tube"])
        ttk.Spinbox(opts, from_=-0.5, to=0.5, increment=0.05, textvariable=self.tube_var,
                    width=7, format="%.2f").grid(row=0, column=3, padx=4)
        ttk.Label(opts, foreground="#666",
                  text="0 = standard.  Too tight: go negative.  Too loose: go positive.").grid(
            row=0, column=4, columnspan=3, sticky="w", padx=12)
        ttk.Label(opts, text="Save to:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.out_var = tk.StringVar(value=self.settings["out"])
        ttk.Entry(opts, textvariable=self.out_var).grid(row=1, column=1, columnspan=5, sticky="ew", padx=4)
        ttk.Button(opts, text="Browse...", command=self.browse_out).grid(row=1, column=6, padx=4)
        ttk.Button(opts, text="Open folder", command=self.open_folder).grid(row=1, column=7, padx=(0, 6))

        # ---- log
        logf = ttk.LabelFrame(main, text="Progress")
        logf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        logf.columnconfigure(0, weight=1)
        self.log_txt = tk.Text(logf, height=5, font=("Consolas", 10), state="disabled", wrap="word")
        self.log_txt.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log_txt.yview)
        lsb.grid(row=0, column=1, sticky="ns", pady=6)
        self.log_txt.configure(yscrollcommand=lsb.set)
        self.progress = ttk.Progressbar(logf, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))

        ttk.Label(main, foreground="#777",
                  text="Part shapes from the LDraw Parts Library (www.ldraw.org), CC BY 4.0. "
                       "LEGO is a trademark of the LEGO Group, which does not sponsor this program.").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

    # ---------- sets tab ----------
    def _build_sets_tab(self, tab):
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)
        tab.rowconfigure(5, weight=2)
        ttk.Label(tab, text="Theme:").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 3))
        self.theme_var = tk.StringVar(value="All themes")
        self.theme_box = ttk.Combobox(tab, textvariable=self.theme_var, state="readonly", height=30)
        self.theme_box.grid(row=0, column=1, columnspan=2, sticky="ew", padx=6, pady=(6, 3))
        self.theme_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_sets())
        ttk.Label(tab, text="Search:").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        self.set_search = tk.StringVar()
        e = ttk.Entry(tab, textvariable=self.set_search, font=("Segoe UI", 11))
        e.grid(row=1, column=1, sticky="ew", padx=6, pady=3)
        e.bind("<KeyRelease>", lambda ev: self._sets_soon())
        ttk.Label(tab, foreground="#666", text="set number or name, e.g. 171 or castle").grid(
            row=1, column=2, sticky="w", padx=6)
        self.sets_count = ttk.Label(tab, foreground="#666", text="")
        self.sets_count.grid(row=2, column=0, columnspan=3, sticky="w", padx=6)

        f1 = ttk.Frame(tab)
        f1.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=6)
        f1.rowconfigure(0, weight=1)
        f1.columnconfigure(0, weight=1)
        self.sets_tree = ttk.Treeview(f1, columns=("num", "name", "year", "pcs", "theme"), show="headings",
                                      selectmode="browse", height=8)
        for col, txt, wd, st in (("num", "Set", 80, False), ("name", "Name", 230, True), ("year", "Year", 50, False),
                                 ("pcs", "Pieces", 60, False), ("theme", "Theme", 170, False)):
            self.sets_tree.heading(col, text=txt)
            self.sets_tree.column(col, width=wd, stretch=st)
        self.sets_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(f1, orient="vertical", command=self.sets_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.sets_tree.configure(yscrollcommand=sb.set)
        self.sets_tree.bind("<<TreeviewSelect>>", lambda ev: self._on_set_select())

        self.set_title = ttk.Label(tab, text="Pick a set to see what's in the box", font=("Segoe UI", 10, "bold"))
        self.set_title.grid(row=4, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        f2 = ttk.Frame(tab)
        f2.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=6)
        f2.rowconfigure(0, weight=1)
        f2.columnconfigure(0, weight=1)
        self.inv_tree = ttk.Treeview(f2, columns=("qty", "colour", "desc", "part", "note"), show="headings",
                                     selectmode="browse")
        for col, txt, wd, st in (("qty", "Qty", 45, False), ("colour", "Colour", 120, False),
                                 ("desc", "Piece", 280, True), ("part", "Shape", 80, False), ("note", "", 150, False)):
            self.inv_tree.heading(col, text=txt)
            self.inv_tree.column(col, width=wd, stretch=st)
        self.inv_tree.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(f2, orient="vertical", command=self.inv_tree.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self.inv_tree.configure(yscrollcommand=sb2.set)
        self.inv_tree.bind("<<TreeviewSelect>>", lambda ev: self._on_inv_select())

        bot = ttk.Frame(tab)
        bot.grid(row=6, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        self.spares_var = tk.BooleanVar(value=False)
        self.figs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bot, text="Minifigures", variable=self.figs_var,
                        command=self._on_set_select).pack(side="left")
        ttk.Checkbutton(bot, text="Spare pieces", variable=self.spares_var,
                        command=self._on_set_select).pack(side="left", padx=8)
        self.set_btn = ttk.Button(bot, text="Make whole set", command=self.make_set)
        self.set_btn.pack(side="right")
        ttk.Button(bot, text="Building instructions", command=self.open_instructions).pack(side="right", padx=6)
        self._inv_rows = {}
        self._sets_job = None
        self._colour_tags = set()

    def _fill_themes(self):
        if not self.sdb:
            return
        th = self.sdb.themes()
        self._theme_names = {f"{t}  ({n:,})": t for t, n in th}
        total = sum(n for _, n in th)
        self.theme_box.configure(values=[f"All themes  ({total:,})"] + list(self._theme_names))
        self.theme_var.set(f"All themes  ({total:,})")

    def _sets_soon(self):
        if self._sets_job:
            self.root.after_cancel(self._sets_job)
        self._sets_job = self.root.after(250, self.refresh_sets)

    def refresh_sets(self):
        self._sets_job = None
        if not self.sdb:
            return
        theme = getattr(self, "_theme_names", {}).get(self.theme_var.get())
        rows = self.sdb.search(self.set_search.get(), theme)
        self.sets_tree.delete(*self.sets_tree.get_children())
        for num, name, year, theme_path, pcs in rows:
            self.sets_tree.insert("", "end", iid=num, values=(num, name, year, pcs, theme_path))
        self.sets_count.configure(text=f"{len(rows):,} sets" + ("  (first 3,000 shown)" if len(rows) >= 3000 else ""))

    def _current_set(self):
        sel = self.sets_tree.selection()
        return sel[0] if sel else None

    def _colour_tag(self, rgb):
        tag = "c" + rgb
        if tag not in self._colour_tags:
            r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
            fg = "#000000" if (0.3 * r + 0.59 * g + 0.11 * b) > 140 else "#ffffff"
            self.inv_tree.tag_configure(tag, background="#" + rgb, foreground=fg)
            self._colour_tags.add(tag)
        return tag

    def _on_set_select(self):
        s = self._current_set()
        if not s or not self.sdb:
            return
        info = self.sdb.info(s)
        rows = self.sdb.contents(s, self.spares_var.get(), self.figs_var.get())
        self.inv_tree.delete(*self.inv_tree.get_children())
        self._inv_rows = {}
        total = printable = 0
        for k, r in enumerate(rows):
            note = sets_core.unprintable_reason(r)
            if r["ld"] is None:
                note = "won't print - " + note
            elif r["source"] == "minifig":
                note = note or "minifigure"
            iid = f"r{k}"
            self._inv_rows[iid] = r
            self.inv_tree.insert("", "end", iid=iid, tags=(self._colour_tag(r["rgb"]),),
                                 values=(r["qty"], r["color"], r["name"], r["ld"] or "-", note))
            total += r["qty"]
            printable += r["qty"] if r["ld"] else 0
        self.set_title.configure(text=f"{info[0]}  {info[1]}  ({info[2]})  -  {total} pieces, "
                                      f"{printable} printable")
        self._show_set_picture(info)

    def _show_set_picture(self, info):
        self.preview_req += 1
        req = self.preview_req
        self.pv_title.configure(text=f"{info[0]}  -  {info[1]}  ({info[2]})")
        self.pv_info.configure(text="Set picture from Rebrickable  ·  click a piece below to see it in 3D")
        url = self.sdb.picture_url(info[0])
        if not url:
            self.preview.show_message("No picture for this set")
            return
        self.preview.show_message("Fetching picture...")
        cache = os.path.join(os.path.dirname(settings_path()), "set pictures")

        def work():
            try:
                from PIL import Image
                path = sets_core.fetch_picture(url, cache)
                im = Image.open(path)
                im.load()
                self.q.put(("picture", (req, im.convert("RGB"))))
            except Exception as e:
                self.q.put(("preview_err", (req, info[0], "Couldn't get the picture (no internet?)")))
        threading.Thread(target=work, daemon=True).start()

    def _on_inv_select(self):
        sel = self.inv_tree.selection()
        if not sel or not self.lib:
            return
        r = self._inv_rows.get(sel[0])
        if not r:
            return
        if r["ld"] is None:
            self.pv_title.configure(text=r["name"])
            self.pv_info.configure(text="")
            self.preview.show_message("No 3D shape for this one")
            return
        self.request_preview(r["ld"], r["name"], r["rgb"], r["color"])

    def open_instructions(self):
        s = self._current_set()
        if s:
            import webbrowser
            webbrowser.open(sets_core.instructions_url(s))

    def make_set(self):
        s = self._current_set()
        if not s:
            messagebox.showinfo(APP, "Pick a set first.")
            return
        if self.busy or not self.lib:
            return
        info = self.sdb.info(s)
        if not messagebox.askyesno(APP, f"Make every printable piece of {info[0]} {info[1]}?\n\n"
                                        f"The files go into a folder named after the set, "
                                        f"with a folder per colour."):
            return
        self.busy = True
        self.gen_btn.configure(state="disabled")
        self.set_btn.configure(state="disabled")
        self._save_settings()
        args = (s, self.out_var.get(), self._num(self.stud_var), self._num(self.tube_var),
                self.spares_var.get(), self.figs_var.get())
        threading.Thread(target=self._run_set, args=args, daemon=True).start()

    def _run_set(self, s, out, stud, tube, spares, figs):
        try:
            folder = sets_core.generate_set(self.lib, self.sdb, s, out, stud, tube, spares, figs,
                                            log=self.log, progress=lambda i, n: self.q.put(("progress", (i, n))))
            self.q.put(("open", folder))
        except Exception as e:
            self.log(f"Set failed - {e}")
            traceback.print_exc()
        self.q.put(("done", None))

    # ---------- plumbing ----------
    def log(self, msg):
        self.q.put(("log", msg))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log_txt.configure(state="normal")
                    self.log_txt.insert("end", val + "\n")
                    self.log_txt.see("end")
                    self.log_txt.configure(state="disabled")
                elif kind == "progress":
                    self.progress.configure(maximum=val[1], value=val[0])
                elif kind == "done":
                    self.busy = False
                    self.gen_btn.configure(state="normal")
                    self.set_btn.configure(state="normal")
                elif kind == "open":
                    try:
                        os.startfile(val)
                    except Exception:
                        pass
                elif kind == "picture":
                    req, im = val
                    if req == self.preview_req:
                        self.preview.show_picture(im)
                elif kind == "sets_ready":
                    self._fill_themes()
                    self.refresh_sets()
                elif kind == "ready":
                    self._fill_categories()
                    self.refresh_list()
                elif kind == "preview":
                    req, num, desc, verts, faces, rgb, cname = val
                    if req == self.preview_req:
                        self._show_preview(num, desc, verts, faces, rgb, cname)
                elif kind == "preview_err":
                    req, num, msg = val
                    if req == self.preview_req:
                        if not self.sdb or num not in (self._current_set() or ""):
                            self.pv_title.configure(text=num)
                            self.pv_info.configure(text="")
                        self.preview.show_message(msg)
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    def _load_lib(self):
        path = find_library()
        if not path:
            self.log("Couldn't find the LDraw library. Put complete.zip next to BrickForge and restart.")
            return
        try:
            self.lib = core.Library(path)
            n = len(self.lib.load_index())
            self.log(f"Library ready: {n:,} parts. Pick a category or search, click a part to preview it.")
            try:
                import winrepair
                self.log("Windows 3D-print repair: " + ("available" if winrepair.AVAILABLE
                         else "not available (" + winrepair.why_unavailable() + ")"))
            except Exception:
                pass
            self.q.put(("ready", None))
            here = os.path.dirname(os.path.abspath(sys.argv[0]))
            for cand in (resource("sets.db"), os.path.join(here, "sets.db")):
                if os.path.exists(cand):
                    self.sdb = sets_core.SetsDB(cand)
                    n = self.sdb.db.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
                    self.log(f"Sets catalogue ready: {n:,} sets (Sets tab).")
                    self.q.put(("sets_ready", None))
                    break
            else:
                self.log("No sets catalogue built in - put the Rebrickable zip next to build.bat and rebuild.")
        except Exception as e:
            self.log(f"Couldn't open the library: {e}")

    @staticmethod
    def _num(var):
        try:
            return round(float(var.get()), 3)
        except Exception:
            return 0.0

    def _save_settings(self):
        try:
            self.settings.update(out=self.out_var.get(), stud=self._num(self.stud_var),
                                 tube=self._num(self.tube_var))
            with open(settings_path(), "w") as f:
                json.dump(self.settings, f, indent=1)
        except Exception:
            pass

    def _close(self):
        self._save_settings()
        self.root.destroy()

    # ---------- browsing ----------
    def _fill_categories(self):
        cats = self.lib.categories(plain_only=not self.all_var.get())
        total = sum(n for _, n in cats)
        self._cat_names = {f"{c}  ({n:,})": c for c, n in cats}
        values = [f"{ALL}  ({total:,})"] + list(self._cat_names)
        self.cat_box.configure(values=values)
        # keep the current category if it's still there
        cur = self._current_cat()
        match = next((v for v, c in self._cat_names.items() if c == cur), None)
        self.cat_var.set(match or values[0])

    def _current_cat(self):
        return getattr(self, "_cat_names", {}).get(self.cat_var.get())

    def _toggle_all(self):
        if self.lib:
            self._fill_categories()
            self.refresh_list()

    def _search_soon(self):
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(250, self.refresh_list)

    def refresh_list(self):
        self._search_job = None
        if not self.lib:
            return
        rows = self.lib.browse(self._current_cat(), self.search_var.get(),
                               plain_only=not self.all_var.get(), limit=3000)
        self.tree.delete(*self.tree.get_children())
        for num, cat, desc in rows:
            self.tree.insert("", "end", iid=num, values=(num, desc.lstrip("~=_|"), cat))
        self.count_lbl.configure(text=f"{len(rows):,} parts" + ("  (first 3,000 shown)" if len(rows) >= 3000 else ""))

    def add_selected(self):
        cur = self.parts_txt.get("1.0", "end").split()
        for item in self.tree.selection():
            num = self.tree.item(item, "values")[0]
            if num not in cur:
                self.parts_txt.insert("end", ("\n" if self.parts_txt.get("1.0", "end").strip() else "") + num)
                cur.append(num)

    # ---------- preview ----------
    def _on_select(self):
        sel = self.tree.selection()
        if not sel or not self.lib:
            return
        vals = self.tree.item(sel[0], "values")
        self.request_preview(vals[0], vals[1])

    def request_preview(self, num, desc, rgb=None, colour_name=""):
        self.preview_req += 1
        req = self.preview_req
        if num in self.mesh_cache:
            v, f = self.mesh_cache[num]
            self._show_preview(num, desc, v, f, rgb, colour_name)
            return
        self.pv_title.configure(text=f"{num}  -  {desc}")
        self.pv_info.configure(text="")
        self.preview.show_message("Building preview...")
        threading.Thread(target=self._build_preview, args=(req, num, desc, rgb, colour_name), daemon=True).start()

    def _build_preview(self, req, num, desc, rgb=None, colour_name=""):
        try:
            v, f, _, _ = core.part_to_mesh(self.lib, num)
            self.mesh_cache[num] = (v, f)
            if len(self.mesh_cache) > 60:
                self.mesh_cache.pop(next(iter(self.mesh_cache)))
            self.q.put(("preview", (req, num, desc, v, f, rgb, colour_name)))
        except Exception as e:
            self.q.put(("preview_err", (req, num, f"Can't preview this one: {e}")))

    def _show_preview(self, num, desc, verts, faces, rgb=None, colour_name=""):
        size = verts.max(axis=0) - verts.min(axis=0)
        self.pv_title.configure(text=f"{num}  -  {desc}" + (f"   ({colour_name})" if colour_name else ""))
        self.pv_info.configure(text=f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm   ·   "
                                    f"{len(faces):,} triangles")
        self.preview.set_mesh(verts, faces, rgb)

    # ---------- output ----------
    def browse_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or default_out())
        if d:
            self.out_var.set(d)

    def open_folder(self):
        d = self.out_var.get()
        os.makedirs(d, exist_ok=True)
        try:
            os.startfile(d)
        except Exception:
            messagebox.showinfo(APP, d)

    def generate(self):
        if self.busy:
            return
        if not self.lib:
            messagebox.showinfo(APP, "The parts library is still loading - give it a moment.")
            return
        nums = [n for n in re.split(r"[\s,;]+", self.parts_txt.get("1.0", "end")) if n]
        if not nums:
            sel = self.tree.selection()
            nums = [self.tree.item(s, "values")[0] for s in sel]
        if not nums:
            messagebox.showinfo(APP, "Pick a part from the list (or type a part number in the make list) first.")
            return
        self.busy = True
        self.gen_btn.configure(state="disabled")
        self._save_settings()
        out, stud, tube = self.out_var.get(), self._num(self.stud_var), self._num(self.tube_var)
        threading.Thread(target=self._run, args=(nums, out, stud, tube), daemon=True).start()

    def _run(self, nums, out, stud, tube):
        made = 0
        for i, n in enumerate(nums, 1):
            self.q.put(("progress", (i - 1, len(nums))))
            try:
                r = core.generate(self.lib, n, out, stud, tube)
                if not r["ok"]:
                    msg = f"{n}: not in the library."
                    if r["suggest"]:
                        msg += "  Did you mean: " + ", ".join(r["suggest"])
                    self.log(msg)
                    continue
                w, d, h = r["size"]
                line = f'{r["number"]}: {r["desc"].lstrip("~=_|")}  ->  {w:.1f} x {d:.1f} x {h:.1f} mm  [{r["sealed"]}]'
                if r["desc"].startswith("~Moved to"):
                    line += "  (old number - library points it at the new one)"
                self.log(line)
                if r["missing"]:
                    self.log("    some pieces of this part are missing from the library: " + ", ".join(r["missing"]))
                made += 1
            except Exception as e:
                self.log(f"{n}: failed - {e}")
                traceback.print_exc()
        self.q.put(("progress", (len(nums), len(nums))))
        self.log(f"Done - {made} STL file(s) saved to {out}")
        self.q.put(("done", None))


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
