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
- Type part numbers on the left (one per line or comma separated), press
  Generate STLs. Files land in Documents\BrickForge STLs unless you change it.
- Don't know the number? Search on the right ("brick 2 x 4", "technic beam",
  "6 x 16"), double-click a result to add it.
- Fit: Stud size / Tube size in mm. 0 is standard. If bricks are too tight,
  try -0.05 or -0.1; too loose, +0.05 or +0.1.
- Parts are placed flat on the bed, studs up, centred. Plain studs, no logos.
- Bambu Studio may say the model has errors and offer to fix them - say yes.
  The library's shapes are made for drawing, not printing, so they often have
  tiny seams the slicer tidies up automatically.
- Printed parts (stickers, torso prints etc.) come out as the plain shape.

UPDATING THE LIBRARY
Download a newer complete.zip from ldraw.org, drop it in the folder and run
build.bat again.

Part shapes: LDraw Parts Library, www.ldraw.org, licensed CC BY 4.0.
