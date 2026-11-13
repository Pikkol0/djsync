"""Suite de test_v140_rc5.py (1.4.2, C183 : fichier découpé pour que la passe parallèle --dist loadfile
ne dépende plus d'un seul gros fichier ; mêmes tests, aucun retiré)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .test_v140_rc5 import (  # noqa: F401,E402 (fixtures et aides du premier fichier)
    Path,
    ROOT,
    _drag_event,
    _table,
    demo,
    logging,
    pump,
    usb,
)


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
        # 1.4.2 (C183) : niveau posé sur le journal qui écrit le résumé (un test d'avant dans le même processus
        # peut avoir relevé celui de « djsync »)
        summary = logging.getLogger("djsync.db.local_library")
        summary.addHandler(caplog.handler)            # même si un test d'avant a coupé la remontée vers la racine
        with caplog.at_level(logging.INFO), caplog.at_level(logging.INFO, logger="djsync.db.local_library"):
            for _ in range(20):                                     # 20 écritures
                for pid in range(17):
                    lg.warning(f"Playlist {pid} not found in masterPlaylists6.xml! Did you add it manually?")
                noise.report()
            lg.warning("Something else")
        lines = [r.getMessage() for r in {id(r): r for r in caplog.records}.values()]   # un enregistrement reçu deux fois compte une fois
        assert sum("not found in masterPlaylists6" in x for x in lines) == 0
        assert sum("17 playlist(s) missing" in x for x in lines) == 1
        assert "Something else" in lines
    finally:
        lg.removeFilter(noise)
        logging.getLogger("djsync.db.local_library").removeHandler(caplog.handler)


# ------------------------------------------------------------------ B92 : colonne Taille
def test_b92_size_column_in_high_quality_search(demo):  # noqa: F811
    from djsync.ui.views.common import result_columns, result_row

    from djsync.ui.views.hq_view import hq_columns

    view = demo.views["search"]
    keys = [c.key for c in result_columns(with_size=True)]
    assert "size" in keys and "size" not in [c.key for c in result_columns()]
    assert "size" not in [c.key for c in view.table.columns] and "views" in [c.key for c in view.table.columns]
    hq = [c.key for c in hq_columns()]                  # 1.4.1 (C133) : Taille sur la page Haute qualité
    assert "size" in hq and "views" not in hq

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
