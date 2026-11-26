"""1.4.4-rc.1 (lot 2) : C221 : tempo variable dans Grille et cues (passages et repères éditables, BPM au curseur,
type corrigé à la main gardé à la réanalyse, repère « nouveau son » = mémoire nommée) et réglage d'analyse
« Dynamique / Classique » (« Jamais » migré en « Classique »).
    pytest -q tests/test_v144_rc1_lot2_c221.py
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from djsync.analysis import grid as G
from djsync.analysis import tempo_profile
from djsync.ui import tempo_grids as TG
from djsync.ui import tempo_segments as TS

from .test_v122 import demo, usb  # noqa: F401  (fixtures)

_C221_SECS = [(0.3, 122.0, 0.3), (60.2, 140.0, 60.2)]


def _c221_store(tmp_path, name="Set.mp3", size=4321):
    tempo_profile.use_store(tmp_path / "tempo.json")
    f = tmp_path / name
    f.write_bytes(b"x" * size)
    return f


# ------------------------------------------------------------------ passages (sans interface)
def test_c221_segments_and_their_bpm():
    beats = TG.split_beats(_C221_SECS, 120000)
    segs = TS.segments_of(beats)
    assert [(s[1], s[3]) for s in segs] == [(122.0, ""), (140.0, "tempo")]
    assert segs[1][0] == 60200 and segs[1][2] == 1
    rebuilt = TS.build(segs, 120000)
    assert len(rebuilt) == len(beats)
    assert max(abs(a[2] - b[2]) for a, b in zip(rebuilt, beats)) <= 1 and [b[1] for b in rebuilt] == [b[1] for b in beats]
    # grille fixe : un seul passage ; grille de live (tempo qui bouge à chaque temps) : un seul aussi, BPM médian
    fixed = G.extend([(1, 12800, 500)], 60000)
    assert TS.segments_of(fixed) == [(fixed[0][2], 128.0, fixed[0][0], "")]
    live = [((i % 4) + 1, 12000 + (i % 7) * 10, 500 + i * 500) for i in range(100)]
    assert len(TS.segments_of(live)) == 1


def test_c221_bpm_at_the_cursor():
    beats = TG.split_beats(_C221_SECS, 120000)
    times = [b[2] for b in beats]
    assert TS.tempo_at(times, beats, 10000) == 122.0
    assert TS.tempo_at(times, beats, 60199) == 122.0
    assert TS.tempo_at(times, beats, 60200) == 140.0
    assert TS.tempo_at(times, beats, 0) == 122.0                  # avant le 1er temps : le 1er tempo
    assert TS.tempo_at(times, beats, 999999) == 140.0


def test_c221_add_move_remove_marker_recomputes_the_grid():
    beats = G.extend([(1, 12800, 500)], 120000)
    segs = TS.segments_of(beats)
    segs, k = TS.add_mark(segs, beats, 30100, "tempo")
    assert k == 1 and segs[1][3] == "tempo"
    at = beats[G.nearest(beats, 30100)]
    assert segs[1][0] == at[2] and segs[1][2] == at[0]           # calé sur un temps, numéro gardé
    assert TS.layout(segs) == TS.layout(TS.segments_of(beats))   # même tempo : la grille ne bouge pas
    segs = TS.set_segment_bpm(segs, 1, 140.0)
    grid = TS.build(segs, 120000)
    assert {b[1] for b in grid} == {12800, 14000}
    switch = next(i for i, b in enumerate(grid) if b[1] == 14000)
    assert grid[switch][2] == at[2] and grid[switch][0] == at[0]
    assert all(b2[2] > b1[2] for b1, b2 in zip(grid, grid[1:]))
    before_ms = [b[2] for b in beats if b[2] < at[2]]                     # avant : la grille d'origine (±1 ms)
    assert len(grid[:switch]) == len(before_ms) and max(abs(b[2] - m) for b, m in zip(grid, before_ms)) <= 1
    # déplacer : vers l'arrière, sur les temps du passage à 140 prolongés ; vers l'avant, sur ceux à 128
    targets = TS.move_targets(segs, grid, 1, 120000)
    ms = [a for a, _n in targets]
    assert ms == sorted(ms) and at[2] in ms and all(beats[0][2] < a < 120000 for a in ms)
    before = [tg for tg in targets if tg[0] < at[2]][-1]
    assert abs((at[2] - before[0]) - 60000 / 140) <= 1
    after = [tg for tg in targets if tg[0] > at[2]][0]
    assert abs((after[0] - at[2]) - 60000 / 128) <= 1
    moved = TS.move_mark(segs, 1, after)
    grid2 = TS.build(moved, 120000)
    assert next(b for b in grid2 if b[1] == 14000)[2] == after[0]
    # supprimer : de nouveau un seul tempo
    gone = TS.remove_mark(moved, 1)
    assert len(gone) == 1 and {b[1] for b in TS.build(gone, 120000)} == {12800}
    # 1er passage : BPM corrigé, calé sur le temps sélectionné
    sel = beats[40]
    one = TS.set_segment_bpm(TS.segments_of(beats), 0, 127.0, (float(sel[2]), sel[0]))
    g3 = TS.build(one, 120000)
    assert any(abs(b[2] - sel[2]) <= 1 and b[0] == sel[0] for b in g3) and {b[1] for b in g3} == {12700}
    # pas de repère sur le tout premier temps
    assert TS.add_mark(TS.segments_of(beats), beats, 0, "tempo")[1] is None


# ------------------------------------------------------------------ registre tempo.json
def test_c221_type_correction_is_kept_at_reanalysis(tmp_path):
    f = _c221_store(tmp_path)
    try:
        tempo_profile.remember(f, tempo_profile.TempoProfile("switch", 122, 140, 20.0))
        assert tempo_profile.set_kind("set.MP3", 4321, "live")
        got = tempo_profile.known(f)
        assert (got.kind, got.user_kind, got.detected) == ("live", "live", "switch")
        tempo_profile.use_store(tmp_path / "tempo.json")               # relu depuis le fichier
        tempo_profile.remember(f, tempo_profile.TempoProfile("ramp", 120, 126, 20.0))   # réanalyse
        got = tempo_profile.known(f)
        assert (got.kind, got.user_kind, got.detected) == ("live", "live", "ramp")
        track = NS(path=str(f), file_size=4321, is_analysed=True)
        assert TG.kind_text(TG.profile_of(track)).startswith(TS_t("grid.seg_kind_live"))
        # « tempo stable » : plus signalé, et la réanalyse garde une grille fixe
        assert TG.TempoGridService.set_kind(track, "none")
        got = tempo_profile.known(f)
        assert got.kind == "" and not got.changes and tempo_profile.grid_mode_for(f) == "never"
        assert TG.TempoGridService.set_kind(track, "")                # « Automatique » : celui de l'analyse
        assert tempo_profile.known(f).kind == "ramp"
        # formats : l'ancien (B125, 10 valeurs) se lit ; le nouveau garde les 10 premières à leur place
        old = ["switch", 122, 140, 20, 0, 1, [[0.3, 122.0, 0.3]], "", 1, 12.5]
        p = tempo_profile.TempoProfile.from_list(old)
        assert p.user_kind == "" and p.detected == "switch" and p.marks == [] and p.downbeat_at == 12.5
        new = p.to_list()
        assert new[:10] == [*old[:3], 20, 0, 1, [[0.3, 122.0, 0.3]], "", 1, 12.5] and len(new) == 13
        assert not tempo_profile.set_kind("unknown.mp3", 12, "live")
    finally:
        tempo_profile.use_store(None)


def test_c221_manual_marks_are_kept_and_rebuild_the_grid_at_reanalysis(tmp_path):
    from djsync.analysis.tempo import BeatGrid

    f = _c221_store(tmp_path)
    try:
        tempo_profile.remember(f, tempo_profile.TempoProfile())
        marks = [(0.5, 128.0, 0.5, ""), (30.5, 140.0, 30.5, "sound")]
        assert tempo_profile.set_marks("Set.mp3", 4321, marks)
        tempo_profile.remember(f, tempo_profile.TempoProfile())        # réanalyse : les repères restent
        assert tempo_profile.known(f).marks == marks
        grid = BeatGrid(bpm=128.0, beats=[(1, 0.5), (2, 0.97)], profile=tempo_profile.TempoProfile())
        assert tempo_profile.apply_manual(f, grid, 60.0)
        assert len(grid.sections) == 2 and {round(x) for x in grid.beat_tempos()} == {128, 140}
        assert (1, 30.5) in [(n, round(t, 3)) for n, t in grid.beats]
        # repères « nouveau son » seuls (même tempo) : la grille de l'analyse reste
        tempo_profile.set_marks("Set.mp3", 4321, [(0.5, 128.0, 0.5, ""), (30.5, 128.0, 30.5, "sound")])
        g2 = BeatGrid(bpm=128.0, beats=[(1, 0.5)])
        assert not tempo_profile.apply_manual(f, g2, 60.0) and g2.beats == [(1, 0.5)]
        tempo_profile.set_marks("Set.mp3", 4321, [])
        assert tempo_profile.known(f).marks == []
    finally:
        tempo_profile.use_store(None)


# ------------------------------------------------------------------ réglage Dynamique / Classique
def test_c221_classic_mode_has_no_detection():
    from .test_v143_lot6 import _switch, _to22k
    from djsync.analysis.tempo import analyze_tempo

    y, _t, _ = _switch([(122.0, 0.3, 60), (140.0, 0.2, 60)])
    x = _to22k(y)
    classic = analyze_tempo(x, 22050, grid_mode="classic")
    assert classic.profile.kind == "" and not classic.sections and not classic.variable
    assert len(set(classic.beat_tempos())) == 1
    dynamic = analyze_tempo(x, 22050)
    assert dynamic.profile.kind == "switch" and dynamic.sections
    try:
        tempo_profile.set_policy("classic")
        assert tempo_profile.grid_mode_for(None) == "classic"
        tempo_profile.set_policy("dynamic")
        assert tempo_profile.grid_mode_for(None) == "auto"
    finally:
        tempo_profile.set_policy("dynamic")


@pytest.mark.parametrize("old,new", [("never", "classic"), ("auto", "dynamic"), ("classic", "classic"),
                                     ("", "dynamic"), ("bad", "dynamic")])
def test_c221_setting_migration(tmp_path, old, new):
    import json

    from djsync.settings import Settings

    p = tmp_path / "settings.json"
    s = Settings()
    s.save(p)
    data = json.loads(p.read_text("utf-8"))
    data["tempo_grid"] = old
    p.write_text(json.dumps(data), "utf-8")
    assert Settings.load(p).tempo_grid == new


def test_c221_settings_page_analysis_choice(demo):  # noqa: F811
    view = demo.views.get("settings")
    if view is None:
        pytest.skip("settings view not built in the demo window")
    combo = view.tempo_grid
    assert [combo.itemData(i) for i in range(combo.count())] == ["dynamic", "classic"]
    assert combo.itemText(0) == TS_t("settings.analysis_mode_dynamic")


def TS_t(key):  # noqa: N802
    from djsync.i18n import t

    return t(key)


# ------------------------------------------------------------------ Grille et cues
def _c221_editor(demo, tmp_path, beats=None):  # noqa: F811
    import dataclasses

    from djsync.ui.grid_editor import GridEditor

    from .qt_util import pump

    track = dataclasses.replace(demo.ctrl.library.list_tracks()[0], is_analysed=True)
    tempo_profile.use_store(tmp_path / "tempo.json")
    data = tempo_profile._load()
    data[f"{Path(track.path).name.casefold()}|{int(track.file_size)}"] = \
        tempo_profile.TempoProfile("switch", 122, 140, 10.0).to_list()
    ed = GridEditor(demo, demo.ctrl, track)
    pump(demo, 1, lambda: False)
    ed.duration_ms = 120000
    ed.beats = beats or G.extend([(1, 12800, 500)], 120000)
    ed.original = list(ed.beats)
    ed.cues, ed.original_cues = [], []
    ed._refresh_info()
    return ed, track


def test_c221_grid_editor_markers_band_and_live_bpm(demo, tmp_path, monkeypatch):  # noqa: F811
    from PySide6.QtGui import QImage, QPainter

    from djsync.i18n import t

    ed, track = _c221_editor(demo, tmp_path)
    try:
        tools = ed.seg_tools
        assert len(tools.segs) == 1 and tools.seg_lbl.text() == t("grid.seg_current", n=1, total=1)
        assert t("grid.seg_bpm_here", bpm="128.00") in tools.live_lbl.text()
        # repère « changement de tempo » au curseur, puis BPM du passage : grille recalculée
        ed._move_cursor(30100.0)
        tools.add("tempo")
        assert len(tools.segs) == 2 and ed.beats == ed.original           # même tempo : rien ne bouge encore
        assert ed.save_btn.isEnabled() and tools.dirty()
        ed._move_cursor(45000.0)
        tools.bpm_entry.setText("140")
        tools.apply_bpm()
        assert {b[1] for b in ed.beats} == {12800, 14000} and ed.beats != ed.original
        assert tools.segs[1][1] == 140.0 and tools.bpm_entry.text() == "140.00"
        # BPM au curseur et sous la souris
        tools.hover(10000.0)
        assert t("grid.seg_bpm_mouse", bpm="128.00") in tools.live_lbl.text()
        assert t("grid.seg_bpm_here", bpm="140.00") in tools.live_lbl.text()
        tools.hover(None)
        assert t("grid.seg_bpm_mouse", bpm="128.00") not in tools.live_lbl.text()
        # dessin : forme d'onde avec repères, bande des passages
        ed.start_ms = 26000.0
        img = QImage(800, 200, QImage.Format_RGB32)
        painter = QPainter(img)
        ed.paint(painter, 800, 200)
        painter.end()
        tools.band.resize(600, 22)
        tools.band.grab()
        # glisser la poignée du repère d'un temps vers l'avant (calé sur un temps à 128)
        ed.canvas.resize(800, 200)
        mark = tools.segs[1][0]
        assert tools.grab(ed._x(mark), 195, 200) and tools.dragging()
        tools.drag(ed._x(mark + 470))
        tools.drop()
        assert tools.segs[1][0] - mark == pytest.approx(60000 / 128, abs=1)
        assert next(b for b in ed.beats if b[1] == 14000)[2] == tools.segs[1][0]
        assert not tools.grab(ed._x(mark), 40, 200)                   # hors de la poignée : rien
        # supprimer : un seul tempo de nouveau
        tools.remove()
        assert len(tools.segs) == 1 and {b[1] for b in ed.beats} == {12800}
        # annuler : repères d'origine
        tools.add("tempo")
        ed._reset()
        assert len(ed.seg_tools.segs) == 1 and not tools.dirty()
    finally:
        ed._closed = True
        ed.deleteLater()
        tempo_profile.use_store(None)


def test_c221_new_track_marker_is_a_named_memory_cue_and_saved(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.i18n import t

    ed, track = _c221_editor(demo, tmp_path)
    try:
        tools = ed.seg_tools
        ed._move_cursor(60000.0)
        tools.add("sound")
        at = tools.segs[1][0]
        mem = [c for c in ed.cues if c.slot == 0]
        assert [(c.ms, c.name) for c in mem] == [(at, t("grid.seg_sound_cue"))]
        assert ed.beats == ed.original and ed.cues_dirty() and ed.save_btn.isEnabled()
        # un autre outil change la grille (décalage) : le repère suit, sa mémoire aussi
        ed._shift(10)
        assert tools.segs[1][3] == "sound" and [c.ms for c in ed.cues if c.slot == 0] == [at + 10]
        saved = []

        def save(cid, beats, cues, ok=None, err=None):
            saved.append((beats, cues))
            ok(None)

        monkeypatch.setattr(demo.ctrl, "save_grid_and_cues", save)
        ed._leaving = True
        ed._save()
        assert saved and saved[0][1] and saved[0][1][0].name == t("grid.seg_sound_cue")
        p = tempo_profile.known(track.path) or TG.profile_of(track)
        assert p is not None and [m[3] for m in p.marks] == ["", "sound"]
        assert abs(p.marks[1][0] * 1000 - (at + 10)) <= 1
    finally:
        ed._closed = True
        ed.deleteLater()
        tempo_profile.use_store(None)


def test_c221_grid_editor_type_menu_kept_in_register(demo, tmp_path):  # noqa: F811
    from djsync.i18n import t

    ed, track = _c221_editor(demo, tmp_path)
    try:
        menu = ed.seg_tools.kind_menu
        assert [menu.itemData(i) for i in range(menu.count())] == list(TS.KIND_CHOICES)
        assert menu.currentIndex() == 0 and t("grid.seg_kind_switch") in menu.itemText(0)
        menu.setCurrentIndex(menu.findData("ramp"))
        p = TG.profile_of(track)
        assert p.user_kind == "ramp" and p.kind == "ramp" and p.detected == "switch"
        assert t("tempo.user_kind", kind=t("grid.seg_kind_ramp")) in ed.info.text()
        menu.setCurrentIndex(menu.findData("none"))
        assert not TG.profile_of(track).kind and ed.tempo_banner.isHidden()
    finally:
        ed._closed = True
        ed.deleteLater()
        tempo_profile.use_store(None)
