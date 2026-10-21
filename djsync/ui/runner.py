"""Exécuteur de tâches : le réseau, la base et FFmpeg tournent hors du thread Tk.

L'interface (Qt, comme Tk avant) n'est PAS thread-safe : les threads de travail ne touchent jamais un widget. Ils
déposent un résultat dans une file ; un timer Tk (`after`) la vide dans le thread UI.

Ramasse-miettes (V0.2.0) : un widget détruit forme des cycles de références (polices, variables,
images Tk). Si le ramasse-miettes automatique de Python les libère dans un thread de travail, leur
`__del__` appelle Tcl depuis ce thread : blocage possible (constaté : téléchargement figé pendant un
import). Le ramassage automatique est donc coupé tant que l'interface tourne, et fait ici, dans le
thread UI, toutes les ~2 s.
"""
from __future__ import annotations

import gc
import logging
import queue
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

# Un pool par nature de travail : la base est sérialisée (1 thread), le reste en parallèle.
_POOLS = {"net": 6, "db": 1, "dl": 2, "cover": 4, "match": 3, "analysis": 1, "tools": 1}


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
        if self._ticks % 80 == 0:               # ~2 s : jeunes générations ; ~20 s : tout
            gc.collect(2 if self._ticks % 800 == 0 else 1)
        if not self._closed:
            self._schedule(self._interval, self._drain)

    def drain(self) -> None:
        """Vide la file tout de suite (tests)."""
        self._drain_once()

    def shutdown(self) -> None:
        self._closed = True
        gc.collect()
        if self._gc_was_enabled:
            gc.enable()
        for pool in self._pools.values():
            pool.shutdown(wait=False, cancel_futures=True)
