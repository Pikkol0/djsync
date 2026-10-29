"""1.3.2 : vue d'ensemble dans la page Grille et cues, dessinée comme Rekordbox (C51) ; lecture plus
fluide, curseur rouge, position jamais en arrière (C52). Portage de la branche 1.4.0 (commit 20ea8ae)."""
from __future__ import annotations

import logging

import pytest

pytest.importorskip("PySide6")

from .test_ui_v024 import demo_grid  # noqa: E402,F401
from .test_v130rc3 import _open_grid  # noqa: E402


def test_overview_in_the_grid_page_and_red_cursor(demo_grid):  # noqa: F811
    from djsync.ui.cursor import CURSOR

    app = demo_grid
    ed = _open_grid(app)
    # C51 : vue d'ensemble dans la page, sous la forme d'onde zoomée et au-dessus des hot cues
    lay = ed.body
    idx = {w: i for i in range(lay.count()) for w in [lay.itemAt(i).widget()] if w is not None}
    assert idx[ed.canvas] < idx[ed.overview] < idx[ed.cue_panel]
    assert not hasattr(app.player_bar, "grid_overview")
    # C52 : curseur rouge vif, centré sur sa position (le halo ne la décale pas)
    ed.canvas.resize(800, 200)
    ed.go_to(ed.beats[20][2])
    img = ed.canvas.grab().toImage()
    dpr = img.devicePixelRatio()
    row = int(150 * dpr)
    reds = [x for x in range(img.width()) if img.pixelColor(x, row).name().upper() == CURSOR.upper()]
    assert reds and abs((min(reds) + max(reds)) / 2 / dpr - ed._x(ed.cursor_ms)) <= 1.0
    ed.close()


def test_overview_drawn_like_rekordbox(demo_grid):  # noqa: F811
    """Fond noir, forme d'onde posée en bas, étiquette carrée de couleur pour une hot cue, triangle pour
    une mémoire."""
    from djsync.analysis.cues import Cue
    from djsync.ui import grid_overview as O
    from djsync.ui import theme

    from .qt_util import pump

    app = demo_grid
    ed = _open_grid(app)
    assert pump(app, 8, lambda: ed.wave is not None)
    ed.cues = [Cue(1, int(ed.duration_ms * 0.25)), Cue(0, int(ed.duration_ms * 0.75))]
    ov = ed.overview
    ov.resize(600, ov.height())
    img = ov.grab().toImage()
    dpr = img.devicePixelRatio()
    W, H = img.width(), img.height()
    assert img.pixelColor(2, 1).name() == "#000000"                          # fond noir
    base = H - theme.px(O.MARK_H) * dpr
    lit = lambda y: sum(1 for x in range(0, W, 3) if img.pixelColor(x, int(y)).name() != "#000000")  # noqa: E731
    assert lit(base - 2 * dpr) > lit(theme.px(O.LABEL_H) * dpr + 2)          # posée en bas, monte vers le haut
    label = img.pixelColor(int(W * 0.25) + 2, int(2 * dpr))
    assert label.name() != "#000000" and label.red() > 150                    # étiquette A (rouge par défaut)
    tri = img.pixelColor(int(W * 0.75), H - 2)
    assert tri.red() > 150 and tri.green() < 120                              # triangle rouge d'une mémoire
    ed.close()


def test_waveform_cached_between_frames_and_adaptive_rate(demo_grid, monkeypatch):  # noqa: F811
    from .qt_util import pump

    app = demo_grid
    ed = _open_grid(app)
    assert pump(app, 8, lambda: ed.wave is not None)
    ed.canvas.resize(800, 200)
    ed.go_to(ed.beats[20][2])
    ed.canvas.grab()
    calls = []
    real = ed._paint_bands
    monkeypatch.setattr(ed, "_paint_bands", lambda *a: (calls.append(1), real(*a)))
    for _ in range(10):                              # lecture : la vue avance un peu à chaque image
        ed.start_ms += 15
        ed.canvas.grab()
    assert calls == []                               # recopie de l'image, pas de nouveau calcul
    ed.go_to(ed.beats[-8][2])                        # la vue sort de l'image : refaite une fois
    ed.canvas.grab()
    assert len(calls) == 1
    ed.canvas.paint_ms = 30.0                        # PC lent : moins d'images par seconde
    slow = [ed._frame_interval() for _ in range(5)][-1]
    assert slow >= 30
    ed.canvas.paint_ms = 1.0                         # PC rapide : retour à la cadence de l'écran
    fast = [ed._frame_interval() for _ in range(40)][-1]
    assert 7 <= fast <= 17
    ed.close()


def test_position_never_goes_back_while_playing():
    from djsync.ui.cursor import Monotonic

    m = Monotonic()
    assert [m(x) for x in (1000, 1016, 1010, 1030, 1025, 1050)] == [1000, 1016, 1016, 1030, 1030, 1050]
    assert m(400) == 400                             # vrai saut en arrière (boucle, retour voulu) : tout de suite
    m.reset()
    assert m(390) == 390


def test_player_scrolling_wave_copies_a_cached_image(demo_grid, monkeypatch):  # noqa: F811
    from djsync.ui.player_bar import ScrollingWave

    pos = {"s": 10.0}
    wave = ScrollingWave(lambda: pos["s"])
    wave.resize(600, 60)
    wave.set_data([(0.5, "#3366ff")] * 150 * 60, [(1, 12800, ms) for ms in range(0, 60000, 500)])
    wave._pos = 10.0
    wave.grab()
    first = wave._cache
    for k in range(10):
        wave._pos = 10.0 + 0.02 * k
        wave.grab()
    assert wave._cache is first                      # même image, juste décalée
    wave._pos = 40.0                                 # loin : refaite
    wave.grab()
    assert wave._cache is not first
    wave.deleteLater()


def test_frame_meter_logs_fps(monkeypatch, caplog):
    from djsync.ui import cursor

    now = {"t": 100.0}
    monkeypatch.setattr(cursor.time, "perf_counter", lambda: now["t"])
    m = cursor.FrameMeter("test")
    with caplog.at_level(logging.INFO, logger="djsync.ui.cursor"):
        for _ in range(700):
            m.frame(2.0)
            now["t"] += 1 / 60
    assert "Playback frames (test): 60 fps" in caplog.text
