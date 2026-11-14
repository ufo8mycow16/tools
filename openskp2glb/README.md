# openskp2glb  (the default SketchUp converter)

SketchUp (.skp) to .glb using the OpenSKP library (MIT, github.com/iamahsanmehmood/openskp, v1.5.0 C++).
Reads every SketchUp version OpenSKP knows - SketchUp 3 up to 2025, old and new file formats.

    ./openskp2glb in.skp out.glb

- textures embedded, repeated components stored once and reused (instanced glTF nodes)
- `openskp2glb` here is a prebuilt Linux x64 binary; if it won't run, `sh build.sh` rebuilds it offline from
  `src_archives/` (OpenSKP source + its three add-ons: miniz, tinygltf, flatbuffers - their licences are inside the zips)

Chosen over our own `skp2glb/` on 14 Nov 2026: it converted all 37 of OpenSKP's sample files (SketchUp 3 to 2021)
where ours managed 8 (ours only reads 2021+), and on the newer files it kept more of the materials and textures
(e.g. 15 textures vs our 1 on the biggest sample). `skp2glb/` stays as a backup.
