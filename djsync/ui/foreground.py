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


def bring_to_front(hwnd: int, user32: Optional[Any] = None, kernel32: Optional[Any] = None) -> str:
    """Renvoie « already », « raised » ou « flashed » (ou « skip » hors Windows).

    1.3.2-rc.2 (B36) : Windows refusait encore le premier plan (journal de l'auteur : icône qui clignote).
    Deux méthodes documentées sont essayées en plus, dans l'ordre : s'attacher un instant à la file
    d'entrée de la fenêtre au premier plan (AttachThreadInput), puis une pression de la touche Alt
    simulée (Windows accorde le premier plan au processus qui a reçu la dernière entrée clavier)."""
    if user32 is None:
        if sys.platform != "win32":
            return "skip"
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
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
        for name, method in (("attach", _attach_raise), ("alt key", _alt_raise)):
            try:
                method(hwnd, user32, kernel32)
            except Exception as exc:  # noqa: BLE001 - méthode absente (tests) ou refusée
                log.debug("Bring to front (%s) failed: %s", name, exc)
                continue
            if user32.GetForegroundWindow() == hwnd:
                log.info("Window brought to the front (%s)", name)
                return "raised"
        _flash(hwnd, user32)
        log.info("Window not allowed to the front: taskbar icon flashing")
        return "flashed"
    except Exception as exc:  # noqa: BLE001 - jamais bloquant au démarrage
        log.warning("Bring to front failed: %s", exc)
        return "error"


def _attach_raise(hwnd: int, user32: Any, kernel32: Any) -> None:
    """S'attache à la file d'entrée du fil qui possède la fenêtre au premier plan, passe devant, se détache."""
    front = user32.GetForegroundWindow()
    theirs = user32.GetWindowThreadProcessId(front, None)
    ours = kernel32.GetCurrentThreadId()
    attached = bool(theirs) and theirs != ours and user32.AttachThreadInput(ours, theirs, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(ours, theirs, False)


VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002


def _alt_raise(hwnd: int, user32: Any, _kernel32: Any) -> None:
    """Alt pressée puis relâchée (sans effet visible), puis nouvelle demande de premier plan."""
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)


def _flash(hwnd: int, user32: Any) -> None:
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
    user32.FlashWindowEx(ctypes.byref(info))


def ensure_front(window: Any, later: Optional[Callable[[int, Callable[[], None]], None]] = None) -> None:
    """Après l'affichage de la fenêtre principale (Windows seulement), puis 300 ms et 1 s plus tard : le
    temps que l'écran de démarrage se ferme."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except Exception:  # noqa: BLE001
        return
    bring_to_front(hwnd)
    if later is not None:                     # 1.3.2-rc.2 (B36) : encore après la fermeture de l'écran de démarrage
        for delay in (300, 1000):
            later(delay, lambda: bring_to_front(hwnd))
