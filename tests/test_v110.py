"""V1.1.0 : diagnostic de bibliothèque (doublons, mauvaise qualité, mauvaise source) et remplacement
par un téléchargement propre."""
from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from djsync.core import quality
from djsync.core.quality import AudioInfo, bad_source, clean_title, find_issues, low_quality, probe


@pytest.mark.parametrize("title,reason", [
    ("One More Time (Clip Officiel)", "clip officiel"),
    ("Song [Official Music Video]", "official music video"),
    ("Song (Vidéo Officielle)", "video officielle"),
    ("Song (Lyrics)", "lyrics"),
    ("Song (Lyric Video)", "lyric video"),
    ("Song (Live)", "live"),
    ("Song | Live at Wembley", "live"),
    ("Song (Sped Up)", "sped up"),
    ("Song - Visualizer", "visualizer"),
    ("Song (Nightcore)", "nightcore"),
])
def test_bad_source_detected(title, reason):
    assert bad_source(title) == reason
    assert bad_source(clean_title(title)) is None


@pytest.mark.parametrize("title", ["Video Games", "Live Forever", "Paroles, paroles", "Alive", "Song (Extended Mix)",
                                   "Song (Official Audio)", "Song (Radio Edit)", "Lyrical Lemonade"])
def test_clean_titles_not_flagged(title):
    assert bad_source(title) is None


def test_low_quality_thresholds():
    assert low_quality(AudioInfo("mp3", 160, 44100)) == "MP3 160 kbps"
    assert low_quality(AudioInfo("mp3", 192, 44100)) is None
    assert low_quality(AudioInfo("mp3", 320, 44100)) is None
    assert low_quality(AudioInfo("aac", 128, 44100)) is None          # YouTube Music (itag 140)
    assert low_quality(AudioInfo("aac", 96, 44100)) == "AAC 96 kbps"
    assert low_quality(AudioInfo("opus", 96, 48000)) == "OPUS 96 kbps"
    assert low_quality(AudioInfo("mp3", 320, 22050)).endswith("22.05 kHz")
    assert low_quality(AudioInfo("flac", 0, 22050)) is None             # sans perte : jamais signalé
    assert low_quality(AudioInfo()) is None                              # illisible : rien à dire


def test_find_issues_source_wins_over_bitrate(tmp_path):
    tracks = [SimpleNamespace(title="A (Clip Officiel)", artist="X", content_id=1),
              SimpleNamespace(title="B", artist="X", content_id=2),
              SimpleNamespace(title="C", artist="X", content_id=3)]
    infos = {"A (Clip Officiel)": AudioInfo("mp3", 128), "B": AudioInfo("mp3", 128), "C": AudioInfo("aac", 256)}
    seen = []
    issues = find_issues(tracks, lambda x: x.title, prober=lambda p: infos[p], progress=lambda i, n: seen.append(i))
    assert [(i.track.content_id, i.kind) for i in issues] == [(1, "source"), (2, "bitrate")]
    assert seen[-1] == 3


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg requis")
def test_probe_reads_real_files(tmp_path):
    def make(name, *args):
        out = tmp_path / name
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=3", *args, str(out)], check=True)
        return out

    mp3 = probe(make("a.mp3", "-ar", "44100", "-b:a", "160k"))
    assert (mp3.codec, mp3.sample_rate) == ("mp3", 44100) and 150 <= mp3.bitrate <= 170
    assert low_quality(mp3)
    m4a = probe(make("b.m4a", "-ar", "44100", "-c:a", "aac", "-b:a", "256k"))
    assert m4a.codec == "aac" and not low_quality(m4a)
    flac = probe(make("c.flac"))
    assert flac.lossless and not low_quality(flac)
    assert probe(tmp_path / "missing.mp3") == AudioInfo()


# ---------------------------------------------------------------------------- interface
pytest.importorskip("PySide6")

from djsync.db import UsbDrive  # noqa: E402
from djsync.models import Candidate, TrackResult  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .demo_fixture import make_demo_usb  # noqa: E402
from .qt_util import close_window, find, make_window, pump  # noqa: E402
from .test_ui_smoke import FakeService  # noqa: E402


@pytest.fixture
def demo(tmp_path, monkeypatch):
    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller
    import djsync.ui.ctrl.diagnostic as diagnostic

    real_probe = quality.probe
    monkeypatch.setattr(quality, "probe", lambda p: AudioInfo("mp3", 128, 44100) if p.name == "Rihanna - Umbrella.wav"
                        else real_probe(p))
    monkeypatch.setattr(diagnostic, "soundcloud_search", lambda q, limit=3: [])
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(), monkeypatch)
    assert pump(window, 6, lambda: window.ctrl.has_library)

    def match(src, per_type=5):
        return [Candidate(TrackResult(video_id=f"new{len(src.title):08d}", title=f"{src.title} (2024 Remaster)",
                                      artist=src.artist, duration_seconds=180 + len(src.title) * 3), 92.0),
                Candidate(TrackResult(video_id="clip0000001", title=f"{src.title} (Official Video)",
                                      artist=src.artist, duration_seconds=200, result_type="video"), 90.0)]

    monkeypatch.setattr(window.ctrl.service, "match_spotify", match)
    yield window
    close_window(window)


def test_diagnostic_from_home_card_replace_and_ignore(demo):
    from djsync.ui.diagnostic_dialog import ALT, DiagnosticDialog
    from djsync.ui.dialogs import ConfirmDialog

    ctrl = demo.ctrl
    home = demo.views["home"]
    assert pump(demo, 8, lambda: home._summaries and home._summaries[0].connected)
    home.diagnose(home._summaries[0].drive, True)
    assert pump(demo, 2, lambda: find(demo, DiagnosticDialog) is not None)
    dlg = find(demo, DiagnosticDialog)
    assert pump(demo, 6, lambda: not dlg._loading)
    kinds = [(k, p.track.title if k != "dup" else len(p)) for k, p in dlg.items]
    assert kinds == [("dup", 2), ("bitrate", "Umbrella")]          # le clip est dans le groupe de doublons
    assert dlg.list.item(0).flags() == dlg.list.item(0).flags().__class__(0)   # en-tête de section

    # ---- doublon : 2 versions + versions propres (la proposition « Official Video » est écartée)
    assert pump(demo, 4, lambda: dlg._choice.button(ALT) is not None)
    assert dlg._choice.button(ALT + 1) is None
    # rc.5 (C63) : garder une version = fusionner dans l'outil Doublons
    assert dlg._choice.checkedId() == 0 and dlg.apply_btn.text() == "Merge in Duplicates…"
    dlg._choice.button(ALT).setChecked(True)
    assert dlg.apply_btn.text() == "Download and replace" and not dlg.note.isHidden()

    # ---- qualité : remplacer Umbrella par la version retéléchargée
    dlg._select(1)
    assert "MP3 128 kbps" in dlg.items[1][1].reason
    assert pump(demo, 4, lambda: dlg._choice.checkedId() == ALT)
    umbrella = dlg.items[1][1].track
    pls_before = {p.name for p in ctrl.playlists if umbrella.content_id in _ids(ctrl, p.playlist_id)}
    dlg._apply()
    assert pump(demo, 2, lambda: find(demo, ConfirmDialog) is not None)
    find(demo, ConfirmDialog)._ok()
    assert len(dlg.items) == 1
    job = ctrl.jobs[-1]
    assert job.replace_ids == [umbrella.content_id]
    assert pump(demo, 8, lambda: job.status == "done")
    tracks = ctrl.library.list_tracks()
    assert umbrella.content_id not in {x.content_id for x in tracks}
    assert pls_before == {p.name for p in ctrl.playlists if job.content_id in _ids(ctrl, p.playlist_id)} == {"Classiques"}

    # ---- ignorer : retenu pour les diagnostics suivants
    dlg._select(0)
    dlg._ignore()
    assert dlg.items == [] and ctrl.settings.diag_ignored[0].startswith("d:")
    dlg.close()
    home._open_diagnostic()
    assert pump(demo, 2, lambda: find(demo, DiagnosticDialog) is not None)
    dlg = find(demo, DiagnosticDialog)
    assert pump(demo, 6, lambda: not dlg._loading)
    assert dlg.items == [] and dlg.count.text() == "Nothing to fix"
    dlg.close()
    assert not demo.errors


def _ids(ctrl, pid):
    return {x.content_id for x in ctrl.library.get_playlist_tracks(pid)}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg requis")
def test_compare_tool_only_rekordbox_analyses(tmp_path, capsys):
    """--compare ne compare QUE les sons analysés par Rekordbox (masterDbId), avec un résumé chiffré."""
    from djsync.analysis.__main__ import main, wilson
    from djsync.db import RekordboxUsbLibrary, drive_from_letter

    from .audio_fixture import song, write_wav

    usb = make_demo_usb(tmp_path)
    with RekordboxUsbLibrary(drive_from_letter(str(usb)), analyze=True, artwork=False) as lib:
        d = lib.default_download_dir("Test")
        d.mkdir(parents=True, exist_ok=True)
        native = lib.add_track(write_wav(d / "native.wav", song(124.0, 0.42, 30, ("A", "F", "C", "G"), (1, 0, 0, 0))),
                               "Native", "Test", None, None, [])
        lib.add_track(write_wav(d / "mine.wav", song(128.0, 0.42, 30, ("A", "F", "C", "G"), (1, 0, 0, 0))),
                      "Mine", "Test", None, None, [])
        with lib._write() as conn:                          # « exporté par Rekordbox »
            conn.execute("UPDATE content SET masterDbId = 1 WHERE content_id = ?", (native.content_id,))
    out_csv = tmp_path / "diag.csv"
    assert main(["--compare", str(usb), "--csv", str(out_csv), "--under", str(usb / "Contents")]) == 0
    out = capsys.readouterr().out
    assert "1 tracks analysed by Rekordbox to compare (1 analysed by DJSync ignored)" in out
    assert "Same BPM (±0.05)                      1/1" in out and "Only 1 tracks" in out
    assert out_csv.read_text(encoding="utf-8-sig").count("\n") == 2
    lo, hi = wilson(45, 50)
    assert 78 < lo < 80 and 95 < hi < 97
    assert wilson(360, 400)[1] - wilson(360, 400)[0] < 6.5


# ---------------------------------------------------------------------- nouvelle version de DJSync
def _releases(*items):
    import json

    return lambda url: json.dumps([{"tag_name": tag, "prerelease": pre, "draft": draft,
                                    "html_url": f"https://github.com/Pikkol0/djsync/releases/tag/{tag}",
                                    "assets": [{"name": "DJSync.exe", "browser_download_url": "x/DJSync.exe"}]}
                                   for tag, pre, draft in items]).encode()


def test_update_versions_and_channels():
    from djsync.core.updates import check, parse_version

    assert parse_version("1.1.0") > parse_version("1.1.0-rc.2") > parse_version("1.1.0-rc.1") > parse_version("1.0.9")
    assert parse_version("v1.2.0") == parse_version("1.2.0") and parse_version("garbage") is None
    feed = _releases(("v1.2.0-rc.1", True, False), ("v1.1.1", False, False), ("v1.3.0", False, True),
                     ("v1.1.0", False, False))
    stable = check("1.1.0", feed)                       # stable : pas de pré-version, pas de brouillon
    assert stable.version == "1.1.1" and not stable.prerelease
    test = check("1.1.0-rc.1", feed)                    # version de test : les pré-versions aussi
    assert test.version == "1.2.0-rc.1" and test.prerelease
    assert check("1.1.1", feed) is None
    assert check("1.1.0-dev.abc1234", feed).version == "1.1.1"      # build de développement


def test_update_offer_in_the_app(demo, monkeypatch):
    import djsync.core.updates as updates
    from djsync.ui.dialogs import ConfirmDialog

    ctrl = demo.ctrl
    monkeypatch.setattr(updates, "_http_get", _releases(("v9.0.0", False, False)))
    ctrl.settings.last_update_check = 0
    ctrl.app_update_check()
    assert pump(demo, 4, lambda: find(demo, ConfirmDialog) is not None)
    dlg = find(demo, ConfirmDialog)
    assert dlg.windowTitle() == "New version of DJSync"
    dlg.close()
    assert ctrl.settings.last_update_check > 0
    ctrl.app_update_check()                              # déjà vérifié aujourd'hui : rien
    pump(demo, 0.5)
    assert find(demo, ConfirmDialog) is None
    ctrl.settings.check_updates = False
    ctrl.settings.last_update_check = 0
    ctrl.app_update_check()                              # désactivé
    pump(demo, 0.5)
    assert find(demo, ConfirmDialog) is None
    assert not demo.errors


def test_grid_backups_are_pruned(tmp_path):
    from djsync.db.library.metadata import prune_folders

    for i in range(35):
        (tmp_path / f"20261022-1200{i:02d}-7").mkdir()
    (tmp_path / "note.txt").write_text("kept")
    prune_folders(tmp_path, 30)
    kept = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert len(kept) == 30 and kept[0] == "20261022-120005-7" and (tmp_path / "note.txt").exists()
