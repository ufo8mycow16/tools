# WoW converter (Glen's install -> Blender / glb / printable), built from WMV 1.1 knowledge

Glen's PC side does nothing clever: `fetch.py`/`fetch.bat` (in Documents\WoW Tools) copy byte ranges
listed in `requests.txt` out of `C:\Games\World of Warcraft\Data\data\data.###` into `out\`.
Everything else runs here.

1. Stage `.build.info`, the build config and `Data/data/*.idx`; `casc.load_idx`.
2. Encoding + root are fetched once, decoded and pickled (`encoding.pkl`, `root.pkl`).
   Root has several variants per file - pick the one that is installed (textures especially).
3. `plan.request_fids([...], path)` -> requests.txt; commit it, double-click fetch.bat, stage `out\<fid>.blte`.
4. `dump.py <m2 fid> <dir> [item texture fid]` -> mesh.npz + PNGs (`m2.py`, `blp.py`).
5. `blender -b --python wowbuild.py -- <dir> <outbase> 3 40 0.9` -> .blend + .glb with the HD pass
   (crease sharp edges and UV seams, Catmull-Clark, cage solved so the surface still passes through
   every original vertex = smoother but same shape). Add `raw` for the untouched model.
   Glen approved look: levels 3, crease angle 40, crease min 0.9.
6. `preview.py -- out.png a.glb b.glb` side-by-side render.

Gotchas: item textures (type 2) aren't in the model - look them up per item. Old palette BLPs: Pillow
gets them wrong, blp.py does them. Commit of requests.txt sometimes didn't land when reusing the
same staged path - use a fresh staged file name and force=true.
TODO: skeleton + animations to glb, character assembly (geosets, skin compositing, attachments), hair.
