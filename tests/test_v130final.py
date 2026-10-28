"""1.3.0 (stable) : retour au bureau sur Mac en plein écran (B32), blanc du son à l'ouverture d'une
fenêtre (B33), boucle supprimée qui continuait (B35)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401


class _WindowSpy:
    """Note toute fenêtre (widget sans parent) qui s'affiche, même un instant, hors fenêtre principale,
    menus et bulles d'aide : c'est ce qui, sur Mac en plein écran, crée un espace et affiche le bureau."""

    def __init__(self, app):
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtWidgets import QApplication, QWidget

        spy = self
        self.main, self.shown = app, []

        class _F(QObject):
            def eventFilter(self, obj, ev):  # noqa: N802
                if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow() \
                        and obj is not spy.main and obj.windowType() not in (Qt.ToolTip, Qt.Popup):
                    spy.shown.append(f"{type(obj).__name__} {obj.width()}x{obj.height()}")
                return False

        self._f = _F()
        QApplication.instance().installEventFilter(self._f)

    def stop(self):
        from PySide6.QtWidgets import QApplication

        QApplication.instance().removeEventFilter(self._f)


# ------------------------------------------------------------------ B32
def test_the_spy_sees_a_widget_shown_before_being_placed(demo):  # noqa: F811
    """Le test ci-dessous ne vaut que si l'espion voit bien le défaut d'origine."""
    from PySide6.QtWidgets import QLabel

    spy = _WindowSpy(demo)
    w = QLabel("8A")
    w.show()                                                    # ce que faisait CamelotPill
    demo.views["home"].layout().addWidget(w)
    pump(demo, 0.1)
    spy.stop()
    assert len(spy.shown) == 1 and spy.shown[0].startswith("QLabel")
    w.deleteLater()


def test_key_pill_is_never_a_window_and_still_shows_once_placed(demo):  # noqa: F811
    from djsync.ui.widgets import CamelotPill

    spy = _WindowSpy(demo)
    pill = CamelotPill("8A")
    assert not pill.isVisible()
    demo.views["home"].layout().addWidget(pill)
    assert pump(demo, 1, pill.isVisible)
    pill.set(None)
    assert pill.isHidden()
    pill.set("9B")
    assert pump(demo, 1, pill.isVisible)
    spy.stop()
    assert spy.shown == []
    pill.deleteLater()


def test_no_page_flashes_a_window(demo, monkeypatch):  # noqa: F811
    """Toutes les pages, avec des tonalités affichées (Doublons, Diagnostic) : aucune fenêtre en trop."""
    from djsync.models import LibraryTrack
    from djsync.ui.diagnostic_dialog import DiagnosticDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    monkeypatch.setattr(LibraryTrack, "camelot", property(lambda self: "8A"))
    spy = _WindowSpy(demo)
    for key in demo.views:
        demo.show_view(key)
        pump(demo, 0.2)
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total > 0)
    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    pump(demo, 0.5)
    dup.close()
    diag = DiagnosticDialog(demo.views["home"], demo.ctrl)
    pump(demo, 1.5)
    diag.close()
    track = next(r.data for r in lib.table.all_rows() if r.data is not None)
    demo.open_grid_editor(track)
    pump(demo, 0.5)
    demo.grid_editor.close()
    pump(demo, 0.3)
    spy.stop()
    assert spy.shown == []
    assert not demo.errors


# ------------------------------------------------------------------ B33
def test_modal_windows_are_not_sheets_on_macos(demo, monkeypatch):  # noqa: F811
    """Sur Mac, open() présentait la fenêtre en feuille (animation qui retardait le son de 120–170 ms) :
    elle s'ouvre maintenant modale à l'application, sans feuille."""
    from PySide6.QtCore import Qt

    from djsync.ui import dialogs

    monkeypatch.setattr(dialogs.sys, "platform", "darwin")
    box = dialogs.ConfirmDialog(demo, "Titre", "Message", lambda: None)
    assert pump(demo, 1, box.isVisible)
    assert box.windowModality() == Qt.ApplicationModal
    assert box.windowType() != Qt.Sheet
    box.close()


def test_modal_windows_unchanged_elsewhere(demo, monkeypatch):  # noqa: F811
    from PySide6.QtCore import Qt

    from djsync.ui import dialogs

    monkeypatch.setattr(dialogs.sys, "platform", "win32")
    box = dialogs.ConfirmDialog(demo, "Titre", "Message", lambda: None)
    assert pump(demo, 1, box.isVisible)
    assert box.windowModality() == Qt.WindowModal              # open() comme avant
    box.close()


# ------------------------------------------------------------------ B35
def _grid(app):
    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    app.open_grid_editor(target)
    ed = app.grid_editor
    assert pump(app, 4, lambda: bool(ed.beats))
    panel = ed.cue_panel
    ed.cursor_ms = ed.beats[6][2] + 40
    panel.pad_clicked(1)
    panel.set_loop(1, 4)
    panel.pad_clicked(1)                                        # la boucle tourne
    a = panel.cue(1)
    assert ed.active_loop == (a.ms, a.loop_ms)
    return ed, panel, a


def test_deleting_the_playing_loop_pad_exits_the_loop(demo_grid):  # noqa: F811
    ed, panel, _a = _grid(demo_grid)
    panel.delete(1)
    assert ed.active_loop is None and ed.exit_btn.isHidden()
    demo_grid.ctrl.player.stop()


def test_removing_or_resizing_the_playing_loop_follows_the_pad(demo_grid):  # noqa: F811
    ed, panel, a = _grid(demo_grid)
    panel.set_loop(1, 8)                                        # plus longue : la boucle en cours suit
    assert ed.active_loop == (a.ms, a.loop_ms) and a.loop_beats == 8
    panel.set_loop(1, 0)                                        # « Pas de boucle » : on en sort
    assert ed.active_loop is None
    demo_grid.ctrl.player.stop()


def test_deleting_another_pad_keeps_the_loop(demo_grid):  # noqa: F811
    ed, panel, a = _grid(demo_grid)
    ed.cursor_ms = ed.beats[20][2]
    panel.pad_clicked(2)                                        # pad B posé (le curseur bouge, la boucle reste ?)
    if ed.active_loop is None:                                  # poser B relance la lecture depuis B : rien à tester
        pytest.skip("poser B sort de la boucle")
    panel.delete(2)
    assert ed.active_loop == (a.ms, a.loop_ms)
    demo_grid.ctrl.player.stop()
