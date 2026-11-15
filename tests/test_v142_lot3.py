"""1.4.2, lot 3 : C188, C189, C186, C193, C187, C194."""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v020 import demo  # noqa: E402,F401


# ------------------------------------------------------------------ C194 : grille par deux kicks
def test_c194_two_kicks_give_the_bpm_and_a_bar_on_the_first_kick():
    from djsync.analysis import grid as G

    found = G.from_two_beats(1000.0, 1000.0 + 32 * 60000.0 / 128.0, 126.0, 240000)
    assert found is not None
    beats, bpm, n = found
    assert n == 32 and bpm == pytest.approx(128.0)
    i = G.nearest(beats, 1000)
    assert beats[i][2] == 1000 and beats[i][0] == 1                   # 1er kick = 1er temps de mesure
    assert all(b[1] == 12800 for b in beats)                          # grille constante
    assert beats[0][2] < 1000 and beats[-1][2] > 16000                # prolongée des deux côtés
    swapped = G.from_two_beats(16000.0, 1000.0, 126.0, 240000)          # ordre des clics indifférent
    assert swapped is not None and swapped[2] == 32
    assert G.from_two_beats(1000.0, 1100.0, 120.0, 240000) is None     # trop proches
    assert G.from_two_beats(1000.0, 1000.0 + 60000.0, 400.0, 240000) is None   # BPM hors de 40-300


def test_c194_grid_editor_two_presses_rewrite_the_grid(demo):  # noqa: F811
    from djsync.ui.grid_editor import GridEditor

    lib = demo.ctrl.library
    track = lib.list_tracks()[0]
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        pump(demo, 1, lambda: False)
        ed.duration_ms = 240000
        ed.beats = [((i % 4) + 1, 12000, 500 * i) for i in range(480)]   # 120 BPM, sur le point d'être corrigé
        ed.original = list(ed.beats)
        start = ed.beats[2][2]
        ed.cursor_ms = float(start)
        ed._kick()
        assert ed._kick1 == float(start) and not ed.kick_cancel.isHidden()
        ed.cursor_ms = float(start) + 16 * 60000.0 / 125.0
        ed._kick()
        assert ed._kick1 is None and ed.kick_cancel.isHidden()
        assert ed.bpm_entry.text().startswith("125")
        assert ed.save_btn.isEnabled()                                     # à enregistrer, annulable
        ed._reset()
        assert ed.beats == ed.original
    finally:
        ed._closed = True
        ed.deleteLater()


# ------------------------------------------------------------------ C188 : listes automatiques repliables
def test_c188_auto_lists_in_a_foldable_group_remembered(demo, monkeypatch):  # noqa: F811
    from PySide6.QtCore import Qt

    from djsync.ui.views import library_view as L

    s = demo.ctrl.settings
    monkeypatch.setattr(s, "save", lambda *a, **k: None)
    view = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 6, lambda: L.AUTO in view._items)
    group = view._items[L.AUTO]
    assert view.nav.indexOfTopLevelItem(group) >= 0
    kids = {group.child(i).data(0, Qt.UserRole) for i in range(group.childCount())}
    assert kids == {L.TODO, L.ORPH, L.MISS, L.NOCUE}
    assert not group.flags() & Qt.ItemIsSelectable                   # jamais ouvert comme une liste
    assert group.isExpanded()
    group.setExpanded(False)
    assert s.auto_lists_open is False
    view._fill_nav()
    assert not view._items[L.AUTO].isExpanded()                         # état retenu
    view._items[L.AUTO].setExpanded(True)
    assert s.auto_lists_open is True and view._items[L.AUTO].text(1) == ""


# ------------------------------------------------------------------ C189 : panneaux repliables
def test_c189_download_panels_fold_and_remember(demo, monkeypatch):  # noqa: F811
    s = demo.ctrl.settings
    monkeypatch.setattr(s, "save", lambda *a, **k: None)
    view = demo.views["downloads"]
    demo.show_view("downloads")
    panel, body, _btn = view._panels["downloads"]
    assert body.isVisible()
    view._toggle_fold("downloads")
    assert s.panels_folded == {"downloads": True}
    assert body.isHidden() and panel.maximumHeight() < 200
    assert view.clear_btn.isVisibleTo(panel)                            # titre et boutons restent
    view._toggle_fold("downloads")
    assert not body.isHidden() and panel.maximumHeight() > 10000
    s.panels_folded = {"analysis": True}
    from djsync.settings import Settings

    assert Settings().normalize().panels_folded == {}


# ------------------------------------------------------------------ C193 : sources filtrées seulement
def test_c193_hq_queries_only_the_filtered_sources(demo, monkeypatch):  # noqa: F811
    from djsync.core.search import ResultFilter

    view = demo.views["hq"]
    monkeypatch.setattr(type(demo.ctrl), "slsk_ready", property(lambda _s: True), raising=False)
    monkeypatch.setattr(demo.ctrl, "free_sources_list", lambda: ["archive", "audius"])
    view._filter = ResultFilter()
    assert view._queried_sources() == (["archive", "audius"], True)
    view._filter = ResultFilter(sources=("audius",))
    assert view._queried_sources() == (["audius"], False)
    view._filter = ResultFilter(sources=("soulseek",))
    assert view._queried_sources() == ([], True)
    calls = []
    monkeypatch.setattr(demo.ctrl, "free_search", lambda *a, **k: calls.append(k.get("only")))
    monkeypatch.setattr(demo.ctrl, "slsk_search", lambda *a, **k: calls.append("slsk"))
    view._filter = ResultFilter(sources=("archive",))
    view.entry.setText("daft punk")
    view.run_search(force=True)
    assert calls == [["archive"]]                                        # Audius et Soulseek pas interrogés


def test_c193_free_search_only_restricts_the_sources(demo, monkeypatch):  # noqa: F811
    from djsync.core import freesources

    seen = []
    monkeypatch.setattr(freesources, "search_all", lambda q, sources, partial=None: seen.append(list(sources)) or [])
    demo.ctrl.settings.free_sources = ["archive", "audius"]
    demo.ctrl.free_search("x", lambda _r: None, only=["audius"])
    assert pump(demo, 4, lambda: bool(seen))
    assert seen == [["audius"]]


# ------------------------------------------------------------------ C187 : « Plus de choix… » à l'accueil
def test_c187_welcome_more_choices_opens_download_settings(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.welcome import WelcomeDialog

    s = demo.ctrl.settings
    monkeypatch.setattr(s, "save", lambda *a, **k: None)
    w = WelcomeDialog(demo, demo.ctrl)
    w._choose(s.language)
    w._to_quality()
    assert len(w.yt_buttons) == 2                                      # deux choix pour débuter
    from PySide6.QtWidgets import QPushButton

    more = [b for b in w.findChildren(QPushButton) if b.text() == t("welcome.more_choices")]
    assert len(more) == 1
    opened = []
    demo.ctrl.on("open_settings_section", opened.append)
    more[0].click()
    assert s.welcome_done is True and opened == ["download"]


# ------------------------------------------------------------------ C186 : sons déjà présents
def test_c186_match_library_track_uses_duplicate_thresholds():
    from djsync.core.duplicates import match_library_track

    lib = [NS(title="One More Time", artist="Daft Punk", content_id=1),
           NS(title="Daft Punk - Around the World", artist="", content_id=2),
           NS(title="Something Else", artist="Other", content_id=3)]
    assert match_library_track("One More Time", "Daft Punk", lib).content_id == 1
    assert match_library_track("Around the World", "Daft Punk", lib).content_id == 2
    assert match_library_track("Love", "Daft Punk", lib) is None


def test_c186_existing_tracks_added_to_playlist_without_download(demo, monkeypatch):  # noqa: F811
    from djsync.models import TrackResult

    ctrl = demo.ctrl
    lib = ctrl.library
    song = next(x for x in lib.list_tracks() if x.title == "One More Time")
    pl = lib.create_playlist("Lot 3")
    ctrl._emit("library")
    assert pump(demo, 4, lambda: any(p.playlist_id == pl.playlist_id for p in ctrl.playlists))
    enq = []
    monkeypatch.setattr(ctrl, "enqueue", lambda *a, **k: enq.append(a))
    found = TrackResult(video_id="zzz", title=song.title, artist=song.artist).with_duplicate(song.display_name)
    lost = TrackResult(video_id="yyy", title="Nothing Like It", artist="Nobody").with_duplicate("x")
    ctrl.add_existing([found, lost], [pl.playlist_id])
    assert pump(demo, 6, lambda: song.content_id in [x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)])
    assert enq == []                                                  # rien de retéléchargé


def test_c186_search_menu_offers_add_for_tracks_already_there(demo):  # noqa: F811
    from djsync.i18n import plural
    from djsync.models import TrackResult

    view = demo.views["search"]
    x = TrackResult(video_id="abc", title="One More Time", artist="Daft Punk").with_duplicate("Daft Punk - One More Time")
    view._tracks = {"abc": x}
    texts = [e[0] for e in view._menu(["abc"]) if e]
    assert plural("search.add_existing_one", "search.add_existing_many", 1) in texts
    y = TrackResult(video_id="def", title="New", artist="Someone")
    view._tracks = {"def": y}
    assert plural("search.add_existing_one", "search.add_existing_many", 1) not in [e[0] for e in view._menu(["def"]) if e]
