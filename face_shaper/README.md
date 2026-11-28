# Face Shaper (REV 1425, 26 Nov)

Glen's own slider page for a character's face - no Daz. A claude.ai artifact: the head in 3D over a lined-up
photo (fade, flip, turn), 64 plain-English Daz face sliders (sliders_g8m.json), undo, and SEND TO CLAUDE, which
writes the values to the artifact's db at `faces/<key>`.

- Chekov's page: https://claude.ai/artifact/Ajau4npssQojPELHL6179c (slug 4ed46060-1ad6-447b-8511-7391c673297b).
  Read what Glen sent: db_get slug, path faces/chekov.
- Make data for a page: `python3 export_head.py <character FBX> <basis.npy> <basis.json> sliders_g8m.json <photo>
  <photo marks json (eye corners R_out/R_in/L_in/L_out in photo px)> <outdir>` - basis = the 322 G8M head sliders
  built for the likeness work (Head Morphs, 200 Plus, Retouch, Spicy Fusion; tools/crew/chekov_build/README.md).
  Base64 head.bin/morphs.bin into head.txt/morphs.txt (artifacts don't serve .bin), copy page_template.html as
  index.html (change KEY and the title), publish_files, then declare {db:{rules:[{path:"",read:"admin",write:"owner"}]},user:{}}.
- Build Glen's values: X = original points + sum(value x slider delta) -> final_X.npy -> kmake_dsf.py ->
  g8_head_swap.py (keep the original face picture) -> make_jcm_data.py points -> bake_skin_ao.py.
- Overlay check: ov_render.py (XN=<points> NOHAIR=1) + ov_make.py = model lined up on the photo by the eye corners.
- Genesis 8 Male only so far (G8F/G9 need their own basis + slider list). Hair does not follow the sliders.

## In this tools repo
Copied from vulcan-fury (tools/crew/faceshaper/, REV 1425). Glen: "keep that tool somewhere, that's amazing ...
so much easier than daz3d". The helpers it leans on live in vulcan-fury's tools/crew/ (rtex/likeness readers,
g8_head_swap.py, make_jcm_data.py, bake_skin_ao.py) and the slider basis is built from the G8M morph packs stored
in vulcan-fury's assets/models/characters/_source/daz_packs/ - clone vulcan-fury alongside to use it.
kmake_dsf.py + kc.py here are Chekov's copies (paths at their tops point at the vulcan-fury clone and the character).
Works for any Daz Genesis 8 Male in any of Glen's games (Vulcan Fury, TWOK, Yesteryear...).

## Kirk (29 Nov 2026)
Kirk's page: https://claude.ai/artifact/KBkxcmi7vpLFX2jSSXBJGL (slug 93450633-4b8b-4855-9d37-53c4cd78cf2d), started from
his CURRENT in-game head (pass 4, miniature fit, kirk_face_clean picture) over Glen's yellow-tunic studio portrait.
Read what he sends: db_get that slug, path faces/kirk. Hair left off (his Trevor hair is a separate library piece).
`reuse_sliders_export.py` = shortcut when no rar tools are around: lifts the 64 sliders out of Chekov's published page
(morphs.txt + meta.json, read_file) back onto full G8M vertices and re-exports them for another G8M head. Kirk's head
set (3331 verts) sits wholly inside Chekov's (3370), so nothing is lost. Photo marks: kirk_photo_marks.json.
