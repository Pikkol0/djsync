"""1.4.0-rc.5 : retours de tests de la rc.4 (B80, B85-B88, B90-B93, C46, C157, C160-C162, C165)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ B87 : glisser pour réordonner
def _table(qapp_rows=6):
    from djsync.ui.table import Column, Row, TrackTable

    table = TrackTable(None, [Column("title", "Title")], reorderable=True)
    table.resize(400, 300)
    table.show()
    table.set_rows([Row(str(i), {"title": f"T{i}"}) for i in range(qapp_rows)])
    reordered = []
    table.on_reordered = lambda: reordered.append(True)
    return table, reordered


def _drag_event(kind, table, pos, ids):
    from PySide6.QtCore import QByteArray, QMimeData, QPointF, Qt
    from PySide6.QtGui import QDragMoveEvent, QDropEvent

    from djsync.ui.table import MIME_IDS

    mime = QMimeData()
    mime.setData(MIME_IDS, QByteArray(",".join(ids).encode()))
    actions = Qt.CopyAction | Qt.MoveAction
    if kind == "move":
        return QDragMoveEvent(pos, actions, mime, Qt.LeftButton, Qt.NoModifier), mime
    return QDropEvent(QPointF(pos), actions, mime, Qt.LeftButton, Qt.NoModifier), mime


def test_b87_internal_drag_is_accepted_and_reorders(demo):  # noqa: F811
    """Qt refusait l'événement après notre acceptation : le dépôt n'arrivait jamais."""
    table, reordered = _table()
    table._drag_ids = ["0"]                   # glisser en cours depuis ce tableau (comme pendant drag.exec)
    rect = table.visualRect(table.model().index(3, 0))
    pos = rect.center()
    pos.setY(rect.bottom() - 2)               # moitié basse : après T3
    move, _m = _drag_event("move", table, pos, ["0"])
    table.dragMoveEvent(move)
    assert move.isAccepted()
    assert table._drop_at == ("3", True)      # ligne d'insertion dessinée sous T3
    table.grab()                              # dessin de la ligne sans erreur
    drop, _m = _drag_event("drop", table, pos, ["0"])
    table.dropEvent(drop)
    assert drop.isAccepted() and reordered
    assert [r.iid for r in table.displayed_rows()][:4] == ["1", "2", "3", "0"]
    assert table._drop_at is None             # ligne effacée après le dépôt
    table.close()


def test_b87_drag_refused_with_a_filter(demo):  # noqa: F811
    table, reordered = _table()
    table._drag_ids = ["0"]
    table.set_filter("T")
    pos = table.visualRect(table.model().index(2, 0)).center()
    move, _m = _drag_event("move", table, pos, ["0"])
    table.dragMoveEvent(move)
    assert not move.isAccepted() and table._drop_at is None
    table.close()


def test_b87_pyside_pinned_for_tests_and_builds():
    pinned = (ROOT / "packaging" / "constraints.txt").read_text("utf-8")
    assert "PySide6-Essentials==" in pinned
    for wf in ("tests.yml", "windows.yml"):
        text = (ROOT / ".github" / "workflows" / wf).read_text("utf-8")
        installs = [ln for ln in text.splitlines() if "pip install -r requirements.txt" in ln]
        assert installs and all("-c packaging/constraints.txt" in ln for ln in installs), wf


# ------------------------------------------------------------------ B85 : barre d'une playlist
@pytest.mark.parametrize("width", [1280, 1024, 900])
@pytest.mark.parametrize("zoom", [100, 150])
def test_b85_playlist_bar_never_squeezes_a_button(demo, width, zoom):  # noqa: F811
    lib = demo.views["library"]
    try:
        demo.ctrl.settings.zoom = zoom
        demo.restyle()
        demo.resize(width, 800)
        demo.show_view("library")
        editable = next((p for p in lib.playlists if p.is_editable and not p.is_folder), None)
        if editable is not None:
            lib._goto(f"p{editable.playlist_id}")
        lib._dirty = True                          # « Enregistrer l'ordre » visible
        lib._refresh_buttons()
        pump(demo, 0.2)
        bar = lib.bar
        bar.fit()
        pump(demo, 0.2)
        shown = [w for w, *_r in bar._items if w.isVisibleTo(bar)]
        assert shown
        for w in shown:                            # jamais plus étroit que son contenu
            assert w.width() >= w.sizeHint().width() - 1, (w.text() if hasattr(w, "text") else "", w.width(), w.sizeHint().width(), bar.level, bar.width(), [(x.text() if hasattr(x, "text") else "", x.width(), x.sizeHint().width()) for x in shown])
        need = sum(w.sizeHint().width() for w in shown) + bar.lay.spacing() * (len(shown) - 1)
        assert need <= bar.width() or bar.level == 3
        if bar.level >= 2:                          # boutons sortis : repris dans le menu ☰
            assert lib._overflow_entries()
    finally:
        demo.ctrl.settings.zoom = 100
        demo.restyle()
        lib._dirty = False
        lib._refresh_buttons()


def test_b85_save_order_only_when_changed(demo):  # noqa: F811
    lib = demo.views["library"]
    demo.show_view("library")
    editable = next((p for p in lib.playlists if p.is_editable and not p.is_folder), None)
    if editable is None:
        pytest.skip("no editable playlist in the demo drive")
    lib._goto(f"p{editable.playlist_id}")
    lib._dirty = False
    lib._refresh_buttons()
    assert not lib.save_btn.isVisibleTo(lib)
    lib._dirty = True
    lib._refresh_buttons()
    pump(demo, 0.1)
    assert lib.save_btn.isVisibleTo(lib) or lib.bar.level == 3
    lib._dirty = False
    lib._refresh_buttons()


def test_b85_fitbar_levels():
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    _app = QApplication.instance() or QApplication([])

    from djsync.ui.icons import qicon
    from djsync.ui.widgets import FitBar

    holder = QWidget()                     # dans une fenêtre, comme dans l'app (une fenêtre seule a une largeur mini)
    holder.resize(4200, 60)
    bar = FitBar(holder)
    main = [QPushButton(f"Main button {i}") for i in range(3)]
    side = [QPushButton(f"Secondary {i}") for i in range(3)]
    for b in main + side:
        b.setIcon(qicon("plus", 16, "#ffffff"))
    for b in main:
        bar.add(b)
    bar.add_stretch()
    for b in side:
        bar.add(b, secondary=True)
    holder.show()

    def width(w):
        bar.resize(w, 40)
        _app.processEvents()
        bar.fit()

    width(4000)
    assert bar.level == 0 and side[0].text() == "Secondary 0"
    width(sum(b.sizeHint().width() for b in main + side) - 40)
    assert bar.level == 1 and side[0].text() == "" and side[0].toolTip() == "Secondary 0"
    width(200)
    assert bar.level >= 2 and not side[0].isVisibleTo(bar) and side[0] in bar.overflow
    holder.hide()                                       # pas encore affichée : textes complets
    bar.fit()
    assert bar.level == 0 and side[0].text() == "Secondary 0"
    keep = QPushButton("Keep me")
    keep.setIcon(qicon("plus", 16, "#ffffff"))
    bar.add(keep, keep_text=True)
    holder.show()
    width(60)
    assert bar.level == 3 and keep.text() == "Keep me" and main[0].text() == ""
    holder.close()


# ------------------------------------------------------------------ B86 : textes de l'ordinateur
def test_b86_delete_label_on_the_computer(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import t

    lib = demo.views["library"]
    assert lib._delete_label() == t("lib.delete")
    monkeypatch.setattr(type(demo.ctrl), "is_local", property(lambda _s: True))
    assert lib._delete_label() == t("lib.delete_local")
    lib._refresh_buttons()
    assert lib.delete_btn.toolTip() == t("lib.delete_local")
    assert "master.db" in t("lib.delete_local_detail")


# ------------------------------------------------------------------ B80 : cases à cocher
@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 2.0])
def test_b80_checkbox_drawn_at_screen_density_with_a_margin(demo, ratio):  # noqa: F811
    from djsync.ui.table import CHECK_OFF, CHECK_ON, check_pixmap

    for state in (CHECK_ON, CHECK_OFF):
        pm = check_pixmap(state, 16, ratio=ratio)
        img = pm.toImage()
        assert pm.width() == round(16 * ratio)          # pixels entiers
        last = img.width() - 1
        for i in range(img.height()):                   # bords libres : rien n'est coupé
            assert img.pixelColor(last, i).alpha() < 40
            assert img.pixelColor(i, last).alpha() < 40


def test_b80_header_box_drawn_by_the_header(demo):  # noqa: F811
    from PySide6.QtCore import Qt

    from djsync.models import TrackResult
    from djsync.ui.table import _Header
    from djsync.ui.views.common import result_row

    v = demo.views["import"]
    assert isinstance(v.dl_table.horizontalHeader(), _Header)
    tracks = [TrackResult(video_id=f"sc{i}", title=f"T{i}", artist="A", source="soundcloud") for i in range(3)]
    v.mode = "direct"
    v._tracks = {x.video_id: x for x in tracks}
    v.dl_table.set_rows([result_row(x, checked=True) for x in tracks])
    assert v.dl_table.model().headerData(0, Qt.Horizontal, Qt.DecorationRole) is None
    v.dl_table.horizontalHeader().grab()


# ------------------------------------------------------------------ B88 : moteur de téléchargement
def test_b88_rollback_target(tmp_path):
    from djsync.core import engine

    folder = tmp_path / "engine"
    assert engine.rollback_target(folder) == ""                 # version intégrée : rien à faire
    folder.mkdir()
    (folder / "engine.json").write_text('{"yt-dlp": "2099.1.1"}', "utf-8")
    assert engine.rollback_target(folder) == "bundled"
    prev = tmp_path / "engine.prev"
    prev.mkdir()
    (prev / "engine.json").write_text('{"yt-dlp": "2098.1.1"}', "utf-8")
    assert engine.rollback_target(folder) == "prev"


def test_b88_check_keeps_the_button_and_shows_the_time(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import t

    view = demo.views["settings"]
    calls = []
    monkeypatch.setattr(demo.ctrl, "engine_check", lambda done: calls.append(done))
    view._engine_check()
    assert view.engine_check_btn.isEnabled()                   # pas de perte de focus : la page ne saute pas
    assert view.engine_check_btn.text() == t("engine.checking")
    view._engine_check()                                       # clic de plus pendant la recherche : ignoré
    assert len(calls) == 1
    calls[0](None, "2026.10.26", None)
    assert view.engine_check_btn.text() == t("engine.check")
    assert t("engine.up_to_date_at", time="")[:12] in view.engine_state.text()


def test_b88_no_button_without_effect(demo, monkeypatch):  # noqa: F811
    from djsync.core import engine

    view = demo.views["settings"]
    monkeypatch.setattr(engine, "rollback_target", lambda folder=None: "")
    view._engine_show()
    assert view.engine_back_btn.isHidden()
    monkeypatch.setattr(engine, "rollback_target", lambda folder=None: "bundled")
    view._engine_show()
    assert not view.engine_back_btn.isHidden() and engine.bundled_version() in view.engine_back_btn.text()


# ------------------------------------------------------------------ B90 : recherche prioritaire
def test_b90_search_has_its_own_queue_and_logs_its_duration(demo, caplog):  # noqa: F811
    from djsync.ui import runner

    assert "search" in runner._POOLS and "views" in runner._POOLS
    got = []
    with caplog.at_level(logging.INFO, logger="djsync.ui.controller"):
        demo.ctrl.search("umbrella", got.append)
        pump(demo, 3, lambda: bool(got))
    assert got
    assert any("Search 'umbrella'" in r.getMessage() and " in " in r.getMessage() for r in caplog.records)


def test_b90_views_of_a_replaced_search_are_dropped(demo, monkeypatch):  # noqa: F811
    from djsync.models import TrackResult

    ctrl = demo.ctrl
    ctrl.settings.fetch_views = True
    asked = []
    monkeypatch.setattr(ctrl.service, "fetch_views", lambda vid: asked.append(vid) or 1000, raising=False)
    tracks = [TrackResult(video_id=f"v{i:010d}", title="x", artist="y", source="ytmusic") for i in range(5)]
    ctrl._views_gen += 1                                    # une nouvelle recherche part avant les vues
    gen = ctrl._views_gen
    monkeypatch.setattr(ctrl.dispatcher, "submit",
                        lambda fn, ok=None, err=None, pool="net": (setattr(ctrl, "_views_gen", gen + 1), fn()))
    ctrl.enrich_views(tracks, lambda vid, n: None)
    assert not asked                                        # requêtes pas parties : abandonnées
