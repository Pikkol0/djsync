"""1.3.2-rc.3 (B51) : la molette (ou le pavé tactile) fait défiler la page au lieu de changer la valeur
d'une liste, d'un compteur ou d'un curseur qui passe sous la souris.

Dans une page qui défile (Paramètres sur une seule page depuis C121), Qt envoie la molette au champ
survolé : on changeait un réglage sans le voir en descendant dans la page. Désormais, tant qu'on n'a pas
cliqué dans le champ (il n'a pas le focus), la molette va à la zone qui défile ; une fois cliqué, elle
change la valeur comme avant. Hors d'une zone qui défile, rien ne change.
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox

GUARDED = (QComboBox, QAbstractSpinBox, QAbstractSlider)


def _scroll_area(w: Any) -> Optional[QAbstractScrollArea]:
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QAbstractScrollArea) and not isinstance(p, GUARDED):
            return p
        p = p.parentWidget()
    return None


def _guarded(obj: Any) -> Optional[Any]:
    """Le champ concerné : l'objet lui-même, ou le champ dont il fait partie (zone de saisie d'un compteur)."""
    w = obj
    for _ in range(3):
        if w is None:
            return None
        if isinstance(w, GUARDED):
            # une barre de défilement est un curseur : on ne la bride pas
            if isinstance(w, QAbstractSlider) and w.metaObject().className() == "QScrollBar":
                return None
            return w
        w = w.parentWidget() if hasattr(w, "parentWidget") else None
    return None


class WheelGuard(QObject):
    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802 (API Qt)
        if event.type() != QEvent.Wheel:
            return False
        w = _guarded(obj)
        if w is None or w.hasFocus():
            return False
        area = _scroll_area(w)
        if area is None:
            return False
        if w.focusPolicy() == Qt.WheelFocus:             # la molette ne doit pas non plus donner le focus
            w.setFocusPolicy(Qt.StrongFocus)
        QApplication.sendEvent(area.viewport(), event)   # la page défile
        return True


_GUARD: Optional[WheelGuard] = None


def guard_children(root: Any) -> int:
    """Pose le filtre sur les listes, compteurs et curseurs de `root` (et leur zone de saisie) ; seulement
    eux, pour ne pas faire passer tous les évènements de l'application par Python. Renvoie leur nombre."""
    global _GUARD
    if _GUARD is None:
        _GUARD = WheelGuard(QApplication.instance())
    n = 0
    for cls in GUARDED:
        for w in root.findChildren(cls):
            if isinstance(w, QAbstractSlider) and w.metaObject().className() == "QScrollBar":
                continue
            if w.property("_wheel_guard"):
                continue
            w.setProperty("_wheel_guard", True)
            w.installEventFilter(_GUARD)
            if w.focusPolicy() == Qt.WheelFocus:
                w.setFocusPolicy(Qt.StrongFocus)
            for child in w.findChildren(QObject):         # zone de saisie d'un compteur, vue d'une liste
                if hasattr(child, "installEventFilter"):
                    child.installEventFilter(_GUARD)
            n += 1
    return n
