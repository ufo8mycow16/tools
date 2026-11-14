// openskp2glb - SketchUp (.skp, any version OpenSKP reads: v3 .. 2025) -> .glb, with textures, instancing kept.
// Thin wrapper over the OpenSKP C++ library (MIT, github.com/iamahsanmehmood/openskp).
// usage: openskp2glb in.skp out.glb
#include <iostream>
#include <openskp/openskp.hpp>
#include <openskp/instanced_glb.hpp>

int main(int argc, char* argv[]) {
  if (argc != 3) { std::cerr << "usage: openskp2glb in.skp out.glb\n"; return 2; }
  try {
    const auto scene = openskp::SkpFile::open(argv[1]).build_instanced_scene();
    openskp::InstancedGlbOptions opt;
    opt.textures = true;
    openskp::export_instanced_glb(scene, argv[2], opt);
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
