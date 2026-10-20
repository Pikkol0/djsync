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
    assert TODO in lib._items and lib._items[TODO].text(1) == "10"

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


def test_player_buttons_grid_editor_page_and_reveal(demo_grid):
    from PySide6.QtWidgets import QApplication

    from djsync.analysis import grid as G
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
    app.show_view("search")
    bar._edit_grid()
    assert pump(app, 4, lambda: app.grid_editor is not None)
    ed = app.grid_editor
    assert isinstance(ed, GridEditor) and ed.window() is app            # une page, pas une fenêtre
    assert app.stack.currentWidget() is ed
    assert pump(app, 4, lambda: bool(ed.beats))
    assert QApplication.activeModalWidget() is None
    ed.grab()                                               # dessin de la forme d'onde et de la grille

    # décalages ±1 / ±10 / ±100 ms
    before = ed.beats[ed.selected][2]
    ed._shift(100)
    assert ed.beats[ed.selected][2] == before + 100 and ed.save_btn.isEnabled()
    ed._shift(-100)
    # glisser sur la forme d'onde : le curseur d'écoute suit
    w = ed.canvas.width()
    ed.press(w * 0.25)
    first = ed.cursor_ms
    ed.press(w * 0.6, dragging=True)
    assert ed.cursor_ms > first
    ed.release()
    # début de mesure exactement sur le curseur
    cursor = ed.beats[3][2] + 37
    ed.cursor_ms = cursor
    ed._bar_here()
    assert ed.beats[ed.selected][2] == cursor and ed.beats[ed.selected][0] == 1
    # BPM x 2 puis / 2
    bpm = sorted(b[1] for b in ed.beats)[len(ed.beats) // 2]
    n = len(ed.beats)
    ed._scale(2.0)
    assert abs(sorted(b[1] for b in ed.beats)[len(ed.beats) // 2] - 2 * bpm) <= 1 and len(ed.beats) > 1.8 * n
    ed._scale(0.5)
    assert abs(sorted(b[1] for b in ed.beats)[len(ed.beats) // 2] - bpm) <= 1
    assert G.nearest(ed.beats, ed.cursor_ms) >= 0

    app.show_view("library")                                # changer d'onglet cache la page…
    bar._edit_grid()                                        # …la rouvrir garde les modifications
    assert pump(app, 2, lambda: app.grid_editor is ed and app.stack.currentWidget() is ed)
    assert ed.beats != ed.original
    ed.close()                                              # retour à l'onglet d'avant
    assert app.grid_editor is None and app.current == "search"
    app.ctrl.player.stop()

    # « Afficher dans la bibliothèque »
    bar._show_in_library(target)
    assert app.current == "library"
    assert pump(app, 2, lambda: lib.table.selected_iids() == [str(target.content_id)])
    assert not app.errors


def test_downloads_and_analysis_page(demo_grid):
    """V0.3.1 : « Downloads & analysis » : tableau des analyses (non analysés + recherche dans toute la
    bibliothèque), réanalyse d'une sélection, icône d'éditeur de grille sur les sons analysés."""
    app = demo_grid
    app.show_view("downloads")
    view = app.views["downloads"]
    assert app._nav["downloads"].text().startswith("Downloads && analysis")
    assert pump(app, 6, lambda: view.an_table.total == 10)            # les 10 sons non analysés
    assert all(not r.data.is_analysed for r in view.an_table.all_rows())
    assert "10" in view.analyse_btn.text()
    view.search.setText("grid test")                                   # toute la bibliothèque, filtrée
    assert pump(app, 2, lambda: len(view.an_table.displayed_rows()) == 1)
    row = view.an_table.displayed_rows()[0]
    assert row.data.is_analysed and row.values["grid"]
    view._cell_click(row.iid, "grid")                                  # icône à droite : éditeur de grille
    assert pump(app, 4, lambda: app.grid_editor is not None)
    assert app.grid_editor.track.content_id == row.data.content_id
    app.grid_editor.close()
    view.search.setText("")
    assert pump(app, 2, lambda: view.an_table.total == 10)
    assert not app.errors
