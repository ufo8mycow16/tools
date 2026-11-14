# skp2glb

SketchUp (.skp, 2021 or later) to .glb, no SketchUp or Blender needed. Our own code, written from the file-format
notes published with skppy (github.com/dantedex/skppy, MIT; `tags.json` is derived from its `skp_tags.yaml`).

    python3 skp2glb.py in.skp out.glb

- metres, Y up; textures packed in; repeated components stored once and reused (like Blender's export)
- faces drawn once and two-sided, except where SketchUp painted front and back differently (then two one-sided faces)
- smooth shading across SketchUp's smoothed edges (under 40 degrees), hidden faces/components left out
- older (pre-2021) SketchUp files aren't supported yet - re-save them in a newer SketchUp, or use Blender + skppy
