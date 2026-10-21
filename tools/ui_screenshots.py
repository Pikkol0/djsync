"""OUTIL DE DÉVELOPPEMENT (pas livré dans l'exécutable) : captures de chaque onglet à plusieurs
tailles de fenêtre, sur une fausse clé de démonstration, sans réseau ni écran.

    python tools/ui_screenshots.py out_dir [--sizes 900x600,1280x800] [--lang fr] [--dialogs]

Les captures sont faites par Qt (QWidget.grab) sur la plateforme « offscreen » : pas besoin d'Xvfb.
Sert à vérifier la mise en page (fenêtre réduite, zoom, langues) à chaque version.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.demo_fixture import make_demo_usb  # noqa: E402


def _pump(seconds: float, until=None) -> None:
    from PySide6.QtWidgets import QApplication

    end = time.time() + seconds
    while time.time() < end:
        QApplication.instance().processEvents()
        if until is not None and until():
            return
        time.sleep(0.02)


def capture(widget, path: Path) -> None:
    _pump(0.3)
    widget.grab().save(str(path))


def _visible(cls):
    from PySide6.QtWidgets import QApplication

    return next((w for w in QApplication.topLevelWidgets() if isinstance(w, cls) and w.isVisible()), None)


def shoot_dialogs(app, out: Path) -> None:
    from djsync.ui.analysis_dialog import AnalysisDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.help_dialog import HelpDialog

    app.resize(1280, 800)
    app.show_view("library")
    lib = app.views["library"]
    _pump(1.5)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    lib._play(str(target.content_id))
    _pump(2.5)
    capture(app, out / "player_waveform.png")
    app.ctrl.player.stop()
    # Bibliothèque ▸ Non analysés pendant une analyse en arrière-plan (carte de la barre latérale)
    gate = threading.Event()
    real = app.ctrl.library.analyze_tracks
    app.ctrl.library.analyze_tracks = lambda ids, **kw: (gate.wait(20), real(ids, **kw))[1]
    lib.show_unanalysed()
    lib._analyse_all()
    q = app.ctrl.analysis
    q.done, q.current = 3, "Daft Punk - One More Time"
    app.ctrl._emit("analysis")
    _pump(1.0)
    capture(app, out / "library_unanalysed.png")
    app.ctrl.stop_analysis()
    gate.set()
    _pump(20, lambda: not q.running)
    app.ctrl.library.analyze_tracks = real
    app.open_grid_editor(target)                        # V0.2.4 : page de la fenêtre principale
    _pump(1.5)
    capture(app, out / "grid_editor.png")
    app.grid_editor.close()
    _pump(0.3)
    for opener, cls, name in (
        (app.open_help, HelpDialog, "dialog_help"),
        (lib._duplicates, DuplicatesDialog, "dialog_duplicates"),
        (lambda: AnalysisDialog(lib, app.ctrl, [target]), AnalysisDialog, "dialog_analysis"),
    ):
        opener()
        _pump(1.5)
        win = _visible(cls)
        if win is not None:
            capture(win, out / f"{name}.png")
            win.close()
            _pump(0.3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--sizes", default="860x560,1280x800,1680x1050")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--theme", default=None)
    ap.add_argument("--zoom", type=int, default=100)
    ap.add_argument("--dialogs", action="store_true", help="also capture Help, Analysis, Duplicates, Grid editor, player")
    ap.add_argument("--local", action="store_true", help="no USB drive: Rekordbox library of this computer (demo)")
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

    controller.find_usb_drives = lambda: [] if args.local else [UsbDrive(root=usb, label="DEMO")]
    controller.MusicService = FakeService
    from djsync.ui.app import DJSyncApp

    settings = Settings()
    if args.local:                          # base de démonstration de pyrekordbox (tests/data/rekordbox6)
        import shutil

        import djsync.db.local_library as local_library

        db_dir = tmp / "Pioneer" / "rekordbox"
        db_dir.mkdir(parents=True)
        for f in (ROOT / "tests" / "data" / "rekordbox6").glob("*"):
            if f.suffix != ".md":
                shutil.copy(f, db_dir / f.name)
        local_library.rekordbox_running = lambda: False
        settings.local_db_dir, settings.local_music_dir = str(db_dir), str(tmp / "Music")
    settings.language = args.lang
    settings.zoom = args.zoom
    if args.theme:
        settings.theme = args.theme
    app = DJSyncApp(settings)
    app.reveal()
    _pump(8, lambda: app.ctrl.has_library)
    for size in args.sizes.split(","):
        w, h = (int(v) for v in size.split("x"))
        app.resize(w, h)
        for key in app.views:
            app.show_view(key)
            if key == "search":
                app.views[key].entry.setText("daft punk")
                app.views[key].run_search()
            _pump(0.8)
            capture(app, args.out / f"{size}_{key}.png")
    if args.dialogs:
        shoot_dialogs(app, args.out)
    app.close()
    print("screenshots:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
