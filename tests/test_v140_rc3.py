"""1.4.0-rc.3 : retours de tests de la rc.2."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401


# ------------------------------------------------------------------ B68 : Afficher dans l'explorateur
def test_b68_explorer_command_quotes_only_the_path():
    from djsync.ui.reveal import reveal_command

    cmd = reveal_command("C:/Users/DJ Test/Musique/Vald - Désaccordé.wav", "win32")
    assert cmd == 'explorer /select,"C:\\Users\\DJ Test\\Musique\\Vald - Désaccordé.wav"'


# ------------------------------------------------------------------ B69 : tableau à cases, hauteur fixe
def test_b69_quality_grid_has_cells_and_fixed_height(demo):  # noqa: F811
    v = demo.views["settings"]
    grid = v.quality_table
    assert len(grid.cells) == 18 and grid.cells[0].text().startswith("Source")
    assert grid.minimumHeight() == grid.maximumHeight() > 0


# ------------------------------------------------------------------ B71 : Espace occupé pendant le défilement
def test_b71_space_card_not_rebuilt_while_scrolling(demo, monkeypatch):  # noqa: F811
    v = demo.views["settings"]
    demo.show_view("settings")
    pump(demo, 0.5)
    calls = []
    monkeypatch.setattr(v.space, "compute", lambda *a, **k: calls.append(1))
    v._space_done = False
    bar = v.area.verticalScrollBar()
    bar.setValue(min(bar.maximum(), v.space_box.y()))
    for step in range(10):                                    # défilement autour de la carte
        bar.setValue(max(0, v.space_box.y() - 50 + step * 10))
        v._space_if_shown()
    assert len(calls) == 1


def test_b71_same_usage_is_not_redrawn():
    from djsync.ui.space_card import SpaceCard

    class U:
        parts, folders, free, total, library, music_elsewhere = {"other": 1}, {}, 1, 2, 0, {}

        def warnings(self):
            return []

    from PySide6.QtWidgets import QVBoxLayout, QWidget

    host = QWidget()
    card = SpaceCard(QVBoxLayout(host), type("C", (), {"settings": None, "on": lambda *a: None})())
    u = U()
    target = {"local": True, "key": "k"}
    card._show(u, target)
    rows = list(card._rows)
    card._show(u, target)
    assert card._rows == rows                                   # mêmes widgets, pas recréés


# ------------------------------------------------------------------ B70 / B73 : volet replié
def test_b70_b73_compact_sidebar_centred_and_rings(demo):  # noqa: F811
    demo.ctrl.settings.sidebar_compact = "on"
    demo._compact = None
    demo._update_compact()
    pump(demo, 0.3)
    b = demo._nav["settings"]
    assert "text-align: center" in b.styleSheet() and b.text() == ""
    assert demo.usb_ring.isVisibleTo(demo.usb_box) and not demo.usb_bar.isVisibleTo(demo.usb_box)
    assert demo.usb_ring.toolTip()
    demo.ctrl.settings.sidebar_compact = "off"
    demo._compact = None
    demo._update_compact()
    assert b.styleSheet() == "" and b.text()
    assert not demo.usb_ring.isVisibleTo(demo.usb_box)


# ------------------------------------------------------------------ B67 : faux sans perte (YouTube en WAV)
def _signal(sr, wall_hz, floor_db):
    import numpy as np

    rng = np.random.default_rng(1)
    n = sr * 8
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / sr)
    spec[f > wall_hz] = 0
    x = np.fft.irfft(spec, n)
    x /= np.abs(x).max()
    if floor_db is not None:                                    # plancher de bruit plat (dither) jusqu'en haut
        x = x + rng.standard_normal(n) * 10 ** (floor_db / 20)
    return x.astype("float32")


def test_b67_brick_wall_with_flat_noise_floor_is_not_lossless():
    from djsync.analysis.spectrum import LOSSLESS, cutoff_of, estimate

    yt = _signal(48000, 20000, -85)                             # mur à 20 kHz, bruit plat au-dessus
    c = cutoff_of(yt, 48000)
    assert 19500 <= c <= 20600 and estimate(c, 48000) != LOSSLESS
    real = _signal(44100, 22050, None)                          # vrai large bande jusqu'à Nyquist
    assert estimate(cutoff_of(real, 44100), 44100) == LOSSLESS


def test_b67_youtube_source_never_lossless():
    from djsync.analysis.spectrum import LOSSLESS
    from djsync.core.quality import AudioInfo

    wav = AudioInfo(codec="wav", sample_rate=44100, cutoff=22000, source="YouTube")
    assert wav.real_kbps == 320 and wav.fake and not wav.real_lossless
    sc = AudioInfo(codec="wav", sample_rate=44100, cutoff=22000, source="SoundCloud")   # original possible
    assert sc.real_kbps == LOSSLESS
