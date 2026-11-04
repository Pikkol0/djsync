"""1.3.2-rc.6 : forme d'onde 3 bandes dessinée en bloc (B50) ; relevé limité (B50)."""
from __future__ import annotations

import time
import types

import numpy as np
import pytest


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _wave(n=20000):
    rng = np.random.default_rng(0)
    return types.SimpleNamespace(low=(rng.random(n) * 127).astype(np.uint8), mid=(rng.random(n) * 90).astype(np.uint8),
                                 high=(rng.random(n) * 50).astype(np.uint8), rate=150.0)


def test_band_image_is_fast_and_layered(qapp):
    from djsync.ui.grid_editor import BAND_COLORS, band_image

    t0 = time.perf_counter()
    img = band_image(_wave(), 1000, 0.6, 5760, 400, 220.0, 400 * 0.27 / 127)
    assert time.perf_counter() - t0 < 1.0               # avant : plusieurs secondes à cette largeur
    assert (img.width(), img.height()) == (5760, 400)
    assert img.pixelColor(100, 220).name() == BAND_COLORS[2]      # aigus devant, au centre
    assert img.pixelColor(100, 2).alpha() == 0                     # transparent hors de la forme d'onde


def test_band_image_outside_the_track_is_empty(qapp):
    from djsync.ui.grid_editor import band_image

    img = band_image(_wave(100), 10_000_000, 0.6, 50, 40, 20.0, 0.1)
    assert all(img.pixelColor(x, y).alpha() == 0 for x in range(0, 50, 7) for y in range(0, 40, 7))


def test_stall_reports_never_exceed_the_limit(tmp_path):
    from djsync.ui import stall as S

    w = S.StallWatch(tmp_path / "s.log")
    w.reports = S.MAX_REPORTS
    w._open().write(b"Timeout!\n")
    w.collect()
    assert w.reports == S.MAX_REPORTS
