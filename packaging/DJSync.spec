# PyInstaller: pyinstaller packaging/DJSync.spec   (from the project root, on the target system)
#
# V1.1.0: Windows (folder packed into DJSync.exe, see below), macOS (DJSync.app) and Linux (DJSync folder).
#
# V1.0.0: builds the APPLICATION folder (dist/DJSync: DJSync.exe + _internal + tools). Users never see
# it: the GitHub workflow packs it into ONE file, DJSync.exe = small launcher + this folder zipped
# (packaging/launcher, packaging/pack_single_exe.py). On first launch, the launcher extracts it next
# to itself into the hidden folder .djsync/app (once, or after an update), then starts it.
#
# Tools added by the workflow into dist/DJSync/tools/:
#   ffmpeg.exe + ffprobe.exe  audio-only build (~6 MB instead of ~150 MB)
#   qjs.exe                   QuickJS-NG, JavaScript runtime for yt-dlp (~2.5 MB instead of Deno ~100 MB)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

# Python code is compiled into ONE archive inside the exe: only real data files (and native
# libraries) are copied next to it. collect_all() would also copy every .py source as a loose file
# (≈ 1 000 for yt-dlp's site extractors alone): useless, and slow to unzip onto a USB stick.
# yt-dlp ships its own PyInstaller hook (hidden imports, yt-dlp-ejs JavaScript files).
import sys

datas, binaries, hidden = [], [], []
for pkg in ("ytmusicapi", "mutagen", "pyrekordbox", "miniaudio", "sqlcipher3"):    # numpy: native hook
    datas += collect_data_files(pkg)               # .py excluded by default
    binaries += collect_dynamic_libs(pkg)
    hidden += collect_submodules(pkg)
if sys.platform == "darwin":
    hidden += ["MediaPlayer"]             # 1.2.3 : touches multimédia / « À l'écoute » (pyobjc)
hidden += ["_cffi_backend"]               # native part of cffi, used by miniaudio (player): not auto-detected
datas += copy_metadata("yt-dlp")           # version of the built-in engine (djsync/core/engine.py)
datas += [("../LICENSE", "."), ("../THIRD_PARTY_NOTICES.md", ".")]     # GPL-3.0 + bundled components

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
import sys

pyz = PYZ(a.pure)
if sys.platform == "win32":
    # Native splash screen while Python starts (closed by djsync/ui/splash.close_native).
    splash = Splash("splash.png", binaries=a.binaries, datas=a.datas, text_pos=None)
    exe = EXE(pyz, a.scripts, splash, [], exclude_binaries=True, name="DJSync", console=False, upx=False,
              icon="djsync.ico")
    coll = COLLECT(exe, splash.binaries, a.binaries, a.datas, name="DJSync", upx=False)
else:
    # macOS / Linux: no native splash (needs Tcl/Tk); the Qt splash shows as soon as Qt starts.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DJSync", console=False, upx=False,
              icon="djsync_icon.png")
    coll = COLLECT(exe, a.binaries, a.datas, name="DJSync", upx=False)
    if sys.platform == "darwin":
        app = BUNDLE(coll, name="DJSync.app", icon="djsync_icon.png", bundle_identifier="io.github.pikkol0.djsync",
                     info_plist={"CFBundleShortVersionString": __import__("os").environ.get("DJSYNC_VERSION", "1.0").split("-")[0],
                                 "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0"})
