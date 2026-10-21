#!/usr/bin/env bash
# Audio-only FFmpeg for Windows (ffmpeg.exe + ffprobe.exe, ~6 MB instead of ~150 MB for a full build),
# cross-compiled on Linux with mingw-w64. Used by .github/workflows/windows.yml.
#
#   sudo apt-get install -y gcc-mingw-w64-x86-64 nasm make
#   packaging/build_ffmpeg.sh out/            # -> out/ffmpeg.exe, out/ffprobe.exe, out/FFMPEG_LICENSE.txt
#
# Only what DJSync and yt-dlp use: read m4a/mp3/flac/wav/aiff/ogg/opus/webm, write m4a (AAC) and
# mp3 (LAME, LGPL), raw PCM to a pipe (playback, analysis), loudness measure (ebur128) and gain.
# The result is LGPL (no --enable-gpl).
set -euo pipefail

OUT="$(mkdir -p "${1:-out}" && cd "${1:-out}" && pwd)"
WORK="${WORK:-$(mktemp -d)}"
FFMPEG_TAG="${FFMPEG_TAG:-n7.1.1}"
LAME_URL="${LAME_URL:-http://archive.ubuntu.com/ubuntu/pool/main/l/lame/lame_3.100.orig.tar.gz}"
HOST=x86_64-w64-mingw32
PREFIX="$WORK/prefix"
JOBS="$(nproc)"

cd "$WORK"
# ---- LAME (MP3 encoder), static
if [ ! -d lame-3.100 ]; then
  curl -sSfL -o lame.tgz "$LAME_URL"
  tar xzf lame.tgz
fi
(cd lame-3.100 && { make distclean >/dev/null 2>&1 || true; } && ./configure --host=$HOST --prefix="$PREFIX" --enable-static --disable-shared \
   --disable-frontend --disable-decoder --disable-gtktest --disable-analyzer-hooks >/dev/null \
 && make -j"$JOBS" >/dev/null && make install >/dev/null)

# ---- FFmpeg
[ -d ffmpeg ] || git clone -q --depth 1 --branch "$FFMPEG_TAG" https://github.com/FFmpeg/FFmpeg ffmpeg
cd ffmpeg
make distclean >/dev/null 2>&1 || true
./configure \
  --target-os=mingw32 --arch=x86_64 --cross-prefix=$HOST- --pkg-config=false \
  --prefix="$PREFIX" --extra-cflags="-I$PREFIX/include -O2" --extra-ldflags="-L$PREFIX/lib -static" \
  --enable-static --disable-shared --disable-debug --disable-doc --disable-ffplay \
  --disable-autodetect --disable-network --disable-everything --enable-small \
  --enable-ffmpeg --enable-ffprobe --enable-swresample --enable-libmp3lame \
  --enable-protocol=file,pipe \
  --enable-demuxer=mov,mp3,aac,flac,wav,aiff,ogg,matroska,pcm_s16le,pcm_f32le \
  --enable-muxer=mp4,ipod,mov,mp3,adts,wav,null,pcm_s16le,pcm_f32le,ogg,opus \
  --enable-decoder=aac,aac_latm,alac,mp3,mp3float,flac,opus,vorbis,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f32be,pcm_u8 \
  --enable-encoder=aac,libmp3lame,pcm_s16le,pcm_f32le,flac \
  --enable-parser=aac,aac_latm,mpegaudio,flac,opus,vorbis \
  --enable-bsf=aac_adtstoasc \
  --enable-filter=aresample,aformat,anull,volume,ebur128,atrim,pan,null,anullsrc,asetpts,apad \
  >/dev/null
make -j"$JOBS" >/dev/null
$HOST-strip ffmpeg.exe ffprobe.exe
cp ffmpeg.exe ffprobe.exe "$OUT/"
cp COPYING.LGPLv2.1 "$OUT/FFMPEG_LICENSE.txt"
ls -la "$OUT"
