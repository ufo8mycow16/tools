BrickForge - LEGO part number to printable STL
===============================================

MAKING THE PROGRAM (once)
1. Put these files in one folder, e.g. C:\BrickForge :
     brickforge.py  ldraw_core.py  make_library.py  build.bat
2. Put the LDraw complete.zip in the same folder.
3. Double-click build.bat. It needs the internet for a minute to fetch two
   Python add-ons (numpy and PyInstaller), then packs everything up.
4. You get BrickForge.exe in that folder. The whole parts library is inside it,
   so you can copy the exe anywhere on its own and delete the rest if you like.

USING IT
- Browse the parts list on the left: pick a category (Brick, Plate, Tile,
  Slope, Technic...) and/or type in the search box to narrow it down
  ("2 x 4", "technic beam", "6205").
- Click a part to see it in the preview. Drag to spin it, mouse wheel to zoom,
  double-click to reset the view.
- Double-click a part (or press "Add to make list") to add it to the make list.
  You can also type part numbers straight into the make list.
- Press Generate STLs. Files land in Documents\BrickForge STLs unless you
  change it.
- The list hides printed, sticker, duplicate and old parts so it isn't
  cluttered - tick the box under the search to show them too.
- Fit: Stud size / Tube size in mm. 0 is standard. If bricks are too tight,
  try -0.05 or -0.1; too loose, +0.05 or +0.1.
- Parts are placed flat on the bed, studs up, centred. Plain studs, no logos.
- Sealing: the library's shapes are made for drawing, not printing (studs just
  sit on top of plates, seams don't quite meet). BrickForge seals each part
  into one solid before saving: first its own sealer (exact - bricks, plates,
  tiles), then for anything trickier the 3D-print repair built into Windows
  (the same one Bambu Studio's "Fix model" uses). The progress log says which.
  If it says "not sealed", Bambu Studio will offer to fix it - say yes.
- Printed parts (stickers, torso prints etc.) come out as the plain shape.

UPDATING THE LIBRARY
Download a newer complete.zip from ldraw.org, drop it in the folder and run
build.bat again.

Part shapes: LDraw Parts Library, www.ldraw.org, licensed CC BY 4.0.
