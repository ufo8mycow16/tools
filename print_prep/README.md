# print_prep - game/Sketchfab models -> real printable props

First used for Glen's **Atiesh** staff topper (Nov 2026): Victor Guebel's Sketchfab Atiesh (CC-BY 4.0),
bird only, on a 25 mm dowel. Output went to `Documents\Atiesh` on Glen's PC.

The idea: game models keep their detail in the *texture*, which a printer can't see. So:
1. **Smooth** the low-poly pieces (`build_bird.py`: seal holes per piece, HD pass = creased Catmull-Clark with the
   cage solved to pass through the original points - same pass as wow_converter).
2. **Fuse** everything into one watertight solid with a voxel remesh (0.4 mm was plenty at 28 cm tall, ~1M tris,
   seconds on 2 cores). Add lathed parts first (post + dowel ferrule with the bore built in - no booleans needed).
3. **Carve the detail for real** (`feathers.py`): turn the normal map into a height map (`normal2height.py`),
   then every fused vertex looks up the nearest point on the smoothed UV'd copy, reads the height and moves
   in/out (0.7 mm looked right). Relief fades out at sharp edges (beak rims went saw-toothed without that)
   and where unmapped parts join.
4. `export_npz.py` checks watertight + volume; write 3MF with `brickforge/ldraw_core.write_3mf`
   (12 MB for 1M tris - stays under the 25 MB commit limit, STL wouldn't).

Other bits: `charms.py` = procedural small parts (disc with loop, gem ring + glue-in half gems, bored beads,
swept claws with wrapped bindings, 3.2 mm cord holes). `look.py` / `look_all.py` = quick clay/colour renders
in Blender; `render.py` = tiny numpy textured renderer when Blender isn't around.

`build_bird.py` is Atiesh-specific in its piece list (DROP/NODISP = connected-component ids of that model)
and ferrule sizes - copy and adjust for the next model.
