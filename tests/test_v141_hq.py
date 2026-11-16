"""1.4.1 : page Haute qualité (C133), filtres et tris (C134), métadonnées (C170), qualité annoncée (C175),
progression (C171), écoute d'un équivalent (C167), albums Internet Archive (C147). Réseau toujours simulé."""
from __future__ import annotations

import pytest

from djsync.core.search import Announced, ResultFilter, announced, filter_results, passes
from djsync.models import TrackResult


class Slsk:
    def __init__(self, ext="flac", bitrate=0, duration=0, sample_rate=0, bit_depth=0, free_slot=True, speed=0,
                 queue=0, vbr=False, size=30_000_000, path="music\\Bicep\\Isles\\01 - Bicep - Glue.flac"):
        self.ext, self.bitrate, self.duration, self.sample_rate, self.bit_depth = ext, bitrate, duration, sample_rate, bit_depth
        self.free_slot, self.speed, self.queue, self.vbr, self.size, self.path = free_slot, speed, queue, vbr, size, path
        self.username = "peer"

    @property
    def lossless(self):
        return self.ext in ("flac", "wav")

    @property
    def stem(self):
        return self.path.split("\\")[-1].rsplit(".", 1)[0]

    @property
    def folder(self):
        return self.path.split("\\")[-2]

    @property
    def name(self):
        return self.path.split("\\")[-1]

    def quality_label(self):
        return self.ext.upper()


def _t(vid, quality="", source="archive", duration=0, slsk=None, **kw):
    return TrackResult(video_id=vid, title=vid, artist="A", duration_seconds=duration, source=source,
                       quality=quality, slsk=slsk, **kw)


# ------------------------------------------------------------------ C175 : qualité annoncée
def test_c175_announced_labels_and_levels():
    assert Announced("flac", None, 44100, 16).label == "FLAC 16/44.1"
    assert Announced("flac").label == "FLAC" and Announced("flac").level == "gold"
    assert Announced("mp3", 245, vbr=True).label == "MP3 VBR ≈ 245" and Announced("mp3", 245).level == ""
    assert Announced("mp3", 320).label == "MP3 320" and Announced("mp3", 320).level == "silver"
    a = announced(_t("s", source="soulseek", slsk=Slsk("flac", sample_rate=96000, bit_depth=24)))
    assert a.label == "FLAC 24/96" and a.family == "lossless"
    assert announced(_t("x", "MP3 320")).kbps == 320 and announced(_t("y", "MP3")).kbps is None
    assert announced(_t("z", source="ytmusic")).family == "aac"


# ------------------------------------------------------------------ C134 : filtre pur
def test_c134_each_criterion_combination_and_missing_values():
    flac = _t("flac", "FLAC", duration=268)
    mp3 = _t("mp3", "MP3 320", source="audius", duration=300)
    unknown = _t("mp3x", "MP3", duration=0)                                      # débit et durée inconnus
    slow = _t("slsk", source="soulseek", slsk=Slsk("mp3", bitrate=256, free_slot=False, speed=50_000))
    fast = _t("slsk2", source="soulseek", slsk=Slsk("flac", free_slot=True, speed=2_000_000))
    album = _t("alb", "FLAC", result_type="album", tracks=(flac, unknown), track_count=2)
    every = [flac, mp3, unknown, slow, fast, album]
    ids = lambda f: [x.video_id for x in filter_results(every, f)]               # noqa: E731
    assert ids(ResultFilter()) == [x.video_id for x in every]
    assert ids(ResultFilter(sources=("soulseek",))) == ["slsk", "slsk2"]
    assert ids(ResultFilter(kind="album")) == ["alb"]
    assert "alb" not in ids(ResultFilter(kind="track"))
    assert ids(ResultFilter(families=("lossless",))) == ["flac", "slsk2", "alb"]
    assert ids(ResultFilter(min_kbps=320)) == ["flac", "mp3", "slsk2", "alb"]    # débit inconnu : écarté
    assert "mp3x" in ids(ResultFilter(duration_s=268, tolerance_s=3))           # durée inconnue : gardée
    assert "mp3" not in ids(ResultFilter(duration_s=268, tolerance_s=3))
    assert ids(ResultFilter(free_slot=True, sources=("soulseek",))) == ["slsk2"]
    assert ids(ResultFilter(min_speed_kbs=500, sources=("soulseek",))) == ["slsk2"]
    both = ResultFilter(sources=("archive",), families=("lossless",), duration_s=268)
    assert ids(both) == ["flac", "alb"]
    # C147 : un filtre qui exclut tous les titres d'un album masque l'album
    assert not passes(album, ResultFilter(families=("mp3",), min_kbps=320))
    f = ResultFilter.from_dict({"sources": ["audius"], "kind": "zzz", "min_kbps": "x", "free_slot": 1})
    assert f.sources == ("audius",) and f.kind == "all" and f.min_kbps == 0 and f.free_slot
    assert ResultFilter.from_dict(f.to_dict()).to_dict() == f.to_dict() and f.active and not ResultFilter().active


# ------------------------------------------------------------------ C147 + C170 : Internet Archive
def _ia_get(url, params=None):
    from djsync.core import freesources as F

    if url == F.ARCHIVE_SEARCH:
        return {"response": {"docs": [
            {"identifier": "ep1", "title": "Isles EP", "creator": "Bicep", "year": "2021",
             "licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
            {"identifier": "single", "title": "Lone", "creator": "Bicep", "date": "2019-05-01"}]}}
    if url.endswith("/ep1"):
        return {"files": [{"name": "02 Apricots.flac", "format": "Flac", "title": "Apricots", "track": "2",
                           "length": "300"},
                          {"name": "01 Glue.flac", "format": "Flac", "title": "Glue", "track": "1", "length": "268"},
                          {"name": "01 Glue.mp3", "format": "VBR MP3", "title": "Glue", "track": "1"},
                          {"name": "03 Atlas.mp3", "format": "VBR MP3", "title": "Atlas", "track": "3"}]}
    if url.endswith("/single"):
        return {"files": [{"name": "Lone.mp3", "format": "VBR MP3", "title": "Lone", "length": "200"}]}
    raise AssertionError(url)


def test_c147_archive_items_become_albums_with_metadata():
    from djsync.core import freesources as F

    out = F.archive_search("bicep", get=_ia_get)
    album, single = out
    assert album.is_album and album.track_count == 3 and album.title == "Isles EP" and album.year == 2021
    assert [x.title for x in album.tracks] == ["Glue", "Apricots", "Atlas"]          # ordre de l'album
    assert [x.track_no for x in album.tracks] == [1, 2, 3]
    assert album.tracks[0].quality == "FLAC" and album.quality == "FLAC"            # meilleur format par titre
    assert album.duration_seconds == 568 and album.license == "CC BY 4.0"
    assert album.thumbnail_url == "https://archive.org/services/img/ep1"           # C170 : pochette
    assert not single.is_album and single.title == "Lone" and single.year == 2019   # 1 titre : morceau isolé


def test_c167_equivalent_query_from_the_file_name():
    from djsync.ui.controller import equivalent_query

    x = _t("s", source="soulseek", slsk=Slsk(path="music\\Bicep\\03 - Bicep - Glue (Original Mix).flac"))
    assert equivalent_query(x) == ("Bicep", "Glue (Original Mix)")
    y = _t("s2", source="soulseek", slsk=Slsk(path="music\\Glue.flac"))
    assert equivalent_query(y) == ("A", "Glue")


# ------------------------------------------------------------------ interface
qt = pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


def _fake_sources(monkeypatch, ctrl, free, slsk=None, order=("audius", "archive")):
    ready = slsk is not None
    monkeypatch.setattr(type(ctrl), "slsk_ready", property(lambda self: ready))
    monkeypatch.setattr(ctrl, "free_sources_list", lambda: ["archive", "audius"])
    calls = {}

    def free_search(q, ok, partial=None, source_done=None):
        calls["free"] = (ok, partial, source_done)

    def slsk_search(q, ok, partial=None):
        calls["slsk"] = (ok, partial)

    monkeypatch.setattr(ctrl, "free_search", free_search)
    monkeypatch.setattr(ctrl, "slsk_search", slsk_search)
    return calls


def test_c133_page_in_the_sidebar_and_opened_from_search(demo, monkeypatch):  # noqa: F811
    from djsync.ui.app import TABS

    assert [k for k, *_ in TABS][:4] == ["home", "search", "hq", "library"]
    calls = _fake_sources(monkeypatch, demo.ctrl, [])
    search = demo.views["search"]
    demo.show_view("search")
    search.entry.setText("bicep glue")
    search.search_tabs.buttons["hq"].click()                     # 1.4.2 (C182) : onglet Haute qualité (D9)
    hq = demo.views["hq"]
    assert demo.current == "hq" and hq.entry.text() == "bicep glue" and "free" in calls
    assert demo._nav["search"].isChecked()                       # une seule entrée « Rechercher » cochée
    assert not hasattr(search, "mode")                           # menu de mode retiré
    assert not hq.p2p.isVisibleTo(hq)                                            # Soulseek coupé : pas de P2P
    assert "Settings ▸ Download" in hq.slsk_state.text()
    opened = []
    demo.ctrl.on("open_settings_section", opened.append)
    hq.slsk_btn.click()
    assert opened == ["download"] and not demo.errors


def test_c171_progress_sources_out_of_order_then_filters_on_late_results(demo, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    calls = _fake_sources(monkeypatch, ctrl, [], slsk=True)
    hq = demo.views["hq"]
    hq.set_filter(ResultFilter())
    demo.show_view("hq")
    hq.entry.setText("bicep")
    hq.run_search(force=True)
    ok, partial, source_done = calls["free"]
    assert hq.progress.isVisible() and hq.progress.summary().startswith("0 / 3 sources finished")
    assert not hq.progress.slsk_row.isHidden()                                   # délai Soulseek à part
    source_done("audius")                                                        # dans le désordre
    flac, mp3 = _t("flac", "FLAC", duration=268), _t("mp3", "MP3 320", source="audius", duration=268)
    partial([mp3])
    assert hq.progress.summary().startswith("1 / 3 sources finished  ·  1 results")
    hq.set_filter(ResultFilter(families=("lossless",)))                          # filtre posé en cours de route
    source_done("archive")
    ok([mp3, flac])                                                              # résultats arrivés après coup
    assert hq.table.displayed_iids() == ["flac"] and "1 hidden" in hq.info.text()
    assert hq.progress.running
    sok, _sp = calls["slsk"]
    sok([])
    assert not hq.progress.running and hq.progress.isHidden()
    assert ctrl.settings.hq_filters["families"] == ["lossless"]                 # mémorisé à part
    assert ctrl.settings.search_mode in ("all", "songs", "videos")
    hq.set_filter(ResultFilter())
    assert not demo.errors


def test_c171_known_total_shows_a_real_percentage(demo):  # noqa: F811
    from djsync.ui.search_progress import SearchProgress

    p = SearchProgress()
    p.set_known(37, 200)
    assert p.text.text() == "37 / 200" and p.bar.maximum() == 200 and p.bar.value() == 37
    p.set_known(200, 200)
    assert p.isHidden()


def test_c134_c175_sort_on_raw_values_and_gold_silver_text(demo, monkeypatch):  # noqa: F811
    from djsync.ui import theme

    ctrl = demo.ctrl
    calls = _fake_sources(monkeypatch, ctrl, [])
    hq = demo.views["hq"]
    hq.set_filter(ResultFilter())
    hq.entry.setText("x")
    hq.run_search(force=True)
    rows = [_t("a", "MP3 96", duration=600), _t("b", "MP3 320", duration=59), _t("c", "MP3 128", duration=75),
            _t("d", "FLAC", duration=5)]
    calls["free"][0](rows)
    hq.table.set_sort("bitrate")
    assert hq.table.displayed_iids()[:3] == ["a", "c", "b"]                     # 96 < 128 < 320 (pas « 128 » < « 320 » < « 96 »)
    hq.table.set_sort("duration")
    assert hq.table.displayed_iids() == ["d", "b", "c", "a"]                    # secondes, pas texte
    hq.table.set_sort("quality", descending=True)
    assert hq.table.displayed_iids()[0] == "d"                                  # sans perte en tête
    v = {i: hq.table.row(i).values for i in "bd"}
    assert v["d"]["quality__color"] == theme.GOLD and v["b"]["quality__color"] == theme.SILVER
    assert v["d"]["quality__tip"] == "Announced quality, checked after the download"
    assert "quality__dot" not in v["d"]                                          # texte, jamais une pastille (D14)
    assert not demo.errors


def test_c147_album_row_expands_in_place_and_stays_grouped(demo, monkeypatch):  # noqa: F811
    from djsync.core import freesources as F

    ctrl = demo.ctrl
    calls = _fake_sources(monkeypatch, ctrl, [])
    hq = demo.views["hq"]
    hq.set_filter(ResultFilter())
    hq.entry.setText("bicep")
    hq.run_search(force=True)
    found = F.archive_search("bicep", get=_ia_get)
    calls["free"][0](found)
    album = hq.table.row("archive:ep1")
    assert album.values["type"] == "Album" and album.values["type__icon"] == "disc"
    assert album.values["duration"] == "Album · 3 tracks" and "album" in album.tags
    assert album.values["title"].startswith("▸ ")
    single = hq.table.row(next(i for i in hq.table.displayed_iids() if i != "archive:ep1"))
    assert single.values["type"] == "Track" and single.values["type__icon"] == "music"
    assert not hq.limits.isHidden()                                             # limites dites à l'écran
    hq._cell_click("archive:ep1", "dl")                                         # ▸ : dépliage en place
    shown = hq.table.displayed_iids()
    i = shown.index("archive:ep1")
    kids = shown[i + 1:i + 4]
    assert [hq.table.row(k).values["title"].strip() for k in kids] == ["1. Glue", "2. Apricots", "3. Atlas"]
    hq.table.set_sort("duration", descending=True)                              # au tri, sous leur album
    shown = hq.table.displayed_iids()
    i = shown.index("archive:ep1")
    assert shown[i + 1:i + 4] == kids
    hq.set_filter(ResultFilter(families=("aac",)))                              # aucun titre ne passe : album masqué
    assert "archive:ep1" not in hq.table.displayed_iids()
    hq.set_filter(ResultFilter(families=("lossless",)))
    assert "archive:ep1" in hq.table.displayed_iids() and len(
        [k for k in hq.table.displayed_iids() if k.startswith("archive:ep1#")]) == 2   # Atlas (MP3) masqué
    hq.set_filter(ResultFilter())
    hq.table.select(["archive:ep1"])
    hq._refresh_buttons()
    assert hq.album_btn.isVisibleTo(hq)
    asked = []
    import djsync.ui.views.hq_view as V

    monkeypatch.setattr(V, "ask_and_download", lambda view, c, tracks, new_name="": asked.append((len(tracks), new_name)))
    hq._download_album()
    assert asked == [(3, "Isles EP")]                                           # playlist proposée, pas créée
    hq._play("archive:ep1")                                                     # double-clic : replié
    assert not [k for k in hq.table.displayed_iids() if k.startswith("archive:ep1#")]
    assert not demo.errors


def test_c147_classic_search_albums_get_the_same_marks(demo):  # noqa: F811
    from djsync.ui.views.common import result_row

    row = result_row(TrackResult(video_id="MPREb", title="Isles", artist="Bicep", result_type="album"))
    assert row.values["type__icon"] == "disc" and row.values["duration"] == "Album" and "album" in row.tags
    song = result_row(TrackResult(video_id="s", title="Glue", artist="Bicep"))
    assert song.values["type__icon"] == "music"


def test_c167_listen_to_an_equivalent(demo, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    calls = _fake_sources(monkeypatch, ctrl, [], slsk=True)
    hq = demo.views["hq"]
    hq.set_filter(ResultFilter())
    hq.entry.setText("glue")
    hq.run_search(force=True)
    x = _t("peer|glue", source="soulseek", slsk=Slsk(path="music\\Bicep\\01 - Bicep - Glue.flac"))
    calls["slsk"][0]([])
    hq._results = [x]
    hq._fill()
    hq.table.select(["peer|glue"])
    hq._refresh_buttons()
    assert hq.equiv_btn.isVisibleTo(hq) and not hq.preview_btn.isEnabled()
    queries, played = [], []
    official = TrackResult(video_id="yt1", title="Glue", artist="Bicep")
    monkeypatch.setattr(ctrl.service, "search", lambda q, **k: (queries.append(q), [official])[1], raising=False)
    monkeypatch.setattr(ctrl, "play_queue", lambda items, i=0: played.append(items[i]))
    hq._play("peer|glue")                                                       # double-clic : l'équivalent
    assert pump(demo, 3, lambda: played) and played[0] is official and queries == ["Bicep Glue"]
    assert hq.equiv.isVisibleTo(hq) and "Bicep - Glue" in hq.equiv.text()
    msgs = []
    ctrl.on("message", lambda kind, text: msgs.append(text))
    monkeypatch.setattr(ctrl.service, "search", lambda q, **k: [], raising=False)
    played.clear()
    hq._equivalent()
    assert pump(demo, 3, lambda: msgs) and not played and "No equivalent" in msgs[-1]
    assert not demo.errors
