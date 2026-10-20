"""OUTIL DE DÉVELOPPEMENT (pas livré dans l'exécutable) : captures de chaque onglet à plusieurs
tailles de fenêtre, sur une fausse clé de démonstration, sans réseau.

    xvfb-run -a -s "-screen 0 1920x1200x24" python tools/ui_screenshots.py out_dir [--sizes 900x600,1280x800]

Sous Windows : lancer simplement `python tools/ui_screenshots.py captures` (les captures utilisent
Pillow ImageGrab si ImageMagick `import` est absent).
Sert à vérifier la mise en page (fenêtre réduite, zoom, langues) à chaque version.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.demo_fixture import DEMO, make_demo_usb  # noqa: E402,F401


def capture(app, path: Path) -> None:
    app.update()
    time.sleep(0.25)
    app.update()
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    if shutil.which("import"):
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", str(path)], check=False)
    else:
        from PIL import ImageGrab

        ImageGrab.grab((x, y, x + w, y + h)).save(path)


def _pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def _toplevel(root, cls):
    for w in root.winfo_children():
        if isinstance(w, cls):
            return w
        hit = _toplevel(w, cls)
        if hit is not None:
            return hit
    return None


def capture_window(win, path: Path) -> None:
    win.update()
    x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
    if shutil.which("import"):
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", str(path)], check=False)
    else:
        from PIL import ImageGrab

        ImageGrab.grab((x, y, x + w, y + h)).save(path)


def shoot_dialogs(app, out: Path) -> None:
    from djsync.ui.analysis_dialog import AnalysisDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.help_dialog import HelpDialog

    app.geometry("1280x800+0+0")
    app.show("library")
    lib = app.views["library"]
    _pump(app, 1.5)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    lib._play(str(target.content_id))
    _pump(app, 2.5)
    capture(app, out / "player_waveform.png")
    app.ctrl.player.stop()
    # V0.2.4 : Bibliothèque ▸ Non analysés pendant une analyse en arrière-plan (carte de la barre latérale)
    import threading
    gate = threading.Event()
    real = app.ctrl.library.analyze_tracks
    app.ctrl.library.analyze_tracks = lambda ids, **kw: (gate.wait(20), real(ids, **kw))[1]
    lib.show_unanalysed()
    lib._analyse_all()
    q = app.ctrl.analysis
    q.done, q.current = 3, "Daft Punk - One More Time"
    app.ctrl._emit("analysis")
    _pump(app, 1.0)
    capture(app, out / "library_unanalysed.png")
    app.ctrl.stop_analysis()
    gate.set()
    end = time.time() + 20
    while q.running and time.time() < end:
        app.update()
        time.sleep(0.02)
    app.ctrl.library.analyze_tracks = real
    app.open_grid_editor(target)                        # V0.2.4 : page de la fenêtre principale
    _pump(app, 1.5)
    capture(app, out / "grid_editor.png")
    app.grid_editor.close()
    _pump(app, 0.3)
    for opener, cls, name in (
        (app.open_help, HelpDialog, "dialog_help"),
        (lambda: lib._duplicates(), DuplicatesDialog, "dialog_duplicates"),
        (lambda: AnalysisDialog(lib, app.ctrl, [target]), AnalysisDialog, "dialog_analysis"),
    ):
        opener()
        _pump(app, 1.5)
        win = _toplevel(app, cls)
        if win is not None:
            capture_window(win, out / f"{name}.png")
            win.close()
            _pump(app, 0.3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--sizes", default="860x560,1280x800,1680x1050")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--theme", default=None)
    ap.add_argument("--dialogs", action="store_true", help="also capture Help, Analysis, Duplicates, Grid editor, player")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="djsync_shots_"))
    os.environ["DJSYNC_HOME"] = str(tmp / "home")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    usb = make_demo_usb(tmp, analysed_song=args.dialogs)

    import djsync.ui.controller as controller
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    from tests.test_ui_smoke import FakeService

    controller.find_usb_drives = lambda: [UsbDrive(root=usb, label="DEMO")]
    controller.MusicService = FakeService
    from djsync.ui.app import DJSyncApp

    settings = Settings()
    settings.language = args.lang
    if args.theme:
        settings.theme = args.theme
    app = DJSyncApp(settings)
    end = time.time() + 8
    while time.time() < end and not app.ctrl.has_library:
        app.update()
        time.sleep(0.02)
    tabs = list(app.views)
    for size in args.sizes.split(","):
        app.geometry(f"{size}+0+0")
        for key in tabs:
            app.show(key)
            if key == "search" and hasattr(app.views[key], "entry"):
                entry = app.views[key].entry
                entry.delete(0, "end")
                entry.insert(0, "daft punk")
                getattr(app.views[key], "run_search", lambda: None)()
            for _ in range(40):
                app.update()
                time.sleep(0.02)
            capture(app, args.out / f"{size}_{key}.png")
    if args.dialogs:
        shoot_dialogs(app, args.out)
    app.ctrl.shutdown()
    app.destroy()
    print("screenshots:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
