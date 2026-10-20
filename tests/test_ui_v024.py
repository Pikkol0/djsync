"""V0.2.4 : analyse en arrière-plan (Bibliothèque ▸ Non analysés, carte de la barre latérale), boutons
du lecteur (grille, options du son), fenêtres à la bonne taille avec un zoom, pastille rafraîchie.
    xvfb-run -a python -m pytest -q tests/test_ui_v024.py
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")

from djsync.db import UsbDrive  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .demo_fixture import make_demo_usb  # noqa: E402
from .test_ui_smoke import FakeService, pump  # noqa: E402
from .test_ui_v020 import _find  # noqa: E402


def _app(tmp_path, monkeypatch, analysed_song=False):
    usb = make_demo_usb(tmp_path, analysed_song=analysed_song)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    from djsync.ui.app import DJSyncApp

    try:
        window = DJSyncApp(Settings())
    except tk.TclError as exc:
        pytest.skip(f"pas d'écran disponible : {exc}")
    errors = []
    window.report_callback_exception = lambda *a: errors.append(a[1])
    window.errors = errors
    window.maxsize(4000, 4000)
    window.geometry("1280x800+0+0")
    assert pump(window, 6, lambda: window.ctrl.has_library)
    pump(window, 3, lambda: window._compact is False)
    return window


@pytest.fixture
def demo(tmp_path, monkeypatch):
    window = _app(tmp_path, monkeypatch)
    yield window
    window.ctrl.shutdown()
    window.destroy()


@pytest.fixture
def demo_grid(tmp_path, monkeypatch):
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg absent")
    window = _app(tmp_path, monkeypatch, analysed_song=True)
    yield window
    window.ctrl.shutdown()
    window.destroy()


def test_unanalysed_section_and_background_analysis(demo):
    from djsync.ui.views.library_view import TODO

    demo.show("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    assert lib.nav.exists(TODO) and lib.nav.item(TODO, "text").rstrip().endswith("10")

    demo.views["home"]._analysis()                      # Accueil ▸ Analyser : ouvre la section
    assert pump(demo, 2, lambda: lib.current == TODO)
    assert lib.table.total == 10 and "10" in lib.analyse_btn.cget("text")
    assert lib.analyse_btn.winfo_ismapped()

    gate = []
    real = demo.ctrl.library.analyze_tracks

    def slow(ids, **kw):                                # la file attend : on peut observer l'état « en cours »
        while not gate:
            import time

            time.sleep(0.02)
        return real(ids, **kw)

    demo.ctrl.library.analyze_tracks = slow
    lib._analyse_all()
    q = demo.ctrl.analysis
    assert q.running and q.total == 10
    assert pump(demo, 2, lambda: demo.an_box.winfo_ismapped())          # carte de la barre latérale
    assert lib.analyse_btn.cget("text") == "Stop analysis"
    # pas de fenêtre modale : on peut changer d'onglet et de playlist pendant l'analyse
    assert demo.grab_current() is None
    demo.show("search")
    demo.show("library")
    # ajouter des sons pendant qu'elle tourne : à la suite, sans doublon
    demo.ctrl.analyze([int(lib.table.displayed_iids()[0])])
    assert q.total == 10
    gate.append(True)
    assert pump(demo, 30, lambda: not q.running)
    assert q.done == 10
    assert pump(demo, 4, lambda: not demo.an_box.winfo_ismapped())
    assert not demo.errors


def test_stop_analysis_empties_the_queue(demo):
    demo.show("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    gate = []
    real = demo.ctrl.library.analyze_tracks

    def slow(ids, **kw):
        import time

        while not gate:
            time.sleep(0.02)
        return real(ids, **kw)

    demo.ctrl.library.analyze_tracks = slow
    lib.show_unanalysed()
    lib._analyse_all()
    q = demo.ctrl.analysis
    demo.ctrl.stop_analysis()
    assert q.cancelled and not q.pending
    gate.append(True)
    assert pump(demo, 20, lambda: not q.running)
    assert q.done < 10
    assert not demo.errors


def test_player_buttons_and_dialog_sizes(demo_grid):
    from djsync.ui import theme
    from djsync.ui.analysis_dialog import AnalysisDialog
    from djsync.ui.grid_editor import GridEditor

    app = demo_grid
    app.show("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    bar = app.player_bar
    assert bar.grid_btn.cget("state") == "disabled"          # rien en lecture
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    lib._play(str(target.content_id))
    assert pump(app, 4, lambda: bar.grid_btn.cget("state") == "normal")
    app.show("search")
    bar._edit_grid()
    assert pump(app, 4, lambda: app.grid_editor is not None)
    ed = app.grid_editor
    assert isinstance(ed, GridEditor) and ed.winfo_toplevel() is app      # une page, pas une fenêtre
    assert pump(app, 4, lambda: bool(ed.beats))
    assert app.grab_current() is None
    ed._shift(10)
    app.show("library")                                     # changer d'onglet cache la page…
    bar._edit_grid()                                        # …la rouvrir garde les modifications
    assert pump(app, 2, lambda: app.grid_editor is ed) and ed.beats != ed.original
    ed.close()                                              # retour à l'onglet d'avant
    assert app.grid_editor is None and app.current == "search"
    app.ctrl.player.stop()

    # « Afficher dans la bibliothèque »
    app.show("search")
    bar._show_in_library(target)
    assert pump(app, 2, lambda: lib.table.selected_iids() == [str(target.content_id)])

    # zoom 145 % : la fenêtre grandit avec son contenu et reste dans l'écran
    theme.set_zoom(145, False, app)
    try:
        dlg = AnalysisDialog(lib, app.ctrl, [target])
        pump(app, 0.6)
        k = dlg._scaling()
        assert dlg.winfo_width() >= int(500 * 1.45 * k) - 2
        assert dlg.winfo_reqheight() <= dlg.winfo_height() + 2   # tout le contenu est visible
        assert 0 <= dlg.winfo_rootx() and dlg.winfo_rootx() + dlg.winfo_width() <= dlg.winfo_screenwidth()
        dlg.close()
    finally:
        theme.set_zoom(100, True, app)
    assert not app.errors


def test_badge_is_redrawn_when_the_key_appears(demo):
    """Pastille Camelot : après l'analyse, la ligne déjà affichée est redessinée avec la tonalité."""
    from djsync.ui.widgets import Row

    lib = demo.views["library"]
    demo.show("library")
    assert pump(demo, 4, lambda: lib.table.total == 10)
    table = lib.table
    row = next(r for r in table.all_rows() if not r.data.camelot)
    table._covered.add(row.iid)
    table._photos[row.iid] = object()
    new = Row(row.iid, dict(row.values), row.cover, row.tags, row.data, badge=("8A", "#ffffff"))
    table.set_rows([new if r.iid == row.iid else r for r in table.all_rows()])
    assert row.iid not in table._covered and row.iid not in table._photos
