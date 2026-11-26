"""1.4.4-rc.1 (lot 2) : C108 : énergie de chaque son (1 à 10), calculée à l'analyse depuis ses mesures (forme
d'onde 3 bandes, sonie, tempo), colonne de la Bibliothèque, lecteur, clic droit ▸ Énergie, option « énergie dans
le commentaire », petit bonus dans Suggestions.

Sons SYNTHÉTIQUES (numpy) du plus calme au plus explosif : nappe lente et douce ; groove (kick, charleston) ;
kick fort, charleston en doubles croches, basse, tempo rapide.
    pytest -q tests/test_v144_rc1_lot2_c108.py
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from djsync.analysis import energy as E

from .test_v122 import demo, usb  # noqa: F401  (fixtures)

_C108_SR = 22050


def _c108_synth(bpm, dur=40.0, kick=0.0, hat=0.0, hat_div=2, pad=0.2, bass=0.0, gain=1.0, seed=1):
    rng = np.random.default_rng(seed)
    sr = _C108_SR
    n = int(dur * sr)
    t = np.arange(n) / sr
    y = pad * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 277 * t) + 0.4 * np.sin(2 * np.pi * 330 * t)) / 1.9
    beat = 60.0 / bpm
    tk = np.arange(int(0.25 * sr)) / sr
    k = np.sin(2 * np.pi * np.cumsum(50 + 100 * np.exp(-tk * 30)) / sr) * np.exp(-tk * 12)
    th = np.arange(int(0.05 * sr)) / sr
    h = np.diff(rng.normal(0, 1, th.size), prepend=0) * np.exp(-th * 80)
    tb = np.arange(int(beat * sr)) / sr
    b = np.sin(2 * np.pi * 55 * tb) * np.exp(-tb * 3)

    def add(sig, at, g):
        i = int(at * sr)
        if i < n:
            e = min(n, i + sig.size)
            y[i:e] += g * sig[:e - i]

    for at in np.arange(0.3, dur, beat):
        if kick:
            add(k, at, kick)
        if bass:
            add(b, at + beat / 2, bass)
        for q in range(hat_div if hat else 0):
            add(h, at + q * beat / hat_div, hat)
    return y / max(1e-9, float(np.abs(y).max())) * 0.9 * gain


def _c108_energy(y, bpm):
    from djsync.analysis.loudness import measure
    from djsync.analysis.waveform import compute_waveforms

    wf = compute_waveforms(y, _C108_SR, y.size / _C108_SR)
    lufs, _peak = measure(y, _C108_SR)
    return E.compute(wf.band_detail, bpm, lufs)


# ------------------------------------------------------------------ calcul
def test_c108_energy_grows_from_calm_to_explosive():
    calm = _c108_energy(_c108_synth(70, pad=0.3, gain=0.15), 70)
    groove = _c108_energy(_c108_synth(110, kick=0.6, hat=0.15, pad=0.2, gain=0.5), 110)
    explosive = _c108_energy(_c108_synth(140, kick=1.0, hat=0.35, hat_div=4, pad=0.15, bass=0.6), 140)
    assert 1 <= calm < groove < explosive <= 10
    assert calm <= 3 and explosive >= 6


def test_c108_bounds_and_missing_waveform():
    loud = bytes([127, 0, 127] * 150 * 30)                        # basses et aigus au maximum, pas d'attaque
    spiky = bytes(([127, 60, 127] + [0, 0, 0] * 4) * 30 * 60)      # attaques serrées
    assert E.compute(spiky, 300.0, 0.0) == 10
    assert 1 <= E.compute(loud, 300.0, 0.0) <= 10
    assert E.compute(bytes([0, 40, 0] * 150 * 30), 40.0, -40.0) == 1
    assert E.compute(b"", 120.0, -8.0) is None                    # pas de forme d'onde
    assert E.compute(bytes([10, 10, 10] * 150), 120.0, -8.0) is None   # moins de 5 s
    assert E.compute(bytes(3 * 150 * 30), 120.0, -8.0) is None    # silence


def test_c108_analyze_file_measures_and_remembers_energy(tmp_path):
    from djsync.analysis import analyze_file

    from .audio_fixture import SR, write_wav
    from djsync.analysis.decode import _resample

    E.use_store(tmp_path / "energy.json")
    try:
        y = _resample(_c108_synth(128, dur=30, kick=0.9, hat=0.3), _C108_SR, SR)
        f = write_wav(tmp_path / "Track.wav", y)
        res = analyze_file(f)
        assert res.energy is not None and 1 <= res.energy <= 10
        assert E.value("track.WAV", f.stat().st_size) == res.energy
    finally:
        E.use_store(None)


# ------------------------------------------------------------------ registre et choix à la main
def test_c108_manual_energy_wins_and_is_kept_at_reanalysis(tmp_path):
    E.use_store(tmp_path / "energy.json")
    try:
        f = tmp_path / "Song.mp3"
        f.write_bytes(b"x" * 999)
        E.remember(f, 4)
        assert E.lookup("song.mp3", 999) == (4, 0) and E.value("Song.mp3", 999) == 4
        assert E.set_manual("Song.mp3", 999, 9)
        E.use_store(tmp_path / "energy.json")                        # relu depuis le fichier
        E.remember(f, 5)                                              # réanalyse
        assert E.lookup("Song.mp3", 999) == (5, 9) and E.value("Song.mp3", 999) == 9
        assert E.set_manual("Song.mp3", 999, 0)                       # « Automatique »
        assert E.value("Song.mp3", 999) == 5
        assert E.set_manual("Other.mp3", 12, 3) and E.value("Other.mp3", 12) == 3   # son analysé par Rekordbox
        E.set_manual("Other.mp3", 12, 0)
        assert E.lookup("Other.mp3", 12) is None
        assert E.set_manual("Song.mp3", 999, 42) and E.lookup("Song.mp3", 999) == (5, 0)   # hors bornes : auto
    finally:
        E.use_store(None)


def test_c108_comment_prefix_keeps_the_rest():
    assert E.with_prefix("", 7) == "E7"
    assert E.with_prefix("https://soundcloud.com/a/b", 7) == "E7 https://soundcloud.com/a/b"
    assert E.with_prefix("E3 my notes", 10) == "E10 my notes"
    assert E.with_prefix("E10 my notes", 0) == "my notes"
    assert E.strip_prefix("E7 https://x.y/z") == "https://x.y/z"
    assert E.strip_prefix("Eagle E7 notes") == "Eagle E7 notes"           # seul un préfixe en tête compte
    assert E.strip_prefix("E77 notes") == "E77 notes"
    from djsync.db.library.common import _match_sources, source_of

    assert source_of("E7 https://soundcloud.com/a/b") == "https://soundcloud.com/a/b"
    assert source_of("E7 notes") is None
    rows = [(1, "E7 https://soundcloud.com/a/b"), (2, "E3 https://www.youtube.com/watch?v=abcdefghijk")]
    hits = _match_sources({"u1": ("https://soundcloud.com/a/b", False), "u2": ("abcdefghijk", True)}, rows)
    assert hits == {"u1": 1, "u2": 2}


def test_c108_suggestions_small_bonus_for_close_energy(tmp_path):
    from djsync.core.suggest import ENERGY_BONUS, score

    E.use_store(tmp_path / "energy.json")
    try:
        def track(cid, name, energy):
            E.set_manual(name, 100, energy)
            return NS(content_id=cid, bpm=128.0, camelot="8A", genre="", path=f"/x/{name}", file_size=100,
                      title=name)

        ref, close, far = track(1, "a.mp3", 7), track(2, "b.mp3", 8), track(3, "c.mp3", 2)
        assert score(ref, close).score - score(ref, far).score == pytest.approx(ENERGY_BONUS)
    finally:
        E.use_store(None)


# ------------------------------------------------------------------ interface
def _c108_track(demo):  # noqa: F811
    return demo.ctrl.library.list_tracks()[0]


def test_c108_library_column_player_and_menu(demo):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.column_views import ORDER
    from djsync.ui.track_menu import track_entries
    from djsync.ui.views.library_view import extra_values

    view = demo.views["library"]
    assert "energy" in [c.key for c in view.cols] and "energy" in ORDER["prepare"]
    x = _c108_track(demo)
    assert extra_values(x)["energy"] == ""                         # pas encore mesurée
    entries = track_entries(view, demo.ctrl, [x], where="library")
    sub = next(e for e in entries if e and e[0] == t("energy.menu"))[1]
    assert len([e for e in sub if e]) == 11
    pick = next(e for e in sub if e and e[0].endswith(t("energy.level_7")))
    events = []
    demo.ctrl.on("energy_changed", lambda: events.append(1))
    pick[1]()
    vals = extra_values(x)
    assert vals["energy"] == "7" and vals["energy__n"] == 7 and vals["energy__tip"] == t("energy.tip_manual", n=7)
    assert events
    sub = next(e for e in track_entries(view, demo.ctrl, [x]) if e and e[0] == t("energy.menu"))[1]
    assert any(e and e[0].startswith("✓") and e[0].endswith(t("energy.level_7")) for e in sub)
    demo.player_bar._show_energy(x)                                 # lecteur : « Énergie 7 »
    assert demo.player_bar.energy_lbl.text() == t("energy.player", n=7)
    sub[0][1]()                                                     # « Automatique »
    assert extra_values(x)["energy"] == ""


def test_c108_comment_option_writes_prefix_and_keeps_the_source(demo):  # noqa: F811
    lib = demo.ctrl.library
    x = _c108_track(demo)
    url = "https://soundcloud.com/someone/some-track"
    with lib._write() as conn:
        conn.execute("UPDATE content SET djComment = ? WHERE content_id = ?", (url, x.content_id))
    assert lib.find_by_source_url(url).content_id == x.content_id
    assert lib.set_energy_comments({x.content_id: 7}) == 1
    got = lib.get_track(x.content_id)
    assert got.comment == f"E7 {url}" and got.source_url == url
    assert lib.find_by_source_url(url).content_id == x.content_id          # doublon toujours reconnu
    assert lib.find_by_source_urls([url])[url].content_id == x.content_id
    assert lib.set_energy_comments({x.content_id: 9}) == 1
    assert lib.get_track(x.content_id).comment == f"E9 {url}"
    assert lib.set_energy_comments({x.content_id: 9}) == 0                 # rien à changer
    # service : sans l'option, rien n'est écrit ; avec, l'énergie choisie à la main va dans le commentaire
    demo.ctrl.settings.energy_comment = False
    demo.ctrl.energy.set_manual([lib.get_track(x.content_id)], 4)
    assert lib.get_track(x.content_id).comment == f"E9 {url}"
    written = []
    demo.ctrl.settings.energy_comment = True
    try:
        orig = lib.set_energy_comments

        def spy(energies):
            written.append(dict(energies))
            return orig(energies)

        lib.set_energy_comments = spy
        demo.ctrl._write = lambda fn, ok=None, msg="", err=None: fn(lib)
        demo.ctrl.energy.set_manual([lib.get_track(x.content_id)], 3)
        assert written == [{x.content_id: 3}] and lib.get_track(x.content_id).comment == f"E3 {url}"
    finally:
        demo.ctrl.settings.energy_comment = False
        demo.ctrl.energy.set_manual([x], 0)


def test_c108_usb_analysis_writes_the_comment_when_asked(tmp_path):
    from djsync.db.library.ingest import _energy_comment

    E.use_store(tmp_path / "energy.json")
    try:
        row = ("/Contents/A/song.mp3", "https://soundcloud.com/a/b", 1234)
        assert _energy_comment(row, NS(energy=6)) == "E6 https://soundcloud.com/a/b"
        E.set_manual("song.mp3", 1234, 2)                             # choisie à la main : prioritaire
        assert _energy_comment(row, NS(energy=6)) == "E2 https://soundcloud.com/a/b"
        assert _energy_comment(("/Contents/A/x.mp3", "E5 notes", 1), NS(energy=5)) is None   # inchangé
        assert _energy_comment(("/Contents/A/x.mp3", "notes", 1), NS(energy=None)) is None
    finally:
        E.use_store(None)


def test_c108_settings_switch(demo):  # noqa: F811
    from djsync.settings import Settings

    assert Settings().energy_comment is False
    view = demo.views.get("settings")
    if view is None:
        pytest.skip("settings view not built in the demo window")
    assert not view.energy_comment_var.isChecked()
