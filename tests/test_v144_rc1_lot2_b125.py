"""1.4.4-rc.1 (lot 2) : B125 : 1er temps de la mesure : entrées des basses et contrôle « à vérifier ».

Sons SYNTHÉTIQUES (numpy) : intro charleston + accords médiums sans basses, puis kick + basse qui entrent au début
d'une mesure ; break puis drop ; roulement de kicks collé au drop ; kicks isolés dans le break ; entrée sur un
demi-temps ; deux drops en désaccord. Vérité terrain exacte : les débuts de mesure de la musique.
    pytest -q tests/test_v144_rc1_lot2_b125.py
"""
from __future__ import annotations

import numpy as np
import pytest

from djsync.analysis import tempo as T
from djsync.analysis import tempo_profile

from .test_v122 import demo, usb  # noqa: F401  (fixtures)

_B125_SR = 22050
_B125_BPM = 126.0
_B125_LEAD = 0.3


def _b125_song(plan, roll_before=None, isolated=None, bass_on=0, seed=3, half_at=None):
    """plan : (nombre de temps, genre) ; genre : « intro » (charleston, accords médiums), « main » (+ kick sur chaque
    temps et basse relancée à chaque mesure, sur le temps `bass_on`), « main_off » (main décalé d'un demi-temps),
    « break » (accords seuls). `half_at` : ce temps-là (et lui seul) arrive un demi-temps plus tard. Chaque partie
    commence une mesure. Renvoie (signal, débuts de mesure en s)."""
    sr, beat = _B125_SR, 60.0 / _B125_BPM
    rng = np.random.default_rng(seed)
    total = sum(n for n, _ in plan)
    y = np.zeros(int((_B125_LEAD + (total + 2) * beat) * sr))
    t = np.arange(int(0.25 * sr)) / sr
    kick = np.sin(2 * np.pi * np.cumsum(50 + 100 * np.exp(-t * 30)) / sr) * np.exp(-t * 12)
    th = np.arange(int(0.05 * sr)) / sr
    hat = 0.2 * np.diff(rng.normal(0, 1, th.size), prepend=0) * np.exp(-th * 80)
    tb = np.arange(int(4 * beat * sr)) / sr
    bass = 0.5 * np.sin(2 * np.pi * 55 * tb) * np.minimum(1, tb / 0.005) * np.exp(-tb * 0.4)
    ts = np.arange(int(0.2 * sr)) / sr
    stab = 0.12 * sum(np.sin(2 * np.pi * f * ts) for f in (440, 554, 659, 880)) * np.exp(-ts * 15)

    def add(sig, at):
        i = int(round(at * sr))
        if 0 <= i < y.size:
            e = min(y.size, i + sig.size)
            y[i:e] += sig[:e - i]

    downs, k = [], 0
    for n, kind in plan:
        for b in range(n):
            at = _B125_LEAD + k * beat + (beat / 2 if kind == "main_off" or k == half_at else 0.0)
            if b % 4 == 0:
                downs.append(at)
            if kind != "break":
                add(hat, at)
                add(hat, at + beat / 2)
            add(stab, at)
            if kind in ("main", "main_off"):
                add(kick, at)
                if b % 4 == bass_on:
                    add(bass, at)
            k += 1
    if roll_before is not None:                  # roulement de kicks (doubles croches) sur les 2 temps d'avant
        for q in range(8):
            add(0.9 * kick[: int(beat / 4 * sr)], roll_before - 2 * beat + q * beat / 4)
    if isolated is not None:                     # une mesure de kicks qui ne tient pas
        for q in range(4):
            add(kick, isolated + q * beat)
    return (y / np.max(np.abs(y)) * 0.9).astype(np.float32), np.array(downs)


def _b125_at(n_beats):
    return _B125_LEAD + n_beats * 60.0 / _B125_BPM


def _b125_on_bar(grid, bar_start):
    """True si les 1ers temps de la grille tombent sur les débuts de mesure de la musique (à 10 ms près)."""
    beat = 60.0 / _B125_BPM
    ones = [t for n, t in grid.beats if n == 1]
    off = ((ones[0] - bar_start) / beat) % 4
    return min(off, 4 - off) * beat < 0.010


def _b125_no_entries(monkeypatch):
    monkeypatch.setattr(T, "_entries", lambda *a, **k: [])


# ------------------------------------------------------------------ analyse
@pytest.mark.parametrize("intro", [64, 65, 63, 66])
def test_b125_downbeat_follows_the_bass_entry_after_the_intro(intro):
    """Intro sans basses puis kick + basse au début d'une mesure : le 1er temps suit l'entrée, même décalée."""
    y, _downs = _b125_song([(intro, "intro"), (96, "main")])
    dbg = {}
    grid = T.analyze_tempo(y, _B125_SR, dbg)
    assert abs(grid.bpm - _B125_BPM) < 0.05
    assert _b125_on_bar(grid, _b125_at(intro)), dbg.get("downbeat_entries")
    assert len(dbg["downbeat_entries"].split()) == 1
    assert grid.profile.downbeat_check is False


def test_b125_drop_after_a_break_with_a_kick_roll_and_isolated_kicks():
    """Drop après un break : roulement de kicks collé au départ et kicks isolés dans le break écartés."""
    plan = [(64, "intro"), (64, "main"), (32, "break"), (64, "main")]
    y, _ = _b125_song(plan, roll_before=_b125_at(160), isolated=_b125_at(138))
    dbg = {}
    grid = T.analyze_tempo(y, _B125_SR, dbg)
    starts = [float(s.split("s:")[0]) for s in dbg["downbeat_entries"].split()]
    assert len(starts) == 2 and abs(starts[0] - _b125_at(64)) < 0.06 and abs(starts[1] - _b125_at(160)) < 0.06
    assert _b125_on_bar(grid, _b125_at(64)) and not grid.profile.downbeat_check


def test_b125_entries_win_over_the_average(monkeypatch):
    """Basse relancée sur le 3e temps : la moyenne (B12) se trompe, les entrées concordantes l'emportent."""
    y, _ = _b125_song([(64, "intro"), (64, "main"), (32, "break"), (64, "main")], bass_on=2)
    with_entries = T.analyze_tempo(y, _B125_SR)
    assert _b125_on_bar(with_entries, _b125_at(64))
    _b125_no_entries(monkeypatch)
    assert not _b125_on_bar(T.analyze_tempo(y, _B125_SR), _b125_at(64))     # avant B125


def test_b125_half_beat_entry_does_not_vote():
    """L'entrée arrive un demi-temps après le temps (la suite est sur la grille) : pas de vote."""
    y, _ = _b125_song([(64, "intro"), (96, "main")], half_at=64)
    dbg = {}
    T.analyze_tempo(y, _B125_SR, dbg)
    assert "downbeat_entries" not in dbg


def test_b125_offbeat_section_moves_the_grid_then_the_entry_votes():
    """Toute la partie principale décalée d'un demi-temps : la grille passe sur les kicks (B11), l'entrée vote."""
    y, _ = _b125_song([(64, "intro"), (96, "main_off")])
    dbg = {}
    grid = T.analyze_tempo(y, _B125_SR, dbg)
    assert _b125_on_bar(grid, _b125_at(64.5)) and len(dbg["downbeat_entries"].split()) == 1


def test_b125_contradictory_entries_mark_the_track_to_check():
    """Deux drops qui ne tombent pas sur la même position de la mesure : « 1er temps à vérifier »."""
    y, _ = _b125_song([(64, "intro"), (64, "main"), (34, "break"), (64, "main")])
    grid = T.analyze_tempo(y, _B125_SR)
    assert grid.profile.downbeat_check is True
    assert abs(grid.profile.downbeat_at - _b125_at(64)) < 0.05 or abs(grid.profile.downbeat_at - _b125_at(162)) < 0.05


def test_b125_entry_against_a_sure_average_is_to_check(monkeypatch):
    """Une entrée qui contredit une moyenne nette : elle l'emporte, le son est à vérifier."""
    from .audio_fixture import song

    y = song(128.0, 0.37, 40, ["A", "F", "E", "A"], [1, 0, 0, 1])
    sr = 44100
    times = np.arange(0.37, 40, 60.0 / 128)
    _env, benv, _fps = T.onset_envelopes(y, sr)
    assert T._downbeat_vote(y, sr, benv, times)[:2] == (0, False)              # sans entrée : la moyenne
    monkeypatch.setattr(T, "_entries", lambda *a, **k: [(42, 6.0)])            # entrée sur le 3e temps
    down, check, at = T._downbeat_vote(y, sr, benv, times)
    assert (down, check) == (2, True) and abs(at - times[42]) < 1e-9


def test_b125_grid_positions_never_move(monkeypatch):
    """Seul le numéro des temps change : positions et tempo de la grille identiques avec ou sans B125."""
    y, _ = _b125_song([(64, "intro"), (64, "main"), (32, "break"), (64, "main")], bass_on=2)
    after = T.analyze_tempo(y, _B125_SR)
    _b125_no_entries(monkeypatch)
    before = T.analyze_tempo(y, _B125_SR)
    assert [t for _, t in after.beats] == [t for _, t in before.beats]
    assert (after.bpm, after.first_beat) == (before.bpm, before.first_beat)
    assert [n for n, _ in after.beats] != [n for n, _ in before.beats]


def test_b125_register_keeps_the_mark_and_clears_it(tmp_path):
    tempo_profile.use_store(tmp_path / "tempo.json")
    try:
        f = tmp_path / "Drop.mp3"
        f.write_bytes(b"x" * 555)
        tempo_profile.remember(f, tempo_profile.TempoProfile(drift_ms=3.0, downbeat_check=True, downbeat_at=31.5))
        tempo_profile.use_store(tmp_path / "tempo.json")                       # relu depuis le fichier
        got = tempo_profile.lookup("drop.MP3", 555)
        assert got.downbeat_check and got.downbeat_at == 31.5 and not got.changes
        assert tempo_profile.set_downbeat_checked("drop.mp3", 555)
        assert not tempo_profile.lookup("drop.mp3", 555).downbeat_check
        assert not tempo_profile.set_downbeat_checked("other.mp3", 555)
        old = tempo_profile.TempoProfile.from_list(["", 1, 1, 0, 0, 0, [], ""])     # format 1.4.3
        assert old.downbeat_check is False and old.downbeat_at == -1.0
    finally:
        tempo_profile.use_store(None)


# ------------------------------------------------------------------ interface
def _b125_track(demo):  # noqa: F811
    import dataclasses

    return dataclasses.replace(demo.ctrl.library.list_tracks()[0], is_analysed=True)


def _b125_mark(tmp_path, track, at=-1.0):
    from pathlib import Path

    tempo_profile.use_store(tmp_path / "tempo.json")
    data = tempo_profile._load()
    data[f"{Path(track.path).name.casefold()}|{int(track.file_size)}"] = \
        tempo_profile.TempoProfile(downbeat_check=True, downbeat_at=at).to_list()


def _b125_editor(demo, track):  # noqa: F811
    from djsync.analysis import grid as G
    from djsync.ui.grid_editor import GridEditor

    from .qt_util import pump

    ed = GridEditor(demo, demo.ctrl, track)
    pump(demo, 1, lambda: False)
    ed.duration_ms = 60000
    ed.beats = G.extend([(1, 12800, 500)], 60000)
    ed.original = list(ed.beats)
    ed._downbeat_setup()
    ed._refresh_info()
    return ed


def test_b125_grid_editor_pick_listen_save_and_mark_removed(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.tempo_grids import TempoGridService

    track = _b125_track(demo)
    _b125_mark(tmp_path, track, at=20.0)
    try:
        assert TempoGridService.downbeat_pending(track)
        ed = _b125_editor(demo, track)
        try:
            assert not ed.downbeat_box.isHidden() and ed.downbeat_banner.text() == t("grid.downbeat_check")
            base = ed._db_base
            assert ed.beats[base][0] == 1 and abs(ed.beats[base][2] - 20000) < 4 * 60000 / 128
            played = []
            monkeypatch.setattr(ed, "play_from", lambda ms, loop=None: played.append(ms))
            ed._downbeat_listen(2)
            assert played == [ed.beats[base + 2][2]]
            ed._downbeat_pick(2)
            assert [b[1:] for b in ed.beats] == [b[1:] for b in ed.original]          # la grille ne bouge pas
            assert ed.beats[base + 2][0] == 1 and ed.beats != ed.original and ed.save_btn.isEnabled()
            assert ed.downbeat_banner.text() == t("grid.downbeat_chosen")
            assert ed.downbeat_picks[2].property("kind") == "primary"
            assert TempoGridService.downbeat_pending(track)                           # pas encore enregistré
            saved = []

            def save(cid, beats, cues, ok=None, err=None):
                saved.append(beats)
                ok(None)

            monkeypatch.setattr(demo.ctrl, "save_grid_and_cues", save)
            ed._save()
            assert saved and saved[0][base + 2][0] == 1
            assert not TempoGridService.downbeat_pending(track)                       # marqueur retiré
        finally:
            ed._closed = True
            ed.deleteLater()
    finally:
        tempo_profile.use_store(None)


def test_b125_grid_editor_keeping_the_analysis_choice_clears_at_once(demo, tmp_path):  # noqa: F811
    from djsync.ui.tempo_grids import TempoGridService

    track = _b125_track(demo)
    _b125_mark(tmp_path, track)
    try:
        ed = _b125_editor(demo, track)
        try:
            ed._downbeat_pick(0)
            assert ed.beats == ed.original and not ed.save_btn.isEnabled()
            assert not TempoGridService.downbeat_pending(track)
        finally:
            ed._closed = True
            ed.deleteLater()
        ed = _b125_editor(demo, track)                                    # son sans marque : rien d'affiché
        try:
            assert ed.downbeat_box.isHidden()
        finally:
            ed._closed = True
            ed.deleteLater()
    finally:
        tempo_profile.use_store(None)


def test_b125_library_analysis_column_says_to_check(demo, tmp_path):  # noqa: F811
    from djsync.i18n import t

    track = _b125_track(demo)
    view = demo.views["library"]
    _b125_mark(tmp_path, track)
    try:
        view._extras = {track.content_id: {}}
        assert view._extra_values(track)["analysis"] == t("lib.an_downbeat")
        view._extras = {track.content_id: {"grid_checked": True}}
        assert view._extra_values(track)["analysis"] == t("lib.an_checked")
    finally:
        tempo_profile.use_store(None)
