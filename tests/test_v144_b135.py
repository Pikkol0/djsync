"""1.4.4 (B135) : l'analyse par passage résout le chemin du son par la bibliothèque (clé « /Contents/… »,
Rekordbox « /PIONEER/… »), comme le reste de Grille et cues ; « Analyser ce passage » et Type ▸ Accélération
marchent alors sur une clé et sur les sons Rekordbox.
    pytest -q tests/test_v144_b135.py
"""
from __future__ import annotations

import dataclasses
import types
import wave
from pathlib import Path

import numpy as np
import pytest

from djsync.analysis import grid as G
from djsync.analysis import tempo_profile as TP
from djsync.db.library.tracks import TracksMixin
from djsync.db.local_library import LocalRekordboxLibrary

from .qt_util import pump
from .test_v122 import demo, usb  # noqa: F401  (fixtures)
from .test_v144_rc1_lot2_c221 import _c221_editor
from .test_v144_rc2 import SR, _clicks

DUR = 40.0


def _write_ramp(path: Path) -> None:
    """Rampe 120 → 132 BPM, 40 s, wav 16 bits mono."""
    path.parent.mkdir(parents=True, exist_ok=True)
    x = _clicks(TP.ramp_times(0.2, DUR, 120.0, 132.0), DUR)
    pcm = (np.clip(x, -1.0, 1.0) * 32000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


class _Lib:
    """Bibliothèque de la démo, sauf la résolution du chemin (celle de la clé ou de Rekordbox)."""

    def __init__(self, real, resolve):
        self._real, self._resolve = real, resolve

    def absolute_path(self, track_or_path):
        return self._resolve(track_or_path)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _key(tmp_path):
    root = tmp_path / "usb"
    _write_ramp(root / "Contents" / "Artist" / "ramp.wav")
    ns = types.SimpleNamespace(drive=types.SimpleNamespace(root=root))
    return "/Contents/Artist/ramp.wav", lambda tp: TracksMixin.absolute_path(ns, tp)


def _pioneer(tmp_path):
    share = tmp_path / "share"
    _write_ramp(share / "PIONEER" / "Imported" / "ramp.wav")
    ns = types.SimpleNamespace(share_dir=share)
    return "/PIONEER/Imported/ramp.wav", lambda tp: LocalRekordboxLibrary.absolute_path(ns, tp)


@pytest.mark.parametrize("where", [_key, _pioneer], ids=["key", "pioneer"])
def test_b135_passage_analysis_resolves_library_paths(demo, tmp_path, monkeypatch, where):  # noqa: F811
    rel, resolve = where(tmp_path)
    assert not Path(rel).is_file()                                   # le chemin enregistré seul est introuvable
    ed, track = _c221_editor(demo, tmp_path, G.extend([(1, 12000, 200)], int(DUR * 1000)))
    msgs = []
    try:
        monkeypatch.setattr(demo.ctrl, "library", _Lib(demo.ctrl.library, resolve))
        monkeypatch.setattr(demo.ctrl, "message", lambda kind, text, *a, **k: msgs.append((kind, text)))
        ed.track = dataclasses.replace(track, path=rel)
        ed.duration_ms = int(DUR * 1000)
        tools = ed.seg_tools
        tools.sync()
        assert tools._audio_path() == str(resolve(ed.track)) and Path(tools._audio_path()).is_file()
        # « Analyser ce passage » : le fichier est trouvé, une proposition arrive
        ed._move_cursor(20000.0)
        tools.analyse(False)
        assert pump(demo, 30, lambda: tools._analysing == 0)
        from djsync.i18n import t
        assert not any(text == t("grid.analyse_no_file") for _k, text in msgs)
        assert tools.proposal is not None
        # 1.4.4 (C242) : forme « Rampe » choisie, analyse selon la forme : rampe analysée et appliquée
        tools._clear_proposal()
        tools.shape_menu.setCurrentIndex(tools.shape_menu.findData("ramp"))
        before = list(ed.beats)
        tools.analyse(False, auto_apply=True)
        assert pump(demo, 30, lambda: tools._analysing == 0 and ed.beats != before)
        assert not any(text == t("grid.analyse_no_file") for _k, text in msgs)
        assert len({b[1] for b in ed.beats}) > 3                       # tempo qui monte : grille variable
    finally:
        ed._closed = True
        ed.deleteLater()
        TP.use_store(None)
