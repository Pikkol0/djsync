"""1.4.0 : zoom de l'interface au clavier et à la molette (C102), colonne « Playlists » (C103)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401
from .test_v130rc3 import _open_grid  # noqa: E402


# ------------------------------------------------------------------ C102
def _wheel(widget, dy, ctrl=True):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(widget.width() / 2, widget.height() / 2)
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy), Qt.NoButton,
                     Qt.ControlModifier if ctrl else Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_zoom_shortcuts_wheel_and_badge(demo):  # noqa: F811
    from djsync.ui import theme

    from .qt_util import pump

    keys = demo.zoom_keys
    texts = [x[0] for x in keys.shortcuts]
    assert len(texts) == len(set(texts)) and {"Ctrl+=", "Ctrl+-", "Ctrl+0"} <= set(texts)
    assert keys.step(1) == 110 and keys.step(1) == 120
    assert keys.badge.isVisible() and keys.badge.text() == "120 %"
    assert demo.ctrl.settings.zoom == 100                       # appliqué après une courte pause
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 120)
    assert abs(theme.zoom() - 1.2) < 1e-6
    # Ctrl + molette sur une page ordinaire : zoom de l'interface
    lib = demo.views["library"]
    demo.show_view("library")
    _wheel(lib.table.viewport(), -120)
    assert keys.pending == 110
    _wheel(lib.table.viewport(), 120, ctrl=False)              # molette seule : défilement, pas de zoom
    assert keys.pending == 110
    assert keys.step(0) == 100
    for _ in range(20):
        keys.step(1)
    assert keys.pending == 200                                  # bornes
    for _ in range(30):
        keys.step(-1)
    assert keys.pending == 80
    keys.step(0)
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 100)


def test_ctrl_wheel_on_the_waveform_keeps_zooming_the_waveform(demo_grid):  # noqa: F811
    app = demo_grid
    ed = _open_grid(app)
    keys = app.zoom_keys
    before = ed.view_s
    _wheel(ed.canvas, 120)
    assert keys.pending is None and ed.view_s != before        # la forme d'onde zoome, pas l'interface
    ed.close()


def test_settings_have_buttons_not_a_slider(demo):  # noqa: F811
    from PySide6.QtWidgets import QSlider

    from .qt_util import pump

    demo.show_view("settings")
    view = demo.views["settings"]
    assert not view.findChildren(QSlider) or all(s.objectName() != "zoom" for s in view.findChildren(QSlider))
    assert not hasattr(view, "zoom")
    view._zoom_step(1)
    assert view.zoom_val.text() == "110 %"
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 110)
    view._zoom_step(0)
    assert pump(demo, 2, lambda: demo.ctrl.settings.zoom == 100)


# ------------------------------------------------------------------ C103
def test_playlists_column_shows_where_each_track_is(demo):  # noqa: F811
    from .qt_util import pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 5, lambda: lib.table.total > 0)
    table = lib.table
    col = table.column_index("playlists")
    assert not table.isColumnHidden(col)                        # affichée par défaut
    assert pump(demo, 5, lambda: getattr(lib, "_member", None) is not None)
    pump(demo, 0.3)
    member = lib._member
    club = next(p for p in lib.playlists if p.name == "Club")
    inside = next(cid for cid, pids in member.items() if club.playlist_id in pids)
    row = table.row(str(inside))
    assert "Club" in row.values["playlists"] and "Club" in row.values["playlists__tip"]
    outside = next((x.content_id for x in lib.all_tracks if not member.get(x.content_id)), None)
    if outside is not None:
        assert table.row(str(outside)).values["playlists"] == "—"
    # la recherche trouve les sons par nom de playlist
    table.set_filter("club")
    assert str(inside) in [r.iid for r in table.all_rows()] or table.count >= 1
    table.set_filter("")
    # clic droit : ouvrir la playlist
    table.select([str(inside)])
    entries = [e for e in lib._menu([str(inside)]) if e]
    opener = next(e for e in entries if "Club" in e[0])
    opener[1]()
    assert lib.in_playlist and lib.playlist.playlist_id == club.playlist_id
    # ajouter un son à une playlist : la colonne suit
    other = next(x for x in lib.all_tracks if club.playlist_id not in member.get(x.content_id, []))
    demo.ctrl.add_to_playlists([other.content_id], [club.playlist_id])
    assert pump(demo, 6, lambda: club.playlist_id in (getattr(lib, "_member", {}) or {}).get(other.content_id, []))
    assert not demo.errors
