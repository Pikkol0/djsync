"""1.4.4-rc.1 (lot 2) : A09 B, A1-11 : longs sons lus au fil de l'eau, sons courts gardés en mémoire (tampon
réservé d'un coup). Sortie audio « null » (DJSYNC_AUDIO_NULL), WAV synthétiques : pas besoin de FFmpeg."""
from __future__ import annotations

import logging
import os
import queue
import time
import wave

import numpy as np
import pytest

os.environ.setdefault("DJSYNC_AUDIO_NULL", "1")             # sortie audio « null » (miniaudio)
pytest.importorskip("miniaudio")

from djsync.audio import player as P  # noqa: E402
from djsync.audio.player import PLAYING, STOPPED, AudioPlayer, NowPlaying  # noqa: E402

_A09_SLACK = 64 * 1024                  # un paquet du décodeur en plus du tampon d'avance


def _a09_wav(path, seconds: float, seed: int = 9) -> bytes:
    """WAV s16 stéréo 44,1 kHz au contenu non périodique (un décalage d'un échantillon se voit) ; renvoie le PCM."""
    rng = np.random.default_rng(seed)
    pcm = (rng.standard_normal(int(seconds * P.RATE) * P.CHANNELS) * 6000).clip(-32768, 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(P.CHANNELS)
        w.setsampwidth(2)
        w.setframerate(P.RATE)
        w.writeframes(pcm)
    return pcm


def _a09_read(stream, nbytes: int, timeout: float = 10.0) -> bytes:
    out = bytearray()
    end = time.time() + timeout
    while len(out) < nbytes and time.time() < end:
        out += stream.read(nbytes - len(out))
        if stream.exhausted:
            break
        time.sleep(0.005)
    return bytes(out)


def _a09_wait(cond, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def env():
    ui = queue.Queue()
    events = []
    player = AudioPlayer(post=ui.put, on_event=lambda k, p: events.append((k, p)))

    def pump(until, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end:
            try:
                ui.get(timeout=0.05)()
            except queue.Empty:
                pass
            player.poll()
            if until():
                return True
        return False

    yield player, events, pump
    player.close()


def test_a09_stream_reason_threshold():
    assert P.stream_reason(5 * 60, free_mb=None) is None                   # son courant : gardé en mémoire
    assert P.stream_reason(P.MEMORY_MAX_S + 1, free_mb=None) == "long track"
    assert P.stream_reason(0.0, free_mb=None) == "unknown length"
    assert P.stream_reason(5 * 60, free_mb=100) == "low free memory"       # PC à court de mémoire
    assert P.stream_reason(5 * 60, free_mb=8000) is None
    assert P.decoded_mb(60) == pytest.approx(10.58, abs=0.01)              # ≈ 10,6 Mo par minute


def test_a09_long_track_streamed_with_bounded_buffer(env, tmp_path, monkeypatch, caplog):
    """Au-delà du seuil (abaissé pour le test) : rien n'est gardé en mémoire, tampon borné, saut = décodeur repositionné."""
    player, events, pump = env
    monkeypatch.setattr(P, "MEMORY_MAX_S", 5)
    f = tmp_path / "long.wav"
    _a09_wav(f, 90)
    bound = P._AHEAD * P.FRAME_BYTES + _A09_SLACK
    with caplog.at_level(logging.INFO, logger="djsync.memory"):
        player.play(f, NowPlaying("Long", "Mix", str(f)))
        assert pump(lambda: player.state == PLAYING)
    assert player._cache is None
    lines = [r.getMessage() for r in caplog.records if r.name == "djsync.memory"]
    assert any("Playback streamed: long.wav (long track, 1.5 min), about 16 MB not kept in memory" in m for m in lines)
    for _ in range(10):                                  # pendant la lecture : jamais plus que le tampon d'avance
        pump(lambda: False, timeout=0.1)
        assert isinstance(player._stream, P._Stream) and player._stream.buffered <= bound
    player.seek(60.0)
    assert isinstance(player._stream, P._Stream) and player._stream.start == pytest.approx(60.0)
    assert pump(lambda: 60.0 <= player.position() < 62.0)
    assert player._stream.buffered <= bound and player._cache is None
    player.toggle_pause()                                # pause : flux rouvert à l'endroit entendu
    assert isinstance(player._stream, P._Stream) and player._stream.start >= 60.0
    player.toggle_pause()
    assert pump(lambda: player.state == PLAYING and player.position() > 60.0)


def test_a09_streamed_samples_match_full_decode(env, tmp_path, monkeypatch):
    """Les échantillons lus en flux sont ceux du son entier, au début et après un saut."""
    player, events, pump = env
    f = tmp_path / "match.wav"
    pcm = _a09_wav(f, 30, seed=3)
    full = P._PcmCache(f, None, 30.0)                    # lecture complète (chemin des sons courts)
    assert _a09_wait(lambda: full.complete)
    assert bytes(full.data) == pcm
    n = 3 * P.RATE * P.FRAME_BYTES
    for start in (0.0, 12.5, 27.0):
        s = P._Stream(f, start, None)
        try:
            got = _a09_read(s, n)
        finally:
            s.close()
        at = int(start * P.RATE) * P.FRAME_BYTES
        assert got == bytes(full.data[at:at + n])
    # même chose par le lecteur, son lu en flux : le flux ouvert au saut part du bon échantillon
    monkeypatch.setattr(P, "MEMORY_MAX_S", 5)
    player.play(f, NowPlaying("T", "A", str(f)))
    assert pump(lambda: player.state == PLAYING)
    player.toggle_pause()
    player.seek(20.0)
    assert isinstance(player._stream, P._Stream)
    at = int(20.0 * P.RATE) * P.FRAME_BYTES
    assert _a09_read(player._stream, n) == pcm[at:at + n]


def test_a09_end_of_streamed_track(env, tmp_path, monkeypatch):
    player, events, pump = env
    monkeypatch.setattr(P, "MEMORY_MAX_S", 1)
    f = tmp_path / "end.wav"
    _a09_wav(f, 2.5)
    player.play(f, NowPlaying("T", "A", str(f)))
    assert pump(lambda: player.state == PLAYING)
    assert player._cache is None
    assert pump(lambda: any(k == "ended" for k, _ in events), timeout=10)
    assert player.state == STOPPED


def test_a09_short_track_unchanged_and_reserved_once(env, tmp_path, monkeypatch, caplog):
    """Son court : gardé décodé (sauts depuis la mémoire, comme avant), tampon réservé à sa taille, pas de ligne."""
    player, events, pump = env
    monkeypatch.setattr(P, "STREAM_KEEP_FREE_MB", 0)
    f = tmp_path / "short.wav"
    pcm = _a09_wav(f, 4)
    with caplog.at_level(logging.INFO, logger="djsync.memory"):
        player.play(f, NowPlaying("T", "A", str(f)))
        assert pump(lambda: player.state == PLAYING)
        assert pump(lambda: player._cache is not None and player._cache.complete)
    assert not [r for r in caplog.records if "Playback streamed" in r.getMessage()]
    cache = player._cache
    assert cache.filled == len(cache.data) == len(pcm) and bytes(cache.data) == pcm
    player.seek(2.0)
    assert isinstance(player._stream, P._MemStream)
    assert pump(lambda: any(k == "ended" for k, _ in events), timeout=8)
    # rejoué : même tampon, pas de nouveau décodage
    player.play(f, NowPlaying("T", "A", str(f)))
    assert pump(lambda: player.state == PLAYING)
    assert player._cache is cache


def test_a09_cache_longer_than_tags_gives_memory_back(tmp_path, monkeypatch, caplog):
    """Durée annoncée fausse : le tampon grossit jusqu'au seuil, puis la mémoire est rendue (lecture en flux)."""
    monkeypatch.setattr(P, "MEMORY_MAX_S", 2)
    f = tmp_path / "liar.wav"
    _a09_wav(f, 5)
    with caplog.at_level(logging.INFO, logger="djsync.memory"):
        cache = P._PcmCache(f, None, 1.0)
        assert _a09_wait(lambda: cache.too_long)
    assert not cache.complete and len(cache.data) == 0
    assert any("longer than its tags say" in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(P, "MEMORY_MAX_S", 60)
    ok = P._PcmCache(f, None, 0.0)                        # durée inconnue : grossit par ajouts, sous le seuil
    assert _a09_wait(lambda: ok.complete)
    assert ok.filled == len(ok.data) == 5 * P.RATE * P.FRAME_BYTES
