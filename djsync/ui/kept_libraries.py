"""1.4.4 (A08, option A) : bascule rapide entre bibliothèques (service tenu par le contrôleur, règle A3-10).

Une seule bibliothèque active (`controller.library`) : elle seule écrit. Quand on en ouvre une autre, celle qu'on
quitte n'est plus refermée : elle reste ouverte « en arrière-plan » ici, et y revenir la reprend telle quelle
(pas de réouverture de la base, pas de reprise / contrôle d'ouverture ; les vues se relisent depuis l'objet gardé).

Gardée seulement si c'est sûr et utile :
* calme : aucune écriture, transaction, lot ni réécriture d'export.pdb en cours (la réécriture en attente est faite
  et le journal WAL vidé avant de la garder, comme à la fermeture) ; aucun téléchargement en cours vers elle ;
* master.db : jamais si Rekordbox est ouvert ; refermée dès que Rekordbox s'ouvre ;
* clé USB : refermée dès qu'elle disparaît (débranchée, éjectée) ;
* mémoire (PC avec peu de mémoire) : rien en mode léger (C65), rien sous `MIN_FREE_MB` de mémoire libre, une
  seule sous `TWO_FREE_MB`, deux au plus sinon (l'ordinateur et une clé, ou deux clés : le cas courant ; une
  bibliothèque gardée ≈ quelques dizaines de Mo, ≈ 100 Mo pour une très grosse master.db, soit moins qu'un
  processus d'analyse). La plus ancienne part en premier.

Une écriture qui viserait une bibliothèque gardée (tâche lancée juste avant la bascule) est refusée par la couche
des bases (`kept_background`), comme sur une bibliothèque fermée avant. La mémoire de l'app est notée dans le
journal (`djsync.memory`, comme memwatch) chaque fois que le nombre de bibliothèques ouvertes change.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)
mem_log = logging.getLogger("djsync.memory")

MAX_KEPT = 2               # bibliothèques gardées en plus de l'active, au plus
MIN_FREE_MB = 1024         # sous ce seuil de mémoire libre : rien n'est gardé (= KEEP_FREE_MB de l'analyse)
TWO_FREE_MB = 2048         # sous ce seuil : une seule gardée


def library_key(target: Any) -> str:
    """Identité d'une bibliothèque : chemin de sa base (exportLibrary.db ou master.db)."""
    try:
        path = getattr(target, "db_path", None) or target
        return os.path.normcase(os.path.abspath(str(path)))
    except Exception:  # noqa: BLE001
        return str(target)


def is_local(lib: Any) -> bool:
    return bool(getattr(lib, "is_local", False))


def configure(lib: Any, s: Any) -> None:
    """Réglages appliqués à une bibliothèque (ouverture ou reprise) ; mêmes valeurs que connect / apply_settings."""
    lib.backup_keep = s.backup_keep
    lib.analyze = False                      # 1.3.0-rc.3 (C32) : analyse par la file
    lib.artwork = True
    lib.ffmpeg_location = s.ffmpeg_location or None
    lib.key_notation = s.key_notation
    lib.auto_cue = s.auto_cue
    lib.native_parts = s.native_parts()
    lib.write_tags = s.write_tags                       # 1.4.3 (S05)
    if is_local(lib):
        lib.protect_foreign = s.protect_foreign         # 1.4.3 (A07, C156)
    else:
        lib.contents_dir = s.contents_dir.strip("/\\") or "Contents"
        lib.pdb_sync = s.pdb_sync
        lib.pdb_allow_growth = s.pdb_allow_growth
        lib.pdb_delay = 3.0                             # 1.4.3 (A1-2)


def app_memory_mb() -> Optional[float]:
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 1e6
    except Exception:  # noqa: BLE001 - psutil absent
        return None


@dataclass
class Kept:
    drive: Any
    lib: Any
    since: float = field(default_factory=time.monotonic)

    @property
    def name(self) -> str:
        return str(getattr(self.drive, "label", "") or getattr(self.drive, "root", "") or self.drive)


class KeptLibraries:
    """Bibliothèques ouvertes en arrière-plan (au plus `MAX_KEPT`). Thread-safe : `park` et `take` tournent dans
    le fil de la base (« db »), la surveillance dans le fil de l'interface."""

    def __init__(self, ctrl: Any) -> None:
        self.ctrl = ctrl
        self._kept: Dict[str, Kept] = {}
        self._lock = threading.Lock()
        self._last_count = -1

    # ------------------------------------------------------------------ état
    def __len__(self) -> int:
        return len(self._kept)

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._kept)

    def holds(self, target: Any) -> bool:
        return library_key(target) in self._kept

    def limit(self) -> Tuple[int, str]:
        """(nombre gardé au plus, raison si 0 ou réduit)."""
        try:
            from ..core.machine import light_active

            if light_active(self.ctrl.settings):
                return 0, "light mode"
        except Exception:  # noqa: BLE001
            log.debug("Light mode unknown", exc_info=True)
        try:
            from ..analysis.pool import free_memory_mb

            free = free_memory_mb()
        except Exception:  # noqa: BLE001
            free = None
        if free is not None and free < MIN_FREE_MB:
            return 0, f"low free memory ({free} MB)"
        if free is not None and free < TWO_FREE_MB:
            return min(1, MAX_KEPT), f"free memory {free} MB"
        return MAX_KEPT, ""

    # ------------------------------------------------------------------ bascule (fil « db »)
    def take(self, target: Any) -> Optional[Tuple[Any, Any]]:
        """(cible, bibliothèque) gardée pour `target`, retirée de la liste ; None s'il n'y en a pas ou si elle ne
        répond plus (elle est alors refermée, l'appelant ouvre comme avant)."""
        key = library_key(target)
        with self._lock:
            entry = self._kept.pop(key, None)
        if entry is None:
            return None
        lib = entry.lib
        problem = self._unhealthy(lib)
        if problem:
            log.info("Library %s kept in the background no longer usable (%s): reopened", entry.name, problem)
            self._close(lib)
            return None
        lib.kept_background = False
        log.info("Library %s taken back from the background (kept %.0f s, not reopened)", entry.name,
                 time.monotonic() - entry.since)
        return entry.drive, lib

    def park(self, drive: Any, lib: Any, active_key: str = "") -> bool:
        """La bibliothèque qu'on quitte : gardée si c'est sûr et s'il y a la place, refermée sinon (comme avant).
        True si elle est gardée."""
        name = str(getattr(drive, "label", "") or getattr(drive, "root", "") or drive)
        key = library_key(drive if drive is not None else lib)
        reason = "same library reopened" if key == active_key else self._refused(lib)
        if not reason:
            try:
                reason = self._quiet(lib)
            except Exception as exc:  # noqa: BLE001 - au moindre doute : fermée comme avant
                reason = f"not quiet: {exc}"
        if reason:
            log.info("Library %s closed, not kept in the background: %s", name, reason)
            self._close(lib)
            return False
        lib.kept_background = True
        with self._lock:
            old = self._kept.pop(key, None)
            self._kept[key] = Kept(drive, lib)
        if old is not None and old.lib is not lib:
            self._close(old.lib)
        log.info("Library %s kept open in the background", name)
        self.trim()
        return True

    def _refused(self, lib: Any) -> str:
        n, why = self.limit()
        if n <= 0:
            return why or "no room"
        if getattr(lib, "read_only", False):
            return "read-only"
        jobs = list(getattr(self.ctrl, "jobs", ()) or ())
        if any(getattr(j, "library", None) is lib and not j.is_finished for j in jobs):
            return "downloads in progress"
        if is_local(lib):
            from ..db import local_library as _local

            if _local.rekordbox_running():
                return "Rekordbox open"
        return ""

    @staticmethod
    def _quiet(lib: Any) -> str:
        """Met la bibliothèque au repos (aucune écriture en attente, aucun verrou) ; "" si c'est fait."""
        lock = getattr(lib, "_lock", None)
        if lock is not None and not lock.acquire(blocking=False):
            return "busy"
        try:
            if getattr(lib, "_batch_depth", 0) or getattr(lib, "_writing", 0):
                return "write in progress"
            if is_local(lib):
                db = getattr(lib, "_db", None)
                if db is None:
                    return "not open"
                db.session.rollback()                         # aucune transaction gardée sur master.db
                reader = lib.__dict__.pop("_reader", None)    # 2e connexion (B52) : rouverte à la demande
                if reader is not None:
                    try:
                        reader.close()
                    except Exception:  # noqa: BLE001
                        log.debug("Ignored error closing the read connection", exc_info=True)
                return ""
            conn = getattr(lib, "_conn", None)
            if conn is None:
                return "not open"
            if not Path(lib.db_path).is_file():
                return "drive gone"
            if getattr(conn, "in_transaction", False):
                return "transaction open"
            if hasattr(lib, "pdb_flush_now"):
                lib.pdb_flush_now()                           # export.pdb en attente : écrit maintenant
            if getattr(lib, "_pdb_dirty", False) and hasattr(lib, "_pdb_flush"):
                lib._pdb_flush()
            if hasattr(lib, "_checkpoint"):
                lib._checkpoint()                             # journal WAL vidé, comme à la fermeture
            if hasattr(lib, "_close_reader"):
                lib._close_reader()                           # 2e connexion (A3-6) : rouverte à la demande
            return ""
        finally:
            if lock is not None:
                lock.release()

    @staticmethod
    def _unhealthy(lib: Any) -> str:
        if is_local(lib):
            return "" if getattr(lib, "_db", None) is not None else "closed"
        try:
            if not Path(lib.db_path).is_file():
                return "drive gone"
        except OSError:
            return "drive gone"
        alive = getattr(lib, "alive", None)
        if alive is not None and alive() is not True:          # retirée puis rebranchée (B28) : connexion morte
            return "database no longer readable"
        return ""

    # ------------------------------------------------------------------ fermetures
    def _close(self, lib: Any) -> None:
        try:
            lib.close()
        except Exception:  # noqa: BLE001
            log.warning("Closing a library kept in the background failed", exc_info=True)

    def drop(self, keys: List[str], reason: str) -> None:
        """Referme tout de suite les bibliothèques gardées `keys` (fil « db »)."""
        out: List[Kept] = []
        with self._lock:
            for k in keys:
                entry = self._kept.pop(k, None)
                if entry is not None:
                    out.append(entry)
        if not out:
            return
        for entry in out:
            log.info("Library %s kept in the background closed: %s", entry.name, reason)

        def work() -> None:
            for entry in out:
                self._close(entry.lib)

        self._submit(work, self.note)

    def trim(self, limit: Optional[int] = None) -> None:
        """Plus que la limite (mode léger activé, mémoire libre en baisse) : les plus anciennes sont refermées."""
        n = self.limit()[0] if limit is None else limit
        with self._lock:
            extra = sorted(self._kept.items(), key=lambda kv: kv[1].since)[:max(0, len(self._kept) - n)]
        if extra:
            self.drop([k for k, _e in extra], "too many libraries open for the memory available")

    def watch(self, rekordbox_open: bool) -> None:
        """Surveillance des clés (toutes les 4 s, fil de l'interface) : Rekordbox ouvert → master.db gardée
        refermée ; clé disparue → refermée ; limite de mémoire revue. Rien à faire sans bibliothèque gardée."""
        if not self._kept:
            return
        with self._lock:
            entries = list(self._kept.items())
        if rekordbox_open:
            self.drop([k for k, e in entries if is_local(e.lib)], "Rekordbox open")
            entries = [(k, e) for k, e in entries if not is_local(e.lib)]

        def probe() -> Tuple[List[str], int]:
            gone = []
            for k, e in entries:
                try:
                    if not is_local(e.lib) and not Path(e.lib.db_path).is_file():
                        gone.append(k)
                except OSError:
                    gone.append(k)
            return gone, self.limit()[0]

        def ok(result: Tuple[List[str], int]) -> None:
            gone, n = result
            if gone:
                self.drop(gone, "drive removed")
            self.trim(n)

        try:
            self.ctrl.dispatcher.submit(probe, ok, lambda exc: log.debug("Kept libraries check: %s", exc),
                                        pool="net")
        except Exception:  # noqa: BLE001
            log.debug("Kept libraries check not run", exc_info=True)

    def close_all(self) -> None:
        """Fermeture de l'app : tout est refermé, tout de suite (fil appelant)."""
        with self._lock:
            out = list(self._kept.values())
            self._kept.clear()
        for entry in out:
            entry.lib.kept_background = False
            self._close(entry.lib)
        if out:
            log.info("Libraries kept in the background closed at exit: %d", len(out))

    def _submit(self, work: Callable[[], None], then: Callable[[], None]) -> None:
        try:
            self.ctrl.dispatcher.submit(work, lambda _r=None: then(), lambda exc: log.warning(
                "Closing a library kept in the background: %s", exc), pool="db")
        except Exception:  # noqa: BLE001 - répartiteur arrêté : tout de suite
            work()
            then()

    # ------------------------------------------------------------------ journal
    def note(self) -> None:
        """Mémoire de l'app quand le nombre de bibliothèques ouvertes change (mesure demandée par l'auteur) ;
        appelé par le contrôleur après chaque ouverture / fermeture, et après une fermeture d'ici."""
        count = len(self._kept) + (1 if getattr(self.ctrl, "library", None) is not None else 0)
        if count == self._last_count:
            return
        self._last_count = count
        rss = app_memory_mb()
        names = ", ".join(e.name for e in list(self._kept.values()))
        mem_log.info("Open libraries: %d (%d kept in the background%s); Memory: RSS %s MB", count, len(self._kept),
                     f": {names}" if names else "", f"{rss:.0f}" if rss is not None else "?")
