"""1.4.3-rc.3 : tests ciblés des fiches de la rc.3 (A7-3, A1-6, A1-7, C185, B89, C53, S05, C109, C176, C72, C94)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from djsync.analysis import rbwave

DATA = Path(__file__).parent / "data"
SECTIONS = ("pwv3", "pwv5", "pwav", "pwv2", "pwv4", "pwv7", "pwv6")


def _signal(rate: int = 44100, seconds: int = 8) -> np.ndarray:
    """Même signal que celui passé au programme de référence (Sleeve) pour rbwave_ref.npz : kick, nappe,
    bruit, 5 kHz ; deux canaux identiques, 16 bits."""
    t = np.arange(rate * seconds) / rate
    rng = np.random.default_rng(7)
    x = (0.7 * np.sin(2 * np.pi * 55 * t) * np.exp(-12 * (t % 0.5)) + 0.2 * np.sin(2 * np.pi * 880 * t) * ((t % 2) < 1)
         + 0.1 * rng.standard_normal(t.size) * np.exp(-60 * ((t + 0.25) % 0.5)) + 0.05 * np.sin(2 * np.pi * 5000 * t))
    return np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16)


def _feed(x16: np.ndarray, rate: int = 44100, piece: int = 100_003):
    mono = (x16.astype(np.float64) / 32768).astype(np.float32)
    f = rbwave.WaveFeed(rate)
    for i in range(0, mono.size, piece):
        f.push(mono[i:i + piece])
    return f.finish()


# ------------------------------------------------------------------------------ A7-3 : formes d'onde
def test_a7_3_matches_sleeve_reference():
    """Mêmes octets que wave_creator.rs / blue_overview.rs de Sleeve (formules de Rekordbox 7.2) sur un signal
    généré : ≥ 99 % d'octets identiques, écart d'au plus 1 (arrondis du float32)."""
    ref = np.load(DATA / "rbwave_ref.npz")
    out = _feed(_signal())
    assert tuple(out[7]) == tuple(int(v) for v in ref["pwvc"])
    for name, got in zip(SECTIONS, out[:7]):
        a, b = ref[name], np.frombuffer(got, np.uint8)
        assert a.size == b.size, name
        diff = np.abs(a.astype(int) - b)
        assert (diff == 0).mean() >= 0.99, name
        assert name == "pwv5" or diff.max() <= 1, name


def test_a7_3_pieces_do_not_change_the_result():
    x = _signal(seconds=5)
    assert _feed(x, piece=4096) == _feed(x, piece=10 ** 7)


def test_a7_3_lengths_and_silence():
    rate = 48000
    x = np.zeros(rate * 3 + 123, dtype=np.int16)
    pwv3, pwv5, pwav, pwv2, pwv4, pwv7, pwv6, pwvc = _feed(x, rate)
    points = -(-x.size * 150 // rate)
    assert len(pwv3) == points and len(pwv5) == 2 * points and len(pwv7) == 3 * points
    assert len(pwv4) == 1200 * 6 and len(pwv6) == 1200 * 3 and len(pwav) == 400 and len(pwv2) == 100
    assert not any(pwv7) and not any(pwv6)


def test_a7_3_unsupported_rate_keeps_previous_method():
    assert rbwave.supported(44100) and rbwave.supported(48000)
    assert not rbwave.supported(22050) and not rbwave.supported(32000)


def _ffmpeg() -> str:
    from djsync.analysis.decode import find_ffmpeg

    f = find_ffmpeg()
    if not f:
        pytest.skip("FFmpeg absent")
    return f


@pytest.fixture(scope="module")
def mp3_file(tmp_path_factory) -> Path:
    ff = _ffmpeg()
    d = tmp_path_factory.mktemp("a7")
    out = d / "beat.mp3"
    expr = "0.7*sin(2*PI*55*t)*exp(-12*mod(t\\,0.5))+0.1*sin(2*PI*660*t)"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc={expr}|{expr}:s=44100:d=30", "-b:a", "192k",
                    str(out)], check=True)
    return out


def test_a7_3_analyze_file_uses_rekordbox_waveforms(mp3_file):
    from djsync.analysis import analyze_file
    from djsync.analysis.decode import decode_with_native
    from djsync.analysis.waveform import compute_waveforms_rekordbox

    res = analyze_file(mp3_file)
    audio, native = decode_with_native(mp3_file)
    try:
        assert native is not None and native.rate == 44100 and native.lead_frames > 0     # amorçage MP3
        assert res.waveforms == compute_waveforms_rekordbox(native)
    finally:
        native.close()
    assert not native.file.exists()                                                    # fichier temporaire effacé


# --------------------------------------------------------------------------- A1-7 : un seul décodage
def test_a1_7_main_signal_unchanged_and_spectrum_identical(mp3_file):
    from djsync.analysis import spectrum
    from djsync.analysis.decode import decode, decode_with_native

    before = decode(mp3_file)
    after, native = decode_with_native(mp3_file)
    try:
        assert np.array_equal(before.samples, after.samples)               # BPM / tonalité : même signal
        assert spectrum.measure_native(native, after.duration) == spectrum.measure(mp3_file, None, before.duration)
    finally:
        native.close()


# --------------------------------------------------------------------------- A1-6 : plusieurs cœurs
def test_a1_6_worker_count(monkeypatch):
    from djsync.analysis import pool

    monkeypatch.delenv("DJSYNC_ANALYSIS_WORKERS", raising=False)
    pool.set_light(False)
    assert pool.worker_count(16) == 4 and pool.worker_count(3) == 2 and pool.worker_count(1) == 1
    pool.set_light(True)
    try:
        assert pool.worker_count(16) == 1
    finally:
        pool.set_light(False)


def test_a1_6_run_analysis_prefetches_in_processes(monkeypatch, mp3_file, tmp_path):
    """Résultats identiques à l'analyse dans le fil, calculés par 2 processus ; écritures dans l'ordre."""
    import shutil

    from djsync.analysis import analyze_file, pool
    from djsync.db.analysis_flow import PENDING, Step, run_analysis

    files = []
    for i in range(3):
        f = tmp_path / f"s{i}.mp3"
        shutil.copy(mp3_file, f)
        files.append(f)
    expected = [analyze_file(f) for f in files]
    monkeypatch.setenv("DJSYNC_ANALYSIS_WORKERS", "2")
    taken = []
    real_take = pool.Prefetch.take

    def spy(self, path, ffmpeg):
        r = real_take(self, path, ffmpeg)
        taken.append(r is not None)
        return r

    monkeypatch.setattr(pool.Prefetch, "take", spy)
    got = []

    def step(cid):
        got.append(analyze_file(files[cid]))
        return Step(PENDING, "", cid)

    saved = []
    try:
        res = run_analysis([0, 1, 2], step, lambda c: None, lambda jobs: saved.extend(jobs) or [True] * len(jobs),
                           path_of=lambda c: files[c])
    finally:
        pool.shutdown()
    assert res == (3, 0, 0) and saved == [0, 1, 2]
    assert all(taken) and len(taken) == 3
    for a, b in zip(expected, got):
        assert a.bpmx100 == b.bpmx100 and a.key.name == b.key.name and a.waveforms == b.waveforms


# ------------------------------------------------------------------------- C185 : longues playlists
def test_c185_sources_read_up_to_2000_tracks():
    from djsync.core import deezer
    from djsync.core.urlimport import PLAYLIST_CAP, SOURCES

    assert PLAYLIST_CAP == 2000 and deezer.MAX_TRACKS == 2000
    assert {s.key: s.limit for s in SOURCES}["youtube"] == 2000 and {s.key: s.limit for s in SOURCES}["spotify"] == 100


@pytest.fixture
def import_demo(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from .qt_util import close_window
    from .test_ui_v024 import _app

    w = _app(tmp_path, monkeypatch)
    yield w
    close_window(w)


def test_c185_import_loads_pages_on_its_own_and_stops_at_2000(import_demo, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from djsync.models import ResolvedUrl, TrackResult, UrlKind

    view = import_demo.views["import"]
    import_demo.show_view("import")

    def tr(i):
        return TrackResult(video_id=f"V{i:010d}", title=f"T{i}", artist="A", album=None, duration_seconds=200,
                           thumbnail_url="", result_type="video")

    asked = []

    def import_more(url, start, ok, err=None):
        asked.append(start)
        ok(ResolvedUrl(UrlKind.YOUTUBE, "Huge", [tr(i) for i in range(start, start + 200)], url, True, "", True, 3000,
                       start))

    monkeypatch.setattr(import_demo.ctrl, "import_more", import_more)
    view._load_direct(ResolvedUrl(UrlKind.YOUTUBE, "Huge", [tr(i) for i in range(1, 201)], "https://youtube.com/p",
                                  True, "", True, 3000, 1))
    for _ in range(40):
        QApplication.processEvents()
    assert len(view.resolved.tracks) == 2000 and len(asked) == 9
    assert view.more_box.isVisibleTo(view) and not view.more_btn.isVisibleTo(view)      # « 2 000 premiers sur 3 000 »
    assert "3000" in view.more_lbl.text().replace(" ", "").replace(" ", "")


# ------------------------------------------------------------------------- B89 : recherche Haute qualité
def test_b89_archive_query_targets_music_and_title_or_artist():
    from djsync.core.freesources import archive_query

    q = archive_query("Jul bande")
    assert "(title:(jul) OR creator:(jul))" in q and "(title:(bande) OR creator:(bande))" in q
    assert "-collection:(podcasts" in q and "radioprograms" in q and "mediatype:(audio)" in q


def test_b89_audius_albums_become_album_rows():
    from djsync.core import freesources as F

    def get(url, params=None):
        if url == F.AUDIUS_HOSTS:
            return {"data": ["https://h.example"]}
        if url.endswith("/v1/tracks/search"):
            return {"data": []}
        if url.endswith("/v1/playlists/search"):
            return {"data": [{"id": "A1", "is_album": True, "playlist_name": "Night Drive", "user": {"name": "Jul"},
                              "permalink": "/jul/album/night-drive"},
                             {"id": "P2", "is_album": False, "playlist_name": "Jul mix", "user": {"name": "x"}}]}
        if url.endswith("/v1/playlists/A1/tracks"):
            return {"data": [{"id": i, "title": f"T{i}", "duration": 200, "user": {"name": "Jul", "handle": "jul"},
                              "permalink": f"/jul/t{i}"} for i in (1, 2, 3)]}
        raise AssertionError(url)

    out = F.audius_search("jul", get=get)
    albums = [x for x in out if x.is_album]
    assert len(albums) == 1 and albums[0].track_count == 3 and albums[0].title == "Night Drive"
    assert [t.track_no for t in albums[0].tracks] == [1, 2, 3] and albums[0].tracks[0].album == "Night Drive"


# ------------------------------------------------------------------------------ C53 : fonds
def test_c53_backgrounds_keep_accent_readable():
    from djsync.ui import theme
    from djsync.ui.palettes import MIN_CONTRAST, PALETTES

    try:
        for bg in theme.BACKGROUNDS:
            theme.apply_background(bg)
            for name in PALETTES:
                theme.apply_palette(name)
                assert theme.contrast(theme.ACCENT, theme.SURFACE) >= MIN_CONTRAST - 0.05, (bg, name)
                assert theme.contrast(theme.TEXT, theme.SURFACE) >= 7.0, bg
        theme.apply_background("bright")
        assert theme.is_bright() and theme.SURFACE == "#FFFFFF"
        theme.apply_background("oled")
        assert theme.BG == "#000000"
    finally:
        theme.apply_background("default")
        theme.apply_palette(theme.DEFAULT_THEME)


def test_c53_background_setting_rebuilds_the_window(import_demo):
    from djsync.ui import theme

    w = import_demo
    try:
        w.ctrl.settings.background = "bright"
        w.ctrl._emit("restyle")
        assert theme.CURRENT_BACKGROUND == "bright" and w._built_background == "bright" and not w.errors
        w.show_view("settings")
        page = w.views["settings"]
        assert page.bg_menu.count() == len(theme.BACKGROUNDS) == 8          # 1.4.4 (C226) : 4 fonds teintés
    finally:
        w.ctrl.settings.background = "default"
        w.ctrl._emit("restyle")
    assert theme.CURRENT_BACKGROUND == "default"


# ---------------------------------------------------------------------------- S05 : tags du fichier
@pytest.mark.parametrize("ext,args", [("mp3", ["-b:a", "128k"]), ("m4a", ["-c:a", "aac"]), ("flac", [])])
def test_s05_bpm_and_key_written_once(tmp_path, ext, args):
    import mutagen

    from djsync.core.file_tags import write_analysis_tags

    ff = _ffmpeg()
    f = tmp_path / f"x.{ext}"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=2", *args, str(f)], check=True)
    assert write_analysis_tags(f, 123.4, "Am") == f.stat().st_size
    assert write_analysis_tags(f, 123.4, "Am") is None                     # déjà là : rien n'est réécrit
    tags = mutagen.File(str(f)).tags
    text = " ".join(f"{k}={v}" for k, v in tags.items())
    assert "123" in text and "Am" in text


# ------------------------------------------------------------------------- C109 : gain automatique
def test_c109_loudness_and_gain():
    from djsync.analysis import loudness

    sr = 22050
    t = np.arange(sr * 10) / sr
    quiet = (0.05 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    loud = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    lq, pq = loudness.measure(quiet, sr)
    ll, pl = loudness.measure(loud, sr)
    assert abs((ll - lq) - 20.0) < 0.1 and abs(lq - (-29.0)) < 0.5            # sinus 1 kHz : BS.1770
    assert loudness.gain_db(lq) == 12.0 and loudness.gain_db(ll) == pytest.approx(loudness.TARGET_LUFS - ll)
    assert loudness.playback_factor(12.0, pq) <= 10 ** (-pq / 20)               # jamais de saturation
    assert loudness.measure(np.zeros(10, np.float32), sr) == (None, None)


def test_c109_gain_remembered_and_applied_by_the_player(tmp_path, mp3_file):
    import shutil

    from djsync.analysis import analyze_file, loudness
    from djsync.audio import player

    loudness.use_store(tmp_path / "gain.json")
    try:
        f = tmp_path / "s.mp3"
        shutil.copy(mp3_file, f)
        res = analyze_file(f)
        assert res.lufs is not None and loudness.known(f) == pytest.approx((res.gain_db, res.peak_db), abs=0.01)
        assert player._gain_of(f) == pytest.approx(loudness.playback_factor(res.gain_db, res.peak_db))
        assert player._gain_of(tmp_path / "unknown.mp3") == 1.0
    finally:
        loudness.use_store(None)


def test_c109_s05_local_library_writes_mixer_gain_and_tags(tmp_path, monkeypatch, mp3_file):
    pytest.importorskip("pyrekordbox")
    import shutil

    import mutagen

    from djsync.analysis import loudness

    from .test_local_library import DATA
    from djsync.db import local_library as L

    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    loudness.use_store(tmp_path / "gain.json")
    lib = L.LocalRekordboxLibrary(L.LocalRekordbox(db_dir, tmp_path / "Music"), backup_root=tmp_path / "b",
                                  owned_path=tmp_path / "owned.json", analyze=True).connect()
    try:
        lib.write_tags = True
        music = lib.default_download_dir("A", "B")
        music.mkdir(parents=True, exist_ok=True)
        path = music / "beat.mp3"
        shutil.copy(mp3_file, path)
        t = lib.add_track(path, "Beat", "A", "B", "", [])
        assert t.is_analysed
        gain = lib._read("SELECT GainHigh, GainLow FROM djmdMixerParam WHERE ContentID = :id", {"id": str(t.content_id)})
        assert gain and (gain[0][0] or gain[0][1])
        size = lib._read("SELECT FileSize FROM djmdContent WHERE ID = :id", {"id": str(t.content_id)})[0][0]
        assert size == path.stat().st_size and "TBPM" in mutagen.File(str(path)).tags
    finally:
        lib.close()
        loudness.use_store(None)


# ---------------------------------------------------------------------- C72 : mise à jour par morceaux
def _fake_exe(root: Path, name: str, version: str, changed: bytes) -> Path:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packaging"))
    import pack_single_exe

    app = root / name
    (app / "_internal").mkdir(parents=True)
    (app / "DJSync.exe").write_bytes(b"app" + changed * 500)
    (app / "_internal" / "Qt6Core.dll").write_bytes(bytes(range(256)) * 20000)       # identique d'une version à l'autre
    (app / "_internal" / "base_library.zip").write_bytes(changed * 30000)
    launcher = root / "launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 4000)
    out = root / f"{name}.exe"
    pack_single_exe.pack(launcher, app, version, out)
    with open(out, "ab") as f:
        f.write(b"AUTHENTICODE" * 200)                     # signature après le bloc de fin
    return out


def test_c72_rebuilds_the_new_exe_from_the_old_one(tmp_path):
    from djsync.core import delta_update as D

    old = _fake_exe(tmp_path, "old", "1.4.2", b"a")
    new = _fake_exe(tmp_path, "new", "1.4.3", b"b")
    man = D.manifest(new, "1.4.3")
    data = new.read_bytes()
    fetched = []

    def rng(url, start, n):
        fetched.append(n)
        return data[start:start + n]

    out = D.download("https://x/DJSync.exe", man["sha256"], old, tmp_path / "dl", get_json=lambda u: man, get_range=rng)
    assert out is not None and out.read_bytes() == data
    assert sum(fetched) < len(data) * 0.2                                     # le gros fichier inchangé n'est pas retéléchargé


def test_c72_falls_back_to_full_download(tmp_path):
    from djsync.core import delta_update as D

    old = _fake_exe(tmp_path, "old", "1.4.2", b"a")
    new = _fake_exe(tmp_path, "new", "1.4.3", b"b")
    man = D.manifest(new, "1.4.3")
    data = new.read_bytes()
    assert D.download("u", "0" * 64, old, tmp_path / "dl", get_json=lambda u: man) is None          # autre fichier

    def broken(url, start, n):
        return data[start:start + n - 1]

    assert D.download("u", man["sha256"], old, tmp_path / "dl", get_json=lambda u: man,
                      get_range=lambda u, s, n: b"x" * n) is None                                 # empreinte fausse
    assert not list((tmp_path / "dl").glob("*.part"))
    other = tmp_path / "other.exe"
    other.write_bytes(b"MZ" + b"\0" * 100)
    with pytest.raises(ValueError):
        D.parts_of(other)                                                                          # exe d'avant le format


def test_c176_app_size_report(tmp_path):
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packaging"))
    import app_size

    text = app_size.report(_fake_exe(tmp_path, "new", "1.4.3", b"b"))
    assert "MB extracted" in text and "_internal/Qt6Core.dll" in text


# ------------------------------------------------------------- C94 : Apple Music, Tidal, Amazon Music
def test_c94_links_are_recognised():
    from djsync.core.urlimport import classify_url
    from djsync.models import UrlKind

    assert classify_url("https://music.apple.com/fr/playlist/soiree/pl.u-abc") == UrlKind.APPLE
    assert classify_url("https://tidal.com/browse/playlist/0a1b2c3d-1111-2222-3333-444455556666") == UrlKind.TIDAL
    assert classify_url("https://listen.tidal.com/album/123456") == UrlKind.TIDAL
    assert classify_url("https://music.amazon.fr/playlists/B0ABCDEF") == UrlKind.AMAZON
    assert classify_url("https://www.amazon.fr/dp/B0") == UrlKind.UNKNOWN


def test_c94_apple_page_is_read():
    from djsync.core.streaming_import import parse_apple

    data = [{"data": {"sections": [{"items": [
        {"title": "Loca", "artistName": "Jul", "duration": 201000, "contentDescriptor": {}},
        {"title": "Bande organisée", "artistName": "Jul, SCH", "duration": 254000, "contentDescriptor": {}},
        {"title": "Loca", "artistName": "Jul", "duration": 201000, "contentDescriptor": {}}]}]}}]
    page = ('<html><head><meta property="og:title" content="Soirée - Playlist - Apple Music"></head><body>'
            f'<script type="application/json" id="serialized-server-data">{json.dumps(data)}</script></body></html>')
    pl = parse_apple(page)
    assert pl.name == "Soirée" and [t.title for t in pl.tracks] == ["Loca", "Bande organisée"]
    assert pl.tracks[1].duration_seconds == 254 and pl.tracks[0].artist == "Jul"


def test_c94_ld_json_pages_apple_and_amazon():
    from djsync.core.streaming_import import StreamingImportError, parse_amazon, parse_apple

    ld = {"@type": "MusicPlaylist", "name": "Club", "track": [
        {"@type": "MusicRecording", "name": "One", "duration": "PT3M25S", "byArtist": {"name": "A"}},
        {"@type": "MusicRecording", "name": "Two", "duration": "PT4M", "byArtist": [{"name": "B"}, {"name": "C"}]}]}
    page = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    for parse in (parse_apple, parse_amazon):
        pl = parse(page)
        assert pl.name == "Club" and [t.duration_seconds for t in pl.tracks] == [205, 240]
        assert pl.tracks[1].artists == ("B", "C")
    with pytest.raises(StreamingImportError) as e:
        parse_amazon("<html>JavaScript only</html>")
    assert e.value.private


def test_c94_tidal_pages():
    from djsync.core import streaming_import as S

    calls = []

    class R:
        def __init__(self, d):
            self.d = d

        def json(self):
            return self.d

    def get(url, headers=None, params=None):
        calls.append((url, dict(params or {})))
        assert headers == {"x-tidal-token": S.TIDAL_TOKEN}
        if url.endswith("/items"):
            off = params["offset"]
            n = min(100, 150 - off)
            return R({"totalNumberOfItems": 150, "items": [
                {"type": "track", "item": {"title": f"T{off + i}", "duration": 200, "artists": [{"name": "X"}],
                                           "album": {"title": "Alb"}}} for i in range(n)]})
        return R({"title": "Mix", "numberOfTracks": 150})

    pl = S.fetch_tidal("https://tidal.com/browse/playlist/0a1b2c3d-1111", get=get)
    assert pl.name == "Mix" and len(pl.tracks) == 150 and not pl.truncated and pl.tracks[0].album == "Alb"
    assert [c[1].get("offset") for c in calls if c[0].endswith("/items")] == [0, 100]
