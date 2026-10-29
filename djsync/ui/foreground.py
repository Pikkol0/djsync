"""Fenêtre au premier plan sous Windows (1.3.2, B36).

Lancé depuis l'Explorateur, DJSync démarre dans un second processus (le lanceur DJSync.exe extrait puis
démarre l'application) : Windows ignore alors souvent `activateWindow()` et la fenêtre s'ouvre derrière
l'Explorateur. Le lanceur transmet désormais son droit au premier plan (AllowSetForegroundWindow) ; ici,
au cas où ce n'est pas suffisant (ancien lanceur, Windows qui refuse quand même), la fenêtre est mise un
instant « toujours au-dessus » puis relâchée, et si elle n'est toujours pas devant, son icône clignote
dans la barre des tâches. Sans effet ailleurs que sous Windows.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040
FLASHW_ALL, FLASHW_TIMERNOFG = 0x3, 0xC


def bring_to_front(hwnd: int, user32: Optional[Any] = None) -> str:
    """Renvoie « already », « raised » ou « flashed » (ou « skip » hors Windows)."""
    if user32 is None:
        if sys.platform != "win32":
            return "skip"
        import ctypes

        user32 = ctypes.windll.user32
    try:
        if user32.GetForegroundWindow() == hwnd:
            return "already"
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        user32.SetForegroundWindow(hwnd)
        if user32.GetForegroundWindow() == hwnd:
            log.info("Window brought to the front")
            return "raised"
        _flash(hwnd, user32)
        log.info("Window not allowed to the front: taskbar icon flashing")
        return "flashed"
    except Exception as exc:  # noqa: BLE001 - jamais bloquant au démarrage
        log.warning("Bring to front failed: %s", exc)
        return "error"


def _flash(hwnd: int, user32: Any) -> None:
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
    user32.FlashWindowEx(ctypes.byref(info))


def ensure_front(window: Any, later: Optional[Callable[[int, Callable[[], None]], None]] = None) -> None:
    """Après l'affichage de la fenêtre principale (Windows seulement), puis une seconde fois 300 ms plus
    tard : le temps que l'écran de démarrage se ferme."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except Exception:  # noqa: BLE001
        return
    bring_to_front(hwnd)
    if later is not None:
        later(300, lambda: bring_to_front(hwnd))
