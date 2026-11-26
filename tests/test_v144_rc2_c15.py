"""1.4.4-rc.2 : C15, mode live (voie XML seule).
    pytest -q tests/test_v144_rc2_c15.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from djsync.core import live as L

from .test_v122 import demo, usb  # noqa: F401  (fixtures)


def _ready(path, title="Song", artist="Artist", url=""):
    return L.LiveTrack(url or f"{artist} - {title}", title, artist, url=url, path=str(path), status="ready",
                       bpm=128.0, key_name="Am", duration=200.0,
                       beats=[(1, 12800, 500), (2, 12800, 969), (3, 12800, 1438), (4, 14000, 1906)],
                       cues=[(0, 500, ""), (1, 969, "Drop")])


def test_c15_xml_is_read_back_by_pyrekordbox(tmp_path):
    from pyrekordbox import RekordboxXml

    song = tmp_path / "Mon son é.mp3"
    song.write_bytes(b"x")
    s = L.LiveSession("2026-11-26", [_ready(song), L.LiveTrack("k", "Broken", "X", status="error")])
    path = L.write_xml(s, tmp_path)
    xml = RekordboxXml(path)
    tracks = xml.get_tracks()
    assert len(tracks) == 1                                         # un son en erreur n'entre pas dans le XML
    tr = tracks[0]
    raw = path.read_text(encoding="utf-8")
    assert "Mon%20son%20%C3%A9.mp3" in raw and 'Location="file://localhost/' in raw
    assert "file://localhost//" not in raw                         # un seul « / » (Mac comme Windows)
    assert tr["Name"] == "Song" and tr["Tonality"] == "Am" and float(tr["AverageBpm"]) == 128.0
    assert [(round(x.Inizio, 3), x.Bpm, x.Battito) for x in tr.tempos] == [(0.5, 128.0, 1), (1.906, 140.0, 4)]
    marks = [(m.Num, round(m.Start, 3), m.Name) for m in tr.marks]
    assert marks == [(-1, 0.5, ""), (0, 0.969, "Drop")]          # mémoire, puis hot cue A
    assert xml.get_playlist("DJSync Live – 2026-11-26") is not None


def test_c15_location_windows_and_mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert L.location(r"C:\Music\DJSync Live\a b.mp3") == "file://localhost/C:/Music/DJSync%20Live/a%20b.mp3"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert L.location("/Users/me/Music/é.mp3") == "file://localhost/Users/me/Music/%C3%A9.mp3"


def test_c15_atomic_replace_never_half_written(tmp_path, monkeypatch):
    s = L.LiveSession("2026-11-26", [_ready(tmp_path / "a.mp3")])
    path = L.write_xml(s, tmp_path)
    before = path.read_bytes()

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    s.tracks.append(_ready(tmp_path / "b.mp3", "Other"))
    with pytest.raises(OSError):
        L.write_xml(s, tmp_path)
    assert path.read_bytes() == before                              # l'ancien XML reste entier
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_c15_register_survives_a_restart_and_keeps_its_start_date(tmp_path):
    s = L.LiveSession("2026-11-25", [_ready(tmp_path / "a.mp3")], started=1.0)
    L.save(s, tmp_path)
    again = L.current(tmp_path)                                     # le lendemain (set après minuit) : même live
    assert again.date == "2026-11-25" and again.tracks[0].beats[0] == (1, 12800, 500)
    again.done = True
    L.save(again, tmp_path)
    assert L.current(tmp_path).date == L.today()                     # rangé : un nouveau live


def test_c15_tidy_plan_no_duplicate_on_same_path(tmp_path):
    a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
    s = L.LiveSession("2026-11-26", [_ready(a, "A"), _ready(b, "B")])
    collection = [NS(path=str(a), content_id=7, title="A", artist="Artist")]   # glissé sur un deck par Rekordbox
    plan = L.tidy_plan(s, collection)
    assert [(tr.title, found.content_id if found else None) for tr, found in plan] == [("A", 7), ("B", None)]


def test_c15_existing_track_found_by_link_then_title():
    tracks = [NS(source_url="https://youtu.be/x", title="Other", artist="Z", path="/a"),
              NS(source_url=None, title="Song (Radio Edit)", artist="Artist", path="/b")]
    assert L.find_existing(tracks, "https://youtu.be/x", "?", "?").path == "/a"
    assert L.find_existing(tracks, "", "Song", "Artist").path == "/b"
    assert L.find_existing(tracks, "", "Nope", "Artist") is None


# ------------------------------------------------------------------ service (sans Rekordbox)
class _Disp:
    def __init__(self):
        self.pools = []

    def submit(self, fn, ok=None, err=None, pool="net"):
        self.pools.append(pool)
        try:
            r = fn()
        except Exception as exc:  # noqa: BLE001
            if err:
                err(exc)
            return
        if ok:
            ok(r)

    def post(self, fn, *a):
        fn(*a)


def _ctrl(tmp_path, monkeypatch):
    from djsync.ui import live_service

    monkeypatch.setattr(live_service.LiveService, "data_dir", staticmethod(lambda: tmp_path))
    paused = []
    downloads = []

    def download(track, folder, on_progress=None):
        f = Path(folder) / f"{track.title}.mp3"
        f.write_bytes(b"x")
        downloads.append(f)
        return NS(file_path=str(f))

    ctrl = NS(settings=NS(local_music_dir=str(tmp_path / "music"), ffmpeg_location="", auto_cue=True,
                          backup_keep=3, key_notation="camelot"),
              dispatcher=_Disp(), messages=[], events=[], library=None, is_local=False,
              analysis=NS(running=True, paused=False), service=NS(download=download))
    ctrl.message = lambda kind, text: ctrl.messages.append((kind, text))
    ctrl._emit = lambda *a: ctrl.events.append(a)

    def pause(p):
        paused.append(p)
        ctrl.analysis.paused = p
    ctrl.pause_analysis = pause
    return ctrl, paused, downloads


def _fake_analysis(monkeypatch):
    import djsync.analysis as A

    grid = NS(beats=[(1, 0.5), (2, 0.969)], beat_tempos=lambda: [128.0, 128.0])
    monkeypatch.setattr(A, "analyze_file", lambda path, ffmpeg=None, **k: NS(
        duration=200.0, bpm=128.0, key=NS(name="Am"), grid=grid, first_downbeat_ms=500))


def test_c15_chain_priority_pool_pauses_analysis_and_writes_xml(tmp_path, monkeypatch):
    from djsync.ui.live_service import LiveService

    _fake_analysis(monkeypatch)
    ctrl, paused, downloads = _ctrl(tmp_path, monkeypatch)
    svc = LiveService(ctrl)
    tr = svc.add(NS(title="Song", artist="Artist", album="", url="https://youtu.be/a", source="youtube"))
    assert tr.status == "ready" and tr.cues == [(0, 500, "")] and tr.beats[0] == (1, 12800, 500)
    assert "live" in ctrl.dispatcher.pools                         # pool à part : devant la file normale
    assert paused == [True, False]                                 # analyse de fond en pause, puis reprise
    assert downloads and "DJSync Live" in str(downloads[0])
    from pyrekordbox import RekordboxXml

    assert len(RekordboxXml(svc.xml_path()).get_tracks()) == 1
    # le même son redemandé : pas de second téléchargement
    svc.add(NS(title="Song", artist="Artist", album="", url="https://youtu.be/a", source="youtube"))
    assert len(downloads) == 1 and len(svc.session.tracks) == 1


def test_c15_error_stays_out_of_xml_and_finish_refused_with_rekordbox_open(tmp_path, monkeypatch):
    from djsync.db import local_library
    from djsync.ui.live_service import LiveService

    _fake_analysis(monkeypatch)
    ctrl, _p, _d = _ctrl(tmp_path, monkeypatch)

    def offline(*_a, **_k):
        raise OSError("Network is unreachable")
    ctrl.service.download = offline
    svc = LiveService(ctrl)
    tr = svc.add(NS(title="Bad", artist="X", album="", url="u", source="youtube"))
    assert tr.status == "error" and tr.error
    from pyrekordbox import RekordboxXml

    assert RekordboxXml(svc.xml_path()).get_tracks() == []
    monkeypatch.setattr(local_library, "rekordbox_running", lambda: True)
    assert not svc.finish()
    assert any(k == "warn" for k, _t in ctrl.messages) and ("live_blocked",) in ctrl.events


def test_c15_finish_without_computer_library_keeps_files(tmp_path, monkeypatch):
    from djsync.db import local_library
    from djsync.ui.live_service import LiveService

    _fake_analysis(monkeypatch)
    ctrl, _p, downloads = _ctrl(tmp_path, monkeypatch)
    ctrl.find_local = lambda: None
    monkeypatch.setattr(local_library, "rekordbox_running", lambda: False)
    svc = LiveService(ctrl)
    svc.add(NS(title="Song", artist="Artist", album="", url="u1", source="youtube"))
    assert svc.finish()
    assert downloads[0].is_file() and L.open_session(tmp_path) is None
    from pyrekordbox import RekordboxXml

    assert RekordboxXml(L.xml_path(tmp_path)).get_tracks() == []         # XML vidé


def test_c15_live_page_and_guide(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.ui import live_service
    from djsync.ui.live_page import LiveGuide, LivePage

    from .qt_util import pump

    monkeypatch.setattr(live_service.LiveService, "data_dir", staticmethod(lambda: tmp_path))
    demo.ctrl.settings.live_guide_done = False
    demo._live_guided = False
    demo.open_live()
    pump(demo, 0.2)
    guides = [w for w in demo.findChildren(LiveGuide)]
    assert guides
    g = guides[-1]
    g.never.setChecked(True)
    g.go(1)
    g.go(1)
    g.go(1)                                                          # Terminé
    pump(demo, 0.2)
    assert demo.ctrl.settings.live_guide_done
    pages = demo.findChildren(LivePage)
    assert pages and pages[-1].finish_btn.isEnabled() is False
    page = pages[-1]
    page._found([NS(title="Song", artist="Artist", duration_seconds=200, url="u", source="youtube", album="")])
    assert page.found.topLevelItemCount() == 1
    assert not demo.errors
    page.close()

