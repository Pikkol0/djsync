# PyInstaller: pyinstaller packaging/DJSync.spec   (run on WINDOWS, from the project root)
#
# V0.5.0: "folder" build that LOOKS like a single file.
#   dist/DJSync/DJSync.exe        <- the only thing the user sees
#   dist/DJSync/.djsync/          <- everything else (Python, Qt, tools, settings), marked hidden
#                                    by DJSync at first launch (djsync/portable.py)
# Why not --onefile: a one-file exe unpacks ~250 MB to %TEMP% at EVERY launch (slow from a USB
# stick, leaves debris if killed). The folder build starts instantly and nothing is written to the PC.
#
# Tools (added by the GitHub workflow, .github/workflows/windows.yml), in .djsync/tools/:
#   ffmpeg.exe + ffprobe.exe  audio-only build (~6 MB instead of ~150 MB)
#   qjs.exe                   QuickJS-NG, JavaScript runtime for yt-dlp (~2.5 MB instead of Deno ~100 MB)
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hidden = [], [], []
for pkg in ("yt_dlp", "ytmusicapi", "sqlcipher3", "mutagen", "pyrekordbox", "miniaudio"):   # numpy: native hook
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h
for pkg in ("yt_dlp_ejs",):                # JavaScript solver used by yt-dlp for YouTube (optional at build)
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass
datas += copy_metadata("yt-dlp")           # version of the built-in engine (djsync/core/engine.py)

# Big packages that must never end up in the exe (pulled in by optional imports of dependencies).
EXCLUDES = [
    "tkinter", "cv2", "matplotlib", "scipy", "pandas", "IPython", "jupyter", "notebook", "pytest",
    "cryptography", "gi", "gtk", "PyQt5", "PyQt6", "pygame", "yaml", "greenlet", "lxml", "docutils",
    "setuptools", "pip", "wheel", "pkg_resources",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtNetwork", "PySide6.QtDBus", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg",
    "PySide6.QtPdf", "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtSql",
]

a = Analysis(["../app.py"], pathex=[".."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=EXCLUDES)
pyz = PYZ(a.pure)
# Native splash screen while Python starts (closed by djsync/ui/splash.close_native).
splash = Splash("splash.png", binaries=a.binaries, datas=a.datas, text_pos=None)
exe = EXE(pyz, a.scripts, splash, [], exclude_binaries=True, name="DJSync", console=False, upx=False,
          icon="djsync.ico", contents_directory=".djsync")
coll = COLLECT(exe, splash.binaries, a.binaries, a.datas, name="DJSync", upx=False)
