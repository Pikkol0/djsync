"""Zoom et couleur à chaud, petite fenêtre (fenêtre Qt réelle hors écran).

1.4.1 (C181) : sorti de test_ui_v020.py, dans son propre fichier pour que la CI (pytest-xdist, --dist
loadfile) le lance sur un autre processus que les autres tests d'interface : c'est un des deux plus longs."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v020 import demo  # noqa: E402,F401


def test_zoom_is_live_and_window_size_does_not_change_it(demo):  # noqa: F811
    from djsync.ui import theme

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total == 10)
    views_before = dict(demo.views)
    demo.ctrl.settings.zoom = 150
    demo.ctrl._emit("restyle")
    pump(demo, 0.3)
    assert theme.zoom() == 1.5 and demo.views == views_before          # pas de reconstruction
    assert lib.table.total == 10
    demo.ctrl.settings.zoom = 100
    demo.ctrl._emit("restyle")
    # petite fenêtre : barre latérale en icônes, le zoom ne bouge pas
    demo.resize(780, 520)
    assert pump(demo, 2, lambda: demo._compact is True)
    assert theme.zoom() == 1.0
    demo.resize(1280, 800)
    assert pump(demo, 2, lambda: demo._compact is False)
    # couleur : à chaud aussi, sans redémarrer (1.3.0-rc.4, B23 : les vues sont refaites dans la nouvelle couleur ;
    # 1.4.2, C144 : « green » est devenu une vraie couleur, « Vert franc »)
    from djsync.ui.palettes import PALETTES

    demo.ctrl.settings.theme = "green"
    demo.ctrl._emit("restyle")
    pump(demo, 0.3)
    assert theme.ACCENT.upper() == PALETTES["green"].upper() and demo.ctrl.has_library
    assert demo.views["library"] is not None and demo._current == "library"
    assert not demo.errors
