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
