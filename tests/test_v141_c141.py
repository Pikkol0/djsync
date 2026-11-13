"""1.4.1 (C141, D14) : or et argent en dégradé métallique, avec un reflet qui passe."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture
def table(qapp_offscreen=None):
    from PySide6.QtWidgets import QApplication

    from djsync.ui import theme
    from djsync.ui.table import Column, Row, TrackTable

    app = QApplication.instance() or QApplication([])
    tbl = TrackTable(None, [Column("q", "Q", 220), Column("t", "T", 160)])
    rows = [Row("a", {"q": "FLAC 16/44", "q__color": theme.GOLD, "t": "x"}),
            Row("b", {"q": "MP3 320", "q__color": theme.SILVER, "t": "y"}),
            Row("c", {"q": "≈ 192 kbps", "q__color": theme.LEVELS["fair"], "t": "z"}),
            Row("d", {"q": "neutre", "t": "w"})]
    tbl.set_rows(rows)
    tbl.setStyleSheet("QTableView { background: #111111; alternate-background-color: #111111; }")
    tbl.resize(420, 200)
    tbl.show()
    tbl.clearSelection()
    tbl.setCurrentIndex(tbl.model().index(-1, -1))
    app.processEvents()
    yield tbl
    tbl.close()


def _spread(img, y0, y1, x0=2, x1=215):
    """Écart de luminosité maximale entre le bord gauche du texte et son milieu : un dégradé
    (sombre au bord, clair au milieu) donne un écart net, une couleur unie presque rien."""
    cols = {}
    for x in range(x0, x1):
        v = max(img.pixelColor(x, y).value() for y in range(y0, y1))
        if v > 90:
            cols[x] = v
    xs = sorted(cols)
    if len(xs) < 10:
        return 0
    left = max(cols[x] for x in xs[: len(xs) // 6])
    mid = max(cols[x] for x in xs[2 * len(xs) // 5: 3 * len(xs) // 5])
    return mid - left


def test_kind_and_reflection_timing():
    from djsync.ui import shine, theme

    assert shine.kind_of(theme.GOLD) == "gold" and shine.kind_of(theme.SILVER.lower()) == "silver"
    assert shine.kind_of(theme.LEVELS["fair"]) is None and shine.kind_of(None) is None
    assert shine.reflection(0.0, 0) == 0.0 and shine.reflection(shine.SWEEP + 0.1, 0) is None
    assert shine.reflection(0.0, 1) != shine.reflection(0.0, 0)            # décalé d'une ligne à l'autre
    shine.set_enabled(False)
    try:
        assert shine.reflection(0.0, 0) is None
    finally:
        shine.set_enabled(True)


def test_gold_and_silver_drawn_as_metal_not_flat(table):
    from djsync.ui import shine

    assert table.has_shine()
    shine.set_enabled(False)                         # dégradé fixe, sans reflet
    img = table.viewport().grab().toImage()
    h = table.rowHeight(0)
    gold, silver, fair = _spread(img, 2, h - 2), _spread(img, h + 2, 2 * h - 2), _spread(img, 2 * h + 2, 3 * h - 2)
    shine.set_enabled(True)
    assert gold >= 25 and silver >= 25              # métal : plus clair au milieu qu'au bord
    assert abs(fair) < 15                            # le jaune « ≈ 192 » reste une couleur unie


def test_clock_runs_only_with_shiny_visible_tables(table, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from djsync.ui import shine

    clock = shine.Clock.get()
    assert clock._timer.isActive()
    monkeypatch.setattr(QApplication, "applicationState", lambda self=None: Qt.ApplicationActive)
    monkeypatch.setattr(shine.time, "monotonic", lambda: 0.0)               # reflet sur la ligne 0
    before = clock.ticks
    clock._tick()
    assert clock.ticks > before
    monkeypatch.setattr(shine.time, "monotonic", lambda: 3.0)               # hors passage pour les lignes 0-3
    before = clock.ticks
    clock._tick()
    assert clock.ticks == before
    shine.set_enabled(False)
    assert not clock._timer.isActive()
    shine.set_enabled(True)
    assert clock._timer.isActive()
