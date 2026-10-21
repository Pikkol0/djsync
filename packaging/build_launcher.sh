#!/usr/bin/env bash
# Builds the single-file launcher (DJSync.exe without its payload) with mingw-w64, on Linux.
#   sudo apt-get install -y gcc-mingw-w64-x86-64
#   packaging/build_launcher.sh out/      # -> out/launcher.exe
# The application is appended afterwards by packaging/pack_single_exe.py.
set -euo pipefail
OUT="$(mkdir -p "${1:-out}" && cd "${1:-out}" && pwd)"
cd "$(dirname "$0")/launcher"
HOST=x86_64-w64-mingw32
$HOST-windres launcher.rc -O coff -o "$OUT/launcher_res.o"
$HOST-gcc -O2 -municode -mwindows -static -DMINIZ_NO_TIME -DNDEBUG \
  launcher.c miniz.c "$OUT/launcher_res.o" -lcomctl32 -o "$OUT/launcher.exe"
$HOST-strip "$OUT/launcher.exe"
rm -f "$OUT/launcher_res.o"
ls -la "$OUT/launcher.exe"
