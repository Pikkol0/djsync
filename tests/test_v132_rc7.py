"""1.3.2 (B53) : molette = zoom sur la forme d'onde de Grille et cues ; Maj / horizontal = défiler."""
from __future__ import annotations

import types

from PySide6.QtCore import Qt


def _event(dx=0, dy=0, mods=Qt.NoModifier):
    return types.SimpleNamespace(angleDelta=lambda: types.SimpleNamespace(x=lambda: dx, y=lambda: dy),
                                 modifiers=lambda: mods)


def _canvas():
    calls = []
    ed = types.SimpleNamespace(zoom=lambda s: calls.append(("zoom", s)), pan=lambda f: calls.append(("pan", f)))
    return types.SimpleNamespace(ed=ed), calls


def test_wheel_zooms_and_shift_or_horizontal_scrolls():
    from djsync.ui.grid_editor import GridCanvas

    c, calls = _canvas()
    GridCanvas.wheelEvent(c, _event(dy=120))
    GridCanvas.wheelEvent(c, _event(dy=-120))
    GridCanvas.wheelEvent(c, _event(dy=120, mods=Qt.ControlModifier))
    assert calls == [("zoom", -1), ("zoom", 1), ("zoom", -1)]
    calls.clear()
    GridCanvas.wheelEvent(c, _event(dy=120, mods=Qt.ShiftModifier))
    GridCanvas.wheelEvent(c, _event(dx=-120))
    assert [k for k, _ in calls] == ["pan", "pan"] and calls[0][1] < 0 < calls[1][1]


def test_touchpad_small_steps_add_up_to_one_zoom_step():
    from djsync.ui.grid_editor import GridCanvas

    c, calls = _canvas()
    for _ in range(5):
        GridCanvas.wheelEvent(c, _event(dy=30))
    assert calls == [("zoom", -1)]                      # 150 cumulés : un seul palier


def test_wider_zoom_range():
    from djsync.ui.grid_editor import VIEW_CHOICES, view_label

    assert VIEW_CHOICES[0] == 0.5 and VIEW_CHOICES[-1] == 120
    assert view_label(0.5) == "0.5 s" and view_label(4) == "4 s"


def test_b52_computer_playlists_use_their_own_queue():
    from djsync.ui.ctrl.library_ops import _read_pool
    from djsync.ui.runner import _POOLS

    assert "ui_db" in _POOLS
    assert _read_pool(types.SimpleNamespace(is_local=True)) == "ui_db"
    assert _read_pool(types.SimpleNamespace()) == "db"


def test_b54_rekordbox_open_refuses_before_downloading(monkeypatch):
    from djsync.ui.ctrl.downloads import DownloadsMixin

    calls = []
    lib = types.SimpleNamespace(ensure_writable=lambda: (_ for _ in ()).throw(RuntimeError("Close Rekordbox first")))
    job = types.SimpleNamespace(library=lib, track=types.SimpleNamespace(video_id="x", title="T", source="youtube"), status="", percent=0,
                                message="")
    ctrl = types.SimpleNamespace(
        settings=types.SimpleNamespace(fetch_metadata=False),
        service=types.SimpleNamespace(download=lambda *a, **k: calls.append("download")),
        dispatcher=types.SimpleNamespace(post=lambda *a, **k: None), engine_failure=lambda *a: None,
        _job_changed=lambda *a: None)
    DownloadsMixin._run_job(ctrl, job)
    assert calls == [] and job.status == "error" and "Rekordbox" in job.message


def test_release_notes_one_bullet_per_section():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("rn", Path(__file__).parents[1] / "packaging" / "release_notes.py")
    rn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rn)
    out = rn.as_list("**Library**: a; b. **Search**: c. **Also**: d")
    assert out.splitlines() == ["- **Library**: a; b.", "- **Search**: c.", "- **Also**: d."]
    assert rn.as_list("plain text") == "plain text"
