"""1.3.2-rc.5 (B50) : trouver ce qui fige l'application pendant la lecture.

Pendant la lecture de Grille et cues, un minuteur de `faulthandler` (fil en C, qui n'a pas besoin de Python)
est réarmé régulièrement. Si l'interface ne le réarme pas à temps (elle est bloquée), il écrit la pile de
chaque fil dans `djsync-stall.log`, même si le blocage vient d'un calcul qui tient Python (ramasse-miettes,
bibliothèque en C). Dès que l'interface repart, ce texte est recopié dans `djsync.log` (donc joint aux
Retours ▸ Envoyer mes logs). Au plus quelques relevés par session, pour ne pas noyer le journal.
"""
from __future__ import annotations

import faulthandler
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

STALL_FILE = "djsync-stall.log"
STALL_S = 0.35            # blocage au-delà duquel les piles sont écrites
REARM_S = 0.1             # réarmé au plus toutes les 100 ms (un fil C recréé à chaque fois)
MAX_REPORTS = 5           # relevés par session
MAX_CHARS = 8000


class StallWatch:
    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            from ..settings import settings_dir

            path = settings_dir() / STALL_FILE
        self.path = Path(path)
        self._stream: Optional[Any] = None
        self._armed_at = 0.0
        self._armed = False
        self.reports = 0

    def _open(self) -> Optional[Any]:
        if self._stream is None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._stream = open(self.path, "wb", buffering=0)  # noqa: SIM115 - gardé ouvert (écrit en C)
            except OSError as exc:
                log.debug("Stall log not available: %s", exc)
                self.reports = MAX_REPORTS
        return self._stream

    def tick(self) -> None:
        """Appelé à chaque image de la lecture : relève un éventuel blocage, puis réarme le minuteur."""
        if self.reports >= MAX_REPORTS:
            return
        self.collect()
        now = time.monotonic()
        if self._armed and now - self._armed_at < REARM_S:
            return
        stream = self._open()
        if stream is None:
            return
        try:
            faulthandler.dump_traceback_later(STALL_S, repeat=False, file=stream, exit=False)
        except (RuntimeError, ValueError, OSError) as exc:
            log.debug("Stall watch: %s", exc)
            self.reports = MAX_REPORTS
            return
        self._armed, self._armed_at = True, now

    def collect(self) -> None:
        """Recopie dans le journal ce que le minuteur a écrit pendant un blocage."""
        stream = self._stream
        if stream is None:
            return
        try:
            fd = stream.fileno()
            if not os.fstat(fd).st_size:
                return
            text = self.path.read_text(encoding="utf-8", errors="replace")[-MAX_CHARS:]
            os.ftruncate(fd, 0)                  # faulthandler écrit à la position du fichier : on la remet à 0
            os.lseek(fd, 0, os.SEEK_SET)
        except (OSError, ValueError):
            return
        if text.strip() and self.reports < MAX_REPORTS:   # rc.6 : jamais plus de MAX_REPORTS (« [6/5] »)
            self.reports += 1
            log.info("UI blocked for more than %.0f ms during playback; what each thread was doing [%d/%d]:\n%s",
                     STALL_S * 1000, self.reports, MAX_REPORTS, text.rstrip())

    def stop(self) -> None:
        if self._armed:
            try:
                faulthandler.cancel_dump_traceback_later()
            except Exception:  # noqa: BLE001
                pass
            self._armed = False
        self.collect()


_WATCH: Optional[StallWatch] = None


def watch() -> StallWatch:
    global _WATCH
    if _WATCH is None:
        _WATCH = StallWatch()
    return _WATCH
