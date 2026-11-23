"""BrickForge sets: browse LEGO sets (Rebrickable catalogue, built into sets.db by
make_sets.py) and generate every printable piece of a set, sorted into colour folders."""
import os, re, sqlite3
from collections import defaultdict

import ldraw_core as core


class SetsDB:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)

    def themes(self):
        rows = self.db.execute("SELECT theme, COUNT(*) FROM sets GROUP BY theme").fetchall()
        tops = defaultdict(int)
        for t, n in rows:
            tops[t.split(" > ")[0]] += n
        return sorted(tops.items(), key=lambda x: x[0].lower())

    def search(self, text="", theme=None, limit=3000):
        q = "SELECT set_num, name, year, theme, num_parts FROM sets WHERE 1=1"
        args = []
        for w in text.split():
            q += " AND (set_num LIKE ? OR name LIKE ? OR theme LIKE ?)"
            args += [w + "%" if w[:1].isdigit() else f"%{w}%", f"%{w}%", f"%{w}%"]
        if theme:
            q += " AND (theme = ? OR theme LIKE ?)"
            args += [theme, theme + " > %"]
        q += " ORDER BY year, set_num LIMIT ?"
        args.append(limit)
        rows = self.db.execute(q, args).fetchall()
        # exact set number first ("171" -> 171-1)
        t = text.strip().lower()
        if t:
            rows.sort(key=lambda r: (r[0].lower().split("-")[0] != t and r[0].lower() != t,))
        return rows

    def info(self, set_num):
        return self.db.execute("SELECT set_num, name, year, theme, num_parts FROM sets WHERE set_num=?",
                               (set_num,)).fetchone()

    def contents(self, set_num, spares=False, minifigs=True):
        """List of dicts, one per part+colour."""
        q = """SELECT sp.rb_part, p.ld_part, p.name, sp.color_id, c.name, c.rgb, c.trans,
                      SUM(sp.qty), sp.source
               FROM set_parts sp JOIN parts p ON p.rb_part = sp.rb_part
               JOIN colors c ON c.id = sp.color_id
               WHERE sp.set_num = ?"""
        if not spares:
            q += " AND sp.spare = 0"
        if not minifigs:
            q += " AND sp.source != 'minifig'"
        q += " GROUP BY sp.rb_part, sp.color_id ORDER BY c.name, p.name"
        out = []
        for rb, ld, name, cid, cname, rgb, trans, qty, src in self.db.execute(q, (set_num,)):
            out.append(dict(rb=rb, ld=ld, name=name, color_id=cid, color=cname, rgb=rgb,
                            trans=bool(trans), qty=int(qty), source=src))
        return out


def instructions_url(set_num):
    return "https://www.lego.com/service/buildinginstructions/" + set_num.split("-")[0]


def unprintable_reason(row):
    n = row["name"].lower()
    if row["ld"] is None:
        if "sticker" in n:
            return "sticker sheet"
        return "no 3D shape for this part in the LDraw library"
    for w in ("string", "rubber", "hose", "chain", "cloth", "fabric", "electric", "motor", "battery"):
        if w in n:
            return "printable, but the real one is " + ("flexible" if w in ("string", "rubber", "hose", "chain", "cloth", "fabric") else "electrical")
    return ""


def generate_set(lib, sdb, set_num, out_dir, stud=0.0, tube=0.0, spares=False, minifigs=True,
                 seal=True, log=print, progress=None, cancel=None):
    info = sdb.info(set_num)
    rows = sdb.contents(set_num, spares, minifigs)
    folder = os.path.join(out_dir, core.safe_filename(f"{set_num} - {info[1]}"))
    os.makedirs(folder, exist_ok=True)
    # group by LDraw shape + colour (two catalogue numbers can share one shape)
    groups = defaultdict(lambda: dict(qty=0, names=set(), rbs=set()))
    skipped = []
    for r in rows:
        if r["ld"] is None:
            skipped.append(r)
            continue
        g = groups[(lib.follow_moved(r["ld"]), r["color"])]
        g["qty"] += r["qty"]
        g["names"].add(r["name"])
        g["rbs"].add(r["rb"])
    shapes = sorted({ld for ld, _ in groups})
    meshes = {}
    done = 0
    log(f"{set_num} {info[1]}: {len(shapes)} different shapes, {len(groups)} shape/colour combinations")
    for i, ld in enumerate(shapes):
        if cancel and cancel():
            log("Stopped.")
            break
        if progress:
            progress(i, len(shapes))
        try:
            V, F, o, missing = core.part_to_mesh(lib, ld, stud, tube)
            how = ""
            if seal:
                V, F, o, how = core.make_printable(V, F, o)
            meshes[ld] = (V, F, how)
        except Exception as e:
            log(f"  {ld}: failed - {e}")
    lines = []
    for (ld, colour), g in sorted(groups.items(), key=lambda x: (x[0][1], x[0][0])):
        if ld not in meshes:
            continue
        V, F, how = meshes[ld]
        desc = lib.description(ld).lstrip("~=_|")
        cdir = os.path.join(folder, core.safe_filename(colour))
        os.makedirs(cdir, exist_ok=True)
        name = core.safe_filename(f"{ld} - {desc} - print {g['qty']}") + ".stl"
        core.write_stl(os.path.join(cdir, name), V, F, f"{ld} {desc}")
        done += g["qty"]
        lines.append(f"  {g['qty']:4d} x  {colour:<22} {ld:<12} {desc}   [{how}]")
    if progress:
        progress(len(shapes), len(shapes))
    # parts list
    with open(os.path.join(folder, "Parts list.txt"), "w", encoding="utf-8") as f:
        f.write(f"{set_num}  {info[1]}  ({info[2]}, {info[3]})\n")
        f.write(f"Building instructions: {instructions_url(set_num)}\n\n")
        f.write(f"PRINTED - {done} pieces, sorted into a folder per colour:\n")
        f.write("\n".join(lines) + "\n")
        warn = [r for r in rows if r["ld"] and unprintable_reason(r)]
        if warn:
            f.write("\nPRINTED, BUT CHECK THESE:\n")
            for r in warn:
                f.write(f"  {r['qty']:4d} x  {r['color']:<22} {r['name']}  - {unprintable_reason(r)}\n")
        if skipped:
            f.write("\nNOT PRINTED:\n")
            for r in skipped:
                f.write(f"  {r['qty']:4d} x  {r['color']:<22} {r['name']}  - {unprintable_reason(r)}\n")
    log(f"Done - {done} pieces in {len(groups)} files, sorted by colour, in {folder}")
    if skipped:
        log("Not printed: " + ", ".join(f"{r['qty']} x {r['name']}" for r in skipped))
    return folder
