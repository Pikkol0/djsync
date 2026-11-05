"""Exécuteur de tâches : le réseau, la base et FFmpeg tournent hors du thread Tk.

L'interface (Qt, comme Tk avant) n'est PAS thread-safe : les threads de travail ne touchent jamais un widget. Ils
déposent un résultat dans une file ; un timer Tk (`after`) la vide dans le thread UI.

Ramasse-miettes (V0.2.0) : un widget détruit forme des cycles de références (polices, variables,
images Tk). Si le ramasse-miettes automatique de Python les libère dans un thread de travail, leur
`__del__` appelle Tcl depuis ce thread : blocage possible (constaté : téléchargement figé pendant un
import). Le ramassage automatique est donc coupé tant que l'interface tourne, et fait ici, dans le
thread UI, toutes les ~2 s.

1.3.2-rc.5 (B50) : le ramassage suit l'horloge, plus le nombre de tours de la file (sous Windows, pendant
la lecture, la file tourne moins souvent et un gros ramassage tombait toutes les ~8 s en figeant l'image et
le son). Petits ramassages fréquents (jeune génération toutes les 0,5 s, intermédiaire toutes les 5 s) ;
ramassage complet seulement hors lecture (toutes les 60 s), suivi d'un gel des objets durables
(`gc.freeze`) pour que les ramassages suivants ne les parcourent plus. Un ramassage de plus de 50 ms est
noté au journal.
"""
from __future__ import annotations

import gc
import logging
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

# Un pool par nature de travail : la base est sérialisée (1 thread), le reste en parallèle.
_POOLS = {"net": 6, "db": 1, "ui_db": 1, "dl": 2, "cover": 4, "match": 3, "analysis": 1, "tools": 1}

GC_YOUNG_S = 0.5          # 1.3.2-rc.5 (B50) : génération 0
GC_MIDDLE_S = 5.0         # génération 1
GC_FULL_S = 60.0          # tout, hors lecture (puis gel des objets durables)
GC_FULL_MAX_S = 600.0     # lecture sans fin : un ramassage complet quand même toutes les 10 min
GC_SLOW_MS = 50.0         # au-delà, noté au journal
GC_SLOW_LOGGED = 10       # les 10 premiers, puis un sur 50


class GcWatch:
    """1.3.2-rc.5 (B50) : durée de chaque ramassage (callback `gc.callbacks`). Rien n'est écrit pendant le
    ramassage ; les lents sont notés au journal ensuite, par `flush()` (thread UI)."""

    def __init__(self) -> None:
        self._t0 = 0.0
        self.slow: list = []
        self.count = 0
        gc.callbacks.append(self._cb)

    def _cb(self, phase: str, info: Dict[str, Any]) -> None:
        if phase == "start":
            self._t0 = time.perf_counter()
            return
        ms = (time.perf_counter() - self._t0) * 1000.0
        if ms >= GC_SLOW_MS:
            self.slow.append((info.get("generation"), ms, info.get("collected", 0)))

    def flush(self) -> None:
        while self.slow:
            gen, ms, collected = self.slow.pop(0)
            self.count += 1
            if self.count <= GC_SLOW_LOGGED or self.count % 50 == 0:
                log.info("Slow garbage collection: generation %s, %.0f ms, %s objects freed, %d frozen"
                         " [%d so far]", gen, ms, collected, gc.get_freeze_count(), self.count)

    def close(self) -> None:
        try:
            gc.callbacks.remove(self._cb)
        except ValueError:
            pass


class UiDispatcher:
    """V0.3.0 : indépendant de la bibliothèque d'interface. Le thread UI vide la file grâce à
    `schedule(ms, fn)` (Qt : QTimer.singleShot ; tests sans interface : appel manuel de `drain`)."""

    def __init__(self, schedule: Optional[Callable[[int, Callable[[], None]], None]] = None,
                 interval_ms: int = 25) -> None:
        if schedule is None:
            from PySide6.QtCore import QTimer

            def schedule(ms: int, fn: Callable[[], None]) -> None:
                QTimer.singleShot(ms, fn)
        self._schedule = schedule
        self._queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._pools: Dict[str, ThreadPoolExecutor] = {
            name: ThreadPoolExecutor(max_workers=n, thread_name_prefix=f"djsync-{name}")
            for name, n in _POOLS.items()
        }
        self._interval = interval_ms
        self._closed = False
        self._ticks = 0
        self._gc_was_enabled = gc.isenabled()
        gc.disable()
        now = time.monotonic()
        self._gc_at = {0: now, 1: now, 2: now}
        self.gc_busy: Callable[[], bool] = lambda: False     # 1.3.2-rc.5 (B50) : vrai pendant la lecture
        self._gc_watch = GcWatch()
        self._schedule(self._interval, self._drain)

    def call_later(self, ms: int, fn: Callable[[], None]) -> None:
        """Appelle fn() dans le thread UI après `ms` millisecondes."""
        if not self._closed:
            self._schedule(ms, fn)

    # ---- thread-safe : appelable depuis n'importe quel thread
    def post(self, fn: Callable[..., None], *args: Any) -> None:
        self._queue.put(lambda: fn(*args))

    def submit(
        self,
        fn: Callable[[], Any],
        on_ok: Optional[Callable[[Any], None]] = None,
        on_err: Optional[Callable[[BaseException], None]] = None,
        pool: str = "net",
    ) -> None:
        """Exécute fn() dans un thread ; on_ok(résultat) ou on_err(exception) dans le thread UI."""
        if self._closed:
            return

        def work() -> None:
            try:
                result = fn()
            except BaseException as exc:  # noqa: BLE001 - remonté à l'UI, jamais perdu
                log.debug("%s task failed", pool, exc_info=True)
                if on_err:
                    self.post(on_err, exc)
                else:
                    log.error("Unhandled error in a %s task: %s", pool, exc)
                return
            if on_ok:
                self.post(on_ok, result)

        self._pools[pool].submit(work)

    # ---- thread UI
    def _drain_once(self) -> None:
        for _ in range(60):  # borne par tick : l'UI reste fluide même si le flux est dense
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:  # noqa: BLE001
                log.exception("Error in a UI callback")

    def _drain(self) -> None:
        if self._closed:
            return
        self._drain_once()
        self._ticks += 1
        self._collect()
        if not self._closed:
            self._schedule(self._interval, self._drain)

    def _collect(self, now: Optional[float] = None) -> Optional[int]:
        """1.3.2-rc.5 (B50) : ramassage selon l'horloge ; renvoie la génération ramassée (ou None)."""
        if self._closed:                    # 1.4.0-rc.2 (B56) : plus rien après la fermeture (pas de gel tardif)
            return None
        now = time.monotonic() if now is None else now
        gen: Optional[int] = None
        since_full = now - self._gc_at[2]
        try:
            busy = bool(self.gc_busy())
        except Exception:  # noqa: BLE001 - simple indication
            busy = False
        if since_full >= GC_FULL_MAX_S or (since_full >= GC_FULL_S and not busy):
            gen = 2
        elif now - self._gc_at[1] >= GC_MIDDLE_S:
            gen = 1
        elif now - self._gc_at[0] >= GC_YOUNG_S:
            gen = 0
        if gen is None:
            return None
        if gen == 2:
            gc.unfreeze()                        # les objets gelés redeviennent visibles…
            gc.collect(2)
            gc.freeze()                          # … puis les survivants (bibliothèque, caches) sont mis à part
        else:
            gc.collect(gen)
        for g in range(gen + 1):
            self._gc_at[g] = now
        self._gc_watch.flush()
        return gen

    def drain(self) -> None:
        """Vide la file tout de suite (tests)."""
        self._drain_once()

    def shutdown(self) -> None:
        self._closed = True
        self._gc_watch.close()
        gc.unfreeze()
        gc.collect()
        if self._gc_was_enabled:
            gc.enable()
        for pool in self._pools.values():
            pool.shutdown(wait=False, cancel_futures=True)
