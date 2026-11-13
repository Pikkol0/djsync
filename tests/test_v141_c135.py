"""1.4.1 (C135) : un seul onglet « Qualité » (ex-« Mauvaise qualité » + « Améliorer »)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from djsync.core import improve as I
from djsync.core.quality import AudioInfo
from djsync.models import TrackResult


def _t(cid, title="Glue", dur=268, artist="Bicep"):
    return SimpleNamespace(content_id=cid, title=title, artist=artist, duration_seconds=dur)


def _slsk(user, lossless=True, bitrate=0):
    return SimpleNamespace(user=user, lossless=lossless, bitrate=bitrate, quality_label=lambda: "FLAC")


# ------------------------------------------------------------------ modèle
def test_rows_flags_and_filters():
    infos = {1: AudioInfo(codec="mp3", bitrate=128, sample_rate=44100),
             2: AudioInfo(codec="flac", bitrate=900, sample_rate=44100, cutoff=16000),       # faux FLAC
             3: AudioInfo(codec="flac", bitrate=900, sample_rate=44100, cutoff=21800),       # vrai FLAC
             4: AudioInfo(codec="aac", bitrate=256, sample_rate=44100, source="YouTube")}
    tracks = [_t(1, "A"), _t(2, "B"), _t(3, "C"), _t(4, "D"), _t(5, "Nothing read")]
    rows = I.assess(tracks, infos)
    assert [w.track.content_id for w in rows][0] == 1 and len(rows) == 4          # sans info : absent
    by = {w.track.content_id: w for w in rows}
    assert by[1].flags(256) == ["under"] and by[2].fake_lossless and "fake" in by[2].flags(256)
    assert by[3].flags(256) == [] and by[4].video == "YouTube" and "video" in by[4].flags(256)
    assert I.video_reason(_t(9, "Song (Official Video)"), AudioInfo(codec="mp3", bitrate=320)) == "official video"
    assert I.video_reason(_t(9, "Song"), AudioInfo(codec="aac", bitrate=256, source="YouTube Music")) == ""
    assert {w.track.content_id for w in I.select(rows, under=256)} == {1, 2}
    assert {w.track.content_id for w in I.select(rows, video=True)} == {4}
    assert {w.track.content_id for w in I.select(rows, fake=True)} == {2}
    assert len(I.select(rows)) == 4                                                # aucun filtre : tous
    assert I.measured_label(infos[3]) and not I.measured_label(infos[1])          # non mesuré : vide


def test_default_order_free_first_then_soulseek_and_youtube_rules():
    row = I.QualityRow(_t(1), AudioInfo(codec="aac", bitrate=128, sample_rate=44100))
    slsk = TrackResult(video_id="s", title="Glue", artist="Bicep", duration_seconds=268, source="soulseek",
                       slsk=_slsk("peer1"))
    free_320 = TrackResult(video_id="a", title="Glue", artist="Bicep", duration_seconds=268, source="audius", quality="MP3 320")
    free_flac = TrackResult(video_id="b", title="Glue", artist="Bicep", duration_seconds=270, source="archive", quality="FLAC")
    far = TrackResult(video_id="c", title="Glue", artist="Bicep", duration_seconds=275, source="archive", quality="FLAC")
    yt = TrackResult(video_id="y", title="Glue", artist="Bicep", duration_seconds=268, source="ytmusic")
    finds = I.better_finds(row, [slsk, free_320, free_flac, far, yt])
    # gratuites suffisantes (≥ 256, ± 3 s) d'abord ; Soulseek ensuite ; YouTube refusé (pas une vidéo)
    assert [f.video_id for f in finds] == ["b", "a", "s", "c"]
    video = I.QualityRow(_t(2), AudioInfo(codec="aac", bitrate=128, sample_rate=44100), video="clip officiel")
    assert [f.video_id for f in I.better_finds(video, [yt])] == ["y"]
    video.finds = [yt]
    assert not I.sure(video)                                    # YouTube : jamais « sûr » (≈ 192)
    row.finds = finds
    assert I.sure(row) and row.gain == "AAC 128 → FLAC"


def test_automatic_choice_prefers_free_and_varies_peers():
    rows = []
    for cid in (1, 2, 3):
        row = I.QualityRow(_t(cid), AudioInfo(codec="mp3", bitrate=128, sample_rate=44100))
        peers = []
        for user in ("alice", "bob"):
            r = TrackResult(video_id=f"{cid}{user}", title="Glue", artist="Bicep", duration_seconds=268,
                            source="soulseek", slsk=_slsk(user))
            peers.append(r)
        row.finds = peers
        rows.append(row)
    free = TrackResult(video_id="free", title="Glue", artist="Bicep", duration_seconds=268, source="archive", quality="FLAC")
    rows[2].finds = rows[2].finds + [free]
    picks = I.choose_batch(rows)
    assert picks[3] is free                                      # même qualité : la source sans pair-à-pair
    assert {I.peer_of(picks[1]), I.peer_of(picks[2])} == {"alice", "bob"}       # pairs variés
    rows[0].chosen = rows[0].finds[1]
    assert I.choose_batch(rows)[1] is rows[0].finds[1]          # choix fait à la main dans le détail


# ------------------------------------------------------------------ interface
pytest.importorskip("PySide6")

from .qt_util import find, pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401


@pytest.fixture
def aac(demo, monkeypatch):  # noqa: F811
    from djsync.core import quality

    monkeypatch.setattr(quality, "probe", lambda path: quality.AudioInfo(codec="aac", bitrate=128, sample_rate=44100))
    monkeypatch.setattr(demo.ctrl, "find_alternatives", lambda track, ok: ok([]))
    return demo


def test_scope_playlist_and_selection(aac):
    from djsync.ui.quality_page import QualityPage

    ctrl = aac.ctrl
    tracks = ctrl.library.list_tracks()
    page = QualityPage(aac.views["home"], ctrl)
    assert pump(aac, 6, lambda: not page._loading and len(page.rows) == len(tracks))
    pl = next(p for p in ctrl.playlists if ctrl.quality_playlist_ids(p.playlist_id))
    ids = set(ctrl.quality_playlist_ids(pl.playlist_id))
    idx = next(i for i in range(page.scope.count()) if tuple(page.scope.itemData(i)) == ("pl", pl.playlist_id))
    page.scope.setCurrentIndex(idx)
    assert pump(aac, 6, lambda: not page._loading and {int(k) for k in page.rows} == ids)
    page.set_scope([tracks[0].content_id])
    assert tuple(page.scope.currentData()) == ("sel", None)
    assert pump(aac, 6, lambda: not page._loading and list(page.rows) == [str(tracks[0].content_id)])
    page.close()
    assert not aac.errors


def test_one_confirmation_for_a_batch_of_three(aac, monkeypatch):
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.quality_page import QualityPage

    ctrl = aac.ctrl
    tracks = ctrl.library.list_tracks()[:3]
    replaced = []
    monkeypatch.setattr(ctrl, "replace_with_download", lambda tr, old: replaced.append(old[0].content_id) or 1)
    page = QualityPage(aac.views["home"], ctrl, ids=[x.content_id for x in tracks])
    assert pump(aac, 6, lambda: not page._loading and len(page.shown) == 3)
    for w in page.shown.values():
        w.finds = [TrackResult(video_id=f"f{w.track.content_id}", title=w.track.title, artist="x",
                               duration_seconds=w.track.duration_seconds, source="archive", quality="FLAC")]
        w.searched = True
    page._fill()
    assert page.sure_btn.isEnabled()
    page._apply_sure()
    dialogs = [w for w in aac.findChildren(ConfirmDialog) if w.isVisible()]
    assert len(dialogs) == 1 and not replaced
    dialogs[0]._ok()
    assert sorted(replaced) == sorted(x.content_id for x in tracks)
    page.close()
    assert not aac.errors


def test_measure_registers_a_task_and_resumes(aac, monkeypatch):
    """Mesure inscrite au volet (pause, arrêt) ; arrêtée puis relancée, elle ne refait que les sons restants."""
    from djsync.analysis import spectrum

    ctrl = aac.ctrl
    seen = []
    gate = {"stop_after": 2}

    def measure(path, ffmpeg, duration, force=False, save=True):
        seen.append(path.name)
        if len(seen) == gate["stop_after"]:
            ctrl.stop_quality()

    monkeypatch.setattr(spectrum, "measure_and_remember", measure)
    tracks = ctrl.library.list_tracks()
    done = []
    assert ctrl.measure_quality(tracks, done.append)
    task = ctrl.tasks.get("quality")
    assert task is not None and task.can_pause and task.can_stop and task.open == "quality"
    assert pump(aac, 6, lambda: done)
    assert len(seen) == 2 and not ctrl.quality_running
    first = list(seen)
    seen.clear()
    gate["stop_after"] = 10_000
    rest = [x for x in tracks if ctrl.library.absolute_path(x).name not in first]
    done.clear()
    assert ctrl.measure_quality(rest, done.append)
    assert pump(aac, 6, lambda: done)
    assert not set(seen) & set(first) and len(seen) == len(rest)
    assert not aac.errors


def test_opened_from_one_track_on_that_track(aac, monkeypatch):
    from djsync.ui.quality_page import QualityDetail, QualityPage

    ctrl = aac.ctrl
    monkeypatch.setattr(ctrl, "free_search", lambda q, ok, partial=None: ok([]))
    x = ctrl.library.list_tracks()[1]
    aac.open_quality([x.content_id], focus=x.content_id)
    assert pump(aac, 6, lambda: find(aac, QualityDetail) is not None)
    page = find(aac, QualityPage)
    assert tuple(page.scope.currentData()) == ("sel", None) and list(page.rows) == [str(x.content_id)]
    detail = find(aac, QualityDetail)
    assert detail.row.track.content_id == x.content_id
    assert pump(aac, 4, lambda: detail.row.searched)
    assert detail.title_edit.text() and detail.state.text()
    detail.close()
    page.close()
    assert not aac.errors


def test_counters_never_start_a_hidden_measure(aac, monkeypatch):
    from djsync.analysis import spectrum
    from djsync.ui.quality_page import QualityPage

    calls = []
    monkeypatch.setattr(spectrum, "measure_and_remember", lambda *a, **k: calls.append(a))
    ctrl = aac.ctrl
    page = QualityPage(aac.views["home"], ctrl)
    assert pump(aac, 6, lambda: not page._loading)
    pump(aac, 0.5)
    assert ctrl.diag_counts.get("quality") == len(page.rows) and not calls and not ctrl.quality_running
    assert "(" in page.measure_btn.text()                       # « Mesurer la qualité (n) » : rien de lancé
    page.close()
    assert not aac.errors
