"""1.4.0-rc.4 : retours de tests de la rc.3."""
from __future__ import annotations

import logging

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401


# ------------------------------------------------------------------ B77 : dossier surveillé (Windows)
def test_b77_same_folder_whatever_the_slashes():
    from djsync.core.watcher import same_folder

    assert same_folder("C:/Users/DJ/Watch", "C:\\Users\\DJ\\Watch")
    assert same_folder("/music/watch/", "/music/watch")
    assert not same_folder("/music/watch", "/music/other")


def test_b77_watcher_kept_between_ticks_and_file_taken(demo, tmp_path, monkeypatch):  # noqa: F811
    import os
    import time

    from djsync.core import watcher

    monkeypatch.setattr(watcher, "MIN_AGE", 0)
    ctrl = demo.ctrl
    folder = tmp_path / "watch"
    folder.mkdir()
    song = folder / "a.m4a"
    song.write_bytes(b"x" * 2000)
    old = time.time() - 60
    os.utime(song, (old, old))
    # le réglage écrit avec l'autre séparateur (comme la boîte de choix de dossier sous Windows)
    ctrl.settings.watch_folder = str(folder) + os.sep            # autre écriture du même dossier
    taken = []
    monkeypatch.setattr(ctrl, "import_files", lambda files, **kw: taken.extend(files))
    ctrl.watch_tick()
    pump(demo, 0.5, lambda: not getattr(ctrl, "_watch_busy", False))
    first = ctrl._watch
    ctrl.watch_tick()
    pump(demo, 1.0, lambda: bool(taken))
    assert ctrl._watch is first                     # pas recréé : il se souvient du passage précédent
    assert taken and "DJSync imported" in taken[0]


# ------------------------------------------------------------------ B81 : faux « free download »
def test_b81_smart_links_are_not_free_downloads():
    from djsync.core.soundcloud import free_download

    assert free_download({"purchase_url": "https://yungeenace.ffm.to/stepharder",
                          "purchase_title": "Stream/download"}) is None
    assert free_download({"purchase_url": "https://artist.lnk.to/x", "purchase_title": "FREE DL"}) is None
    assert free_download({"purchase_url": "https://www.beatport.com/x", "purchase_title": "Download"}) is None
    assert free_download({"purchase_url": "https://hypeddit.com/x", "purchase_title": "Buy"})
    assert free_download({"purchase_url": "https://x.example/y", "purchase_title": "FREE DL"})


# ------------------------------------------------------------------ C148, B80 : vraies cases
def test_c148_checkboxes_header_state_and_range(demo, monkeypatch):  # noqa: F811
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from djsync.models import TrackResult
    from djsync.ui.table import CHECK_MIXED, CHECK_OFF, CHECK_ON, _CheckDelegate

    v = demo.views["import"]
    tracks = [TrackResult(video_id=f"sc{i}", title=f"T{i}", artist="A", source="soundcloud") for i in range(5)]
    v.mode = "direct"
    v._tracks = {x.video_id: x for x in tracks}
    from djsync.ui.views.common import result_row

    v.dl_table.set_rows([result_row(x, checked=False) for x in tracks])
    assert isinstance(v.dl_table.itemDelegateForColumn(0), _CheckDelegate)
    assert v.dl_table.header_check_state() == CHECK_OFF
    v._toggle(v.dl_table, "sc0")
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: Qt.ShiftModifier))
    v._toggle(v.dl_table, "sc3")                                  # Maj + clic : plage 0 → 3
    checked = [r.iid for r in v.dl_table.all_rows() if r.values["chk"] == CHECK_ON]
    assert checked == ["sc0", "sc1", "sc2", "sc3"]
    assert v.dl_table.header_check_state() == CHECK_MIXED
    assert "4" in v.count_lbl.text() and "5" in v.count_lbl.text()
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: Qt.NoModifier))
    v._toggle_all(v.dl_table)
    assert v.dl_table.header_check_state() == CHECK_ON
    v.dl_table.select(["sc1", "sc2"])
    v._toggle_selected(v.dl_table)                                # Espace
    assert v.dl_table.row("sc1").values["chk"] == CHECK_OFF
    assert not demo.errors


def test_b80_header_corners_rounded():
    from djsync.ui import theme

    css = theme.stylesheet() if hasattr(theme, "stylesheet") else ""
    if not css:
        pytest.skip("pas de feuille de style exposée")
    assert "section:horizontal:first" in css and "border-top-left-radius" in css


# ------------------------------------------------------------------ C151 : bouton Free Download
def test_c151_free_download_button_for_selection(demo):  # noqa: F811
    from djsync.models import TrackResult
    from djsync.ui.views.common import result_row

    v = demo.views["import"]
    a = TrackResult(video_id="a", title="A", artist="X", source="soundcloud", free_download_url="https://hypeddit.com/a")
    b = TrackResult(video_id="b", title="B", artist="X", source="soundcloud")
    v.mode = "direct"
    v._tracks = {"a": a, "b": b}
    v.dl_table.set_rows([result_row(a, checked=True), result_row(b, checked=True)])
    v.dl_table.select(["b"])
    v._refresh_buttons()
    assert v.free_btn.isHidden()
    opened = []
    demo.ctrl.on("open_url", opened.append)
    v.dl_table.select(["a", "b"])
    v._refresh_buttons()
    assert not v.free_btn.isHidden()
    v.free_btn.click()
    assert opened == ["https://hypeddit.com/a"]


# ------------------------------------------------------------------ C152 : vues YouTube
def test_c152_views_label_says_youtube():
    from djsync.i18n import fr

    assert "YouTube" in fr.STRINGS["settings.fetch_views"]


# ------------------------------------------------------------------ C153 : carte Activité
def test_c153_activity_card_opens_downloads(demo):  # noqa: F811
    demo.show_view("home")
    demo.an_open.click()
    assert demo.stack.currentWidget() is demo.views["downloads"]
    demo.show_view("home")
    demo.an_ring.on_click()
    assert demo.stack.currentWidget() is demo.views["downloads"]


# ------------------------------------------------------------------ B75 : YouTube plafonné à ≈ 192
def test_b75_youtube_and_opus_signature_capped_at_192():
    from djsync.core.quality import AudioInfo

    assert AudioInfo(codec="wav", sample_rate=48000, cutoff=20100, source="YouTube").real_kbps == 192
    assert AudioInfo(codec="m4a", sample_rate=44100, cutoff=20100, source="YouTube Music").real_kbps == 192
    assert AudioInfo(codec="wav", sample_rate=48000, cutoff=20100).real_kbps == 192      # signature Opus
    assert AudioInfo(codec="mp3", sample_rate=44100, cutoff=20100, bitrate=320).real_kbps == 320


def test_b75_quality_table_and_setting_text(demo):  # noqa: F811
    from djsync.i18n import t

    assert "192" in t("yt.settings_best")
    v = demo.views["settings"]
    cells = [c.text() for c in v.quality_table.cells]
    assert any("160–192" in c for c in cells)


# ------------------------------------------------------------------ C146 : choix du flux à l'accueil
def test_c146_welcome_quality_step(demo, monkeypatch):  # noqa: F811
    from djsync.ui.welcome import WelcomeDialog

    s = demo.ctrl.settings
    monkeypatch.setattr(s, "save", lambda *a, **k: None)
    s.youtube_best = False
    w = WelcomeDialog(demo, demo.ctrl)
    w._choose(s.language)
    w._to_quality()
    assert w._step == 3 and w.yt_buttons["m4a"].isChecked() and w.yt_warn.isHidden()
    w._pick_yt("best")
    assert not w.yt_warn.isHidden()
    w._finish()
    assert s.youtube_best is True and s.welcome_done is True
    v = demo.views["settings"]
    v.yt_best_var.setChecked(False)
    assert v.yt_best_warn.isHidden()
    v.yt_best_var.setChecked(True)
    assert not v.yt_best_warn.isHidden()


# ------------------------------------------------------------------ C155 : fenêtres l'une après l'autre
def test_c155_startup_windows_one_at_a_time(demo):  # noqa: F811
    shown = []
    demo._startup_queue.clear()
    busy = {"on": True}
    demo.startup_dialog_open = lambda: busy["on"]           # une fenêtre est ouverte
    demo.queue_startup("light_mode", lambda: shown.append("light"))
    demo.queue_startup("welcome", lambda: shown.append("welcome"))
    demo.queue_startup("light_mode", lambda: shown.append("light"))   # pas deux fois
    demo._pump_startup()
    assert shown == []
    busy["on"] = False
    demo._pump_startup()
    assert shown == ["welcome"]                              # l'accueil d'abord
    demo._pump_startup()
    assert shown == ["welcome", "light"]
    del demo.startup_dialog_open


def test_c155_update_is_a_banner_not_a_window(demo):  # noqa: F811
    from types import SimpleNamespace

    demo.ctrl.settings.welcome_done = True
    demo._app_update(SimpleNamespace(version="9.9.9", asset=None, url="https://x", prerelease=False), "1.4.0")
    assert demo.update_bar.isVisibleTo(demo) and "9.9.9" in demo.update_text.text()
    assert not demo.startup_dialog_open()


# ------------------------------------------------------------------ B76 : volet replié
def test_b76_compact_two_rings_fit_the_column(demo):  # noqa: F811
    from djsync.ui import theme
    from djsync.ui.app import SIDEBAR_COMPACT

    # 1.4.0-rc.5 (C161) : anneaux de 30 px dans un volet de 56 px (marges 10 + cartes 1) : toujours entiers
    inner = theme.px(SIDEBAR_COMPACT) - 2 * theme.px(10) - 2 * theme.px(1)
    assert demo.an_ring.width() <= inner and demo.dl_ring.width() <= inner
    demo.ctrl.settings.sidebar_compact = "on"
    demo._compact = None
    demo._update_compact()
    b = demo._nav["settings"]
    side = theme.px(SIDEBAR_COMPACT - 12)
    assert b.height() == side or b.maximumHeight() == side
    demo.ctrl.settings.sidebar_compact = "off"
    demo._compact = None
    demo._update_compact()


# ------------------------------------------------------------------ C150 : colonnes au contenu
def test_c150_columns_fit_content(demo):  # noqa: F811
    from djsync.models import TrackResult
    from djsync.ui.views.common import result_row

    v = demo.views["import"]
    t = v.dl_table
    assert t.fit_content
    rows = [result_row(TrackResult(video_id=f"x{i}", title="Short", artist="A", source="soundcloud"), checked=True)
            for i in range(3)]
    for r in rows:
        r.values["source"] = "SoundCloud · protected (YouTube Music version)"
    t.set_rows(rows)
    assert t._content_width("source") > t._content_width("title")
    assert t._content_width("lib") == 0                        # colonne vide : réduite à son titre


# ------------------------------------------------------------------ B78 : sources gratuites
def test_b78_archive_order_relevance_and_parallel():
    import threading
    import time

    from djsync.core import freesources as F

    docs = [{"identifier": f"jul{i}", "title": f"Jul - Album {i}", "creator": "Jul"} for i in range(6)]
    active, peak = [0], [0]
    lock = threading.Lock()

    def get(url, params=None):
        if url == F.ARCHIVE_SEARCH:
            return {"response": {"docs": docs}}
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with lock:
            active[0] -= 1
        ident = url.rsplit("/", 1)[1]
        return {"files": [{"name": f"{ident}-02.mp3", "format": "VBR MP3", "title": "Deux", "track": "2"},
                          {"name": f"{ident}-01.flac", "format": "Flac", "title": "Un", "track": "1"}]}

    start = time.monotonic()
    out = F.archive_search("Jul", get=get)
    took = time.monotonic() - start
    assert peak[0] > 1 and took < 0.2 * 6 * 0.6               # en parallèle
    assert [x.video_id.split("/")[0] for x in out][:2] == ["archive:jul0", "archive:jul0"]   # ordre d'archive.org
    assert [x.title for x in out][:2] == ["Un", "Deux"]         # ordre des pistes
    assert len(out) == 12                                       # pistes sans artiste propre trouvées par l'album


def test_b78_sources_in_parallel_with_partial():
    from djsync.core import freesources as F

    seen = []
    orig = (F.archive_search, F.audius_search)
    try:
        F.archive_search = lambda q, get=None: [1]
        F.audius_search = lambda q, get=None: [2]
        out = F.search_all("x", ["archive", "audius"], partial=lambda n, rs: seen.append(n))
    finally:
        F.archive_search, F.audius_search = orig
    assert sorted(out) == [1, 2] and sorted(seen) == ["archive", "audius"]


# ------------------------------------------------------------------ B82 : SoundCloud
def test_b82_known_errors():
    from djsync.ui.controller import known_error

    assert known_error("ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271") \
        == "error.browser_cookies"
    assert known_error("ERROR: [soundcloud] x: Unable to download JSON metadata: HTTP Error 404: Not Found") \
        == "error.sc_private"


def test_b82_cookie_error_detected():
    from djsync.core import downloader as D

    assert D.cookie_error(Exception("Could not copy Chrome cookie database"))
    assert not D.cookie_error(Exception("HTTP Error 403"))


# ------------------------------------------------------------------ B83 : Soulseek, cas limites
def _r(user, path="x\\Bicep - Glue.flac", duration=200):
    from djsync.core.soulseek import SlskResult

    return SlskResult(user, path, 9_000_000, "flac", duration=duration, free_slot=True)


def test_b83_state_column_shows_peer_state():
    from djsync.models import DownloadJob, TrackResult
    from djsync.ui.ctrl.soulseek import peer_state

    job = DownloadJob(id=1, track=TrackResult(video_id="x", title="t", artist="a"))
    job.status, job.percent = "downloading", 0.0
    job.peer_state = peer_state("queued_at:12", 0.0)
    assert "12" in job.status_label and "%" not in job.status_label
    job.peer_state = peer_state("downloading", 40.0)
    assert job.status_label.endswith("%")


def test_b83_research_once_then_clear_message(demo):  # noqa: F811
    from djsync.core.soulseek import SoulseekStalled
    from djsync.models import DownloadJob
    from djsync.ui.ctrl.soulseek import track_of

    ctrl = demo.ctrl
    searches = []

    class C:
        connected = True

        def download(self, result, progress=None, should_stop=None, stall=0.0, reach=0.0, queue_wait=0.0):
            if result.username == "fresh":
                return "ok"
            raise SoulseekStalled("no answer from the user in 20 s")

        def search(self, query, duration=0, **kw):
            searches.append(query)
            return [_r("mute"), _r("fresh"), _r("far", duration=260)]

    ctrl.slsk = C()
    job = DownloadJob(id=21, track=track_of(_r("mute")))
    ctrl._slsk_alts = {21: []}
    assert ctrl._slsk_download_any(job, _r("mute"), lambda p, s: None) == "ok"
    assert len(searches) == 1

    class Never(C):
        def download(self, *a, **k):
            raise SoulseekStalled("no answer from the user in 20 s")

        def search(self, query, duration=0, **kw):
            searches.append(query)
            return []

    ctrl.slsk = Never()
    job = DownloadJob(id=22, track=track_of(_r("mute")))
    ctrl._slsk_alts = {22: []}
    from djsync.core.soulseek import SoulseekError
    from djsync.i18n import t

    with pytest.raises(SoulseekError, match=t("slsk.gave_up")[:20]):
        ctrl._slsk_download_any(job, _r("mute"), lambda p, s: None)
    assert len(searches) == 2 and not ctrl._slsk_busy()


def test_b83_library_noise_filtered_and_router_seen():
    from djsync.core.soulseek import Metrics, _QuietPeersFor, _RouterWatch

    f = _QuietPeersFor("aioslsk")

    def rec(name, level, msg):
        return logging.LogRecord(name, level, __file__, 1, msg, None, None)

    assert not f.filter(rec("aioslsk.network.network", logging.INFO, "successfully fulfilled ConnectToPeer request"))
    assert not f.filter(rec("aioslsk.network.connection", logging.WARNING, "read error"))
    assert f.filter(rec("aioslsk.network.upnp", logging.INFO, "found 0 IGD devices"))
    assert f.filter(rec("aioslsk.network.network", logging.INFO, "UPnP: rechecking port mapping in 600 seconds"))
    assert f.filter(rec("djsync.core.soulseek", logging.INFO, "anything"))
    m = Metrics()
    h = _RouterWatch(m)
    h.emit(rec("aioslsk.network.upnp", logging.INFO, "found 0 IGD devices"))
    assert m.routers == 0
    h.emit(rec("aioslsk.network.upnp", logging.INFO, "found 1 IGD devices"))
    assert m.routers == 1
