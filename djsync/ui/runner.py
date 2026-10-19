"""Exécuteur de tâches : le réseau, la base et FFmpeg tournent hors du thread Tk.

Tkinter n'est PAS thread-safe : les threads de travail ne touchent jamais un widget. Ils
déposent un résultat dans une file ; un timer Tk (`after`) la vide dans le thread UI.
"""
from __future__ import annotations

import logging
import queue
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

# Un pool par nature de travail : la base est sérialisée (1 thread), le reste en parallèle.
_POOLS = {"net": 6, "db": 1, "dl": 2, "cover": 4, "match": 3}


class UiDispatcher:
    def __init__(self, root: Any, interval_ms: int = 25) -> None:
        self._root = root
        self._queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._pools: Dict[str, ThreadPoolExecutor] = {
            name: ThreadPoolExecutor(max_workers=n, thread_name_prefix=f"djsync-{name}")
            for name, n in _POOLS.items()
        }
        self._interval = interval_ms
        self._closed = False
        self._root.after(self._interval, self._drain)

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
                log.debug("Tâche %s en erreur", pool, exc_info=True)
                if on_err:
                    self.post(on_err, exc)
                else:
                    log.error("Erreur non gérée dans une tâche %s : %s", pool, exc)
                return
            if on_ok:
                self.post(on_ok, result)

        self._pools[pool].submit(work)

    # ---- thread UI
    def _drain(self) -> None:
        for _ in range(60):  # borne par tick : l'UI reste fluide même si le flux est dense
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:  # noqa: BLE001
                log.exception("Erreur dans un callback d'interface")
        if not self._closed:
            self._root.after(self._interval, self._drain)

    def shutdown(self) -> None:
        self._closed = True
        for pool in self._pools.values():
            pool.shutdown(wait=False, cancel_futures=True)
