"""Outils communs des tests d'interface Qt : fenêtre réelle (offscreen), boucle d'évènements pompée."""
from __future__ import annotations

import sys
import time

import pytest

pytest.importorskip("PySide6")


def pump(app, seconds=1.0, until=None):
    """Fait tourner la boucle Qt jusqu'à `until()` (ou `seconds`)."""
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance()
    end = time.time() + seconds
    while time.time() < end:
        qapp.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return bool(until and until())


def find(app, cls):
    """Première fenêtre/enfant de type `cls` encore visible."""
    from PySide6.QtWidgets import QApplication

    for w in QApplication.topLevelWidgets():
        if isinstance(w, cls) and w.isVisible():
            return w
    hits = [w for w in app.findChildren(cls) if w.isVisible()]
    return hits[0] if hits else None


def make_window(settings, monkeypatch, size=(1280, 800)):
    """DJSyncApp affichée ; les exceptions des slots Qt sont collectées dans `window.errors`."""
    from djsync.ui.app import DJSyncApp

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append(a[1]))
    window = DJSyncApp(settings)
    window.errors = errors
    window.resize(*size)
    window._start_maximized = bool(settings.maximized)   # 1.3.2-rc.3 (C123) : taille fixe dans les tests
    window.reveal()
    return window


def close_window(window):
    """Ferme la fenêtre ET la détruit vraiment. 1.4.2 (C183) : sans boucle Qt lancée, deleteLater() n'était
    jamais exécuté (processEvents ne traite pas les destructions différées) : chaque test laissait ~940 widgets
    et ~20 fenêtres, et chaque feuille de style (zoom, couleur, langue) les reprenait tous : plusieurs minutes
    sur les derniers tests d'un processus. Les fenêtres de premier niveau restantes (pages, bulles) aussi."""
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    try:
        window.close()
        window.deleteLater()
    except RuntimeError:                           # déjà détruite (fermée par le test lui-même)
        pass
    pump(None, 0.05)
    for w in list(QApplication.topLevelWidgets()):
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:                       # déjà détruit
            pass
    for _i in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
