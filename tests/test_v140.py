"""1.4.0 : sources de meilleure qualité (C10) et fichiers de l'ordinateur (C26)."""
import shutil
from pathlib import Path
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


def test_soundcloud_free_download_link():
    from djsync.core.soundcloud import free_download
    from djsync.ui.views.common import result_row

    assert free_download({"purchase_url": "https://hypeddit.com/x/y", "purchase_title": "Buy"}) == "https://hypeddit.com/x/y"
    assert free_download({"purchase_url": "https://example.com/a", "purchase_title": "FREE DL"}) == "https://example.com/a"
    assert free_download({"purchase_url": "https://www.beatport.com/track/x/1", "purchase_title": "Buy"}) is None
    assert free_download({"purchase_url": "javascript:alert(1)", "purchase_title": "free"}) is None
    row = result_row(_sc("f1", free_download_url="https://hypeddit.com/x/y"))
    assert "free download" in row.values["source"].lower() or "gratuit" in row.values["source"].lower()


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


# ------------------------------------------------------------------ C10.3 : dossier surveillé, liens d'achat
def test_watched_folder_waits_for_stable_files_and_moves_them(tmp_path):
    import os
    import time

    from djsync.core.watcher import DONE_DIR, FolderWatch

    (tmp_path / "Bandcamp").mkdir()
    w = _wav(tmp_path / "Bandcamp" / "Artist - Song.wav")
    (tmp_path / "x.wav.crdownload").write_bytes(b"x" * 100)       # téléchargement en cours : ignoré
    old = time.time() - 60
    os.utime(w, (old, old))
    fw = FolderWatch(tmp_path)
    assert fw.stable_files() == []                                 # premier passage : on note la taille
    assert fw.stable_files() == [w]                                # inchangé : prêt
    moved = fw.take(w)
    assert moved == tmp_path / DONE_DIR / "Bandcamp" / "Artist - Song.wav" and moved.exists() and not w.exists()
    assert fw.stable_files() == [] and fw.stable_files() == []     # « DJSync importés » n'est jamais repris
    w2 = _wav(tmp_path / "Bandcamp" / "Artist - Song.wav")         # même nom une 2e fois : suffixe
    assert fw.take(w2).name == "Artist - Song (2).wav"
    fresh = _wav(tmp_path / "new.wav")                             # trop récent : attend encore
    fw.stable_files()
    assert fresh not in fw.stable_files(now=os.stat(fresh).st_mtime + 1)


def test_watch_tick_imports_into_the_imported_playlist(tmp_path, monkeypatch):
    import os
    import time

    from .qt_util import close_window, pump
    from .test_v130rc3 import _demo_app

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        monkeypatch.setattr(ctrl.settings, "analyze_after_download_usb", False)
        folder = tmp_path.parent / (tmp_path.name + "_watch")
        folder.mkdir()
        w = _wav(folder / "Peggy Gou - Nanana.wav")
        old = time.time() - 60
        os.utime(w, (old, old))
        ctrl.settings.watch_folder = str(folder)
        ctrl.settings.watch_playlist = True
        ctrl.watch_tick()                                          # 1er passage : rien n'est pris
        assert pump(app, 3, lambda: not ctrl._watch_busy)
        ctrl.watch_tick()
        names = lambda: {p.name for p in ctrl.library.list_playlists()}  # noqa: E731
        assert pump(app, 10, lambda: "Imported" in names() and not ctrl._importing)
        pl = next(p for p in ctrl.library.list_playlists() if p.name == "Imported")
        tracks = ctrl.library.get_playlist_tracks(pl.playlist_id)
        assert [x.title for x in tracks] == ["Nanana"]
        assert not w.exists() and (folder / "DJSync imported" / w.name).exists()
        assert not app.errors
    finally:
        close_window(app)


def test_buy_links_clean_the_query():
    from djsync.core.buy import links, query

    assert query("Daft Punk", "Daft Punk - One More Time (Official Video)") == "Daft Punk One More Time"
    assert query("", "Strobe [HD]") == "Strobe"
    got = dict(links("Bicep", "Glue"))
    assert set(got) == {"Beatport", "Bandcamp", "Traxsource", "Juno Download", "Qobuz"}
    assert got["Beatport"] == "https://www.beatport.com/search?q=Bicep+Glue"


def test_buy_entry_is_a_submenu_that_opens_the_store():
    from PySide6.QtWidgets import QMenu

    from djsync.ui.table import _fill_menu
    from djsync.ui.views.common import buy_entry

    opened = []

    class Ctrl:
        def _emit(self, ev, url):
            opened.append((ev, url))

    entry = buy_entry(Ctrl(), "Bicep", "Glue")
    menu = QMenu()
    _fill_menu(menu, [entry])
    sub = menu.actions()[0].menu()
    assert sub is not None and [a.text() for a in sub.actions()][0] == "Beatport"
    sub.actions()[1].trigger()
    assert opened == [("open_url", "https://bandcamp.com/search?q=Bicep+Glue&item_type=t")]


# ------------------------------------------------------------------ C26 sens C : FLAC pour les platines
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_flac_converted_for_players_keeps_bits_and_caps_the_rate(tmp_path):
    import mutagen

    from djsync.core import players

    src = _wav(tmp_path / "s.wav")
    hi = tmp_path / "hi.flac"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "96000", "-sample_fmt", "s32",
                    "-bits_per_raw_sample", "24", "-metadata", "title=Hi", str(hi)], check=True)
    assert players.needs(hi, "aiff") and not players.needs(hi, "") and not players.needs(src, "wav")
    out = players.convert(hi, players.target_path(hi, "aiff"), "aiff")
    info = mutagen.File(str(out)).info
    assert out.suffix == ".aiff" and info.bits_per_sample == 24 and info.sample_rate == 48000
    assert hi.exists() and not list(tmp_path.glob("*.djsync-part*"))
    wav = players.convert(hi, tmp_path / "w.wav", "wav")
    assert mutagen.File(str(wav)).info.bits_per_sample == 24


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_import_saves_flac_as_wav_on_the_key(lib, tmp_path):  # noqa: F811
    from djsync.core.importer import import_files

    outside = tmp_path.parent / (tmp_path.name + "_flac")
    outside.mkdir()
    f = _flac(outside / "a.flac", "Strobe", "deadmau5")
    rep = import_files(lib, [f], player_format="wav")
    assert len(rep.added) == 1 and not rep.failed
    t = rep.added[0]
    assert t.path.endswith(".wav") and t.title == "Strobe" and f.exists()
    assert not list(Path(lib.contents_root).rglob("*.flac"))
    rep = import_files(lib, [f], player_format="wav")             # 2e fois : déjà là, pas de 2e fichier
    assert rep.already and len(list(Path(lib.contents_root).rglob("*.wav"))) == 1


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_soundcloud_original_flac_saved_as_aiff_on_the_key(tmp_path, monkeypatch):
    from djsync.models import DownloadedTrack

    from .qt_util import close_window, pump
    from .test_v130rc3 import _demo_app

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        monkeypatch.setattr(ctrl.settings, "analyze_after_download_usb", False)
        monkeypatch.setattr(ctrl.settings, "fetch_metadata", False)
        ctrl.settings.player_format = "aiff"

        def fake_download(track, dest, on_progress=None, tag=True):
            f = _flac(Path(dest) / "orig.flac", track.title, track.artist)
            return DownloadedTrack(track=track, file_path=str(f), original=True)

        monkeypatch.setattr(ctrl.service, "download", fake_download)
        job = ctrl.enqueue([_sc("z1", original_available=True)], [])[0]
        assert pump(app, 15, lambda: job.status in ("done", "error"))
        assert job.status == "done" and job.file_path.endswith(".aiff") and job.original
        assert not Path(job.file_path).with_suffix(".flac").exists()
    finally:
        close_window(app)


# ------------------------------------------------------------------ C48 : meilleur flux YouTube (réglage)
def test_youtube_best_stream_is_opt_in(tmp_path, monkeypatch):
    from djsync.core import downloader as D
    from djsync.models import TrackResult
    from djsync.settings import Settings

    assert Settings().youtube_best is False
    seen = []
    monkeypatch.setattr(D.Downloader, "_run", lambda self, tr, dest, base, extra, n: (seen.append(extra),
                                                                                      (_wav(dest / f"{base}.wav"), "251"))[1])
    monkeypatch.setattr(D, "finalize", lambda path, *a, **k: path)
    monkeypatch.setattr(D, "tag_audio", lambda *a, **k: None)
    d = D.Downloader()
    yt = TrackResult(video_id="y" * 11, title="T", artist="A")
    d.download(yt, tmp_path / "a")
    assert seen[-1]["format"] == D._YT_NATIVE and "postprocessors" not in seen[-1]
    d.youtube_best, d.youtube_auth = True, {"cookiesfrombrowser": ("firefox",)}
    d.download(yt, tmp_path / "b")
    assert seen[-1]["format"].startswith("141/") and seen[-1]["postprocessors"][0]["preferredquality"] == "256"
    assert seen[-1]["cookiesfrombrowser"] == ("firefox",)
    d.download(_sc("s9"), tmp_path / "c")                          # SoundCloud : réglage YouTube sans effet
    assert "postprocessors" not in seen[-1] and "cookiesfrombrowser" not in seen[-1]


# ------------------------------------------------------------------ C46 : vraie qualité (spectre)
def _noise(path, cutoff=0, codec_args=()):
    """Bruit rose de 30 s ; `cutoff` : passe par un MP3 coupé à cette fréquence (comme LAME / YouTube)."""
    src = path.with_name(path.stem + ".src.flac")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=30:c=pink:a=0.3",
                    "-ar", "44100", str(src)], check=True)
    if not cutoff:
        src.replace(path) if path.suffix == ".flac" else subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), *codec_args, str(path)], check=True)
        src.unlink(missing_ok=True)
        return path
    mp3 = path.with_name(path.stem + ".lossy.mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-b:a", "128k", "-cutoff", str(cutoff),
                    str(mp3)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), *codec_args, str(path)], check=True)
    src.unlink()
    mp3.unlink()
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_spectrum_tells_real_from_fake(tmp_path):
    from djsync.analysis import spectrum as S
    from djsync.core.quality import low_quality, probe

    real = _noise(tmp_path / "real.flac")
    fake = _noise(tmp_path / "fake.flac", cutoff=16000)
    fake320 = _noise(tmp_path / "fake320.mp3", cutoff=16000, codec_args=("-b:a", "320k"))
    good320 = _noise(tmp_path / "good320.mp3", codec_args=("-b:a", "320k", "-cutoff", "20500"))
    assert S.estimate(S.measure(real)) == S.LOSSLESS
    assert S.estimate(S.measure(fake)) == 128
    assert S.estimate(S.measure(good320)) == 320
    assert probe(fake).cutoff == 0                                 # pas encore mesuré : rien n'est décodé
    for f in (real, fake, fake320, good320):
        S.measure_and_remember(f)
    r, f, f3, g3 = (probe(x) for x in (real, fake, fake320, good320))
    assert r.real_lossless and not r.fake and low_quality(r) is None
    assert f.fake and not f.real_lossless and f.effective_kbps == 128 and "≈ 128 kbps" in low_quality(f)
    assert f3.fake and "MP3 320" in low_quality(f3)
    assert not g3.fake and low_quality(g3) is None
    assert S.lookup("FAKE.flac", fake.stat().st_size) == f.cutoff  # même nom (casse) et taille : sans disque


def test_library_never_gives_gold_to_a_fake_lossless(tmp_path):
    from djsync.analysis import spectrum as S
    from djsync.models import LibraryTrack
    from djsync.ui import theme
    from djsync.ui.views.library_view import extra_values

    f = tmp_path / "x.flac"
    f.write_bytes(b"0" * 1000)
    x = LibraryTrack(content_id=1, title="X", artist="A", album=None, duration_seconds=1, bpm=None, source_url=None,
                     date_added="", is_analysed=False, path=str(f), file_type=5, bitrate=900,
                     sample_rate=44100, file_size=1000)
    assert extra_values(x)["format__color"] == theme.LEVELS["gold"] and "real" not in extra_values(x)
    S.remember(f, 16100)
    v = extra_values(x)
    assert v["real"] == "≈ 128 kbps" and v["format__color"] == theme.LEVELS["warn"]
    S.remember(f, 21800)
    assert extra_values(x)["format__color"] == theme.LEVELS["gold"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")
def test_analysis_measures_the_real_quality(tmp_path):
    from djsync.analysis import analyze_file, spectrum as S

    f = _noise(tmp_path / "n.flac", cutoff=16000)
    res = analyze_file(f)
    assert res.cutoff and S.estimate(res.cutoff) == 128 and S.known(f) == res.cutoff


# ------------------------------------------------------------------ C51 / C52 : éditeur des cues et du BPM
from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v130rc3 import _open_grid  # noqa: E402


def test_overview_in_the_grid_page_and_red_cursor(demo_grid):  # noqa: F811
    from djsync.ui.cursor import CURSOR

    app = demo_grid
    ed = _open_grid(app)
    # C51 : vue d'ensemble dans la page, sous la forme d'onde zoomée et au-dessus des hot cues
    lay = ed.body
    idx = {w: i for i in range(lay.count()) for w in [lay.itemAt(i).widget()] if w is not None}
    assert idx[ed.canvas] < idx[ed.overview] < idx[ed.cue_panel]
    assert not hasattr(app.player_bar, "grid_overview")
    # C52 : curseur rouge vif, centré sur sa position (le halo ne la décale pas)
    ed.canvas.resize(800, 200)
    ed.go_to(ed.beats[20][2])
    img = ed.canvas.grab().toImage()
    xc = int(round(ed._x(ed.cursor_ms)))
    dpr = img.devicePixelRatio()
    row = int(150 * dpr)
    reds = [x for x in range(img.width()) if img.pixelColor(x, row).name().upper() == CURSOR.upper()]
    assert reds and abs((min(reds) + max(reds)) / 2 / dpr - ed._x(ed.cursor_ms)) <= 1.0 and xc > 0
    ed.close()


def test_waveform_cached_between_frames_and_adaptive_rate(demo_grid, monkeypatch):  # noqa: F811
    from .qt_util import pump

    app = demo_grid
    ed = _open_grid(app)
    assert pump(app, 8, lambda: ed.wave is not None)
    ed.canvas.resize(800, 200)
    ed.go_to(ed.beats[20][2])
    ed.canvas.grab()
    calls = []
    real = ed._paint_bands
    monkeypatch.setattr(ed, "_paint_bands", lambda *a: (calls.append(1), real(*a)))
    for _ in range(10):                              # lecture : la vue avance un peu à chaque image
        ed.start_ms += 15
        ed.canvas.grab()
    assert calls == []                               # recopie de l'image, pas de nouveau calcul
    assert ed.wave is not None
    ed.go_to(ed.beats[-8][2])                        # la vue sort de l'image : refaite une fois
    ed.canvas.grab()
    assert len(calls) == 1
    ed.canvas.paint_ms = 30.0                        # PC lent : moins d'images par seconde
    slow = [ed._frame_interval() for _ in range(5)][-1]
    assert slow >= 30
    ed.canvas.paint_ms = 1.0                         # PC rapide : retour à la cadence de l'écran
    fast = [ed._frame_interval() for _ in range(40)][-1]
    assert 7 <= fast <= 17
    ed.close()



# ------------------------------------------------------------------ C45 (partie 2) : sources libres
def _fake_get(url, params=None):
    if url == "https://api.audius.co":
        return {"data": ["https://node.audius.example"]}
    if url.endswith("/v1/tracks/search"):
        return {"data": [{"id": "Ab1", "title": "Glue (Free DL)", "duration": 268, "permalink": "/bicep/glue",
                          "user": {"name": "Bicep", "handle": "bicep"}, "license": "", "downloadable": True,
                          "artwork": {"480x480": "https://img/a.jpg"}},
                         {"id": "X", "title": "Hidden", "is_streamable": False, "user": {}}]}
    if "advancedsearch" in url:
        return {"response": {"docs": [{"identifier": "netlabel-ep", "title": "Isles EP", "creator": ["Bicep"],
                                       "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"}]}}
    if url.endswith("/metadata/netlabel-ep"):
        return {"files": [
            {"name": "01 Glue.flac", "format": "Flac", "title": "Glue", "length": "4:28"},
            {"name": "01 Glue.mp3", "format": "VBR MP3", "title": "Glue", "length": "268.1"},
            {"name": "02 Apricots.flac", "format": "Flac", "title": "Apricots"},
            {"name": "cover.jpg", "format": "JPEG"}]}
    raise AssertionError(url)


def test_free_sources_search_with_licence_and_quality():
    from djsync.core import freesources as F

    res = F.search_all("bicep glue", ["archive", "audius"], get=_fake_get)
    arch = [x for x in res if x.source == "archive"]
    aud = [x for x in res if x.source == "audius"]
    assert len(arch) == 1 and arch[0].quality == "FLAC" and arch[0].duration_seconds == 268
    assert arch[0].license == "CC BY-NC 4.0" and arch[0].source_url.endswith("/netlabel-ep/01%20Glue.flac")
    assert arch[0].source_label == "Internet Archive" and arch[0].album == "Isles EP"
    assert len(aud) == 1 and aud[0].source_url == "https://audius.co/bicep/glue" and aud[0].quality == "MP3 320"
    assert F.search_all("x", ["archive"], get=lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))) == []

    from djsync.ui.views.common import result_row
    from djsync.ui import theme

    row = result_row(arch[0])
    assert row.values["source"] == "Internet Archive · FLAC · CC BY-NC 4.0" and row.values["source__color"] == theme.GOLD


def test_lossless_from_a_free_source_is_never_transcoded(tmp_path, monkeypatch):
    from djsync.core import downloader as D
    from djsync.models import TrackResult

    monkeypatch.setattr(D.Downloader, "_run", lambda self, tr, dest, base, extra, n: ((_wav(dest / f"{base}.wav")), "0"))
    monkeypatch.setattr(D, "finalize", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no transcode")))
    monkeypatch.setattr(D, "tag_audio", lambda *a, **k: None)
    d = D.Downloader(audio_format="mp3", normalize=True)
    tr = TrackResult(video_id="archive:x", title="T", artist="A", source="archive",
                     source_url="https://archive.org/download/x/t.wav", quality="WAV")
    res = d.download(tr, tmp_path)
    assert res.original and res.file_path.endswith(".wav")
