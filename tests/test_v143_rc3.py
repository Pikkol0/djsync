"""1.4.3-rc.3 : tests ciblés des fiches de la rc.3 (A7-3, A1-6, A1-7, C185, B89, C53, S05, C109, C176, C72, C94)."""
from __future__ import annotations

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
