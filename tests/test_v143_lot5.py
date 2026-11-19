"""1.4.3-rc.1, lot 5 (session de mesures du 19/11) : C69 (tempo qui change : type détecté, pastille, liste
automatique ; grille variable réservée aux tempos qui bougent peu à peu), C109 (référence −10,7 LUFS calée sur
Rekordbox), A01 (tonalité).

Sons synthétiques (audio_fixture.py) : vérité terrain exacte.
    pytest -q tests/test_v143_lot5.py
"""
from types import SimpleNamespace

import numpy as np
import pytest

from djsync.analysis import tempo_profile
from djsync.analysis.tempo import analyze_tempo

from .audio_fixture import SR, song


def _to22k(y: np.ndarray) -> np.ndarray:
    from djsync.analysis.decode import _resample as lowpass_resample

    return lowpass_resample(y, SR, 22050)


CHORDS, MINORS = ["A", "F", "E", "A"], [1, 0, 0, 1]


# ------------------------------------------------------------------ C69 : profil de tempo
def test_c69_beat_switch_is_detected_and_keeps_a_fixed_grid():
    """Beatswitch (122 puis 140 BPM, une minute chacun, comme un son de l'échantillon) : signalé avec les deux
    tempos ; la grille reste fixe (la grille variable ne suit pas un saut net : C16)."""
    y = np.concatenate([song(122.0, 0.3, 60, CHORDS, MINORS), song(140.0, 0.2, 60, CHORDS, MINORS)])
    grid = analyze_tempo(_to22k(y), 22050)
    p = grid.profile
    assert p.kind == "switch", p
    assert abs(p.lo - 122) <= 1.5 and abs(p.hi - 140) <= 1.5
    assert not grid.variable and not p.variable


@pytest.mark.parametrize("start,end", [(120.0, 127.0), (127.0, 120.0)])
def test_c69_gradual_tempo_is_a_ramp_with_a_following_grid(start, end):
    grid = analyze_tempo(_to22k(song(start, 0.3, 120, CHORDS, MINORS, bpm_end=end)), 22050)
    assert grid.profile.kind == "ramp", grid.profile
    assert grid.variable and grid.profile.variable


def test_c69_constant_tempo_says_nothing():
    grid = analyze_tempo(_to22k(song(124.0, 0.3, 90, CHORDS, MINORS)), 22050)
    assert grid.profile is not None and grid.profile.kind == "" and not grid.variable


def test_c69_short_five_four_passage_is_not_a_beat_switch():
    """Rapport 5:4 bref (intro, pont) : motif rythmique plutôt qu'un vrai changement (mesuré : 6 faux
    beatswitchs sur 337 sons de référence sans cette règle)."""
    y = np.concatenate([song(100.0, 0.3, 14, CHORDS, MINORS), song(125.0, 0.2, 100, CHORDS, MINORS)])
    assert analyze_tempo(_to22k(y), 22050).profile.kind != "switch"


def test_c69_register_roundtrip(tmp_path):
    tempo_profile.use_store(tmp_path / "tempo.json")
    try:
        f = tmp_path / "Live.m4a"
        f.write_bytes(b"x" * 1234)
        p = tempo_profile.TempoProfile("live", 120.0, 124.0, 180.0, True)
        tempo_profile.remember(f, p)
        tempo_profile.use_store(tmp_path / "tempo.json")                    # relu depuis le fichier
        got = tempo_profile.lookup("live.M4A", 1234)
        assert got == p and got.changes
        assert tempo_profile.known(f) == p
        assert tempo_profile.lookup("autre.m4a", 1234) is None
        assert tempo_profile.TempoProfile.from_list(["switch", 100, 130, 5]).variable is False   # ancien format
    finally:
        tempo_profile.use_store(None)


@pytest.mark.parametrize("lang,kind,variable,text", [
    ("fr", "live", True, "Version live détectée · grille variable"),
    ("fr", "switch", False, "Beatswitch détecté (100 → 130 BPM) · grille fixe : à vérifier dans Grille et cues"),
    ("en", "set", True, "Mix or set detected · variable grid"),
    ("en", "ramp", True, "Speed-up or slow-down detected (120–127 BPM) · variable grid"),
])
def test_c69_library_pastille_text(lang, kind, variable, text):
    from djsync.i18n import get_language, set_language
    from djsync.ui.views.library_view import tempo_text

    old = get_language()
    set_language(lang)
    try:
        lo, hi = (100.0, 130.0) if kind == "switch" else (120.0, 127.0)
        assert tempo_text(tempo_profile.TempoProfile(kind, lo, hi, 150.0, variable)) == text
        assert tempo_text(tempo_profile.TempoProfile()) == "" and tempo_text(None) == ""
    finally:
        set_language(old)


def test_c69_tempo_values_and_auto_list(tmp_path):
    from djsync.ui.views import library_view as lv

    tempo_profile.use_store(tmp_path / "tempo.json")
    try:
        f = tmp_path / "set.m4a"
        f.write_bytes(b"y" * 99)
        tempo_profile.remember(f, tempo_profile.TempoProfile("set", 126, 128, 900.0, True))
        g = tmp_path / "calme.m4a"
        g.write_bytes(b"z" * 77)
        tempo_profile.remember(g, tempo_profile.TempoProfile("", 124, 124, 4.0, False))
        a = SimpleNamespace(path=str(f), file_size=99, is_analysed=True)
        b = SimpleNamespace(path=str(g), file_size=77, is_analysed=True)
        assert lv.tempo_values(a)["bpm__dot"] and lv.tempo_values(a)["bpm__tip"]
        assert lv.tempo_values(b) == {}
        view = SimpleNamespace(all_tracks=[a, b])
        assert lv.LibraryView._tempo_tracks(view) == [a]
        assert lv.TEMPO in lv.SPECIAL
    finally:
        tempo_profile.use_store(None)


# ------------------------------------------------------------------ C109 : référence calée sur Rekordbox
def test_c109_reference_matches_rekordbox_auto_gain():
    from djsync.analysis import loudness

    assert loudness.TARGET_LUFS == -10.7
    assert loudness.gain_db(-8.7) == pytest.approx(-2.0)
