"""1.4.4-rc.2 : tests ciblés des fiches B131 + C237 (passages éditables, onglets), C238 (thème × luminosité), B134
(export.pdb gardé ouvert), C240 (disque absent), B133 (tailles), B132 (surlignage), B130 (champ de lien),
B118 (cellules du tableau), C239 (bouton Transférer).
    pytest -q tests/test_v144_rc2.py
"""
from __future__ import annotations

import numpy as np
import pytest

from djsync.analysis import grid as G
from djsync.analysis import segment_tempo as ST
from djsync.analysis import tempo_profile as TP
from djsync.ui import tempo_grids as TG
from djsync.ui import tempo_segments as TS

from .test_v122 import demo, usb  # noqa: F401  (fixtures)
from .test_v144_rc1_lot2_c221 import _c221_editor

SR = 22050


def _clicks(times, dur):
    """Kick grave sur le 1er temps de chaque mesure, clic aigu sur les autres."""
    x = np.zeros(int(dur * SR), np.float32)
    n = int(0.05 * SR)
    env = np.exp(-np.arange(n) / (0.01 * SR))
    for i, t in enumerate(times):
        a = int(t * SR)
        if a + n >= x.size:
            break
        f = 60 if i % 4 == 0 else 1000
        x[a:a + n] += (np.sin(2 * np.pi * f * np.arange(n) / SR) * env * (1.0 if i % 4 == 0 else 0.5)).astype(np.float32)
    return x


# ------------------------------------------------------------------ B131 : calculs sans Qt
def test_b131_ramp_beats_are_integrated_and_bounded():
    times = TP.ramp_times(0.5, 60.5, 120.0, 132.0)
    gaps = np.diff(times)
    assert times[0] == 0.5 and times[-1] < 60.5
    assert 60 / gaps[0] == pytest.approx(120.0, abs=0.6) and 60 / gaps[-1] == pytest.approx(132.0, abs=0.6)
    assert np.all(np.abs(np.diff(gaps) / gaps[:-1]) < 0.03)               # jamais plus de 3 % d'un temps au suivant
    beats = TP.marks_beats([(0.5, 120.0, 0.5, "", "ramp", 132.0, "main")], 61.0)
    assert [b[0] for b in beats[:5]] == [1, 2, 3, 4, 1]
    assert beats[0][2] == pytest.approx(120.0, abs=0.6) and beats[-1][2] == pytest.approx(132.0, abs=0.6)


def test_b131_paliers_give_the_c221_grid_and_free_continues():
    marks = [(0.5, 120.0, 0.5, ""), (30.5, 140.0, 30.5, "tempo")]
    a = TP.marks_beats(marks, 60.0)
    b = TP.section_beats([(0.5, 120.0, 0.5), (30.5, 140.0, 30.5)], 60.0)
    assert [(n, t) for n, t, _bpm in a] == b
    free = TP.marks_beats([(0.5, 120.0, 0.5, ""), (30.5, 0.0 + 1, 30.5, "tempo", "free", 1.0, "main")], 60.0)
    assert {round(x[2]) for x in free} == {120}                        # libre : le tempo d'avant continue
    nums = [x[0] for x in free]
    assert all(((nums[i] % 4) + 1) == nums[i + 1] for i in range(len(nums) - 1))


def test_b131_old_tempo_json_format_is_read(tmp_path):
    TP.use_store(tmp_path / "tempo.json")
    try:
        f = tmp_path / "Set.mp3"
        f.write_bytes(b"x" * 4321)
        TP.remember(f, TP.TempoProfile("switch", 122, 140))
        assert TP.set_marks("Set.mp3", 4321, [(0.5, 122.0, 0.5, ""), (30.0, 140.0, 30.0, "tempo")])
        p = TP.known(f)
        assert p.marks == [(0.5, 122.0, 0.5, ""), (30.0, 140.0, 30.0, "tempo")]       # 4 valeurs : palier
        assert [TP.mark_origin(m) for m in p.marks] == ["auto", "main"]
        # un seul passage, rampe à la main : gardé (7 valeurs) et la réanalyse le garde
        assert TP.set_marks("Set.mp3", 4321, [(0.5, 120.0, 0.5, "", "ramp", 130.0, "main")])
        assert TP.known(f).marks == [(0.5, 120.0, 0.5, "", "ramp", 130.0, "main")]
        TP.remember(f, TP.TempoProfile("ramp", 120, 130))
        assert TP.known(f).marks and TP.has_manual(TP.known(f))
        # passages de l'analyse seulement : refaits à la réanalyse
        assert TP.set_marks("Set.mp3", 4321, [(0.5, 120.0, 0.5, "", "ramp", 130.0, "auto"),
                                              (40.0, 130.0, 40.0, "", "step", 130.0, "auto")])
        TP.remember(f, TP.TempoProfile("ramp", 120, 130))
        assert TP.known(f).marks == []
    finally:
        TP.use_store(None)


def test_b131_scope_this_passage_for_the_grid_tools():
    secs = [(0.5, 122.0, 0.5), (60.5, 140.0, 60.5)]
    beats = TG.split_beats(secs, 120000)
    segs = TS.segments_of(beats)
    lo, hi = TS.bounds(segs, 1, 120000)
    for new in (G.shift(beats, 10, 120000), G.scale_tempo(beats, 2.0, 200, 120000),
                G.set_bpm(beats, 141.0, 200, 120000), G.set_downbeat(beats, 200),
                G.shift_half_beat(beats, 200, 120000)):
        out = TS.splice(beats, new, lo, hi)
        before = [b for b in out if b[2] < lo - 300]
        assert before == [b for b in beats if b[2] < lo - 300]              # 1er passage intact
        assert {b[1] for b in before} == {12200}
        gaps = np.diff([b[2] for b in out])
        assert gaps.min() > 0                                               # aucun temps en double
    resegmented = TS.resegment(segs, TS.splice(beats, G.set_bpm(beats, 141.0, 200, 120000), lo, hi), 1)
    assert resegmented[0][1] == 122.0 and resegmented[1][1] == pytest.approx(141.0, abs=0.01)
    assert TS.origin_of(resegmented[1]) == "main"


def test_b131_add_mark_splits_a_ramp_continuously():
    segs = [TS.seg(500, 120.0, 1, "", "ramp", 132.0, "main")]
    beats = TS.build(segs, 60000)
    segs2, k = TS.add_mark(segs, beats, 30000, "tempo")
    assert k == 1 and TS.shape_of(segs2[0]) == TS.shape_of(segs2[1]) == "ramp"
    assert TS.end_of(segs2[0]) == segs2[1][1] and TS.end_of(segs2[1]) == 132.0
    assert TS.to_marks(segs2)[1][4:] == ("ramp", 132.0, "main")


# ------------------------------------------------------------------ B131 : analyse d'un passage (sons synthétiques)
def test_b131_passage_analysis_step_ramp_octave_and_weak():
    dur = 40.0
    x = _clicks(np.arange(0.3, dur, 60 / 128), dur)
    r = ST.analyze(x, SR, 0.0, dur, 126.0)
    assert r.shape == "step" and r.bpm == pytest.approx(128.0, abs=0.05) and abs(r.first_ms - 300) <= 15
    assert r.number == 1 and r.ok
    ramp = _clicks(TP.ramp_times(0.2, dur, 120.0, 132.0), dur)
    r = ST.analyze(ramp, SR, 0.0, dur, 125.0)
    assert r.shape == "ramp" and r.bpm == pytest.approx(120.0, abs=1.0) and r.bpm_end == pytest.approx(132.0, abs=1.0)
    assert ST.analyze(x, SR, 0.0, dur, 126.0, neighbours=[64.0]).note == "octave"     # ×2 : refusé
    assert ST.analyze(np.zeros(int(dur * SR), np.float32), SR, 0.0, dur, 126.0).shape == "free"
    assert ST.analyze(x[: 5 * SR], SR, 0.0, 5.0, 126.0).note == "short"               # moins de 8 mesures


# ------------------------------------------------------------------ B131 + C237 : interface
def test_c237_tabs_band_and_single_back(demo, tmp_path):  # noqa: F811
    from PySide6.QtWidgets import QPushButton

    from djsync.i18n import t

    ed, _track = _c221_editor(demo, tmp_path)
    try:
        tools = ed.seg_tools
        assert set(ed.tab_btns) == {"grid", "tempo", "cues"}
        ed.show_tab("cues")
        assert ed.zones.currentWidget() is ed._tab_pages["cues"] and demo.ctrl.settings.grid_tab == "cues"
        ed.show_tab("tempo")
        assert demo.ctrl.settings.grid_tab == "tempo"
        # tempo constant : pas de bande, pas de « Appliquer à », pas de tableau
        assert not tools.band.isVisibleTo(ed) and not tools.scope_box.isVisibleTo(ed)
        backs = [b for b in ed.findChildren(QPushButton) if b.text() == t("grid.back")]
        assert len(backs) == 1                                               # un seul Retour (en haut)
        # deux passages : bande fine, clic à l'endroit exact
        ed._move_cursor(60000.0)
        tools.add("tempo")
        ed._move_cursor(80000.0)
        tools.bpm_entry.setText("140")
        tools.apply_bpm()
        assert tools.multi() and tools.band.isVisibleTo(ed) and tools.band.height() <= 12
        assert tools.table.topLevelItemCount() == 2
        tools.band.resize(1200, 10)
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(300, 5), QPointF(300, 5), Qt.LeftButton,
                         Qt.LeftButton, Qt.NoModifier)
        tools.band.mousePressEvent(ev)
        assert ed.cursor_ms == pytest.approx(30000, abs=150)               # 300 / 1200 du son, pas un début de passage
        assert "140" in tools.band_tip(90000)
    finally:
        ed._closed = True
        ed.deleteLater()
        TP.use_store(None)


def test_b131_tools_change_only_the_passage_under_the_cursor(demo, tmp_path):  # noqa: F811
    beats = TG.split_beats([(0.5, 122.0, 0.5), (60.5, 140.0, 60.5)], 120000)
    ed, _track = _c221_editor(demo, tmp_path, beats)
    try:
        tools = ed.seg_tools
        assert len(tools.segs) == 2
        ed._move_cursor(90000.0)
        ed.selected = G.nearest(ed.beats, 90000)
        ed.bpm_entry.setText("141")
        ed._apply_bpm()
        assert {b[1] for b in ed.beats if b[2] < 60000} == {12200}          # 1er passage intact (beatswitch gardé)
        assert {b[1] for b in ed.beats if b[2] > 61000} == {14100}
        assert len(tools.segs) == 2 and tools.segs[1][1] == pytest.approx(141.0, abs=0.01)
        # tout le son : décalage de tout, bornes recalées
        tools.set_scope("all")
        mark = tools.segs[1][0]
        ed._shift(10)
        assert any(b[2] == 510 for b in ed.beats) and len(tools.segs) == 2
        assert tools.segs[1][0] == mark + 10
        # forme : rampe à la main, grille recalculée
        tools.set_scope("passage")
        ed._move_cursor(90000.0)
        tools.shape_menu.setCurrentIndex(tools.shape_menu.findData("ramp"))
        assert TS.shape_of(tools.segs[1]) == "ramp" and not tools.end_entry.isHidden()
        assert len({b[1] for b in ed.beats if b[2] > 62000}) > 3
        # type « Tempo stable » : grille fixe
        tools.kind_menu.setCurrentIndex(tools.kind_menu.findData("none"))
        assert len({b[1] for b in ed.beats}) == 1
    finally:
        ed._closed = True
        ed.deleteLater()
        TP.use_store(None)


# ------------------------------------------------------------------ C238 : thème × luminosité
def test_c238_brightness_is_separate_and_migrated(tmp_path):
    from djsync.settings import Settings
    from djsync.ui import theme
    from djsync.ui.palettes import THEMES

    assert len(theme.TINTS) >= 14 and theme.BRIGHTNESSES == ("dark", "oled", "light")
    assert len(THEMES) >= 10 and {v[1] for v in THEMES.values()} == {"dark", "oled", "light"}
    try:
        theme.apply_background("navy", "oled")
        assert theme.BG == "#000000" and theme.CURRENT_BACKGROUND == "navy"
        theme.apply_background("navy", "light")
        assert theme.is_bright() and theme.CURRENT_BRIGHTNESS == "light"
        theme.apply_background("bright")                                      # ancien fond
        assert (theme.CURRENT_BACKGROUND, theme.CURRENT_BRIGHTNESS) == ("default", "light")
    finally:
        theme.apply_background("default", "dark")
    s = Settings(background="oled")
    s.normalize()
    assert (s.background, s.brightness) == ("default", "oled")


def test_c238_settings_brightness_menu_rebuilds(demo):  # noqa: F811
    from djsync.ui import theme

    from .qt_util import pump

    demo.show_view("settings")
    view = demo.views["settings"]
    try:
        view.light_menu.setCurrentText(view._light_labels["light"])
        pump(demo, 0.3)
        assert demo.ctrl.settings.brightness == "light" and theme.CURRENT_BRIGHTNESS == "light"
        assert not demo.errors
    finally:
        demo.ctrl.settings.brightness = "dark"
        demo.ctrl._emit("restyle")
        pump(demo, 0.2)


# ------------------------------------------------------------------ B134 : export.pdb gardé ouvert
def test_b134_locked_pdb_is_late_and_written_again(usb, monkeypatch):  # noqa: F811
    from djsync.db import pdb as pdbmod
    from djsync.db.pdb import lock

    from types import SimpleNamespace as NS

    lib = _open_usb(usb)
    try:
        monkeypatch.setattr(lib, "_pdb_enabled", lambda: True)
        monkeypatch.setattr(lib, "_pdb_journal", lambda: NS(marks=[]))
        monkeypatch.setattr(lib, "_pdb_reconcile", lambda _j: (NS(), NS(empty=True)))
        monkeypatch.setattr(lock, "pdb_locked", lambda _p: True)
        lib.pdb_retry_s = 0.2
        lib._pdb_dirty = True
        lib._pdb_flush()
        assert lib.pdb_late and lib.pdb_state == "stale" and lib._pdb_retry_timer is not None
        monkeypatch.setattr(lock, "pdb_locked", lambda _p: False)
        import time

        deadline = time.monotonic() + 5
        while lib.pdb_late and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not lib.pdb_late                                             # réécrit tout seul
        _ = pdbmod
    finally:
        lib.close()


def test_b134_lock_error_and_probe():
    from djsync.db.pdb.lock import is_lock_error, pdb_locked

    assert is_lock_error(PermissionError(13, "Access is denied"))
    err = OSError("x")
    err.winerror = 32
    assert is_lock_error(err)
    assert not is_lock_error(ValueError("bad page"))
    assert not pdb_locked("/nonexistent/export.pdb")


def _open_usb(usb):  # noqa: F811
    from djsync.db import RekordboxUsbLibrary, UsbDrive

    root = usb if not isinstance(usb, tuple) else usb[0]
    return RekordboxUsbLibrary(UsbDrive(root=root, label="T"), analyze=False).connect()


# ------------------------------------------------------------------ C240 : disque absent
def test_c240_missing_disk_is_a_line_not_a_full_bar(tmp_path):
    from djsync.core import space

    bars = space.computer_disks({}, {"Q:\\": 5 * 1024 ** 3, str(tmp_path): 1024}, tracks_by_disk={"Q:\\": 12})
    absent = [b for b in bars if b.absent]
    assert len(absent) == 1 and absent[0].title == "Q:\\" and absent[0].tracks == 12
    assert absent[0].usage.total == 0 and absent[0].usage.parts["music"] == 5 * 1024 ** 3


# ------------------------------------------------------------------ B133 : une seule fonction de taille
def test_b133_one_size_function_and_labels():
    from djsync.i18n import set_language, t
    from djsync.ui.backups_dialog import _size
    from djsync.ui.p2p_panel import human_bytes
    from djsync.ui.views.common import human_size

    set_language("en")
    try:
        assert _size(16 * 1024 * 1024) == human_size(16 * 1024 * 1024) == human_bytes(16 * 1024 * 1024) == "16.0 MB"
        assert t("space.backups_usb") != t("space.backups_pc")
        assert "computer" in t("space.fp_backups", size="1 MB")
    finally:
        set_language("en")


# ------------------------------------------------------------------ B132 : flash() s'efface toujours
def test_b132_flash_twice_still_clears(demo):  # noqa: F811
    from PySide6.QtWidgets import QLabel

    from djsync.ui.widgets import flash

    from .qt_util import pump

    w = QLabel("x", demo)
    w.setStyleSheet("color: red;")
    flash(w, ms=150)
    pump(demo, 0.05)
    flash(w, ms=150)                                                  # retapé avant la fin
    assert pump(demo, 2, lambda: w.property("flashed") is False)
    assert w.styleSheet() == "color: red;"


# ------------------------------------------------------------------ B130 : champ « Lien ou playlist »
@pytest.mark.parametrize("zoom", [100, 150, 200])
def test_b130_link_field_fits_its_font(demo, zoom):  # noqa: F811
    from PySide6.QtGui import QFont

    from djsync.ui.widgets import LinkOrListEdit

    e = LinkOrListEdit("Paste a link\nor type a list")
    f = QFont(e.font())
    f.setPointSizeF(10.0 * zoom / 100)
    e.setFont(f)
    e.show()
    line = e._line_height()
    assert e.wanted_lines() == 2 and e.height() >= 2 * line
    assert e.verticalScrollBarPolicy().name.endswith("AlwaysOff")
    e.setText("\n".join(f"Artist {i} - Title" for i in range(9)))
    assert e.wanted_lines() == 6 and e.verticalScrollBarPolicy().name.endswith("AsNeeded")
    e.close()


# ------------------------------------------------------------------ B118 et C239
def test_b118_no_item_rule_and_cells_painted(demo):  # noqa: F811
    from djsync.ui import theme

    assert "QTableView::item" not in theme.stylesheet()
    demo.show_view("library")
    lib = demo.views["library"]
    table = lib.table
    table.resize(900, 400)
    assert not table.grab().isNull()                                               # cellules peintes sans erreur
    assert lib.transfer_btn.objectName() == "lib_transfer"                         # C239
    assert not demo.errors
