"""Lecteur : décodage m4a via FFmpeg, états, seek, fin de morceau (sortie audio « null »)."""
import os
import queue
import shutil
import subprocess
import time

import pytest

os.environ.setdefault("DJSYNC_AUDIO_NULL", "1")             # sortie audio « null » (miniaudio)
pytest.importorskip("miniaudio")
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg requis")

from djsync.audio.player import LOADING, PAUSED, PLAYING, STOPPED, AudioPlayer, NowPlaying  # noqa: E402


@pytest.fixture
def env(tmp_path):
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

    def make(name, seconds, *codec):
        path = tmp_path / name
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                        *codec, str(path)], check=True)
        return path

    yield player, events, pump, make
    player.close()


def test_m4a_is_decoded_in_background_then_played(env):
    player, events, pump, make = env
    f = make("a.m4a", 6, "-c:a", "aac", "-b:a", "128k")
    player.play(f, NowPlaying("Titre", "Artiste", str(f)))
    assert player.state == LOADING                      # rendu immédiatement : l'UI ne bloque pas
    assert pump(lambda: player.state == PLAYING)
    assert player.duration == pytest.approx(6, abs=0.3)
    assert any(k == "loaded" for k, _ in events)
    assert pump(lambda: player.position() > 0.3)

    player.toggle_pause(); assert player.state == PAUSED
    p1 = player.position(); time.sleep(0.3)
    assert player.position() == p1                      # figée en pause
    player.seek(4.0)                                    # seek en pause : reste en pause, position = 4 s
    assert player.state == PAUSED and player.position() == pytest.approx(4.0, abs=0.2)
    player.toggle_pause(); assert player.state == PLAYING
    assert pump(lambda: player.position() > 4.3)
    player.stop(); assert player.state == STOPPED and player.position() == 0.0


def test_mp3_plays_directly_and_end_is_detected(env):
    player, events, pump, make = env
    f = make("b.mp3", 1.5, "-b:a", "128k")
    player.play(f, NowPlaying("T", "A", str(f)))
    assert pump(lambda: player.state == PLAYING)
    assert pump(lambda: any(k == "ended" for k, _ in events), timeout=6)
    assert player.state == STOPPED


def test_a_newer_play_cancels_a_slow_previous_one(env):
    player, events, pump, make = env
    a, b = make("a.m4a", 4, "-c:a", "aac"), make("b.mp3", 4)
    player.play(a, NowPlaying("A", "x", str(a)))
    player.play(b, NowPlaying("B", "x", str(b)))        # remplace A avant la fin de son décodage
    assert pump(lambda: player.state == PLAYING)
    time.sleep(0.5); pump(lambda: False, timeout=0.5)
    assert player.meta.title == "B"
    assert [p[0].title for k, p in events if k == "loaded"] == ["B"]


def test_errors_are_reported_not_raised(env, tmp_path):
    player, events, pump, make = env
    player.play(tmp_path / "absent.m4a", NowPlaying("x", "y", "z"))
    assert events[-1][0] == "missing" and events[-1][1].endswith("absent.m4a")    # 1.3.0-rc.3 (B20)
    bad = tmp_path / "bad.m4a"; bad.write_bytes(b"pas de l'audio")
    player.play(bad, NowPlaying("x", "y", str(bad)))
    assert pump(lambda: any(k == "error" for k, _ in events[1:]))
    assert player.state == STOPPED
    player.ffmpeg_location = str(tmp_path / "nowhere")
    old, shutil_which = shutil.which, shutil.which
    shutil.which = lambda *_a, **_k: None               # FFmpeg introuvable
    try:
        good = make("g.m4a", 1, "-c:a", "aac")
        n = len(events); player.play(good, NowPlaying("x", "y", str(good)))
        assert pump(lambda: any(k == "error" and "FFmpeg" in str(p) for k, p in events[n:]))
    finally:
        shutil.which = old
