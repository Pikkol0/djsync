"""1.4.0 : sources de meilleure qualité (C10) et fichiers de l'ordinateur (C26)."""
import shutil
import subprocess

import pytest

from .test_usb_library import lib, usb  # noqa: F401  (fixtures)


def _wav(path, seconds=3.0):
    import numpy as np

    from .audio_fixture import write_wav

    t = np.linspace(0, seconds, int(44100 * seconds), endpoint=False)
    return write_wav(path, (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32"))


def _flac(path, title, artist, genre=""):
    src = _wav(path.with_suffix(".src.wav"))
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-metadata", f"title={title}",
           "-metadata", f"artist={artist}", "-metadata", "album=Promo", "-metadata", f"genre={genre}",
           "-metadata", "date=2024", str(path)]
    subprocess.run(cmd, check=True)
    src.unlink()
    return path


# ------------------------------------------------------------------ C26 sens A : core
def test_read_info_tags_then_file_name(tmp_path):
    from djsync.core.importer import read_info

    w = _wav(tmp_path / "Daft Punk - One More Time.wav")
    i = read_info(w)
    assert (i.title, i.artist, i.lossless) == ("One More Time", "Daft Punk", True)
    if shutil.which("ffmpeg"):
        f = _flac(tmp_path / "x.flac", "Strobe", "deadmau5", "Progressive House")
        i = read_info(f)
        assert (i.title, i.artist, i.album) == ("Strobe", "deadmau5", "Promo")
        assert i.meta["genre"] == "Progressive House" and i.meta["year"] == 2024


def test_collect_walks_folders_and_keeps_audio_only(tmp_path):
    from djsync.core.importer import collect

    (tmp_path / "a" / "b").mkdir(parents=True)
    w1 = _wav(tmp_path / "a" / "1.wav")
    w2 = _wav(tmp_path / "a" / "b" / "2.wav")
    (tmp_path / "a" / "notes.txt").write_text("x")
    (tmp_path / "a" / ".hidden.wav").write_bytes(b"x")
    assert collect([tmp_path / "a", w1]) == [w1, w2]


def test_import_copies_to_the_drive_and_never_touches_the_original(lib, tmp_path):  # noqa: F811
    from djsync.core.importer import import_files

    outside = tmp_path.parent / (tmp_path.name + "_src")              # hors de la clé (la clé = tmp_path)
    outside.mkdir()
    w = _wav(outside / "Kaytranada - Glowed Up.wav")
    before = w.read_bytes()
    rep = import_files(lib, [w])
    assert len(rep.added) == 1 and not rep.failed
    x = rep.added[0]
    assert x.title == "Glowed Up" and x.artist == "Kaytranada" and x.path.startswith("/Contents/Kaytranada/")
    assert lib.absolute_path(x).is_file() and w.read_bytes() == before
    # deuxième fois : déjà là, pas de second fichier
    rep2 = import_files(lib, [w])
    assert not rep2.added and len(rep2.already) == 1
    assert len(list(lib.absolute_path(x).parent.iterdir())) == 1
    # fichier illisible : signalé, rien de copié
    bad = outside / "Broken - Track.wav"
    bad.write_bytes(b"RIFF0000WAVEnope")
    rep3 = import_files(lib, [bad])
    assert rep3.failed and not (lib.contents_root / "Broken").exists()


def test_import_into_playlist_flags_duplicates(lib, tmp_path):  # noqa: F811
    from djsync.core.importer import import_files

    pl = lib.create_playlist("Promos")
    src = tmp_path.parent / (tmp_path.name + "_src")
    src.mkdir()
    a = _wav(src / "Burial - Archangel.wav")
    import_files(lib, [a], [pl.playlist_id])
    b = _wav(src / "Burial - Archangel (Original Mix).wav")
    rep = import_files(lib, [b], [pl.playlist_id])
    assert [x.title for x in lib.get_playlist_tracks(pl.playlist_id)] == ["Archangel", "Archangel (Original Mix)"]
    assert rep.duplicates and rep.duplicates[0].title == "Archangel (Original Mix)"


# ------------------------------------------------------------------ C26 sens A : interface
def test_import_button_and_drop_add_to_the_open_playlist(tmp_path, monkeypatch):
    from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PySide6.QtGui import QDropEvent

    from .qt_util import close_window, pump
    from .test_v130rc3 import _demo_app

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        monkeypatch.setattr(ctrl.settings, "analyze_after_download_usb", False)
        app.show_view("library")
        lib = app.views["library"]
        assert pump(app, 5, lambda: lib.table.total > 0)
        club = next(k for k, p in lib._by_iid.items() if p.name == "Club")
        lib._goto(club)
        assert pump(app, 4, lambda: lib.table.total == 3)
        src = tmp_path / "in"
        src.mkdir()
        w = _wav(src / "Fred again.. - Delilah.wav")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(w))])
        ev = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        lib.table.dropEvent(ev)
        assert pump(app, 10, lambda: lib.table.total == 4)
        assert any(r.data.title == "Delilah" for r in lib.table.all_rows())
        assert lib.import_btn.isEnabled()
        assert not app.errors
    finally:
        close_window(app)


def test_import_on_the_computer_references_in_place(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    from djsync.core.importer import import_files

    from .test_local_library import local as local_fixture  # noqa: F401

    gen = local_fixture.__wrapped__(tmp_path, monkeypatch)
    lib = next(gen)
    try:
        lib.analyze = False
        promo = tmp_path / "Promos" / "Peggy Gou - Nanana.wav"
        promo.parent.mkdir()
        _wav(promo)
        rep = import_files(lib, [promo])
        assert len(rep.added) == 1
        x = rep.added[0]
        assert lib.absolute_path(x) == promo.resolve() and x.title == "Nanana"
        lib.delete_tracks([x.content_id])                  # retiré de la collection : fichier gardé
        assert promo.is_file()
    finally:
        next(gen, None)


# ------------------------------------------------------------------ C10.1 : fichier d'origine SoundCloud
def _sc(vid="sc1", **kw):
    from djsync.models import TrackResult

    return TrackResult(video_id=vid, title="Promo", artist="Artist", duration_seconds=200, source="soundcloud",
                       source_url=f"https://soundcloud.com/artist/{vid}", **kw)


def test_soundcloud_auth_and_availability_without_network():
    from djsync.core.soundcloud import auth_options, original_available

    assert auth_options("", "") == {}
    assert auth_options("Firefox", "") == {"cookiesfrombrowser": ("firefox",)}
    assert auth_options("chrome", " tok ") == {"username": "oauth", "password": "tok"}   # le jeton l'emporte
    assert auth_options("netscape", "") == {}
    assert original_available("https://www.youtube.com/watch?v=x") is None


def test_downloader_keeps_the_original_untouched(tmp_path, monkeypatch):
    from djsync.core import downloader as D

    calls = {}

    def fake_run(self, track, dest, base, extra, notify):
        calls["extra"] = extra
        p = dest / f"{base}.wav"
        _wav(p)
        return p, "download"

    monkeypatch.setattr(D.Downloader, "_run", fake_run)
    monkeypatch.setattr(D, "finalize", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no transcode")))
    d = D.Downloader(audio_format="mp3", normalize=True)
    d.soundcloud_auth = {"username": "oauth", "password": "tok"}
    res = d.download(_sc(want_original=True), tmp_path)
    assert res.original and res.file_path.endswith(".wav")
    assert calls["extra"]["format"].startswith("download/") and calls["extra"]["password"] == "tok"
    # sans demande : flux habituel, pas d'identifiants pour YouTube
    from djsync.models import TrackResult

    monkeypatch.setattr(D.Downloader, "_run", lambda self, tr, dest, base, extra, n: (calls.update(extra=extra),
                                                                                       (_wav(dest / f"{base}.wav"), "hls"))[1])
    monkeypatch.setattr(D, "finalize", lambda path, *a, **k: path)
    res = d.download(TrackResult(video_id="y" * 11, title="T", artist="A"), tmp_path / "yt")
    assert not res.original and "password" not in calls["extra"] and not calls["extra"]["format"].startswith("download")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg requis")
def test_original_in_an_unreadable_format_becomes_wav(tmp_path, monkeypatch):
    from djsync.core import downloader as D

    def fake_run(self, track, dest, base, extra, notify):
        src = _wav(tmp_path / "s.wav")
        out = dest / f"{base}.ogg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-c:a", "libvorbis", str(out)],
                       check=True)
        return out, "download"

    monkeypatch.setattr(D.Downloader, "_run", fake_run)
    res = D.Downloader().download(_sc(want_original=True), tmp_path / "dl", tag=False)
    assert res.original and res.file_path.endswith(".wav") and not list((tmp_path / "dl").glob("*.ogg"))


def test_enqueue_asks_for_the_original_by_setting_or_choice(tmp_path, monkeypatch):
    from .qt_util import close_window, pump
    from .test_v130rc3 import _demo_app

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        monkeypatch.setattr(ctrl, "_run_job", lambda job: None)
        ctrl.settings.soundcloud_original = True
        jobs = ctrl.enqueue([_sc("a", original_available=True), _sc("b", original_available=False), _sc("c")], [])
        assert [j.track.want_original for j in jobs] == [True, False, True]
        jobs = ctrl.enqueue([_sc("d", original_available=True)], [], original=False)
        assert not jobs[0].track.want_original
        ctrl.settings.soundcloud_original = False
        assert not ctrl.enqueue([_sc("e", original_available=True)], [])[0].track.want_original
        assert ctrl.enqueue([_sc("f", original_available=True)], [], original=True)[0].track.want_original
    finally:
        close_window(app)


def test_quality_tiers_gold_and_silver():
    from djsync.ui import levels as L

    assert L.tier(0, True) == "gold" and L.tier(320) == "silver" and L.tier(256) is None
    from djsync.core.quality import AudioInfo

    assert L.audio_text(AudioInfo("flac", 900, 44100), 5)[1] == "gold"
    assert L.audio_text(AudioInfo("mp3", 320, 44100), 1)[1] == "silver"
    assert 'font-weight:700' in L.html("FLAC", "gold")


def test_result_row_marks_the_original_in_gold():
    from djsync.ui import theme
    from djsync.ui.views.common import result_row

    r = result_row(_sc(original_available=True))
    assert r.values["source__color"] == theme.GOLD and "original" in r.values["source"]
    assert "source__color" not in result_row(_sc()).values
