"""1.4.4 stable (B136, C241, C242) : Grille et cues en deux onglets (Tempo, Cues) qui ne bougent plus, trois panneaux
côte à côte, BPM écrit dans la bande des passages, type déduit des passages, analyse selon la forme, deux kicks.
    pytest -q tests/test_v144_b136.py
"""
from __future__ import annotations

import types

import pytest

from djsync.analysis import grid as G
from djsync.analysis import tempo_profile as TP
from djsync.ui import tempo_segments as TS

from .qt_util import pump
from .test_v122 import demo, usb  # noqa: F401  (fixtures)
from .test_v144_rc1_lot2_c221 import _c221_editor


def test_c242_deduced_kind_and_c241_band_text():
    step = TS.seg(0, 128.0, 1)
    assert TS.deduced_kind([step]) == "none"
    assert TS.deduced_kind([step, TS.seg(60000, 140.0, 1, "tempo")]) == "switch"
    ramp = TS.seg(60000, 128.0, 1, "tempo", shape="ramp", end=140.0, origin="main")
    assert TS.deduced_kind([step, ramp]) == "ramp"

    class FM:
        def horizontalAdvance(self, text):               # noqa: N802
            return 7 * len(text)

    assert TS.band_text(step, 200, FM()) == "128.00"
    assert TS.band_text(step, 30, FM()) == "128"
    assert TS.band_text(ramp, 200, FM()) == "128.0 → 140.0"
    assert TS.band_text(ramp, 70, FM()) == "128→140"
    assert TS.band_text(ramp, 20, FM()) == ""
    assert TS.band_text(TS.seg(0, 128.0, 1, "tempo", shape="free", origin="main"), 300, FM()) == ""


def test_c242_two_kicks_anywhere_further():
    far = G.from_two_beats(500.0, 500.0 + 16 * 60000.0 / 131.0, 128.0, 240000)
    assert far is not None and far[2] == 16 and far[1] == pytest.approx(131.0, abs=0.01)


def test_b136_two_tabs_that_do_not_move(demo, tmp_path):  # noqa: F811
    ed, _track = _c221_editor(demo, tmp_path)
    try:
        assert list(ed.tab_btns) == ["tempo", "cues"]
        ed.resize(1280, 900)
        pump(demo, 0.3)
        pos = {k: b.geometry() for k, b in ed.tab_btns.items()}
        tools = ed.seg_tools
        ed._move_cursor(30100.0)
        tools.add("tempo")                                               # deux passages : « Appliquer à » visible
        ed.show_tab("tempo")
        pump(demo, 0.2)
        assert tools.scope_box.isVisibleTo(ed)
        assert {k: b.geometry() for k, b in ed.tab_btns.items()} == pos
        ed.show_tab("cues")
        pump(demo, 0.2)
        assert not tools.scope_box.isVisibleTo(ed)
        assert {k: b.geometry() for k, b in ed.tab_btns.items()} == pos  # les onglets ne bougent pas
        assert tools.scope_box.sizePolicy().retainSizeWhenHidden()
        demo.ctrl.settings.grid_tab = "grid"                             # ancien réglage : Tempo
        ed.show_tab("grid", remember=False)
        assert ed.current_tab == "tempo"
        # trois panneaux côte à côte à 1280 px
        z = ed.tempo_zones
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QResizeEvent

        z.resize(1018, 400)
        z.resizeEvent(QResizeEvent(QSize(1018, 400), QSize(1018, 400)))
        assert z.box.direction() == z.box.Direction.LeftToRight
        # 2e kick grisé tant que le 1er n'est pas posé ; le 1er se replace
        assert not ed.kick2_btn.isEnabled() and ed.kick_btn.isEnabled()
        ed._move_cursor(1000.0)
        ed._kick_first()
        ed._move_cursor(2000.0)
        ed._kick_first()
        assert ed._kick1 == 2000.0 and ed.kick2_btn.isEnabled()
    finally:
        ed._closed = True
        ed.deleteLater()
        TP.use_store(None)


def test_c242_analysis_follows_the_shape(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.analysis import segment_tempo as ST

    ed, _track = _c221_editor(demo, tmp_path)
    calls = []

    def fake(path, lo, hi, bpm, nb, ffmpeg, allow_ramp=True):
        calls.append(allow_ramp)
        return types.SimpleNamespace(shape="step", bpm=bpm, bpm_end=bpm, ok=True, note="short")

    try:
        tools = ed.seg_tools
        monkeypatch.setattr(ST, "analyze_file", fake)
        monkeypatch.setattr(tools, "_audio_path", lambda: __file__)
        tools.analyse(False)                                             # palier : analysé en palier
        assert pump(demo, 10, lambda: tools._analysing == 0) and calls[-1] is False
        tools.analyse(False, mode="auto")                                # forme libre : DJSync choisit
        assert pump(demo, 10, lambda: tools._analysing == 0) and calls[-1] is True
        assert tools.analyse_menu.actions() and "(" in tools.analyse_btn.text()
    finally:
        ed._closed = True
        ed.deleteLater()
        TP.use_store(None)
