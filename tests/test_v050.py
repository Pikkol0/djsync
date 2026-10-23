"""V0.5.0 : copie de playlists entre bibliothèques, mémoire cue automatique, moteur yt-dlp
(détection d'échec, mise à jour vérifiée, retour arrière), format de sortie / normalisation."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

from djsync.analysis.anlz import read_memory_cues, read_path
from djsync.core import engine
from djsync.core.camelot import to_musical
from djsync.db import RekordboxUsbLibrary, drive_from_letter
from djsync.db._key import get_default_key
from djsync.db.transfer import copy_playlist

from .test_usb_library import usb  # noqa: F401 (fixture)

CUE_DDL = ("CREATE TABLE cue(cue_id integer primary key, content_id integer, kind integer, colorTableIndex integer, "
           "cueComment varchar, isActiveLoop integer, beatLoopNumerator integer, beatLoopDenominator integer, "
           "inUsec integer, outUsec integer, in150FramePerSec integer, out150FramePerSec integer, "
           "inMpegFrameNumber integer, outMpegFrameNumber integer, inMpegAbs integer, outMpegAbs integer, "
           "inDecodingStartFramePosition integer, outDecodingStartFramePosition integer, inFileOffsetInBlock integer, "
           "OutFileOffsetInBlock integer, inNumberOfSampleInBlock integer, outNumberOfSampleInBlock integer)")


def _add_cue_table(root: Path) -> None:
    conn = sqlcipher.connect(str(root / "PIONEER" / "rekordbox" / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute(CUE_DDL)
    conn.commit()
    conn.close()


@pytest.fixture
def usb_lib(usb):  # noqa: F811
    _add_cue_table(usb)
    lib = RekordboxUsbLibrary(drive_from_letter(str(usb)), analyze=True).connect()
    lib.auto_cue = True
    yield lib
    lib.close()


@pytest.fixture
def local(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    from djsync.db import local_library as L

    from .test_local_library import DATA

    db_dir = tmp_path / "pc" / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    target = L.LocalRekordbox(db_dir, tmp_path / "pc" / "Music")
    lib = L.LocalRekordboxLibrary(target, backup_root=tmp_path / "bk", owned_path=tmp_path / "owned.json",
                                  analyze=True).connect()
    lib.auto_cue = True
    yield lib
    lib.close()


def _wav(folder: Path, name: str, bpm: float = 124.0, seconds: float = 8.0) -> Path:
    from .test_local_library import make_wav

    return make_wav(folder, name, seconds, bpm=bpm)


# ------------------------------------------------------------------ mémoire cue
def test_usb_memory_cue_on_first_downbeat(usb_lib):
    path = _wav(usb_lib.default_download_dir("Art"), "Cue me")
    t = usb_lib.add_track(path, "Cue me", "Art")
    dat = usb_lib.drive.root / t.analysis_path.lstrip("/")
    cues = read_memory_cues(dat.read_bytes())
    assert len(cues) == 1
    from djsync.analysis.cues import read_cues

    ext_cues = read_cues(None, dat.with_suffix(".EXT").read_bytes())          # 1.3.0 : liste étendue du .EXT
    assert [c.ms for c in ext_cues] == cues and not ext_cues[0].slot
    # 1.3.0 : comme Rekordbox, rien dans la table `cue` de exportLibrary.db
    assert usb_lib._read("SELECT 1 FROM cue WHERE content_id = ?", (t.content_id,)) == []
    beats = __import__("djsync.analysis.anlz", fromlist=["read_beats"]).read_beats(dat.read_bytes())
    assert cues[0] == next(ms for n, _t, ms in beats if n == 1)        # premier temps fort de la grille
    usb_lib.analyze_track(t.content_id, force=True)                      # réanalyse : la mémoire est gardée
    assert read_memory_cues(dat.read_bytes()) == cues


def test_local_memory_cue_rows(local):
    path = _wav(local.default_download_dir("Art", ""), "Local cue")
    t = local.add_track(path, "Local cue", "Art")
    rows = local._read("SELECT Kind, InMsec, InFrame, OutMsec, ContentUUID FROM djmdCue WHERE ContentID = :i",
                       {"i": str(t.content_id)})
    assert len(rows) == 1 and rows[0][0] == 0 and rows[0][3] == -1 and rows[0][2] == rows[0][1] * 150 // 1000
    cues = json.loads(local._read("SELECT Cues FROM contentCue WHERE ContentID = :i", {"i": str(t.content_id)})[0][0])
    assert cues[0]["Kind"] == 0 and cues[0]["InMsec"] == rows[0][1]


# --------------------------------------------------------------- copie de playlists
def test_copy_playlist_usb_to_computer_reuses_analysis(usb_lib, local):
    a = usb_lib.add_track(_wav(usb_lib.default_download_dir("DJ"), "One"), "One", "DJ", "LP",
                          "https://music.youtube.com/watch?v=AAAAAAAAAAA")
    b = usb_lib.add_track(_wav(usb_lib.default_download_dir("DJ"), "Two", bpm=130), "Two", "DJ")
    pl = usb_lib.create_playlist("Set")
    usb_lib.add_to_playlist(pl.playlist_id, [a.content_id, b.content_id])
    grid = usb_lib.beat_grid(a.content_id)
    usb_lib.save_beat_grid(a.content_id, [(n, t, ms + 7) for n, t, ms in grid.beats])   # grille corrigée à la main

    res = copy_playlist(usb_lib, pl.playlist_id, local)
    assert (res.copied, res.reused, res.failed) == (2, 0, 0)
    copied = local.get_playlist_tracks(res.playlist_id)
    assert [t.title for t in copied] == ["One", "Two"] and all(t.is_analysed for t in copied)
    one = copied[0]
    assert Path(one.path).is_file() and local.drive.music_dir.resolve().as_posix() in one.path
    dat = local.absolute_path(one.analysis_path)
    assert read_path(dat.read_bytes()) == "?/One.wav"                      # chemin réécrit à la façon du PC
    assert local.beat_grid(one.content_id).beats[0][2] == grid.beats[0][2] + 7   # correction conservée
    assert one.source_url and one.bpm == pytest.approx(usb_lib.get_track(a.content_id).bpm, abs=0.01)
    # 2e copie : rien n'est recopié, la playlist n'a pas de doublon
    again = copy_playlist(usb_lib, pl.playlist_id, local)
    assert (again.copied, again.reused) == (0, 2) and again.playlist_id == res.playlist_id
    assert len(local.get_playlist_tracks(res.playlist_id)) == 2


def test_copy_playlist_computer_to_usb(usb_lib, local):
    t = local.add_track(_wav(local.default_download_dir("PC", ""), "Home"), "Home", "PC")
    pl = local.create_playlist("From PC")
    local.add_to_playlist(pl.playlist_id, [t.content_id])
    res = copy_playlist(local, pl.playlist_id, usb_lib)
    assert res.copied == 1 and not res.problems
    got = usb_lib.get_playlist_tracks(res.playlist_id)[0]
    assert got.path.startswith("/Contents/") and got.is_analysed
    dat = usb_lib.drive.root / got.analysis_path.lstrip("/")
    assert read_path(dat.read_bytes()) == got.path


def test_to_musical():
    assert (to_musical("8A"), to_musical("2B"), to_musical("Am"), to_musical("?")) == ("Am", "F#", "Am", None)


# ---------------------------------------------------------------------- moteur yt-dlp
@pytest.mark.parametrize("msg,expected", [
    ("ERROR: [youtube] abc: Signature extraction failed: Some formats may be missing", True),
    ("ERROR: [youtube] abc: Requested format is not available", True),
    ("ERROR: [youtube] abc: Unable to download API page: Unable to connect to proxy", False),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", False),
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", False),
    ("ERROR: [youtube] abc: Video unavailable", False),
    ("Cannot read: Unable to extract initial player response; please report this issue", True),
])
def test_looks_outdated(msg, expected):
    assert engine.looks_outdated(msg) is expected


def _fake_pypi(version: str):
    """Wheels minimaux de yt-dlp et yt-dlp-ejs servis par un faux PyPI."""
    def wheel(files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, text in files.items():
                zf.writestr(name, text)
        return buf.getvalue()

    blobs = {
        "yt-dlp": wheel({"yt_dlp/__init__.py": "", "yt_dlp/version.py": f"__version__ = '{version}'\n",
                         f"yt_dlp-{version}.dist-info/METADATA": "x", "../evil.py": "boom"}),
        "yt-dlp-ejs": wheel({"yt_dlp_ejs/__init__.py": ""}),
    }
    urls = {f"https://files/{n}.whl": b for n, b in blobs.items()}

    def fetch(url):
        if url in urls:
            return urls[url]
        name = url.split("/pypi/")[1].split("/")[0]
        return json.dumps({"info": {"version": version}, "urls": [
            {"packagetype": "sdist", "url": "x", "digests": {"sha256": ""}},
            {"packagetype": "bdist_wheel", "url": f"https://files/{name}.whl",
             "digests": {"sha256": hashlib.sha256(blobs[name]).hexdigest()}}]}).encode()
    return fetch


def test_engine_install_activate_and_rollback(tmp_path, monkeypatch):
    folder = tmp_path / "engine"
    monkeypatch.setattr(engine, "bundled_version", lambda: "2026.08.19")
    saved_path, saved_mods = list(sys.path), {k: v for k, v in sys.modules.items() if k.split(".")[0] in engine.MODULES}
    try:
        rel = engine.latest(_fake_pypi("2099.1.2"))
        assert rel.version == "2099.1.2" and rel.newer_than("2026.08.19") and not rel.newer_than("2099.01.02")
        engine.install(rel, _fake_pypi("2099.1.2"), folder)
        assert (folder / "yt_dlp" / "version.py").is_file() and (folder / "yt_dlp_ejs").is_dir()
        assert not (tmp_path / "evil.py").exists()                    # chemin hors dossier refusé
        assert engine.override_version(folder) == "2099.1.2" and str(folder) in sys.path
        from yt_dlp.version import __version__
        assert __version__ == "2099.1.2"                               # pris en compte sans redémarrer
        # une version plus ancienne que celle de l'exe n'est jamais utilisée
        monkeypatch.setattr(engine, "bundled_version", lambda: "2100.1.1")
        sys.path.remove(str(folder))
        assert engine.activate(folder) is False
        # empreinte fausse : refusée, l'installation en place n'est pas touchée
        bad = engine.latest(_fake_pypi("2101.1.1"))
        bad.files["yt-dlp"] = (bad.files["yt-dlp"][0], "0" * 64)
        with pytest.raises(RuntimeError, match="Checksum"):
            engine.install(bad, _fake_pypi("2101.1.1"), folder)
        assert engine.override_version(folder) == "2099.1.2"
        engine.rollback(folder)
        assert not folder.exists()                                     # retour à la version embarquée
    finally:
        sys.path[:] = saved_path
        for k in [k for k in sys.modules if k.split(".")[0] in engine.MODULES]:
            del sys.modules[k]
        sys.modules.update(saved_mods)


def test_js_runtimes_prefers_installed_then_bundled_quickjs(tmp_path, monkeypatch):
    from djsync import portable

    tools = tmp_path / portable.CONTENTS / "tools"
    tools.mkdir(parents=True)
    (tools / "qjs.exe").write_bytes(b"")
    monkeypatch.setattr(portable, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(engine.shutil, "which", lambda n: None)
    assert engine.js_runtimes() == {"quickjs": {"path": str(tools / "qjs.exe")}}
    monkeypatch.setattr(engine.shutil, "which", lambda n: "/usr/bin/deno" if n == "deno" else None)
    assert list(engine.js_runtimes()) == ["deno", "quickjs"]


# ------------------------------------------------------------- format / normalisation
ffmpeg = shutil.which("ffmpeg")


@pytest.mark.skipif(ffmpeg is None, reason="FFmpeg requis")
def test_finalize_mp3_and_normalize(tmp_path):
    from djsync.core.audio_post import finalize, measure

    src = tmp_path / "quiet.m4a"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-af", "volume=-20dB", "-c:a", "aac", str(src)], check=True)
    assert finalize(src, ffmpeg) == src                          # m4a sans normalisation : intact
    before = measure(src, ffmpeg)
    out = finalize(src, ffmpeg, "m4a", normalize=True)
    after = measure(out, ffmpeg)
    assert out == src and after.integrated > before.integrated + 5 and after.true_peak <= -0.5
    mp3 = finalize(out, ffmpeg, "mp3")
    assert mp3.suffix == ".mp3" and mp3.is_file() and not src.exists()


def test_grid_band_wave_is_fine_and_aligned():
    """V1.0.0 : forme d'onde 3 bandes de l'éditeur de grille, 450 points/s, calée sur les attaques."""
    import numpy as np

    from djsync.analysis.waveform import GRID_RATE, band_wave

    sr = 22050
    x = np.zeros(sr * 4, dtype=np.float32)
    for k in range(4):                                   # 4 « kicks » graves, un par seconde
        start = k * sr
        t = np.arange(2000) / sr
        x[start:start + 2000] = 0.9 * np.sin(2 * np.pi * 60 * t) * np.exp(-t * 30)
    w = band_wave(x, sr)
    assert w.rate == GRID_RATE and w.low.size == 4 * GRID_RATE and w.duration_ms == 4000
    for k in range(4):
        onset = int(np.argmax(w.low[k * GRID_RATE:(k + 1) * GRID_RATE] > 20))
        assert onset * 1000 / GRID_RATE < 6                 # attaque visible à moins de 6 ms près
    assert w.low.max() > 3 * max(1, w.high.max())           # un kick, c'est des basses


def test_grid_wave_cache(tmp_path):
    """V1.1.0 : forme d'onde de la grille mise en cache (rouvrir la grille d'un son est immédiat)."""
    from djsync.analysis import waveform as W

    path = _wav(tmp_path / "m", "cached", bpm=128, seconds=5)
    first = W.cached_band_wave(path, None, tmp_path / "cache")
    assert len(list((tmp_path / "cache").glob("*.npz"))) == 1
    W._WAVE_MEMORY.clear()
    again = W.cached_band_wave(path, None, tmp_path / "cache")          # relue sur disque
    assert again.rate == first.rate and (again.low == first.low).all() and (again.high == first.high).all()
