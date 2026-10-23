"""Rapports d'erreur automatiques (1.2.3).

Quand DJSync rencontre une erreur inattendue (exception non prévue, ou erreur affichée qui n'est pas
une situation normale comme « pas d'Internet » ou « Rekordbox est ouvert »), DJSync propose d'envoyer
un rapport à l'auteur par le même chemin que l'onglet Retours : type d'erreur, trace, état de la clé
(format, export.pdb) et fin du journal, chemins personnels masqués. Réglage (Paramètres) : demander
à chaque fois (défaut), toujours envoyer, ne jamais envoyer.

Garde-fous : un même problème n'est envoyé qu'une fois par jour, au plus MAX_PER_DAY rapports par jour,
envoi en arrière-plan qui n'interrompt jamais l'application et ne lève jamais d'exception.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

MAX_PER_DAY = 5


def expected(exc: BaseException) -> bool:
    """Situations normales, déjà expliquées à l'utilisateur : pas de rapport."""
    from ..db.errors import (
        AmbiguousDriveError, DatabaseLockedError, DriveNotFoundError, DuplicatePlaylistError, PlaylistNotFoundError,
        ReadOnlyError, TrackNotFoundError,
    )
    from .feedback import FeedbackError

    if isinstance(exc, (KeyboardInterrupt, SystemExit, FeedbackError, DriveNotFoundError, AmbiguousDriveError,
                        ReadOnlyError, DatabaseLockedError, PlaylistNotFoundError, TrackNotFoundError,
                        DuplicatePlaylistError)):
        return True
    try:
        from ..ui.controller import is_offline_error
    except Exception:  # noqa: BLE001 - sans interface : test réseau minimal
        def is_offline_error(e: Any) -> bool:
            return "connection" in str(e).lower() or "timed out" in str(e).lower()
    if is_offline_error(exc):
        return True
    low = str(exc).lower()
    return any(k in low for k in ("rekordbox is running", "close rekordbox", "no space left", "disk full",
                                  "cancelled", "canceled"))


def signature(exc: BaseException) -> str:
    """Même type d'erreur au même endroit du code = même problème."""
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    ours = [f for f in frames if "djsync" in f.filename.replace("\\", "/")]
    where = ours[-1] if ours else (frames[-1] if frames else None)
    key = f"{type(exc).__name__}|{Path(where.filename).name}:{where.name}:{where.lineno}" if where else type(exc).__name__
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class ErrorReporter:
    def __init__(self, state_path: Path, mode: Callable[[], str], context: Callable[[], Dict[str, Any]],
                 send: Optional[Callable[[Dict[str, Any]], None]] = None,
                 ask: Optional[Callable[[str, Callable[[bool], None]], None]] = None) -> None:
        """mode() -> "ask" | "always" | "never" ; context() -> {version, library, drive_root, client, log_dir}
        (lu au moment du rapport) ; ask(résumé, réponse) : demande à l'utilisateur (thread UI)."""
        self.state_path = Path(state_path)
        self.mode, self.context = mode, context
        self.ask = ask
        self._send = send
        self._lock = threading.Lock()
        self.sent: List[str] = []                 # signatures envoyées pendant cette session (tests, journal)

    # -------------------------------------------------------------- limites
    def _state(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        today = time.strftime("%Y-%m-%d")
        if data.get("day") != today:
            data = {"day": today, "sent": []}
        return data

    def _allow(self, sig: str) -> bool:
        with self._lock:
            st = self._state()
            if sig in st["sent"] or len(st["sent"]) >= MAX_PER_DAY:
                return False
            st["sent"].append(sig)
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                self.state_path.write_text(json.dumps(st), encoding="utf-8")
            except OSError:
                pass
            return True

    # -------------------------------------------------------------- envoi
    def report(self, exc: BaseException, where: str = "", wait: bool = False) -> bool:
        """Erreur inattendue, pas déjà signalée aujourd'hui : envoie (mode « always ») ou demande
        (mode « ask »). Renvoie True si un envoi est lancé ou proposé. Ne lève jamais."""
        try:
            import os

            mode = "never" if os.environ.get("DJSYNC_ERROR_REPORTS") == "off" else self.mode()
            if mode == "never" or expected(exc):
                return False
            sig = signature(exc)
            if not self._allow(sig):
                return False
            if mode == "ask" and self.ask is not None:
                summary = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"[:300]
                self.ask(summary, lambda yes: self._start(exc, sig, where, False) if yes else None)
                return True
            return self._start(exc, sig, where, wait)
        except Exception as e:  # noqa: BLE001 - un rapport ne doit jamais casser l'appli
            log.info("Error report not sent: %s", e)
            return False

    def _start(self, exc: BaseException, sig: str, where: str, wait: bool) -> bool:
        try:
            ctx = self.context()
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            if where:
                details = f"Where: {where}\n\n{details}"
            th = threading.Thread(target=self._post, args=(exc, sig, details, ctx), daemon=True,
                                  name="error-report")
            th.start()
            if wait:
                th.join(30)
            return True
        except Exception as e:  # noqa: BLE001 - un rapport ne doit jamais casser l'appli
            log.info("Error report not sent: %s", e)
            return False

    def _post(self, exc: BaseException, sig: str, details: str, ctx: Dict[str, Any]) -> None:
        from . import feedback as fb

        try:
            info = fb.system_info(str(ctx.get("version", "?")), str(ctx.get("library", "")))
            root = ctx.get("drive_root")
            report = fb.drive_report(Path(root) if root else None)
            log_text = fb.log_tail(Path(ctx["log_dir"])) if ctx.get("log_dir") else ""
            title = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
            payload = fb.build_error_payload(title, details, info, log_text, report, str(ctx.get("client", "")))
            (self._send or fb.send)(payload)
            self.sent.append(sig)
            log.info("Error report sent (%s)", sig)
        except Exception as e:  # noqa: BLE001
            log.info("Error report not sent: %s", e)


_REPORTER: Optional[ErrorReporter] = None


def install(reporter: ErrorReporter) -> None:
    """Rapports aussi pour les exceptions non rattrapées (slots Qt, threads)."""
    import sys

    global _REPORTER
    _REPORTER = reporter
    previous = sys.excepthook

    def hook(exc_type: Any, exc: BaseException, tb: Any) -> None:
        logging.getLogger("djsync").error("Unhandled exception", exc_info=(exc_type, exc, tb))
        if exc is not None:
            reporter.report(exc, "unhandled")
        if previous not in (None, sys.__excepthook__):
            previous(exc_type, exc, tb)

    sys.excepthook = hook

    def thread_hook(args: Any) -> None:
        if args.exc_value is not None and args.thread is not None and args.thread.name == "error-report":
            return
        logging.getLogger("djsync").error("Unhandled exception in thread %s", getattr(args.thread, "name", "?"),
                                          exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        if args.exc_value is not None:
            reporter.report(args.exc_value, f"thread {getattr(args.thread, 'name', '?')}")

    threading.excepthook = thread_hook


def current() -> Optional[ErrorReporter]:
    return _REPORTER
