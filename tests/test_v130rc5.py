"""1.3.0-rc.5 : C39 (son en retard sous Windows : réserve de la carte son mesurée et réduite, saut entendu
tout de suite)."""
from __future__ import annotations

import time

import numpy as np
import pytest

from .audio_fixture import write_wav


def test_output_latency_is_measured_from_the_device_calls(monkeypatch):
    from djsync.audio import player as P

    p = P.AudioPlayer(post=lambda f: f())
    clock = [10.0]
    monkeypatch.setattr(P.time, "monotonic", lambda: clock[0])
    n = int(P.RATE * 0.04)
    # au démarrage la carte son remplit sa réserve d'un coup (3 paquets), puis réclame au rythme du son
    for _ in range(3):
        p._fill(n)
    for _ in range(20):
        clock[0] += 0.04
        p._fill(n)
    assert p.output_latency() == pytest.approx(0.12, abs=1e-3)       # 3 paquets de 40 ms d'avance
    # la position entendue retire ce retard mesuré (et plus la valeur prévue de 200 ms)
    p.state = P.PLAYING
    p._frames = p._cb_frames = 5 * P.RATE
    p._cb_time, p._cb_period = clock[0], 0.04
    assert p.position() == pytest.approx(5.0 - 0.12, abs=1e-3)


def test_reserve_is_small_outside_macos():
    import sys

    from djsync.audio import player as P

    total = P.BUFFER_MS * (P.PERIODS or 3)
    if sys.platform == "darwin":
        assert P.BUFFER_MS == 200
    else:
        assert total <= 100                                  # ~80 ms au lieu de ~600 ms


def _playing(tmp_path):
    from djsync.audio import player as P

    path = write_wav(tmp_path / "s.wav", (0.1 * np.sin(np.linspace(0, 4000, 44100 * 30))).astype("float32"))
    p = P.AudioPlayer(post=lambda f: f())
    p.play(path, P.NowPlaying("s", "a", str(path)))
    t0 = time.time()
    while p.state != P.PLAYING and time.time() - t0 < 10:
        time.sleep(0.02)
    assert p.state == P.PLAYING
    return p


def test_seek_while_playing_is_heard_at_once(tmp_path):
    p = _playing(tmp_path)
    time.sleep(0.5)
    assert p.output_latency() > 0
    old_device = p._device
    p.seek(12.0)
    assert p._device is not None and p._device is not old_device    # réserve vidée : carte son relancée
    assert p._prev is None                                         # plus d'ancien passage à afficher
    time.sleep(0.3)
    assert 12.0 <= p.position() < 12.6                             # on entend le nouvel endroit
    p.close()


def test_loop_jump_keeps_the_reserve(tmp_path):
    p = _playing(tmp_path)
    time.sleep(0.3)
    device = p._device
    p.seek(3.0, flush=False)                                       # retour au début d'une boucle
    assert p._device is device                                     # la fin de boucle déjà envoyée se joue
    p.close()


# ------------------------------------------------------------------ B25 : formes d'onde comme Rekordbox
def _heights(level, sr=44100, seconds=4.0):
    from djsync.analysis.waveform import compute_waveforms

    t = np.arange(int(sr * seconds)) / sr
    x = (level * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    wf = compute_waveforms(x, sr, seconds)
    v = np.frombuffer(wf.color_detail, ">u2")
    return (v >> 2) & 31, wf


def test_waveform_height_follows_the_real_level():
    loud, _ = _heights(0.95)
    quiet, _ = _heights(0.4)
    # Rekordbox : ≈ 16 pour un son à fond, ≈ 2-3 à -8 dB ; avant, DJSync étirait tout jusqu'à 31
    assert 13 <= np.median(loud) <= 19
    assert np.median(quiet) <= 4 and np.median(quiet) < np.median(loud)


def test_waveform_is_one_point_later_like_rekordbox():
    from djsync.analysis.waveform import DETAIL_RATE, compute_waveforms

    sr = 44100
    x = np.zeros(sr * 3, dtype=np.float32)
    x[sr: sr + 200] = 0.95                                  # un coup à 1,000 s
    wf = compute_waveforms(x, sr, 3.0)
    h = (np.frombuffer(wf.color_detail, ">u2") >> 2) & 31
    assert int(np.argmax(h)) == DETAIL_RATE + 1             # point 151 (6,7 ms plus tard), comme Rekordbox
