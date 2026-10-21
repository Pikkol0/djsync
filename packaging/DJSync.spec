# PyInstaller: pyinstaller packaging/DJSync.spec   (run on WINDOWS, from the project root)
# Builds dist/DJSync.exe, a single file. Copy it to the drive (root or DJSync/ folder) with
#   ffmpeg.exe, ffprobe.exe, deno.exe next to it (added to the PATH at start-up).
# NOT yet validated on Windows.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for pkg in ("yt_dlp", "ytmusicapi", "sqlcipher3", "pygame", "mutagen", "pyrekordbox"):   # numpy : hook PyInstaller natif
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

# PySide6: PyInstaller's own hook keeps only the Qt modules actually imported (Core, Gui, Widgets).
a = Analysis(["../app.py"], pathex=[".."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork"])
pyz = PYZ(a.pure)
# Native splash screen: shown by the exe while it unpacks (the slow part of a one-file build);
# closed by DJSync as soon as its window is ready (djsync/ui/splash.close_native).
splash = Splash("splash.png", binaries=a.binaries, datas=a.datas, text_pos=None)
# Exe icon: DJSync logo in the default colour. Both images come from tools/export_logos.py.
exe = EXE(pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [], name="DJSync", console=False,
          upx=False, icon="djsync.ico")
