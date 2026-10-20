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
    window.reveal()
    return window


def close_window(window):
    window.close()
    window.deleteLater()
    pump(window, 0.05)
