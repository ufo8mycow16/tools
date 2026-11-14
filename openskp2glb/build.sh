#!/bin/sh
# Rebuild openskp2glb from the archives in src_archives/ - no network needed.
# usage: sh build.sh            (leaves ./openskp2glb next to this script)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mktemp -d)
cd "$W"
tar xzf "$HERE/src_archives/openskp-cpp-1.5.0.tar.gz"
for z in miniz tinygltf flatbuffers; do mkdir $z; unzip -q "$HERE/src_archives/$z.zip" -d $z; done
cmake -S openskp-cpp-1.5.0 -B build -DCMAKE_BUILD_TYPE=Release -DOPENSKP_BUILD_TESTS=OFF \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
  -DFETCHCONTENT_SOURCE_DIR_MINIZ="$(ls -d "$W"/miniz/*/)" \
  -DFETCHCONTENT_SOURCE_DIR_TINYGLTF="$(ls -d "$W"/tinygltf/*/)" \
  -DFETCHCONTENT_SOURCE_DIR_FLATBUFFERS="$(ls -d "$W"/flatbuffers/*/)" >/dev/null
cmake --build build -j"$(nproc)" >/dev/null
g++ -std=c++17 -O2 -Iopenskp-cpp-1.5.0/include -Ibuild/include "$HERE/openskp2glb.cpp" build/libOpenSkp.a -o "$HERE/openskp2glb"
strip "$HERE/openskp2glb"
rm -rf "$W"
echo "built $HERE/openskp2glb"
