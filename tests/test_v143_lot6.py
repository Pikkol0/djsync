"""1.4.3-rc.1, lot 6 : C16 (grille par passage pour les beatswitchs, sons à valider, grille fixe, réglage
« grille variable : auto / jamais ») et A04 (encodeur lu dans l'en-tête, confiance « sûr / probable »,
spectrogramme au clic droit).

Sons synthétiques (audio_fixture.song, concaténés pour les beatswitchs) : vérité terrain exacte.
    pytest -q tests/test_v143_lot6.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from djsync.analysis import tempo_profile
from djsync.analysis.tempo import analyze_tempo

from .audio_fixture import SR, song, write_wav

CHORDS, MINORS = ["A", "F", "E", "A"], [1, 0, 0, 1]
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _to22k(y: np.ndarray) -> np.ndarray:
    from djsync.analysis.decode import _resample

    return _resample(y, SR, 22050)


def _switch(parts):
    """Passages (bpm, 1er temps, durée) mis bout à bout ; renvoie (signal, temps exacts, débuts des passages)."""
    ys, truth, starts, off = [], [], [], 0.0
    for bpm, first, dur in parts:
        bo: list = []
        ys.append(song(bpm, first, dur, CHORDS, MINORS, beats_out=bo))
        starts.append(off + bo[0])
        truth += [b + off for b in bo]
        off += dur
    return np.concatenate(ys), np.array(truth), starts


def _errors_ms(grid, truth):
    got = np.array([t for _, t in grid.beats])
    return np.array([np.min(np.abs(got - b)) * 1000 for b in truth]), got


# ------------------------------------------------------------------ C16 : grille par passage
@pytest.mark.parametrize("parts", [
    [(122.0, 0.3, 60), (140.0, 0.2, 60)],                    # beatswitch de l'échantillon (122 -> 140)
    [(140.0, 0.3, 60), (100.0, 0.25, 70)],                   # 100 hors de la plage du tempo local (lu x4/3 avant)
    [(95.0, 0.3, 50), (128.0, 0.1, 50), (95.0, 0.2, 50)],   # trois passages, retour au tempo du début
])
def test_c16_beat_switch_gets_one_grid_per_passage(parts):
    y, truth, starts = _switch(parts)
    grid = analyze_tempo(_to22k(y), 22050)
    p = grid.profile
    assert p.kind == "switch" and p.split and not grid.variable
    assert [round(b) for _, b, _ in grid.sections] == [round(b) for b, _, _ in parts]
    err, got = _errors_ms(grid, truth)
    assert len(got) == len(truth) and err.max() < 5.0, err.max()          # chaque temps à moins de 5 ms
    # raccord exactement au 1er temps du passage suivant ; mesure qui recommence au changement
    for (start, _bpm, down), real in zip(grid.sections, starts):
        assert abs(start - real) < 0.005 and abs(down - real) < 0.005
    tempos = grid.beat_tempos()
    assert {round(x) for x in tempos} == {round(b) for b, _, _ in parts}
    # BPM de la liste : celui qui couvre le plus de temps
    span: dict = {}
    for b, _f, d in parts:
        span[b] = span.get(b, 0) + d
    assert round(grid.bpm) == round(max(span, key=span.get))
    assert (p.lo, p.hi) == (min(b for b, _, _ in parts), max(b for b, _, _ in parts))


def test_c16_pqtz_carries_the_tempo_of_each_passage():
    from djsync.analysis import AnalysisResult

    y, _truth, _ = _switch([(122.0, 0.3, 60), (140.0, 0.2, 60)])
    grid = analyze_tempo(_to22k(y), 22050)
    res = AnalysisResult(120.0, grid, None, None)
    beats = res.pqtz_beats()
    assert {b[1] for b in beats} == {12200, 14000}
    switch = next(i for i, b in enumerate(beats) if b[1] == 14000)
    assert beats[switch][0] == 1 and all(b[1] == 12200 for b in beats[:switch])
    assert all(b2[2] > b1[2] for b1, b2 in zip(beats, beats[1:]))


def test_c16_never_keeps_a_fixed_grid_for_every_kind():
    y, _t, _ = _switch([(122.0, 0.3, 60), (140.0, 0.2, 60)])
    grid = analyze_tempo(_to22k(y), 22050, grid_mode="never")
    assert grid.profile.kind == "switch" and not grid.profile.split and not grid.sections
    assert len({b for b in grid.beat_tempos()}) == 1
    ramp = analyze_tempo(_to22k(song(120.0, 0.3, 120, CHORDS, MINORS, bpm_end=127.0)), 22050, grid_mode="never")
    assert ramp.profile.kind == "ramp" and not ramp.variable


def test_c16_constant_tempo_is_untouched():
    grid = analyze_tempo(_to22k(song(124.0, 0.3, 90, CHORDS, MINORS)), 22050)
    assert not grid.sections and not grid.profile.split and grid.bpm == 124.0


def test_c16_section_beats_join_without_a_too_short_beat():
    secs = [(0.5, 120.0, 0.5), (10.3, 140.0, 10.3)]               # 120 BPM : temps à 10,0 ; 10,3 - 10,0 < 0,5 temps
    beats = tempo_profile.section_beats(secs, 20.0)
    times = [t for _, t in beats]
    gaps = np.diff(times)
    assert gaps.min() >= 0.5 * 60 / 140 - 1e-6
    assert (1, 10.3) in [(n, round(t, 3)) for n, t in beats]
    assert beats[0] == (1, 0.5) and tempo_profile.section_at(secs, 12.0) == 1


def test_c16_register_keeps_sections_and_the_user_choice(tmp_path):
    tempo_profile.use_store(tmp_path / "tempo.json")
    try:
        f = tmp_path / "Switch.mp3"
        f.write_bytes(b"x" * 321)
        p = tempo_profile.TempoProfile("switch", 122, 140, 20.0, False, True, [(0.3, 122.0, 0.3), (60.2, 140.0, 60.2)])
        tempo_profile.remember(f, p)
        assert tempo_profile.grid_mode_for(f) == "auto"
        assert tempo_profile.set_choice("switch.MP3", 321, "fixed")
        tempo_profile.use_store(tmp_path / "tempo.json")                       # relu depuis le fichier
        got = tempo_profile.known(f)
        assert got.sections == p.sections and got.split and got.choice == "fixed"
        assert tempo_profile.grid_mode_for(f) == "never"
        tempo_profile.remember(f, tempo_profile.TempoProfile("switch", 122, 140, 20.0))   # réanalyse
        assert tempo_profile.known(f).choice == "fixed"                         # le choix reste
        assert tempo_profile.TempoProfile.from_list(["live", 1, 2, 3, 1]).sections == []   # format du lot 5
        tempo_profile.set_policy("never")
        assert tempo_profile.grid_mode_for(tmp_path / "other.mp3") == "never"
        tempo_profile.set_policy("bad")
        assert tempo_profile.policy() == "auto"
    finally:
        tempo_profile.set_policy("auto")
        tempo_profile.use_store(None)


def test_c16_pool_worker_receives_the_grid_mode(tmp_path, monkeypatch):
    from djsync.analysis import pool

    seen = {}

    def fake(path, ffmpeg, **kw):
        seen.update(kw)
        return "ok"

    import djsync.analysis as A

    monkeypatch.setattr(A, "analyze_file", fake)
    assert pool._work("x.wav", None, True, "never") == "ok"
    assert seen == {"_in_worker": True, "_skip_spectrum": True, "grid_mode": "never"}


def test_c16_service_split_fixed_and_choice(tmp_path):
    from djsync.ui import tempo_grids as TG

    secs = [(0.3, 122.0, 0.3), (60.2, 140.0, 60.2)]
    beats = TG.split_beats(secs, 120000)
    assert {b[1] for b in beats} == {12200, 14000} and not TG.is_constant(beats)
    marks = TG.changes(beats)
    assert len(marks) == 1 and marks[0][1:] == (122.0, 140.0) and beats[marks[0][0]][2] == 60200
    assert TG.main_tempo(beats) == 122.0                         # 59,9 s contre 59,6 s : le plus long
    assert TG.main_tempo(TG.split_beats(secs, 130000)) == 140.0
    sel = TG.changes(beats)[0][0] + 4
    fixed, bpm = TG.TempoGridService.fixed_grid(beats, sel, 120000)
    assert TG.is_constant(fixed) and bpm == 122.0 and beats[sel][2] in [b[2] for b in fixed]
    tempo_profile.use_store(tmp_path / "tempo.json")
    try:
        f = tmp_path / "s.m4a"
        f.write_bytes(b"y" * 50)
        tempo_profile.remember(f, tempo_profile.TempoProfile("switch", 122, 140, 0.0, False, True, secs))
        track = NS(path=str(f), file_size=50, is_analysed=True)
        svc = TG.TempoGridService(NS(settings=NS(tempo_grid="never")))
        assert tempo_profile.policy() == "never"
        assert svc.split_grid(track, 120000) == beats
        svc.remember_choice(track, fixed)
        assert tempo_profile.known(f).choice == "fixed"
        svc.remember_choice(track, beats)
        assert tempo_profile.known(f).choice == ""
        assert TG.TempoGridService.pending(track, False) and not TG.TempoGridService.pending(track, True)
        assert not TG.TempoGridService.pending(track, None)       # pas encore lu : rien d'affirmé
    finally:
        tempo_profile.set_policy("auto")
        tempo_profile.use_store(None)


@pytest.mark.parametrize("lang,text", [
    ("fr", "Beatswitch détecté (122 → 140 BPM) · grille par passage"),
    ("en", "Beat switch detected (122 → 140 BPM) · grid per passage"),
])
def test_c16_library_text_and_validation_mark(tmp_path, lang, text):
    from djsync.i18n import get_language, set_language
    from djsync.ui import theme
    from djsync.ui.views import library_view as lv

    old = get_language()
    set_language(lang)
    tempo_profile.use_store(tmp_path / "tempo.json")
    try:
        p = tempo_profile.TempoProfile("switch", 122, 140, 0.0, False, True, [(0.3, 122.0, 0.3), (60.2, 140.0, 60.2)])
        assert lv.tempo_text(p) == text
        p.choice = "fixed"
        assert lv.tempo_text(p).endswith(lv.t("tempo.grid_fixed"))
        f = tmp_path / "a.mp3"
        f.write_bytes(b"z" * 10)
        tempo_profile.remember(f, tempo_profile.TempoProfile("live", 120, 124, 150.0, True))
        x = NS(path=str(f), file_size=10, is_analysed=True, content_id=7)
        assert lv.tempo_values(x, False)["bpm__dot"] == theme.WARN
        assert lv.tempo_values(x, False)["bpm__tip"].endswith(lv.t("tempo.to_check"))
        assert lv.tempo_values(x, True)["bpm__dot"] == theme.SKY
        view = NS(all_tracks=[x], _extras={7: {"grid_checked": False}})
        view._tempo_tracks = lambda: lv.LibraryView._tempo_tracks(view)
        assert lv.LibraryView._tempo_pending(view) == [x]
        view._extras = {7: {"grid_checked": True}}
        assert lv.LibraryView._tempo_pending(view) == []
    finally:
        tempo_profile.use_store(None)
        set_language(old)


def test_c16_settings_value_is_checked(tmp_path):
    from djsync.settings import Settings

    s = Settings()
    assert s.tempo_grid == "auto"
    s.tempo_grid = "sometimes"
    p = tmp_path / "settings.json"
    s.save(p)
    assert Settings.load(p).tempo_grid == "auto"


# ------------------------------------------------------------------ C16 : Grille et cues
pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v020 import demo  # noqa: E402,F401


def test_c16_grid_editor_fixed_and_per_passage_buttons(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.ui import tempo_grids as TG
    from djsync.ui.grid_editor import GridEditor

    lib = demo.ctrl.library
    track = lib.list_tracks()[0]
    secs = [(0.3, 122.0, 0.3), (60.2, 140.0, 60.2)]
    tempo_profile.use_store(tmp_path / "tempo.json")
    p = tempo_profile.TempoProfile("switch", 122, 140, 0.0, False, True, secs)
    monkeypatch.setattr(tempo_profile, "lookup", lambda _n, _s: p)
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        pump(demo, 1, lambda: False)
        ed.duration_ms = 120000
        ed.beats = TG.split_beats(secs, 120000)
        ed.original = list(ed.beats)
        ed._refresh_info()
        assert not ed.tempo_banner.isHidden() and "122" in ed.tempo_banner.text()
        assert not ed.fixed_grid_btn.isHidden() and ed.split_grid_btn.isHidden()
        assert "passage" in ed.info.text()
        ed.selected = 10
        ed._fixed_grid()
        assert TG.is_constant(ed.beats) and ed.save_btn.isEnabled()
        assert ed.fixed_grid_btn.isHidden() and not ed.split_grid_btn.isHidden()
        ed._split_grid()
        assert ed.beats == ed.original and not ed.save_btn.isEnabled()
        # dessin des changements de tempo (trait et « 122.0 → 140.0 ») sans erreur
        from PySide6.QtGui import QImage, QPainter

        ed.cursor_ms = 60200.0
        ed.start_ms = 58000.0
        img = QImage(800, 200, QImage.Format_RGB32)
        painter = QPainter(img)
        ed.paint(painter, 800, 200)
        painter.end()
        assert ed._changes_cache and ed._changes_cache[0][1:] == (122.0, 140.0)
    finally:
        ed._closed = True
        ed.deleteLater()
        tempo_profile.use_store(None)


def test_c16_settings_page_has_the_grid_choice(demo):  # noqa: F811
    view = demo.views.get("settings")
    if view is None:
        pytest.skip("settings view not built in the demo window")
    combo = view.tempo_grid
    assert [combo.itemData(i) for i in range(combo.count())] == ["auto", "never"]


# ------------------------------------------------------------------ A04 : en-tête de l'encodeur
def _mp3(tmp_path: Path, name: str, args: list) -> Path:
    src = write_wav(tmp_path / "src.wav", song(124.0, 0.2, 8, CHORDS, MINORS))
    out = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *args, str(out)], check=True)
    return out


def _as_lame(path: Path, method: int, lowpass_hz: int, kbps: int) -> Path:
    """Remplace l'en-tête « Lavc » d'FFmpeg par celui de LAME (mode, passe-bas, débit), comme l'écrit lame.exe."""
    data = bytearray(path.read_bytes())
    for tag in (b"Xing", b"Info"):
        x = data.find(tag)
        if x >= 0:
            break
    flags = int.from_bytes(data[x + 4:x + 8], "big")
    y = x + 8 + (4 if flags & 1 else 0) + (4 if flags & 2 else 0) + (100 if flags & 4 else 0) + (4 if flags & 8 else 0)
    data[y:y + 9] = b"LAME3.100"
    data[y + 9] = method
    data[y + 10] = lowpass_hz // 100
    data[y + 20] = min(255, kbps)
    path.write_bytes(bytes(data))
    return path


@pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg required")
def test_a04_reads_mp3_and_aac_encoders(tmp_path):
    from djsync.analysis import encoder as E

    cbr = _mp3(tmp_path, "cbr.mp3", ["-c:a", "libmp3lame", "-b:a", "320k"])
    info = E.read(cbr)
    assert info.codec == "mp3" and info.name.startswith("FFmpeg (Lavc") and info.mode == "CBR"
    assert info.kbps == 320 and info.lowpass == 0
    lame = E.read(_as_lame(cbr, 0x01, 20500, 320))
    assert (lame.name, lame.mode, lame.kbps, lame.lowpass) == ("LAME 3.100", "CBR", 320, 20500) and lame.lame
    vbr = E.read(_as_lame(_mp3(tmp_path, "v0.mp3", ["-c:a", "libmp3lame", "-q:a", "0"]), 0x04, 19500, 32))
    assert (vbr.mode, vbr.kbps, vbr.lowpass) == ("VBR", 0, 19500)
    m4a = tmp_path / "a.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp_path / "src.wav"), "-c:a", "aac", "-b:a", "256k",
                    str(m4a)], check=True)
    aac = E.read(m4a)
    assert aac.codec == "aac" and aac.name.startswith("FFmpeg (Lavf") and "AAC" in aac.profile and aac.kbps > 100
    assert E.read(tmp_path / "src.wav") is None and E.read(tmp_path / "missing.mp3") is None
    E.use_store(tmp_path / "encoder.json")
    try:
        E.remember(cbr, lame)
        E.use_store(tmp_path / "encoder.json")
        assert E.lookup("CBR.mp3", cbr.stat().st_size) == lame
    finally:
        E.use_store(None)


def test_a04_confidence_from_header_and_spectrum():
    from djsync.analysis.encoder import EncoderInfo
    from djsync.core.quality import AudioInfo

    lame320 = EncoderInfo("mp3", "LAME 3.100", "CBR", 320, 20500)
    ok = AudioInfo("mp3", 320, 44100, cutoff=20000, encoder=lame320)
    assert ok.header_verdict() == "confirm" and ok.confidence == "sure" and ok.real_kbps == 320 and not ok.fake
    low = AudioInfo("mp3", 320, 44100, cutoff=16500, encoder=lame320)            # faux 320, sûr
    assert low.header_verdict() == "fake" and low.confidence == "sure" and low.fake and low.real_kbps == 128
    mid = AudioInfo("mp3", 320, 44100, cutoff=18750, encoder=lame320)            # 192 sous un passe-bas de 20,5
    assert mid.header_verdict() == "fake"
    v0 = AudioInfo("mp3", 245, 44100, cutoff=19500, encoder=EncoderInfo("mp3", "LAME 3.100", "VBR", 0, 19500))
    assert v0.confidence == "sure" and v0.real_kbps == 256                       # VBR : la classe du spectre
    bare = AudioInfo("mp3", 320, 44100, cutoff=19500)                            # pas d'en-tête : spectre seul
    assert bare.confidence == "probable"
    claimed = AudioInfo("aac", 256, 44100, cutoff=16500)                          # 256 qui coupe à 16,5 : faux sûr
    assert claimed.confidence == "sure" and claimed.fake
    flac = AudioInfo("flac", 900, 44100, cutoff=22050)
    assert flac.confidence == "probable" and AudioInfo("mp3", 320, 44100).confidence == ""


@pytest.mark.parametrize("lang,sure,clue", [("fr", "(sûr)", "encodé par LAME 3.100"),
                                            ("en", "(sure)", "encoded by LAME 3.100")])
def test_a04_labels_and_clues(lang, sure, clue):
    from djsync.analysis.encoder import EncoderInfo
    from djsync.core.improve import confidence_suffix, measured_label, quality_clues
    from djsync.core.quality import AudioInfo
    from djsync.i18n import get_language, set_language

    old = get_language()
    set_language(lang)
    try:
        info = AudioInfo("mp3", 320, 44100, cutoff=20000, encoder=EncoderInfo("mp3", "LAME 3.100", "CBR", 320, 20500))
        assert measured_label(info) == f"≈ 320 {sure}" and confidence_suffix(info) == f" {sure}"
        tip = quality_clues(info)
        assert clue in tip and "20.5" in tip and "CBR" in tip
        bare = quality_clues(AudioInfo("flac", 900, 44100, cutoff=22050))
        assert bare.endswith(("spectrum only", "spectre seul"))
        assert quality_clues(AudioInfo("mp3", 320, 44100)) == ""
    finally:
        set_language(old)


def test_a04_library_column_uses_the_register(tmp_path):
    from djsync.analysis import encoder as E
    from djsync.analysis import spectrum as S
    from djsync.ui.views.library_view import extra_values

    S.use_store(tmp_path / "q.json")
    E.use_store(tmp_path / "e.json")
    try:
        f = tmp_path / "t.mp3"
        f.write_bytes(b"\0" * 2000)
        S.remember(f, 16500)
        E.remember(f, E.EncoderInfo("mp3", "LAME 3.100", "CBR", 320, 20500))
        x = NS(path=str(f), file_size=2000, file_type=1, bitrate=320, sample_rate=44100, source_url="", color=0,
               genre="", year=0, label="", rating=0, play_count=0, created="", comment="")
        v = extra_values(x)
        assert v["real"].startswith("≈ 128 kbps (") and "LAME 3.100" in v["real__tip"]
    finally:
        S.use_store(None)
        E.use_store(None)


# ------------------------------------------------------------------ A04 : spectrogramme
def test_a04_spectrogram_shows_the_cutoff(tmp_path):
    from djsync.analysis.spectrum import spectrogram
    from djsync.ui.spectrum_dialog import palette, to_image

    rng = np.random.default_rng(3)
    x = rng.normal(0, 0.2, SR * 6)
    spec = np.fft.rfft(x)
    spec[np.fft.rfftfreq(x.size, 1 / SR) > 16000] = 0                             # coupure à 16 kHz
    y = np.fft.irfft(spec, x.size).astype(np.float32)
    f = write_wav(tmp_path / "cut16.wav", y)
    db, sr, dur = spectrogram(f, columns=60)
    assert sr == 44100 and abs(dur - 6) < 0.1 and db.shape[1] <= 60 and db.max() == 0.0
    freqs = np.linspace(0, sr / 2, db.shape[0])
    assert db[(freqs > 12000) & (freqs < 15000)].mean() - db[freqs > 17500].mean() > 40
    img = to_image(db)
    assert (img.width(), img.height()) == (db.shape[1], db.shape[0])
    assert palette().shape == (256, 3) and tuple(palette()[0]) == (0, 0, 0)


def test_a04_track_menu_has_spectrum(demo):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.track_menu import track_entries

    track = demo.ctrl.library.list_tracks()[0]
    entries = [e for e in track_entries(demo, demo.ctrl, [track], where="library") if e]
    assert t("spectrum.open") in [e[0] for e in entries]
    many = [e for e in track_entries(demo, demo.ctrl, demo.ctrl.library.list_tracks()[:2], where="library") if e]
    assert t("spectrum.open") not in [e[0] for e in many]


def test_a04_spectrum_dialog_opens_and_draws(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.ui.spectrum_dialog import SpectrumDialog

    track = demo.ctrl.library.list_tracks()[0]
    db = np.full((1025, 40), -60.0)
    db[:700] = -10.0
    monkeypatch.setattr("djsync.analysis.spectrum.spectrogram", lambda *a, **k: (db, 44100, 200.0))
    monkeypatch.setattr("djsync.analysis.encoder.read_and_remember", lambda p: None)
    monkeypatch.setattr(demo.ctrl.library, "absolute_path", lambda _x: tmp_path / "exists.wav")
    (tmp_path / "exists.wav").write_bytes(b"x")
    dlg = SpectrumDialog(demo, demo.ctrl, track)
    try:
        pump(demo, 3, lambda: dlg.canvas.image is not None)
        assert dlg.canvas.image is not None and dlg.canvas.sr == 44100
        dlg.canvas.resize(600, 320)
        dlg.canvas.repaint()
    finally:
        dlg.close()
