"""Analyse en arrière-plan (Bibliothèque ▸ Non analysés, carte de la barre latérale), boutons du
lecteur (grille, options du son), « Afficher dans la bibliothèque »."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")

from djsync.db import UsbDrive  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .demo_fixture import make_demo_usb  # noqa: E402
from .qt_util import close_window, find, make_window, pump  # noqa: E402
from .test_ui_smoke import FakeService  # noqa: E402


def _app(tmp_path, monkeypatch, analysed_song=False):
    usb = make_demo_usb(tmp_path, analysed_song=analysed_song)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(), monkeypatch)
    assert pump(window, 6, lambda: window.ctrl.has_library)
    return window


@pytest.fixture
def demo(tmp_path, monkeypatch):
    window = _app(tmp_path, monkeypatch)
    yield window
    close_window(window)


@pytest.fixture
def demo_grid(tmp_path, monkeypatch):
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg absent")
    window = _app(tmp_path, monkeypatch, analysed_song=True)
    yield window
    close_window(window)


def _slow(ctrl, gate):
    real = ctrl.library.analyze_tracks

    def slow(ids, **kw):                                # la file attend : on peut observer l'état « en cours »
        while not gate:
            time.sleep(0.02)
        return real(ids, **kw)

    ctrl.library.analyze_tracks = slow


def test_unanalysed_section_and_background_analysis(demo):
    from PySide6.QtWidgets import QApplication

    from djsync.ui.views.library_view import TODO

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    assert TODO in lib._items and lib._items[TODO].text(0).rstrip().endswith("10")

    demo.views["home"]._analysis()                      # Accueil ▸ Analyser : ouvre la section
    assert pump(demo, 2, lambda: lib.current == TODO)
    assert demo.current == "library"
    assert lib.table.total == 10 and "10" in lib.analyse_btn.text()
    assert lib.analyse_btn.isVisible()

    gate = []
    _slow(demo.ctrl, gate)
    lib._analyse_all()
    q = demo.ctrl.analysis
    assert q.running and q.total == 10
    assert pump(demo, 2, lambda: demo.an_box.isVisible())               # carte de la barre latérale
    assert lib.analyse_btn.text() == "Stop analysis"
    # pas de fenêtre modale : on peut changer d'onglet pendant l'analyse
    assert QApplication.activeModalWidget() is None
    demo.show_view("search")
    demo.show_view("library")
    # ajouter des sons pendant qu'elle tourne : à la suite, sans doublon
    demo.ctrl.analyze([int(lib.table.displayed_iids()[0])])
    assert q.total == 10
    gate.append(True)
    assert pump(demo, 30, lambda: not q.running)
    assert q.done == 10
    assert pump(demo, 4, lambda: not demo.an_box.isVisible())
    assert not demo.errors


def test_stop_analysis_empties_the_queue(demo):
    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    gate = []
    _slow(demo.ctrl, gate)
    lib.show_unanalysed()
    lib._analyse_all()
    q = demo.ctrl.analysis
    demo.ctrl.stop_analysis()
    assert q.cancelled and not q.pending
    gate.append(True)
    assert pump(demo, 20, lambda: not q.running)
    assert q.done < 10
    assert not demo.errors


def test_player_buttons_grid_editor_and_reveal(demo_grid):
    from PySide6.QtWidgets import QApplication

    from djsync.ui.grid_editor import GridEditor

    app = demo_grid
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    bar = app.player_bar
    assert not bar.grid_btn.isEnabled()                     # rien en lecture
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    lib._play(str(target.content_id))
    assert pump(app, 4, lambda: bar.grid_btn.isEnabled())
    bar._edit_grid()
    assert pump(app, 4, lambda: find(app, GridEditor) is not None)
    ed = find(app, GridEditor)
    assert pump(app, 4, lambda: bool(ed.beats))
    assert QApplication.activeModalWidget() is None         # non modale : l'appli reste utilisable
    ed.grab()                                               # dessin de la forme d'onde et de la grille
    before = ed.beats[ed.selected][2]
    ed._shift(10)
    assert ed.beats[ed.selected][2] == before + 10 and ed.save_btn.isEnabled()
    ed._reset()
    ed.close()
    app.ctrl.player.stop()

    # « Afficher dans la bibliothèque »
    app.show_view("search")
    bar._show_in_library(target)
    assert app.current == "library"
    assert pump(app, 2, lambda: lib.table.selected_iids() == [str(target.content_id)])
    assert not app.errors
