"""BrickForge - type a LEGO part number, get a printable STL.

Part shapes come from the LDraw Parts Library (www.ldraw.org), CC BY 4.0.
Plain studs, no logos.
"""
import json, os, queue, re, sys, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ldraw_core as core

APP = "BrickForge"
VERSION = "1.0"


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
    for cand in (resource("ldraw_lib.zip"),
                 os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ldraw_lib.zip"),
                 os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "complete.zip")):
        if os.path.exists(cand):
            return cand
    return None


class App:
    def __init__(self, root):
        self.root = root
        self.lib = None
        self.q = queue.Queue()
        self.busy = False
        self.settings = {"out": default_out(), "stud": 0.0, "tube": 0.0}
        try:
            with open(settings_path()) as f:
                self.settings.update(json.load(f))
        except Exception:
            pass

        root.title(f"{APP} {VERSION} - LEGO part to STL")
        root.geometry("900x680")
        root.minsize(760, 560)
        self._build()
        self.log("Loading parts library...")
        threading.Thread(target=self._load_lib, daemon=True).start()
        root.after(100, self._poll)
        root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- layout ----------
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(3, weight=1)

        # left: part numbers to make
        left = ttk.LabelFrame(main, text="Part numbers to make (one per line, or separated by commas)")
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", **pad)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.parts_txt = tk.Text(left, height=10, width=30, font=("Consolas", 11), undo=True)
        self.parts_txt.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        ttk.Button(left, text="Clear", command=lambda: self.parts_txt.delete("1.0", "end")).grid(
            row=1, column=0, sticky="w", padx=6, pady=(0, 6))
        self.gen_btn = ttk.Button(left, text="Generate STLs", command=self.generate)
        self.gen_btn.grid(row=1, column=1, sticky="e", padx=6, pady=(0, 6))

        # right: search
        right = ttk.LabelFrame(main, text="Find a part by name or number")
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", **pad)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        ent = ttk.Entry(right, textvariable=self.search_var, font=("Segoe UI", 11))
        ent.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ent.bind("<Return>", lambda e: self.search())
        ttk.Button(right, text="Search", command=self.search).grid(row=0, column=1, padx=6)
        cols = ("num", "desc")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=12)
        self.tree.heading("num", text="Part")
        self.tree.heading("desc", text="Description")
        self.tree.column("num", width=90, stretch=False)
        self.tree.column("desc", width=300)
        self.tree.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(6, 0), pady=(0, 6))
        sb = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=2, sticky="ns", pady=(0, 6))
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda e: self.add_selected())
        ttk.Button(right, text="Add selected to list  (or double-click)", command=self.add_selected).grid(
            row=2, column=0, columnspan=2, sticky="e", padx=6, pady=(0, 6))

        # settings
        opts = ttk.LabelFrame(main, text="Fit and output")
        opts.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
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
        ttk.Button(opts, text="Browse...", command=self.browse).grid(row=1, column=6, padx=4)
        ttk.Button(opts, text="Open folder", command=self.open_folder).grid(row=1, column=7, padx=(0, 6))

        # log
        logf = ttk.LabelFrame(main, text="Progress")
        logf.grid(row=3, column=0, columnspan=2, sticky="nsew", **pad)
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.log_txt = tk.Text(logf, height=8, font=("Consolas", 10), state="disabled", wrap="word")
        self.log_txt.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log_txt.yview)
        lsb.grid(row=0, column=1, sticky="ns", pady=6)
        self.log_txt.configure(yscrollcommand=lsb.set)
        self.progress = ttk.Progressbar(logf, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))

        ttk.Label(main, foreground="#777",
                  text="Part shapes from the LDraw Parts Library (www.ldraw.org), CC BY 4.0. "
                       "LEGO is a trademark of the LEGO Group, which does not sponsor this program.").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=8)

    # ---------- helpers ----------
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
                elif kind == "results":
                    self.tree.delete(*self.tree.get_children())
                    for num, desc in val:
                        self.tree.insert("", "end", values=(num, desc))
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _load_lib(self):
        path = find_library()
        if not path:
            self.log("Couldn't find the LDraw library. Put complete.zip next to BrickForge and restart.")
            return
        try:
            self.lib = core.Library(path)
            n = len(self.lib.load_index())
            self.log(f"Library ready: {n:,} parts. Type part numbers on the left, or search on the right.")
        except Exception as e:
            self.log(f"Couldn't open the library: {e}")

    def _save_settings(self):
        try:
            self.settings.update(out=self.out_var.get(), stud=self._num(self.stud_var),
                                 tube=self._num(self.tube_var))
            with open(settings_path(), "w") as f:
                json.dump(self.settings, f, indent=1)
        except Exception:
            pass

    @staticmethod
    def _num(var):
        try:
            return round(float(var.get()), 3)
        except Exception:
            return 0.0

    def _close(self):
        self._save_settings()
        self.root.destroy()

    # ---------- actions ----------
    def browse(self):
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

    def search(self):
        if not self.lib:
            return
        words = self.search_var.get()
        res = self.lib.search(words)
        self.q.put(("results", res))
        self.log(f'Search "{words}": {len(res)} found' + (" (showing first 500)" if len(res) >= 500 else ""))

    def add_selected(self):
        for item in self.tree.selection():
            num = self.tree.item(item, "values")[0]
            cur = self.parts_txt.get("1.0", "end").strip()
            self.parts_txt.insert("end", ("\n" if cur else "") + num)

    def generate(self):
        if self.busy:
            return
        if not self.lib:
            messagebox.showinfo(APP, "The parts library is still loading - give it a moment.")
            return
        nums = [n for n in re.split(r"[\s,;]+", self.parts_txt.get("1.0", "end")) if n]
        if not nums:
            messagebox.showinfo(APP, "Type at least one part number first, e.g. 3001")
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
                line = f'{r["number"]}: {r["desc"]}  ->  {w:.1f} x {d:.1f} x {h:.1f} mm'
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
