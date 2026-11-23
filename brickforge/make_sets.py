"""Builds sets.db (SQLite) for BrickForge from the Rebrickable catalogue download
(the zip of CSVs: sets, themes, colors, parts, inventories, inventory_parts, ...).

Each set's contents are flattened (minifigs and sets-within-sets included) and every
Rebrickable part number is matched to an LDraw shape where one exists.
Usage: python make_sets.py all_downloads.zip ldraw_lib.zip sets.db
"""
import csv, io, os, re, sqlite3, sys, zipfile
from collections import defaultdict


def read_csv(z, name):
    member = next((n for n in z.namelist() if n.lower().endswith(name)), None)
    if member is None:
        raise SystemExit(f"  {name} is missing from the catalogue zip")
    data = z.read(member)
    if member.lower().endswith(".gz"):
        import gzip
        data = gzip.decompress(data)
    return csv.DictReader(io.StringIO(data.decode("utf-8-sig")))


def ldraw_part_names(lib_zip):
    names = set()
    with zipfile.ZipFile(lib_zip) as z:
        for n in z.namelist():
            low = n.lower()
            parts = low.split("/")
            if low.endswith(".dat") and len(parts) >= 2 and parts[-2] == "parts":
                names.add(parts[-1][:-4])
    return names


def main(catalogue="all_downloads.zip", lib_zip="ldraw_lib.zip", out="sets.db"):
    z = zipfile.ZipFile(catalogue)
    ld = ldraw_part_names(lib_zip)
    print(f"  LDraw shapes: {len(ld):,}")

    # ---------- part number matching ----------
    ld_map, bl_map = {}, {}
    for r in read_csv(z, "part_mappings.csv"):
        if r["ext_system"] == "LD":
            ld_map.setdefault(r["part_num"], r["ext_id"].lower())
        elif r["ext_system"] == "BL":
            bl_map.setdefault(r["part_num"], r["ext_id"].lower())
    rel = defaultdict(list)
    for r in read_csv(z, "part_relationships.csv"):
        c, p, t = r["child_part_num"], r["parent_part_num"], r["rel_type"]
        if t in ("P", "M", "T"):          # printed -> plain, mould variant -> main, pattern -> plain
            rel[c].append(p)
        elif t == "A":                    # alternates both ways
            rel[c].append(p)
            rel[p].append(c)
    cache = {}

    def direct(p):
        low = p.lower()
        for cand in (low, ld_map.get(p), bl_map.get(p)):
            if cand and cand in ld:
                return cand
        return None

    def resolve(p, depth=0):
        if p in cache:
            return cache[p]
        cache[p] = None
        hit = direct(p)
        if not hit and depth < 3:
            for q in rel.get(p, ()):
                hit = resolve(q, depth + 1)
                if hit:
                    break
        if not hit:
            # strip print/pattern codes and mould letters: 3009b -> 3009, 3626cpr123 -> 3626c -> 3626
            for pat in (r"(pr|pat|px|ps)\d+.*$", r"[a-z]+$"):
                q = re.sub(pat, "", p.lower())
                if q and q != p.lower():
                    hit = direct(q) or (resolve(q, depth + 1) if depth < 3 else None)
                    if hit:
                        break
        if not hit:
            # plain minifig torso / hips-and-legs assemblies: any colour, same shape
            for pat, generic in ((r"^973c", "973c01"), (r"^970c", "970c00"), (r"^76382c", "973c01")):
                if re.match(pat, p.lower()) and generic in ld:
                    hit = generic
                    break
        cache[p] = hit
        return hit

    # ---------- themes, sets, colours, names ----------
    themes = {r["id"]: (r["name"], r["parent_id"]) for r in read_csv(z, "themes.csv")}

    def theme_path(tid):
        out, seen = [], set()
        while tid and tid in themes and tid not in seen:
            seen.add(tid)
            name, parent = themes[tid]
            out.append(name)
            tid = parent
        return " > ".join(reversed(out))

    db_path = out
    if os.path.exists(db_path):
        os.remove(db_path)
    db = sqlite3.connect(db_path)
    db.executescript("""
        CREATE TABLE sets(set_num TEXT PRIMARY KEY, name TEXT, year INT, theme TEXT, num_parts INT, img_url TEXT);
        CREATE TABLE colors(id INT PRIMARY KEY, name TEXT, rgb TEXT, trans INT);
        CREATE TABLE parts(rb_part TEXT PRIMARY KEY, name TEXT, ld_part TEXT);
        CREATE TABLE ld_colors(ld_id INT PRIMARY KEY, color_id INT);
        CREATE TABLE set_parts(set_num TEXT, rb_part TEXT, color_id INT, qty INT, spare INT, source TEXT);
    """)
    sets = {}
    for r in read_csv(z, "sets.csv"):
        sets[r["set_num"]] = r
    db.executemany("INSERT INTO sets VALUES (?,?,?,?,?,?)",
                   [(s, r["name"], int(r["year"] or 0), theme_path(r["theme_id"]), int(r["num_parts"] or 0),
                     r.get("img_url") or "")
                    for s, r in sets.items()])
    db.executemany("INSERT INTO colors VALUES (?,?,?,?)",
                   [(int(r["id"]), r["name"], r["rgb"], 1 if r["is_trans"] in ("True", "t", "1") else 0)
                    for r in read_csv(z, "colors.csv")])
    part_names = {r["part_num"]: r["name"] for r in read_csv(z, "parts.csv")}
    ldc = {}
    for r in read_csv(z, "color_mappings.csv"):
        if r["ext_system"] == "LD" and r["ext_id"].lstrip("-").isdigit():
            ldc.setdefault(int(r["ext_id"]), int(r["id"]))
    db.executemany("INSERT INTO ld_colors VALUES (?,?)", list(ldc.items()))

    # ---------- inventories (newest version of each set / minifig) ----------
    inv_of = {}
    for r in read_csv(z, "inventories.csv"):
        s, v = r["set_num"], int(r["version"] or 1)
        if s not in inv_of or v > inv_of[s][1]:
            inv_of[s] = (r["id"], v)
    wanted = {iid for iid, _ in inv_of.values()}
    inv_parts = defaultdict(list)
    for r in read_csv(z, "inventory_parts.csv"):
        if r["inventory_id"] in wanted:
            inv_parts[r["inventory_id"]].append(
                (r["part_num"], int(r["color_id"]), int(r["quantity"]), r["is_spare"] in ("True", "t", "1")))
    inv_figs = defaultdict(list)
    for r in read_csv(z, "inventory_minifigs.csv"):
        inv_figs[r["inventory_id"]].append((r["fig_num"], int(r["quantity"])))
    inv_sets = defaultdict(list)
    for r in read_csv(z, "inventory_sets.csv"):
        inv_sets[r["inventory_id"]].append((r["set_num"], int(r["quantity"])))

    def contents(set_num, mult=1, source="set", depth=0):
        """(rb_part, color, qty, spare, source) for everything in a set, nested sets/minifigs expanded."""
        if set_num not in inv_of or depth > 4:
            return
        iid = inv_of[set_num][0]
        for p, c, q, sp in inv_parts.get(iid, ()):
            yield p, c, q * mult, sp, source
        for fig, q in inv_figs.get(iid, ()):
            yield from contents(fig, mult * q, "minifig", depth + 1)
        for sub, q in inv_sets.get(iid, ()):
            yield from contents(sub, mult * q, source if source != "set" else "set", depth + 1)

    rows, used = [], set()
    for k, s in enumerate(sets):
        agg = defaultdict(int)
        for p, c, q, sp, src in contents(s):
            agg[(p, c, int(sp), src)] += q
        for (p, c, sp, src), q in agg.items():
            rows.append((s, p, c, q, sp, src))
            used.add(p)
        if len(rows) > 200000:
            db.executemany("INSERT INTO set_parts VALUES (?,?,?,?,?,?)", rows)
            rows = []
        if k % 5000 == 0:
            print(f"  sets {k:,} / {len(sets):,}")
    db.executemany("INSERT INTO set_parts VALUES (?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO parts VALUES (?,?,?)",
                   [(p, part_names.get(p, ""), resolve(p)) for p in used])
    db.execute("CREATE INDEX sp_set ON set_parts(set_num)")
    db.commit()
    tot = db.execute("SELECT SUM(qty) FROM set_parts WHERE spare=0").fetchone()[0] or 0
    hit = db.execute("SELECT SUM(sp.qty) FROM set_parts sp JOIN parts p ON p.rb_part=sp.rb_part "
                     "WHERE sp.spare=0 AND p.ld_part IS NOT NULL").fetchone()[0] or 0
    db.execute("VACUUM")
    db.close()
    print(f"Sets database: {len(sets):,} sets, {len(used):,} different parts, "
          f"{100 * hit / max(tot, 1):.1f}% of pieces have a printable shape -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
