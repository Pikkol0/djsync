"""1.4.4 (B128 option C, A09 A) : relevé de la mémoire et du processeur de l'app, dans le journal.

But : trouver ce qui gonfle (rapport du 22/11 : mémoire épuisée après ~2 h, objets suivis par le ramasse-miettes
de 265 000 à 1,15 million) et mesurer l'app (repos, usage, pic) sans outil à installer.

Toutes les 5 minutes, une ligne « Memory: RSS … MB (peak …), CPU … %, objects … » ; quand la mémoire a grossi de
plus de 15 % depuis le dernier relevé détaillé (ou toutes les 30 minutes), les 8 types d'objets les plus nombreux
et ceux qui ont le plus augmenté. Un fil en arrière-plan, quelques millisecondes par relevé (le détail par type
compte les objets suivis : ≈ 0,1 s pour un million). Rien n'est envoyé : le journal reste sur l'ordinateur,
joint seulement par « Envoyer mes logs » ou un rapport d'erreur.
"""
from __future__ import annotations

import gc
import logging
import os
import threading
import time
from collections import Counter
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("djsync.memory")

PERIOD_S = 300
DETAIL_EVERY_S = 1800
GROWTH = 0.15


def type_counts() -> Counter:
    return Counter(type(o).__name__ for o in gc.get_objects())


def top_growth(before: Dict[str, int], after: Dict[str, int], n: int = 8) -> List[Tuple[str, int]]:
    """Types qui ont le plus augmenté (nom, +nombre), les plus forts d'abord."""
    diff = [(k, after.get(k, 0) - before.get(k, 0)) for k in after]
    return sorted([d for d in diff if d[1] > 0], key=lambda d: -d[1])[:n]


class MemWatch:
    def __init__(self, period_s: float = PERIOD_S) -> None:
        self.period_s = period_s
        self.peak_mb = 0.0
        self._last_detail_mb = 0.0
        self._last_detail_at = 0.0
        self._last_types: Dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc = None

    def _process(self):
        if self._proc is None:
            import psutil

            self._proc = psutil.Process(os.getpid())
            self._proc.cpu_percent(None)                 # premier appel : référence
        return self._proc

    def sample(self, detail: Optional[bool] = None) -> str:
        """Un relevé ; renvoie la ligne écrite (aussi pour les tests et les rapports d'erreur)."""
        try:
            proc = self._process()
            rss = proc.memory_info().rss / 1e6
            cpu = proc.cpu_percent(None)
        except Exception:  # noqa: BLE001 - psutil absent : seulement les objets
            rss, cpu = 0.0, 0.0
        self.peak_mb = max(self.peak_mb, rss)
        tracked = len(gc.get_objects())
        line = f"Memory: RSS {rss:.0f} MB (peak {self.peak_mb:.0f} MB), CPU {cpu:.0f} %, objects {tracked}, " \
               f"gc counts {gc.get_count()}"
        now = time.monotonic()
        if detail is None:
            detail = (not self._last_detail_at or now - self._last_detail_at >= DETAIL_EVERY_S
                      or (self._last_detail_mb and rss > self._last_detail_mb * (1 + GROWTH)))
        if detail:
            counts = type_counts()
            top = ", ".join(f"{k} {v}" for k, v in counts.most_common(8))
            line += f"; top: {top}"
            if self._last_types:
                grown = ", ".join(f"{k} +{v}" for k, v in top_growth(self._last_types, counts))
                if grown:
                    line += f"; grown: {grown}"
            self._last_types = dict(counts)
            self._last_detail_mb, self._last_detail_at = rss, now
        log.info(line)
        return line

    def _run(self) -> None:
        while not self._stop.wait(self.period_s):
            try:
                self.sample()
            except Exception:  # noqa: BLE001 - un relevé raté ne doit rien arrêter
                log.debug("Memory sample failed", exc_info=True)

    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            self.sample(detail=True)                     # relevé de départ (app au repos)
        except Exception:  # noqa: BLE001
            log.debug("First memory sample failed", exc_info=True)
        self._thread = threading.Thread(target=self._run, name="memwatch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
