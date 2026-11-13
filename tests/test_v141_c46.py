"""1.4.1 (C46) : qualité supposée sur plusieurs indices (calée sur le banc A05)."""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from djsync.analysis import spectrum as S

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")


def _music(path: Path, seconds: float = 70.0, sr: int = 44100) -> Path:
    """Bruit rose rythmé (plein spectre jusqu'à 22 kHz) : un « vrai sans perte » de synthèse."""
    rng = np.random.default_rng(7)
    n = int(seconds * sr)
    env = 0.4 + 0.6 * (np.sin(2 * np.pi * 2.0 * np.arange(n) / sr) > 0)       # passages forts / faibles
    chans = []
    for _ in range(2):                                     # stéréo : le MP3 coupe comme sur un vrai son
        f = np.fft.rfft(rng.standard_normal(n))
        f /= np.sqrt(np.maximum(np.arange(f.size), 1))
        pink = np.fft.irfft(f, n)
        chans.append(pink / np.abs(pink).max() * 0.6 * env)
    data = (np.clip(np.stack(chans, axis=1), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(data.tobytes())
    return path


def _ffmpeg(src: Path, dst: Path, *opts: str) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *opts, str(dst)], check=True)
    return dst


def _klass(path: Path) -> int:
    return S.estimate(S.measure(path), 44100)


def test_representative_values_round_trip():
    for kbps, cut in S.REPRESENTATIVE.items():
        assert S.estimate(cut, 44100) == kbps


def test_classify_rules_on_synthetic_features():
    def feat(edge_hz, holes):
        spec = []
        for lo in range(S.BAND_LO, S.BAND_HI, S.BAND_STEP):
            if lo >= 22050:
                spec.append(None)
            else:
                spec.append(-15.0 - (lo - 10000) / 1000 if lo < edge_hz else -90.0)
        quant = [[-100.0, -100.0 + holes, -80.0] for _ in range(10)]
        return {"spec": spec, "quant": quant}

    assert S.classify([feat(30000, 12)] * 3)[0] == S.LOSSLESS          # rien coupé, pas de trous
    assert S.classify([feat(30000, 40)] * 3)[0] == 256                 # plein spectre mais troué : MP3 V0
    assert S.classify([feat(20250, 30)] * 3)[0] == 320                 # mur à 20 kHz + trous : MP3 320
    assert S.classify([feat(20250, 12)] * 3)[0] == 320                 # Opus : plafonné ailleurs (core.quality)
    assert S.classify([feat(19500, 30)] * 3)[0] == 256
    assert S.classify([feat(18750, 30)] * 3)[0] == 192
    assert S.classify([feat(16750, 30)] * 3)[0] == 128
    assert S.classify([])[0] == 0 and S.classify([None, None])[0] == 0


def test_gentle_master_roll_off_is_not_a_codec_wall():
    spec = []
    for lo in range(S.BAND_LO, S.BAND_HI, S.BAND_STEP):           # descente douce de 4 dB / kHz
        spec.append(None if lo >= 22050 else -15.0 - 4.0 * (lo - 10000) / 1000)
    f = {"spec": spec, "quant": [[-100.0, -88.0, -80.0]] * 10}
    assert S.classify([f] * 3)[0] == S.LOSSLESS


@needs_ffmpeg
def test_true_lossless_and_fake_lossless(tmp_path):
    ref = _music(tmp_path / "ref.wav")
    assert _klass(ref) == S.LOSSLESS
    mp3 = _ffmpeg(ref, tmp_path / "a.mp3", "-c:a", "libmp3lame", "-b:a", "128k")
    fake = _ffmpeg(mp3, tmp_path / "fake.wav", "-c:a", "pcm_s16le")
    assert _klass(mp3) == 128
    assert _klass(fake) == 128                    # 1.4.0 : « Sans perte » (bruit de fond du WAV)
    flac = _ffmpeg(mp3, tmp_path / "fake.flac", "-c:a", "flac")
    assert _klass(flac) == 128


@needs_ffmpeg
def test_mp3_320_and_192(tmp_path):
    ref = _music(tmp_path / "ref.wav")
    assert _klass(_ffmpeg(ref, tmp_path / "b.mp3", "-c:a", "libmp3lame", "-b:a", "192k")) == 192
    assert _klass(_ffmpeg(ref, tmp_path / "c.mp3", "-c:a", "libmp3lame", "-b:a", "320k")) == 320


@needs_ffmpeg
def test_youtube_opus_never_lossless_and_capped(tmp_path):
    from djsync.core.quality import probe

    ref = _music(tmp_path / "ref.wav", sr=48000)
    opus = _ffmpeg(ref, tmp_path / "v.opus", "-c:a", "libopus", "-b:a", "128k")
    wav = _ffmpeg(opus, tmp_path / "v.wav", "-c:a", "pcm_s16le", "-ar", "48000")
    for f in (opus, wav):
        assert S.estimate(S.measure(f), 48000) != S.LOSSLESS
        S.measure_and_remember(f)
        assert probe(f).real_kbps <= 192                     # signature de l'Opus (48 kHz, mur vers 20 kHz)


@needs_ffmpeg
def test_three_slices_are_read(tmp_path, monkeypatch):
    ref = _music(tmp_path / "ref.wav")
    starts = []
    real = S._decode_slice
    monkeypatch.setattr(S, "_decode_slice", lambda p, f, sr, st: starts.append(st) or real(p, f, sr, st))
    S.measure(ref, duration=70.0)
    assert [round(s) for s in starts] == [round(70 * p - 10) for p in S.POSITIONS]


def test_old_store_is_not_reused():
    assert S._file().name == "quality-3.json" or S._store_path is not None
