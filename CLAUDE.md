# Glen's tools repo - read this first

Everything Claude builds that could be useful again goes here, so it isn't lost inside one project.
Glen (athrak) owns it; Claude maintains it. Keep this index up to date when adding a tool.

## Where the big things live (not in this repo)
- **Blender 4.2.23 LTS (Linux)**: orphan branch `tools-blender` of `ufo8mycow16/vulcan-fury`, split in 90 MB parts.
  `git clone --depth 1 --branch tools-blender --single-branch https://github.com/ufo8mycow16/vulcan-fury /tmp/bl`,
  `cat /tmp/bl/*.part* > /tmp/blender.tar.xz`, `tar -xf` into `/home/claude/blender` (`--strip-components=1`);
  run headless: `blender -b --python script.py -- args`.
- **WoW Model Viewer 1.1 (full source, Windows app)**: orphan branch `tools-wowmodelviewer` of this repo, 90 MB parts.
  Views/exports WoW models, textures, buildings from Glen's install (OBJ, PNG, BLP). Glen calls it an important tool.
  `git clone --depth 1 --branch tools-wowmodelviewer --single-branch https://github.com/ufo8mycow16/tools /tmp/wmv`,
  `cat /tmp/wmv/*.part* > /tmp/wmv.tar.gz`, `sha256sum -c` against `SHA256SUMS` (named wowmodelviewer-1.1.tar.gz), `tar -xzf`.
  Includes a Blender FBX import addon (`blender_addon/`) and CASC listfile (`ThirdParty/casclib/listfile/`).
- **VICE / xa source tarballs**: Glen supplies them (vice-3.10.tar.gz, xa-2.4.1.tar.gz); build with `vice_build/build_vice.sh`.

## Index
| folder | what | how |
|---|---|---|
| `openskp2glb/` | **Default SketchUp converter** (.skp, any version SketchUp 3 to 2025 -> .glb) - prebuilt wrapper over the OpenSKP library, textures + instancing on. Rebuilds offline from `src_archives/`. | `./openskp2glb in.skp out.glb` (or `sh build.sh` first) |
| `skp2glb/` | Backup converter. Our own SketchUp (.skp, 2021+) -> .glb converter (first written for Klingon Challenge, Nov 2026). Textures, components, smoothing kept. | `python3 skp2glb.py in.skp out.glb` |
| `monitor_remaster/` | Turns a converted SketchUp CRT monitor into a game-ready prop (Halcyon 1084, Late Night BBS): real plastic/grime materials, own badge, CRT screen with 0..1 UVs, bakes to one texture set. | `blender -b --python build_monitor.py -- in.glb outdir` then `bake_monitor.py -- outdir 2048`; `preview.py -- out.png file.glb\|.blend` (VIEW=34/front/back/badge) |
| `c64/` | Commodore 64 kit: `d64.py` (list + extract a .d64), `cpu6502.py` + `unpack.py` (run a packer in a tiny 6502 to get the unpacked memory), `dis6502.py` (disassembler), `vmon.py` (drive a running VICE: memory, screen grab, joystick, keys, snapshots), `c64gfx.py` (draw chars/sprites in C64 colours). | see each file's top |
| `wow_converter/` | WoW (Glen's install) -> .blend/.glb with an HD smoothing pass that keeps the shape. Reads CASC via a tiny fetcher on his PC. | see `wow_converter/README.md` |
| `brickforge/` | **BrickForge**: LEGO part number -> printable STL (Glen, Nov 2026). Windows tkinter app (category browser + search, spinnable depth-sorted 3D preview drawn with numpy, make list) over the LDraw library (CC BY 4.0, Glen supplies `complete.zip` from ldraw.org - too big for git). Fit tweaks for stud/tube width. Seals parts into one solid: `ldraw_seal.py` (own sealer: inside/outside ray test + rebuild flat surfaces under studs/tubes; ~30% of random parts, ~all basic bricks/plates/tiles) then `winrepair.py` (Windows Printing3D RepairAsync via pywinrt, same service as Bambu "Fix model" - Bambu source checked: FixModelByWin10.cpp). `ldraw_core.py` works headless here too. `make_6205_custom.py` = the hand-built 6205 that started it. Sets tab (v1.3): `make_sets.py` turns the Rebrickable CSV zip (Glen has all_downloads.zip; not in git) into sets.db (sets, colours, per-set parts with minifigs/subsets flattened, Rebrickable->LDraw matching via LD/BL mappings, mould/print/alternate relationships, plain minifig torso/legs -> 973c01/970c00; 98.3% of pieces matched). `sets_core.py` = browse + generate a whole set into colour folders. v1.5: "complete assembly" parts (e.g. train base with wheels+magnets) are broken into their separate pieces via Library.components() + ld_colors table, metal/magnets listed as not printed. v1.4: clicking a set fetches its Rebrickable picture (img_url, cached in %APPDATA%\BrickForge\set pictures, needs internet + pillow) into the preview pane. Glen's first sets: 171-1 train (Dave's childhood set) and 375-2 yellow castle. | Windows: drop `complete.zip` in, run `build.bat` -> `BrickForge.exe`. Here: `from ldraw_core import Library, generate; generate(Library('complete.zip'), '3001', 'out/')` |
| `vice_build/` | Build VICE headless here with no flex/dos2unix/xa installed + our log.c start-up crash fix. | `sh build_vice.sh vice.tar.gz xa.tar.gz` |

## VICE notes (learned the hard way)
- Run: `x64sc -default -directory <vice>/data -warp +sound -binarymonitor -binarymonitoraddress ip4://127.0.0.1:6502 -autostart game.d64`, then `vmon.Mon()`.
- Joystick through the monitor only works with the port's device set to **IO simulation** (id 37):
  `m.set_res_int('JoyPort2Device', 37)`; the lines are active-low (vmon.joy() inverts for you). Monitor port 1 = control port 2.
- `m.keys()` only reaches programs that read keys through the KERNAL; games scanning the keyboard directly won't see it.
- The joystick latch needs the emulator to run a moment (up to a frame) before the C64 sees it.
- In warp a few wall-clock seconds are minutes of game time - grab screens quickly after starting a game.
