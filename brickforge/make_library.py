"""Packs the bits of the LDraw complete.zip that BrickForge needs into ldraw_lib.zip,
plus a ready-made part list for the search box."""
import re, sys, zipfile


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def main(src="complete.zip", dst="ldraw_lib.zip"):
    zin = zipfile.ZipFile(src)
    keep, index = [], []
    for info in zin.infolist():
        low = info.filename.lower()
        if info.is_dir():
            continue
        if low.endswith(".dat") and ("/parts/" in low or "/p/" in low):
            keep.append(info)
            parts = low.split("/")
            if len(parts) >= 2 and parts[-2] == "parts":
                first = zin.read(info).decode("utf-8", "replace").split("\n", 1)[0].strip()
                desc = first[1:].strip() if first.startswith("0") else ""
                index.append((parts[-1][:-4], desc))
        elif low.endswith(("careadme.txt", "calicense4.txt")):
            keep.append(info)
    # real parts first, then old/moved ones (descriptions starting with ~)
    index.sort(key=lambda x: (x[1].startswith("~"), natural(x[0])))
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for i, info in enumerate(keep):
            zout.writestr(info.filename, zin.read(info))
            if i % 2000 == 0:
                print(f"  packed {i:,} / {len(keep):,} files")
        zout.writestr("parts_index.tsv", "\n".join(f"{n}\t{d}" for n, d in index))
    print(f"Library packed: {len(index):,} parts, {len(keep):,} files -> {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])
