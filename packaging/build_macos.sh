#!/usr/bin/env bash
# Builds DJSync-macOS.dmg on a Mac (Apple silicon), exactly like the GitHub workflow does.
# Useful when GitHub's Mac machines are busy. Needs: Xcode command line tools (xcode-select --install),
# Python 3.10+ (python.org), git. Takes ~15 minutes the first time (FFmpeg is compiled once).
#
#   git clone https://github.com/Pikkol0/djsync.git && cd djsync
#   packaging/build_macos.sh                    # -> out/DJSync-macOS.dmg (+ .sha256)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

echo "== 1/6 Python environment"
"$PY" -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt pyinstaller dmgbuild

echo "== 2/6 Audio-only FFmpeg (compiled once, kept in .ffmpeg-mac)"
if [ ! -x .ffmpeg-mac/ffmpeg ]; then
  TARGET=native WORK="$ROOT/.ffmpeg-work" packaging/build_ffmpeg.sh .ffmpeg-mac
fi

echo "== 3/6 DJSync.app"
export DJSYNC_VERSION="$(python -c 'import djsync; print(djsync.__version__)')"
rm -rf build dist
pyinstaller --noconfirm packaging/DJSync.spec

echo "== 4/6 Bundled tools"
T=dist/DJSync.app/Contents/MacOS/tools
mkdir -p "$T"
cp .ffmpeg-mac/ffmpeg .ffmpeg-mac/ffprobe .ffmpeg-mac/FFMPEG_LICENSE.txt "$T/"
curl -sSfL -o "$T/qjs" https://github.com/quickjs-ng/quickjs/releases/latest/download/qjs-darwin-arm64
chmod +x "$T/ffmpeg" "$T/ffprobe" "$T/qjs"
codesign --force --deep -s - dist/DJSync.app

echo "== 5/6 Self-test"
usb="$(mktemp -d)"
ditto dist/DJSync.app "$usb/DJSync.app"
DJSYNC_SELFTEST="$usb/selftest.json" QT_QPA_PLATFORM=offscreen "$usb/DJSync.app/Contents/MacOS/DJSync" || true
python packaging/check_selftest.py "$usb/selftest.json" > /dev/null && echo "self-test OK"

echo "== 6/6 Disk image"
mkdir -p out
tiffutil -cathidpicheck packaging/dmg_background.png packaging/dmg_background@2x.png -out "$usb/bg.tiff"
dmgbuild -s packaging/dmg_settings.py -D app=dist/DJSync.app -D background="$usb/bg.tiff" "DJSync" out/DJSync-macOS.dmg
hdiutil verify out/DJSync-macOS.dmg > /dev/null
(cd out && shasum -a 256 DJSync-macOS.dmg > DJSync-macOS.dmg.sha256)
echo
echo "Done: $ROOT/out/DJSync-macOS.dmg ($(du -h out/DJSync-macOS.dmg | cut -f1))"
