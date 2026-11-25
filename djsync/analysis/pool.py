"""Analyse sur plusieurs cœurs (1.4.3, A1-6).

Le calcul d'une analyse (`analyze_file` : décodage, tempo, tonalité, formes d'onde, spectre) tourne dans des
processus séparés : un fil Python ne rend pas assez la main pendant le calcul numpy pour que plusieurs fils
aillent plus vite. Le nombre de processus vaut cœurs − 1, 4 au plus ; 1 en mode léger (rien ne change alors :
le calcul reste dans le fil d'analyse).

Les écritures ne bougent pas : la boucle d'analyse (`db/analysis_flow.run_analysis`) annonce les sons à
venir (`Prefetch`), les processus les calculent d'avance, et chaque `analyze_file` du fil d'analyse prend le
résultat déjà prêt au lieu de recalculer. Le registre de la vraie qualité (spectrum) n'est écrit que par le
processus principal. Les processus restent ouverts entre deux lots et se ferment après une minute sans travail.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

MAX_WORKERS = 4
IDLE_CLOSE_S = 60.0

_light = False
_local = threading.local()
_lock = threading.Lock()
_executor: Any = None
_executor_size = 0
_last_use = 0.0
_broken = False


def set_light(light: bool) -> None:
    """Mode léger (C65) : un seul calcul à la fois, dans le fil d'analyse."""
    global _light
    _light = bool(light)


WORKER_MB = 250            # 1.4.4 (A09 B) : mémoire d'un processus d'analyse (mesure du 20/11 : ≈ 200 Mo)
KEEP_FREE_MB = 1024        # mémoire laissée libre pour l'app et le reste de l'ordinateur


def free_memory_mb() -> Optional[int]:
    try:
        import psutil

        return int(psutil.virtual_memory().available / 1e6)
    except Exception:  # noqa: BLE001 - psutil absent ou refusé : on ne limite pas
        log.debug("Free memory unknown", exc_info=True)
        return None


def worker_count(cores: Optional[int] = None, free_mb: Optional[int] = -1) -> int:
    """cœurs − 1, 4 au plus ; 1.4.4 (A09 B) : et pas plus que la mémoire libre ne le permet (≈ 250 Mo par
    processus, 1 Go laissé libre) ; au moins 1."""
    if _light or _broken or os.environ.get("DJSYNC_ANALYSIS_WORKERS") == "1":
        return 1
    env = os.environ.get("DJSYNC_ANALYSIS_WORKERS")
    if env and env.isdigit():
        return max(1, min(MAX_WORKERS, int(env)))
    cores = cores if cores is not None else (os.cpu_count() or 1)
    n = max(1, min(MAX_WORKERS, cores - 1))
    free_mb = free_memory_mb() if free_mb == -1 else free_mb
    if free_mb is not None:
        by_memory = max(1, (free_mb - KEEP_FREE_MB) // WORKER_MB)
        if by_memory < n:
            log.info("Analysis processes limited by free memory: %d instead of %d (%d MB free)", by_memory, n,
                     free_mb)
            n = int(by_memory)
    return n


def _work(path: str, ffmpeg: Optional[str], cutoff_known: bool, grid_mode: str = "auto") -> Any:
    """Dans le processus de calcul. `grid_mode` (C16) : décidé par le processus principal (réglage et choix par
    son), le processus de calcul ne lit pas le registre des tempos."""
    from . import analyze_file

    return analyze_file(path, ffmpeg, _in_worker=True, _skip_spectrum=cutoff_known, grid_mode=grid_mode)


def _get_executor(workers: int) -> Any:
    global _executor, _executor_size, _last_use
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    with _lock:
        _last_use = time.monotonic()
        if _executor is not None and _executor_size == workers:
            return _executor
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
        _executor = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
        _executor_size = workers
        threading.Thread(target=_idle_watch, name="analysis-pool-idle", daemon=True).start()
        log.info("Analysis on %d processes", workers)
        return _executor


def _idle_watch() -> None:
    global _executor
    while True:
        time.sleep(5.0)
        with _lock:
            if _executor is None:
                return
            busy = getattr(_local_registry, "active", 0)
            if not busy and time.monotonic() - _last_use > IDLE_CLOSE_S:
                _executor.shutdown(wait=False, cancel_futures=True)
                _executor = None
                return


class _Registry:
    active = 0


_local_registry = _Registry()


def shutdown() -> None:
    """Fermeture de l'application."""
    global _executor
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


class Prefetch:
    """Calcule d'avance les sons d'une liste (dans l'ordre), `ahead` à la fois au plus."""

    def __init__(self, paths: Sequence[Optional[Path]], ffmpeg: Optional[str], workers: int):
        self.paths = [str(p) if p else None for p in paths]
        self.ffmpeg = ffmpeg
        self.workers = workers
        self.ahead = workers * 2
        self.futures: Dict[str, Any] = {}
        self.order: List[Tuple[int, str]] = []
        self.next = 0
        self.at = 0
        self.executor = _get_executor(workers)

    def advance(self, index: int) -> None:
        """La boucle en est au son `index` : les calculs plus anciens et non repris sont abandonnés."""
        global _last_use
        self.at = index
        if _broken:
            return
        for i, p in [(i, p) for i, p in self.order if i < index]:
            fut = self.futures.pop(p, None)
            if fut is not None:
                fut.cancel()
        self.order = [(i, p) for i, p in self.order if i >= index]
        while self.next < len(self.paths) and len(self.order) < self.ahead:
            p = self.paths[self.next]
            if p and p not in self.futures:
                from .spectrum import known
                from .tempo_profile import grid_mode_for

                try:
                    self.futures[p] = self.executor.submit(_work, p, self.ffmpeg, known(p) is not None,
                                                           grid_mode_for(p))
                    self.order.append((self.next, p))
                except Exception:  # noqa: BLE001 - processus indisponibles : calcul dans le fil d'analyse
                    log.warning("Analysis processes unavailable, one track at a time", exc_info=True)
                    _mark_broken()
                    return
            self.next += 1
        _last_use = time.monotonic()

    def take(self, path: Any, ffmpeg: Optional[str]) -> Any:
        """Résultat déjà calculé pour `path` (exception du calcul relancée), sinon None."""
        fut = self.futures.pop(str(path), None)
        if fut is None or ffmpeg != self.ffmpeg:
            return None
        self.order = [(i, p) for i, p in self.order if p != str(path)]
        try:
            result = fut.result()
        except Exception as exc:  # noqa: BLE001
            from concurrent.futures.process import BrokenProcessPool

            if isinstance(exc, BrokenProcessPool):
                log.warning("Analysis process stopped (%s), one track at a time", exc)
                _mark_broken()
                return None
            raise
        _remember(path, result)
        return result

    def close(self) -> None:
        for fut in self.futures.values():
            fut.cancel()
        self.futures.clear()


def _mark_broken() -> None:
    global _broken, _executor
    _broken = True
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _remember(path: Any, result: Any) -> None:
    """Le registre de la vraie qualité n'est écrit que par le processus principal."""
    try:
        from .spectrum import known, remember

        if getattr(result, "lufs", None) is not None:          # 1.4.3 (C109)
            from .loudness import remember as remember_gain

            remember_gain(path, result.gain_db, result.peak_db)
        enc = getattr(result, "encoder", None)                                   # 1.4.3 (A04)
        if enc is not None:
            from .encoder import remember as remember_encoder

            remember_encoder(path, enc)
        profile = getattr(getattr(result, "grid", None), "profile", None)      # 1.4.3 (C69)
        if profile is not None:
            from .tempo_profile import remember as remember_tempo

            remember_tempo(path, profile)
        if result.cutoff is not None and known(path) is None:
            remember(path, result.cutoff)
        elif result.cutoff is None:
            result.cutoff = known(path)
    except Exception:  # noqa: BLE001
        log.debug("Ignored error in pool._remember", exc_info=True)


def current() -> Optional[Prefetch]:
    return getattr(_local, "prefetch", None)


class prefetching:
    """`with prefetching(paths, ffmpeg) as pre:` dans le fil d'analyse ; sans effet à 1 processus."""

    def __init__(self, paths: Sequence[Optional[Path]], ffmpeg: Optional[str]):
        self.paths = list(paths)
        self.ffmpeg = ffmpeg
        self.pre: Optional[Prefetch] = None

    def __enter__(self) -> Optional[Prefetch]:
        workers = worker_count()
        if workers > 1 and sum(1 for p in self.paths if p) > 1:
            try:
                self.pre = Prefetch(self.paths, self.ffmpeg, workers)
                _local.prefetch = self.pre
                _local_registry.active += 1
                self.pre.advance(0)
            except Exception:  # noqa: BLE001
                log.warning("Analysis processes unavailable, one track at a time", exc_info=True)
                _mark_broken()
                self.pre = None
                _local.prefetch = None
        return self.pre

    def __exit__(self, *exc: Any) -> None:
        if self.pre is not None:
            self.pre.close()
            _local_registry.active = max(0, _local_registry.active - 1)
        _local.prefetch = None
