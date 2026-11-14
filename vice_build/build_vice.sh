#!/bin/sh
# Build VICE (headless, no sound) in a cloud session that has no flex / dos2unix / xa and no network installs.
#   usage: sh build_vice.sh <vice-x.y.tar.gz> <xa-x.y.z.tar.gz> [workdir]
# Glen supplies both tarballs (vice from vice-emu.sourceforge.io, xa from floodgap.com/retrotech/xa).
# Result: <workdir>/vice-*/src/x64sc (C64) and src/c1541 (disk tool); ROMs are in <workdir>/vice-*/data.
set -e
VICE_TGZ=$1; XA_TGZ=$2; W=${3:-/home/claude/vice_build}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$W/bin" && cd "$W"
tar -xzf "$XA_TGZ" && (cd xa-* && make xa >/dev/null) && cp xa-*/xa bin/
cp "$HERE/flex" "$HERE/dos2unix" bin/ && chmod +x bin/*
tar -xzf "$VICE_TGZ"
cd vice-*
# VICE 3.10 crashes at start-up when its output isn't a terminal (log.c) - our fix:
patch -p1 < "$HERE/log_c_headless_fix.patch"
# flex: VICE ships the generated monitor lexer (src/monitor/mon_lex.c), so a do-nothing flex is enough
PATH="$W/bin:$PATH" ac_cv_prog_LEX=flex ac_cv_prog_lex_root=lex.yy ac_cv_lib_lex='none needed' \
  ./configure --enable-headlessui --without-pulse --without-alsa --disable-html-docs --disable-pdf-docs \
  --without-libcurl --disable-realdevice --disable-hardsid --without-flac --without-vorbis > configure.log
PATH="$W/bin:$PATH" make -j"$(nproc)" > make.log 2>&1
ls -la src/x64sc src/c1541
