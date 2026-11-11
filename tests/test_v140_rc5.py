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


def test_b90_only_visible_rows_get_views(demo, monkeypatch):  # noqa: F811
    from djsync.models import TrackResult

    view = demo.views["search"]
    demo.show_view("search")
    demo.resize(1100, 600)
    results = [TrackResult(video_id=f"v{i:010d}", title=f"T{i}", artist="A", source="ytmusic") for i in range(80)]
    asked = []
    monkeypatch.setattr(demo.ctrl, "enrich_views", lambda tracks, cb, max_items=30: asked.extend(tracks))
    view._show_results(results)
    pump(demo, 0.3)
    view._enrich_visible()
    assert asked and len({x.video_id for x in asked}) < len(results)
    assert set(view.table.visible_iids()) <= {x.video_id for x in results}


# ------------------------------------------------------------------ B91 : bruit de pyrekordbox
def test_b91_missing_playlist_warnings_summed_up(caplog):
    from djsync.db import local_library

    noise = local_library._PlaylistXmlNoise()
    lg = logging.getLogger("pyrekordbox.masterdb.database.test")
    lg.addFilter(noise)
    try:
        with caplog.at_level(logging.INFO):
            for _ in range(20):                                     # 20 écritures
                for pid in range(17):
                    lg.warning(f"Playlist {pid} not found in masterPlaylists6.xml! Did you add it manually?")
                noise.report()
            lg.warning("Something else")
        lines = [r.getMessage() for r in caplog.records]
        assert sum("not found in masterPlaylists6" in x for x in lines) == 0
        assert sum("17 playlist(s) missing" in x for x in lines) == 1
        assert "Something else" in lines
    finally:
        lg.removeFilter(noise)


# ------------------------------------------------------------------ B92 : colonne Taille
def test_b92_size_column_in_high_quality_search(demo):  # noqa: F811
    from djsync.ui.views.common import result_columns, result_row

    view = demo.views["search"]
    keys = [c.key for c in result_columns(with_size=True)]
    assert "size" in keys and "size" not in [c.key for c in result_columns()]
    view._show_mode_columns()
    assert "size" not in view.table._wanted and "views" in view.table._wanted
    view.mode.setCurrentIndex(1)
    assert "views" not in view.table._wanted and "size" in view.table._wanted
    view.mode.setCurrentIndex(0)

    class Slsk:
        size, lossless, bitrate, free_slot, queue, speed = 12_300_000, True, 0, True, 0, 0

        @staticmethod
        def quality_label():
            return "FLAC"

    from djsync.models import TrackResult

    row = result_row(TrackResult(video_id="s1", title="T", artist="A", source="soulseek", slsk=Slsk()))
    assert row.values["size"].startswith("12") and row.values["views"] == ""


# ------------------------------------------------------------------ B93 : page du morceau
def test_b93_track_page_offered_for_soundcloud(demo):  # noqa: F811
    from djsync.models import TrackResult
    from djsync.ui.views.common import result_row

    v = demo.views["import"]
    tracks = [TrackResult(video_id="sc1", title="T", artist="A", source="soundcloud",
                          source_url="https://soundcloud.com/artist/track"),
              TrackResult(video_id="yt1", title="U", artist="B", source="youtube",
                          source_url="https://www.youtube.com/watch?v=abcdefghijk")]
    v.mode = "direct"
    v._tracks = {x.video_id: x for x in tracks}
    v.dl_table.set_rows([result_row(x, checked=False) for x in tracks])
    v.dl_table.select(["sc1"])
    v._refresh_buttons()
    assert v._page_urls() == ["https://soundcloud.com/artist/track"] and not v.page_btn.isHidden()
    opened = []
    demo.ctrl.on("open_url", opened.append)
    labels = [e[0] for e in v._menu(["sc1"]) if e]
    from djsync.i18n import t

    assert t("sc.page_open") in labels
    v._open_pages()
    assert opened == ["https://soundcloud.com/artist/track"]
    v.dl_table.select(["yt1"])
    v._refresh_buttons()
    assert v.page_btn.isHidden()


# ------------------------------------------------------------------ C160 : dossier surveillé
def test_c160_register_and_source_column(demo, tmp_path):  # noqa: F811
    from djsync.core import watched
    from djsync.i18n import t

    watched.record([("Song.m4a", 1234)], "C:/Achats", "2026-11-06")
    assert watched.lookup("song.m4a", 1234)["folder"] == "C:/Achats"
    assert watched.lookup("song.m4a", 999) is None
    lib = demo.views["library"]
    track = demo.ctrl.library.list_tracks()[0]
    name = track.path.replace("\\", "/").rsplit("/", 1)[-1]
    from dataclasses import replace

    size = track.file_size or 4321
    track = replace(track, file_size=size)
    watched.record([(name, size)], "C:/Achats", "2026-11-06")
    values = lib._source_values(track) if not track.source_url else None
    if values is not None:
        assert values["source"] == t("watch.source") and values["source__icon"] == "watch"
        assert "C:/Achats" in values["source__tip"]


def test_c160_old_playlist_renamed(demo):  # noqa: F811
    from djsync.i18n import t

    ctrl = demo.ctrl
    lib = ctrl.library
    old = lib.create_playlist("Importés")
    pid = ctrl._watch_playlist(lib, t("watch.playlist"))
    assert pid == old.playlist_id
    assert any(p.name == t("watch.playlist") for p in lib.list_playlists())
    assert ctrl._watch_playlist(lib, t("watch.playlist")) == pid          # repris, pas recréé


def test_c160_first_import_message(demo, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    ctrl = demo.ctrl
    ctrl.settings.watch_first_done = False
    said, actions = [], []
    monkeypatch.setattr(ctrl, "message", lambda kind, text: said.append(text))
    ctrl.on("message_action", lambda text, fn: actions.append(text))
    track = ctrl.library.list_tracks()[0]
    report = SimpleNamespace(added=[track])
    ctrl._watched_done(report, ctrl.library, "/watch")
    assert said and actions and ctrl.settings.watch_first_done
    said.clear()
    ctrl._watched_done(report, ctrl.library, "/watch")
    assert not said                                                        # une seule fois


def test_c160_settings_explain_and_live_in_libraries(demo):  # noqa: F811
    from djsync.i18n import t

    view = demo.views["settings"]
    box = next(b for _s, b in view._cards if b.objectName() == "card_watch")
    assert box in view.section_cards("libraries")
    texts = " ".join(w.text() for w in box.findChildren(type(view.no_match)))
    assert t("watch.settings_hint")[:30] in texts                         # explication visible, pas en bulle


# ------------------------------------------------------------------ C161 : volet replié, analyse d'un lot
def test_c161_analysis_counts_the_whole_batch():
    from djsync.ui.ctrl.library_ops import AnalysisQueue

    q = AnalysisQueue()
    q.reset()
    assert q.expect([1, 2, 3]) == 3 and q.total == 3 and q.waiting
    assert q.fulfil(1, 101) and q.total == 3 and q.pending == [101]
    assert not q.fulfil(9, 109)                       # pas attendu
    assert q.drop(2) and q.total == 2                 # échec : retiré du total
    q.ids.add(103)
    assert q.fulfil(3, 103) and q.total == 1          # déjà en file (doublon) : retiré
    q.expect([4])
    q.cancel()
    assert 4 in q.stopped and not q.expected and q.total == 1


def test_c161_downloads_counted_from_the_start(demo, monkeypatch):  # noqa: F811
    from djsync.models import TrackResult

    ctrl = demo.ctrl
    ctrl.settings.analyze_after_download_usb = True
    started = []
    monkeypatch.setattr(ctrl.dispatcher, "submit", lambda *a, **k: started.append(k.get("pool")))
    tracks = [TrackResult(video_id=f"v{i:010d}", title=f"T{i}", artist="A", source="ytmusic") for i in range(13)]
    jobs = ctrl.enqueue(tracks, [])
    q = ctrl.analysis
    assert q.total == 13 and q.expected == {j.id for j in jobs}
    jobs[0].status = "error"
    ctrl._job_changed(jobs[0])
    assert q.total == 12
    q.cancel()


def test_c161_collapsed_sidebar_rings_bigger(demo):  # noqa: F811
    from djsync.ui import mini_ring, theme
    from djsync.ui.app import SIDEBAR_COMPACT

    assert mini_ring.RING_PX == 30 and mini_ring.RING_ICON_PX == 14 and SIDEBAR_COMPACT == 56
    ring = mini_ring.MiniRing("wave")
    assert ring.width() == theme.px(30)
    ring.grab()


# ------------------------------------------------------------------ C162 / C46 : qualité supposée
def test_c162_estimated_quality_wording():
    from djsync.i18n import en, fr

    def texts(mod):
        return " ".join(v for d in vars(mod).values() if isinstance(d, dict) for v in d.values() if isinstance(v, str))

    fr_text, en_text = texts(fr), texts(en)
    assert "Qualité réelle" not in fr_text and "qualité réelle" not in fr_text
    assert "Real quality" not in en_text and "real quality" not in en_text
    assert "Qualité supposée" in fr_text and "Estimated quality" in en_text


# ------------------------------------------------------------------ C165 : Paramètres rangés
def test_c165_settings_reorganised(demo):  # noqa: F811
    view = demo.views["settings"]
    names = {key: [b.objectName() for b in view.section_cards(key)] for key in
             ("libraries", "download", "djsync")}
    lib = names["libraries"]
    assert lib.index("card_watch") < lib.index("card_pdb") < lib.index("card_backups")
    assert names["download"][:3] == ["card_search", "card_format", "card_youtube"]
    assert names["djsync"] == ["card_updates", "card_about", "card_install"]
    assert any(view.latency_box in b.findChildren(type(view.latency_box)) for b in view.section_cards("analysis"))
    assert not any(view.light_menu in b.findChildren(type(view.light_menu))
                   for b in view.section_cards("general")[:1])           # plus dans Apparence
    assert view.quality_box.isHidden()                                      # tableau replié
    view.quality_toggle.setChecked(True)
    assert not view.quality_box.isHidden()
    view.quality_toggle.setChecked(False)


def test_c165_no_card_repeats_its_section_title(demo):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.views.settings_view import SECTIONS

    view = demo.views["settings"]
    for key, _icon in SECTIONS:
        section = t(f"settings.section_{key}")
        for box in view.section_cards(key):
            titles = [w.text() for w in box.findChildren(type(view.no_match)) if w.property("role") == "h2"]
            assert section not in titles, (key, titles)


# ------------------------------------------------------------------ C157 : visibilité
def test_c157_readme_site_and_pages_workflow():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "free Rekordbox USB export for Pioneer CDJs, without Rekordbox" in readme
    assert "## Why DJSync?" in readme and "README.fr.md" in readme and "1.4.0-rc.5" in readme
    fr_readme = (ROOT / "README.fr.md").read_text("utf-8")
    assert "Pourquoi DJSync" in fr_readme and "README.md" in fr_readme
    page = (ROOT / "site" / "index.html").read_text("utf-8")
    assert "<title>DJSync" in page and 'property="og:image"' in page
    for name in ("logo.png", "og.png", "library.png"):
        assert (ROOT / "site" / name).is_file()
    wf = (ROOT / ".github" / "workflows" / "pages.yml").read_text("utf-8")
    assert "actions/deploy-pages@" in wf and "path: site" in wf
