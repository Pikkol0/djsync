"""Changement de langue sans redémarrage (fenêtre Qt réelle hors écran).

1.4.1 (C181) : sorti de test_ui_v020.py, dans son propre fichier pour que la CI (pytest-xdist, --dist
loadfile) le lance sur un autre processus que les autres tests d'interface : c'est un des deux plus longs."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402
from .test_ui_v020 import demo  # noqa: E402,F401


def test_language_rebuild(demo):  # noqa: F811
    demo.ctrl.settings.language = "fr"
    demo.ctrl._emit("rebuild_ui")
    pump(demo, 0.5)
    assert demo._nav["home"].text() == "Accueil" and demo.ctrl.has_library
    demo.show_view("library")
    assert pump(demo, 3, lambda: demo.views["library"].table.total == 10)
    demo.ctrl.settings.language = "en"
    demo.ctrl._emit("rebuild_ui")
    pump(demo, 0.3)
    assert demo._nav["home"].text() == "Home"
    assert not demo.errors
