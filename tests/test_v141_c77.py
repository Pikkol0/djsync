"""1.4.1 (C77) : un seul type de forme d'onde (Bleu, RGB, 3 bandes), lu dans les fichiers d'analyse."""
from __future__ import annotations

import struct

import pytest

from djsync.analysis import anlz


def _ext_with(pwv3: bytes, pwv5: bytes) -> bytes:
    def tag(code: bytes, body: bytes) -> bytes:
        return code + struct.pack(">II", 24, 24 + len(body)) + struct.pack(">III", 1, len(body) // (2 if code == b"PWV5" else 1), 0) + body
    return anlz._file([tag(b"PWV3", pwv3), tag(b"PWV5", pwv5)])


def test_detail_and_overview_follow_the_style():
    pwv3 = bytes([(7 << 5) | 31, (0 << 5) | 10])                      # blanc et haut, puis bleu et bas
    pwv5 = struct.pack(">H", (7 << 13) | (0 << 10) | (0 << 7) | (31 << 2))   # rouge, haut
    ext = _ext_with(pwv3, pwv5)
    blue = anlz.read_detail(ext, "blue")
    assert len(blue) == 2 and blue[0] == (1.0, anlz.blue_colour(7)) and blue[1][1] == anlz.blue_colour(0)
    assert anlz.read_detail(ext, "rgb") == [(1.0, "#FC0000")]
    assert anlz.read_detail(ext) == anlz.read_detail(ext, "rgb")         # par défaut : comme avant
    two = anlz._file([b"PWV6" + struct.pack(">II", 20, 20 + 6) + struct.pack(">II", 3, 2) + bytes([100, 10, 5, 5, 10, 120])])
    dat = anlz._file([b"PWAV" + struct.pack(">II", 20, 21) + struct.pack(">II", 1, 0x10000) + bytes([(3 << 5) | 31])])
    assert [c for _h, c in anlz.read_overview(dat, None, "3band", two)] == ["#1F6FE5", "#F6EAD2"]   # basses, aigus
    assert anlz.read_overview(dat, None, "blue", two) == [(1.0, anlz.blue_colour(3))]
    assert anlz.read_overview(dat, None, "rgb", two)                     # pas de PWV4 : un autre aperçu


pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v024 import demo_grid  # noqa: E402,F401


def _open_editor(demo):  # noqa: F811
    from djsync.ui.grid_editor import GridEditor

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total > 0)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    demo.open_grid_editor(target)
    ed = demo.grid_editor
    assert isinstance(ed, GridEditor) and pump(demo, 6, lambda: bool(ed.beats))
    return ed


def test_one_look_from_the_start_and_applied_without_restart(demo_grid):  # noqa: F811
    demo = demo_grid
    ctrl = demo.ctrl
    ctrl.settings.waveform_style = "3band"
    ed = _open_editor(demo)
    assert ed.wave is not None                                          # 3 bandes tout de suite, jamais RGB d'abord
    ctrl.settings.waveform_style = "rgb"
    ctrl._emit("waveform_style")
    assert pump(demo, 4, lambda: ed.wave is None and ed.detail)
    assert ed._wave_state == "ready"
    ed.grab()
    ctrl.settings.waveform_style = "blue"
    ctrl._emit("waveform_style")
    from djsync.analysis.anlz import blue_colour

    blues = {blue_colour(k) for k in range(8)}
    assert pump(demo, 4, lambda: ed.detail and all(c in blues for _h, c in ed.detail[:200]))
    ed.grab()
    ctrl.settings.waveform_style = "3band"
    ctrl._emit("waveform_style")
    assert pump(demo, 4, lambda: ed.wave is not None)
    ed.close()
    assert not demo.errors
