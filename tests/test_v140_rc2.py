"""1.4.0-rc.2 : retours de tests de la rc.1."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


# ------------------------------------------------------------------ B58 : onglet Améliorer
def test_b58_every_diagnostic_tab_opens_its_own_page(demo, monkeypatch):  # noqa: F811
    from djsync.ui import diag_tabs
    from djsync.ui.diagnostic_dialog import DiagnosticDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.improve_dialog import ImproveDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    kinds = {"missing": MissingFilesDialog, "dup": DuplicatesDialog, "quality": DiagnosticDialog,
             "improve": ImproveDialog}
    for tab in diag_tabs.TABS:
        if tab == "uniformize":
            continue
        demo.open_diagnostic(tab)
        assert pump(demo, 2, lambda t=tab: isinstance(demo.stack.currentWidget(), kinds[t])), tab
        assert demo.ctrl.settings.diag_tab == tab
        demo.stack.currentWidget().close()
        pump(demo, 0.3)
    demo.ctrl.settings.diag_tab = "improve"                 # dernier onglet mémorisé : Améliorer
    demo.open_diagnostic()
    assert pump(demo, 2, lambda: isinstance(demo.stack.currentWidget(), ImproveDialog))
    assert demo.stack.currentWidget() in demo._diag_pages()
    demo.stack.currentWidget().close()
    assert not demo.errors


# ------------------------------------------------------------------ B63 : tâche reprise au retour
def test_b63_quality_page_comes_back_with_its_task(demo):  # noqa: F811
    from djsync.ui.diagnostic_dialog import DiagnosticDialog

    demo.open_diagnostic("quality")
    page = demo.stack.currentWidget()
    assert isinstance(page, DiagnosticDialog)
    demo.show_view("library")                                  # ailleurs pendant la tâche
    assert demo.stack.currentWidget() is not page
    demo.open_diagnostic()                                     # bouton Diagnostic : même page
    assert demo.stack.currentWidget() is page
    demo.open_diagnostic("quality")
    assert demo.stack.currentWidget() is page
    pages = [demo.stack.widget(i) for i in range(demo.stack.count())]
    assert sum(isinstance(p, DiagnosticDialog) for p in pages) == 1
    page.close()
    assert not demo.errors


# ------------------------------------------------------------------ B61 / B65 : colonnes
def test_b65_every_track_table_remembers_its_columns(demo):  # noqa: F811
    from djsync.ui.improve_dialog import ImproveDialog
    from djsync.ui.widgets import TrackTable

    for view in demo.views.values():
        for table in view.findChildren(TrackTable):
            assert table._layout_key, type(view).__name__
    page = ImproveDialog(demo.views["home"], demo.ctrl)
    assert page.table._layout_key == "improve"
    page.close()


def test_b61_narrow_last_column_does_not_eat_the_title(demo):  # noqa: F811
    v = demo.views["downloads"]
    table = v.table
    table._user_widths["title"] = 30                       # largeur trop petite retenue d'avant
    demo.show_view("downloads")
    demo.resize(1400, 800)
    pump(demo, 0.5)
    table._fit_columns()
    head = table.horizontalHeader()
    idx = {c.key: i for i, c in enumerate(table.columns)}
    from djsync.ui import theme

    assert head.sectionSize(idx["title"]) >= theme.px(160)
    assert head.sectionSize(idx["time"]) < theme.px(160)   # l'Heure garde sa taille


# ------------------------------------------------------------------ C132 : barre Espace occupé
def test_c132_other_files_first_and_caches_not_grey(demo):  # noqa: F811
    from djsync.ui.space_card import PART_COLORS, SpaceBar

    bar = SpaceBar()
    bar.set_parts({"music": 5, "caches": 1, "other": 9, "free": 20})
    keys = [k for k, _v in bar.ordered()]
    assert keys[0] == "other" and keys[-1] == "free"
    assert PART_COLORS["caches"] != PART_COLORS["other"] and PART_COLORS["caches"].upper() != "#9AA0A6"


# ------------------------------------------------------------------ B57 : sommaire des Paramètres
def test_b57_settings_nav_follows_what_is_visible(demo):  # noqa: F811
    v = demo.views["settings"]
    demo.show_view("settings")
    pump(demo, 0.5)
    bar = v.area.verticalScrollBar()
    bar.setValue(0)                                        # en haut de la page
    v._set_nav("djsync")                                   # section retenue d'une visite précédente
    v._sync_nav()
    assert v._current_section == "general"
    v._start_section = "advanced"                          # ouverture sur une section demandée
    v._sync_nav()
    assert bar.value() > 0 and v._current_section != "general"


# ------------------------------------------------------------------ C139 : afficher dans l'explorateur
def test_c139_reveal_command_per_system(tmp_path):
    from djsync.ui.reveal import reveal, reveal_command

    f = tmp_path / "a b.m4a"
    f.write_bytes(b"x")
    assert reveal_command(f, "win32").startswith("explorer /select,")      # B68 (rc.3) : chaîne
    assert reveal_command(f, "darwin") == ["open", "-R", str(f)]
    assert reveal_command(f, "linux") is None
    assert reveal(tmp_path / "absent.m4a") is False


def test_c139_library_menu_has_reveal_and_missing_file_is_explained(demo, monkeypatch):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui import reveal as R

    v = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: len(v.table.displayed_iids()) > 0)
    iid = v.table.displayed_iids()[0]
    v.table.select([iid])
    entries = [e for e in v._menu([iid]) if e]
    label = t("reveal.finder") if R.sys.platform == "darwin" else t("reveal.explorer")
    entry = next(e for e in entries if e[0] == label)
    shown = []
    monkeypatch.setattr(R, "reveal", lambda p: shown.append(p) or False)
    msgs = []
    monkeypatch.setattr(demo.ctrl, "message", lambda kind, text: msgs.append(kind))
    entry[1]()
    assert shown and msgs == ["error"]


# ------------------------------------------------------------------ B64 : playlists SoundCloud
def _sc_api(i, title, drm=False):
    proto = "ctr-encrypted-hls" if drm else "hls"
    return {"id": i, "title": title, "user": {"username": "Uploader"}, "duration": 200000,
            "permalink_url": f"https://soundcloud.com/u/t{i}", "policy": "MONETIZE",
            "publisher_metadata": {"artist": "Artiste"},
            "media": {"transcodings": [{"format": {"protocol": proto}}]}}


def test_b64_soundcloud_playlist_entries_are_completed_and_drm_flagged():
    from djsync.core import soundcloud as sc
    from djsync.core.urlimport import resolve_direct
    from djsync.models import UrlKind

    calls = []

    def fetch(url, query):
        calls.append(query["ids"])
        return [_sc_api(int(i), f"Son {i}", drm=int(i) % 2 == 0) for i in query["ids"].split(",")]

    details = lambda ids: sc.tracks_details(ids, fetch=fetch)  # noqa: E731
    entries = [{"id": str(i), "url": f"https://api.soundcloud.com/tracks/{i}"} for i in range(1, 121)]
    info = {"_type": "playlist", "title": "Rap", "entries": entries}
    res = resolve_direct("https://soundcloud.com/u/sets/rap", UrlKind.SOUNDCLOUD,
                         extractor=lambda u, o: info, details=details)
    assert len(calls) == 3                                     # par lots de 50
    assert [t.title for t in res.tracks[:2]] == ["Son 1", "Son 2"] and res.tracks[0].artist == "Artiste"
    assert res.tracks[0].duration_seconds == 200 and res.tracks[0].source_url.startswith("https://soundcloud.com/")
    assert not res.tracks[0].protected and res.tracks[1].protected


def test_b64_protected_track_downloads_the_youtube_music_version(tmp_path):
    from djsync.core.service import MusicService, ProtectedTrackError
    from djsync.models import Candidate, TrackResult

    svc = MusicService.__new__(MusicService)
    got = []

    class D:
        def download(self, track, dest, prog, tag=True):
            got.append(track.source)
            if track.source == "soundcloud":
                raise RuntimeError("ERROR: [soundcloud] 1: This video is DRM protected")
            return "ok"

    svc._downloader = D()
    yt = TrackResult(video_id="abc", title="Son", artist="Artiste", duration_seconds=200, source="ytmusic",
                     result_type="song")
    svc.match_spotify = lambda src, per_type=5: [Candidate(yt, 95.0)]
    sc = TrackResult(video_id="1", title="Son", artist="Artiste", duration_seconds=200, source="soundcloud")
    assert svc.download(sc, tmp_path) == "ok" and got == ["soundcloud", "ytmusic"]   # erreur DRM : relais
    got.clear()
    from dataclasses import replace

    sc = replace(sc, protected=True)
    assert svc.download(sc, tmp_path) == "ok" and got == ["ytmusic"]                  # connu : direct
    svc.match_spotify = lambda src, per_type=5: []
    with pytest.raises(ProtectedTrackError):
        svc.download(sc, tmp_path)


# ------------------------------------------------------------------ B66 / B60 : erreurs connues
def test_b66_known_errors_are_explained():
    from djsync.i18n import t
    from djsync.ui.controller import known_error

    assert known_error(Exception("Sign in to confirm you're not a bot")) == "error.youtube_bot"
    assert known_error(Exception("[soundcloud] 1: This video is DRM protected")) == "error.drm"
    assert known_error(Exception("Soulseek: Banned")) == "error.slsk_banned"
    assert known_error(Exception("other")) == ""
    assert "VPN" in t("error.youtube_bot")


def test_b66_bot_refusals_pause_youtube_then_retry_when_browser_chosen(demo):  # noqa: F811
    from djsync.models import DownloadJob, TrackResult

    c = demo.ctrl
    jobs = []
    for i in range(4):
        tr = TrackResult(video_id=f"v{i}", title=f"T{i}", artist="A", source="youtube")
        job = DownloadJob(id=i, track=tr, status="error", reason="error.youtube_bot")
        jobs.append(job)
    c.jobs[:] = jobs
    for job in jobs[:3]:
        c._youtube_bot(job)
    assert c.youtube_paused(jobs[0])
    retried = []
    c.retry = lambda job: retried.append(job)
    c.retry_bot_failures()
    assert retried == jobs and not c.youtube_paused(jobs[0])


# ------------------------------------------------------------------ B60 : pair bloqué -> autre pair
def _slsk(user, path, free=True, speed=0, queue=0):
    from djsync.core.soulseek import SlskResult

    return SlskResult(user, path, 9_000_000, path.rsplit(".", 1)[-1], free_slot=free, speed=speed, queue=queue)


def test_b60_alternatives_same_file_other_users_fast_first():
    from djsync.core.soulseek import alternatives

    chosen = _slsk("a", "x\\Bicep - Glue.flac")
    pool = [chosen, _slsk("b", "y\\bicep - glue.flac", free=False, queue=4),
            _slsk("c", "z\\Bicep - Glue.flac", speed=900_000), _slsk("d", "z\\Bicep - Glue.mp3"),
            _slsk("e", "z\\Bicep - Other.flac"), _slsk("c", "w\\Bicep - Glue.flac")]
    assert [r.username for r in alternatives(chosen, pool)] == ["c", "b"]


def test_b60_stalled_peer_switches_to_another(demo, monkeypatch, tmp_path):  # noqa: F811
    from djsync.core.soulseek import SoulseekStalled
    from djsync.models import DownloadJob
    from djsync.ui.ctrl.soulseek import track_of

    ctrl = demo.ctrl
    first, second = _slsk("slow", "x\\Bicep - Glue.flac"), _slsk("fast", "y\\Bicep - Glue.flac")
    out = tmp_path / "Bicep - Glue.flac"
    out.write_bytes(b"x")
    tried = []

    class C:
        connected = True

        def download(self, result, progress=None, should_stop=None, stall=0.0, **kw):     # rc.3 : reach…
            tried.append((result.username, stall))
            if result.username == "slow":
                raise SoulseekStalled("no data for 60 s")
            return out

    ctrl.slsk = C()
    job = DownloadJob(id=777, track=track_of(first))
    ctrl._slsk_alts = {777: [second]}
    assert ctrl._slsk_download_any(job, first, lambda p, s: None) == out
    assert [u for u, _s in tried] == ["slow", "fast"] and tried[0][1] == 60.0
    assert job.track.slsk.username == "fast"


def test_b60_share_by_default_and_speed_shown():
    from djsync.settings import Settings
    from djsync.ui.views.common import result_row
    from djsync.ui.ctrl.soulseek import track_of

    assert Settings().soulseek_share is True
    row = result_row(track_of(_slsk("a", "x\\Bicep - Glue.flac", speed=1_500_000)))
    assert "1.5" in row.values["type"]


# ------------------------------------------------------------------ B59 : recherche haute qualité
def test_b59_no_answer_is_sent_again_once(monkeypatch):
    from djsync.core import soulseek as S

    class Req:
        def __init__(self, n):
            self.results = [] if n == 1 else [object()]

    sent = []

    class Searches:
        def search(self, q):
            sent.append(q)
            return Req(len(sent))

        def remove_request(self, r):
            pass

    c = S.SoulseekClient("u", "p", ".")
    c._client = type("X", (), {"searches": Searches()})()
    c._call = lambda coro, timeout: coro
    monkeypatch.setattr(S, "from_aioslsk", lambda r: [])
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    c.search("fred again", seconds=0.01)
    assert sent == ["fred again", "fred again"]


def test_b59_hq_search_shows_searching_not_no_result(demo, monkeypatch):  # noqa: F811
    view = demo.views["hq"]                         # 1.4.1 (C133) : la recherche haute qualité a sa page
    ctrl = demo.ctrl
    monkeypatch.setattr(type(ctrl), "slsk_ready", property(lambda self: True))
    monkeypatch.setattr(ctrl, "free_search", lambda q, ok, partial=None, source_done=None: ok([]))
    monkeypatch.setattr(ctrl, "slsk_search", lambda q, ok, partial=None: partial([]))
    skel = []
    monkeypatch.setattr(view.table, "show_skeleton", lambda: skel.append(1))
    view.entry.setText("fred again")
    view.run_search(force=True)
    pump(demo, 0.3)
    assert skel


# ------------------------------------------------------------------ C137 : vraie qualité expliquée
def test_c137_settings_explain_real_quality_and_warn_on_mp3(demo):  # noqa: F811
    from djsync.i18n import t

    v = demo.views["settings"]
    assert any("MP3 160" in c.text() for c in v.quality_table.cells)      # rc.3 : grille (B69)
    v.format_menu.setCurrentText(v._format_labels["mp3_320"])         # 1.4.1 (C143) : une seule liste
    assert not v.format_warn.isHidden()
    v.format_menu.setCurrentText(v._format_labels["original"])
    assert v.format_warn.isHidden()
    assert "does not bring back" in t("settings.quality_mp3_320_tip").lower()
