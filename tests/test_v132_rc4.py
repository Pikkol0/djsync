"""1.3.2-rc.4 : freezes de la lecture (B50, test GRI-3 de la rc.3)."""
from __future__ import annotations

import logging
import types


# ------------------------------------------------------------------ B50 : détection de Rekordbox sans psutil
def test_windows_uses_one_snapshot_not_psutil_status(monkeypatch):
    import psutil

    from djsync.db import local_library as L

    monkeypatch.setattr(L, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(L, "_windows_process_names", lambda: ["System", "explorer.exe", "rekordbox.exe"])

    def boom(*_a, **_k):
        raise AssertionError("psutil must not be used on Windows when the snapshot works")

    monkeypatch.setattr(psutil, "process_iter", boom)
    assert L.rekordbox_running() is True
    monkeypatch.setattr(L, "_windows_process_names", lambda: ["System", "rekordboxAgent.exe"])
    assert L.rekordbox_running() is False


def test_windows_fallback_asks_names_only(monkeypatch):
    import psutil

    from djsync.db import local_library as L

    monkeypatch.setattr(L, "os", types.SimpleNamespace(name="nt"))

    def fail():
        raise OSError(5, "denied")

    monkeypatch.setattr(L, "_windows_process_names", fail)
    asked = []

    def fake_iter(attrs):
        asked.append(list(attrs))
        return [types.SimpleNamespace(info={"name": "rekordbox.exe"})]

    monkeypatch.setattr(psutil, "process_iter", fake_iter)
    assert L.rekordbox_running() is True
    assert asked == [["name"]]              # jamais « status » sous Windows (un relevé complet par processus)


def test_posix_still_skips_zombies(monkeypatch):
    import psutil

    from djsync.db import local_library as L

    monkeypatch.setattr(L, "os", types.SimpleNamespace(name="posix"))
    procs = [types.SimpleNamespace(info={"name": "rekordbox", "status": psutil.STATUS_ZOMBIE}),
             types.SimpleNamespace(info={"name": "bash", "status": "running"})]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: procs)
    assert L.rekordbox_running() is False


def test_real_process_list_is_quick():
    import time

    from djsync.db import local_library as L

    t0 = time.perf_counter()
    names = L._process_names()
    assert names and time.perf_counter() - t0 < 2.0


# ------------------------------------------------------------------ B50 : contrôle des clés lent noté au journal
def test_slow_drive_check_is_logged(caplog, monkeypatch):
    from djsync.ui import controller as C

    monkeypatch.setitem(C._slow_polls, "n", 0)
    with caplog.at_level(logging.INFO, logger=C.log.name):
        C._note_slow_poll(0.001, 0.002, 0.003, 0.001)
        assert "Slow drive check" not in caplog.text
        C._note_slow_poll(0.001, 0.002, 0.450, 0.001)
    assert "Slow drive check: 454 ms" in caplog.text and "Rekordbox 450" in caplog.text


# ------------------------------------------------------------------ B50 : empreintes ralenties pendant la lecture
def test_fingerprints_yield_only_while_playing_and_not_cached(tmp_path, monkeypatch):
    from djsync.analysis import fingerprint as F
    from djsync.ui.ctrl import library_ops as O

    audio = tmp_path / "a.m4a"
    audio.write_bytes(b"x" * 10)
    cache = tmp_path / "fp"
    assert F.fingerprint_cached(audio, cache) is False
    cache.mkdir()
    (cache / f"{F.file_key(audio)}.npy").write_bytes(b"")
    assert F.fingerprint_cached(audio, cache) is True
    assert F.fingerprint_cached(tmp_path / "missing.m4a", cache) is False

    slept = []
    monkeypatch.setattr(O.time, "sleep", lambda s: slept.append(s))
    ctrl = types.SimpleNamespace(player=types.SimpleNamespace(state="paused"))
    O.LibraryOpsMixin._yield_to_playback(ctrl)
    assert slept == []
    ctrl.player.state = "playing"
    O.LibraryOpsMixin._yield_to_playback(ctrl)
    assert slept == [O.PLAYBACK_YIELD_S]
