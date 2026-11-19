"""Outils de bibliothèque V0.5.0 : copie de playlists vers une autre bibliothèque (clé USB ↔
ordinateur, clé ↔ clé) et complétion des métadonnées (Deezer) des sons déjà présents.

Ces tâches longues ont leur propre thread (« tools ») : la bibliothèque reste utilisable.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

from ...i18n import t

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransferEnd:
    """1.4.2 (C23) : une bibliothèque de départ ou d'arrivée d'un transfert."""
    key: str                # "local" ou racine de la clé
    name: str               # nom affiché, et « Nom (origine) » de « Garder les deux »
    target: Any             # UsbDrive ou LocalRekordbox
    is_local: bool = False
    active: bool = False    # c'est la bibliothèque ouverte


class ToolsMixin:
    _tool_busy = False
    _transfer_stop = False

    @property
    def tool_busy(self) -> bool:
        return self._tool_busy

    # ------------------------------------------------------------ copie de playlists
    def copy_targets(self) -> List[Tuple[str, Any]]:
        """Bibliothèques vers lesquelles copier (toutes sauf l'active) : [(nom affiché, cible)]."""
        out: List[Tuple[str, Any]] = []
        active = str(self.drive.root) if self.drive is not None else None
        if self.local is not None and str(self.local.root) != active:
            out.append((t("local.name"), self.local))
        for d in self.drives:
            if str(d.root) != active:
                out.append((d.label or str(d.root), d))
        return out

    def _open_target(self, target: Any, read_only: bool = False) -> Any:
        from ...db.local_library import LocalRekordbox, LocalRekordboxLibrary
        from ...db import RekordboxUsbLibrary

        s = self.settings
        common = dict(backup_keep=s.backup_keep, analyze=False, artwork=True, read_only=read_only,
                      ffmpeg_location=s.ffmpeg_location or None, key_notation=s.key_notation)
        if isinstance(target, LocalRekordbox):
            lib: Any = LocalRekordboxLibrary(target, **common).connect()
        else:
            lib = RekordboxUsbLibrary(target, contents_dir=s.contents_dir, pdb_sync=s.pdb_sync,
                                      pdb_allow_growth=s.pdb_allow_growth, **common).connect()
        lib.auto_cue = s.auto_cue
        return lib

    # ------------------------------------------------- 1.4.2 (C23) : transférer des playlists en lot
    def transfer_ends(self) -> List["TransferEnd"]:
        """Bibliothèques entre lesquelles transférer : l'ordinateur, puis chaque clé préparée."""
        out: List[TransferEnd] = []
        active = str(self.drive.db_path) if self.drive is not None and self.library is not None else ""
        if self.local is not None:
            out.append(TransferEnd("local", t("local.name"), self.local, True, str(self.local.db_path) == active))
        for d in self.drives:
            out.append(TransferEnd(str(d.root), d.label or str(d.root), d, False, str(d.db_path) == active))
        if self.drive is not None and self.library is not None and not any(e.active for e in out):
            d = self.drive                                    # bibliothèque ouverte à la main (lecteur forcé)
            local = bool(getattr(d, "is_local", False))
            out.append(TransferEnd("local" if local else str(d.root), t("local.name") if local
                                   else (d.label or str(d.root)), d, local, True))
        return out

    def _transfer_libs(self, ends: Sequence["TransferEnd"], read_only: bool) -> Tuple[dict, List[Any]]:
        """{clé: bibliothèque ouverte} : la bibliothèque active est reprise telle quelle, les autres sont
        ouvertes le temps du travail (à refermer : seconde valeur)."""
        libs: dict = {}
        opened: List[Any] = []
        try:
            for end in ends:
                if end.key in libs:
                    continue
                active = self.library is not None and self.drive is not None \
                    and str(self.drive.db_path) == str(end.target.db_path)
                if active:
                    libs[end.key] = self.library
                else:
                    libs[end.key] = self._open_target(end.target, read_only=read_only)
                    opened.append(libs[end.key])
        except BaseException:
            for lib in opened:
                lib.close()
            raise
        return libs, opened

    def transfer_playlists(self, end: "TransferEnd", ok: Callable[[Any], None],
                           err: Optional[Callable[[BaseException], None]] = None) -> None:
        """Arbre des playlists d'une bibliothèque (lecture seule)."""
        def work() -> Any:
            libs, opened = self._transfer_libs([end], read_only=True)
            try:
                return libs[end.key].list_playlists()
            finally:
                for lib in opened:
                    lib.close()

        self.dispatcher.submit(work, ok, err or self._on_error, pool="tools")

    def transfer_compare(self, jobs: Sequence[Tuple["TransferEnd", "TransferEnd", Sequence[int]]],
                         ok: Callable[[List[Any]], None], err: Optional[Callable[[BaseException], None]] = None,
                         progress: Optional[Callable[[int, int, str], None]] = None) -> None:
        """« Comparer » : une comparaison par sens, toutes calculées avant toute écriture. Ne fait que lire."""
        jobs = [(a, b, list(ids)) for a, b, ids in jobs]
        last = [0.0]

        def report(i: int, total: int, name: str) -> None:
            now = time.monotonic()
            if progress and (now - last[0] > 0.2 or i == total):
                last[0] = now
                self.dispatcher.post(progress, i, total, name)

        def work() -> List[Any]:
            from ...db import transfer

            libs, opened = self._transfer_libs([e for a, b, _ids in jobs for e in (a, b)], read_only=True)
            try:
                return [transfer.compare(libs[a.key], libs[b.key], ids, a.name, report) for a, b, ids in jobs]
            finally:
                for lib in opened:
                    lib.close()

        self.dispatcher.submit(work, ok, err or self._on_error, pool="tools")

    def transfer_apply(self, jobs: Sequence[Tuple["TransferEnd", "TransferEnd", Any]],
                       ok: Callable[[List[Any]], None], err: Optional[Callable[[BaseException], None]] = None,
                       progress: Optional[Callable[[int, int, str], None]] = None) -> bool:
        """« Appliquer » : un transfert à sens unique par comparaison, l'un après l'autre. Point de restauration
        de chaque clé touchée et sauvegarde de master.db avant (db/transfer.apply). False si un outil tourne."""
        if self._tool_busy:
            return False
        self._tool_busy = True
        self._transfer_stop = False
        jobs = list(jobs)
        totals = [sum(len(line.src_track_ids) for line in comp.lines if line.will_write) for _a, _b, comp in jobs]
        grand = sum(totals)
        task = self.tasks.start("transfer", "task.transfer", icon="copy", open="transfer", total=grand,
                                can_stop=True, stop=self.transfer_stop)
        last = [0.0]

        def work() -> List[Any]:
            from ...db import transfer

            results: List[Any] = []
            libs, opened = self._transfer_libs([e for a, b, _c in jobs for e in (a, b)], read_only=False)
            try:
                base = 0
                for (a, b, comp), total in zip(jobs, totals):
                    def report(i: int, _n: int, title: str, base: int = base) -> None:
                        now = time.monotonic()
                        if now - last[0] > 0.3 or base + i == grand:
                            last[0] = now
                            task.progress(base + i, grand, title)
                            if progress:
                                self.dispatcher.post(progress, base + i, grand, title)

                    if self._transfer_stop:
                        break
                    results.append(transfer.apply(libs[a.key], libs[b.key], comp, report,
                                                  lambda: self._transfer_stop,
                                                  backup_label=t("transfer.backup_label", origin=a.name)))
                    base += total
                    if results[-1].stopped:
                        break
            finally:
                for lib in opened:
                    lib.close()
            return results

        def done(results: List[Any]) -> None:
            self._tool_busy = False
            task.finish()
            for res in results:
                if res.problems:
                    log.warning("Transfer problems: %s", "; ".join(res.problems))
            self._emit("library")
            self.refresh_drives()
            ok(results)

        def fail(exc: BaseException) -> None:
            self._tool_busy = False
            task.fail(str(exc))
            self._emit("library")
            (err or self._on_error)(exc)

        self.dispatcher.submit(work, done, fail, pool="tools")
        return True

    def copy_stop(self) -> None:
        """1.4.3 (C210) : « Copier vers » arrêté après le son en cours (ce qui est copié reste)."""
        self._copy_stop = True
        self.tasks.mark_stopping("copy")

    def transfer_stop(self) -> None:
        """Arrêt demandé : pris en compte entre deux playlists (ce qui est fait reste cohérent)."""
        self._transfer_stop = True
        self.tasks.mark_stopping("transfer")

    # ------------------------------------------------- 1.4.2 (C24) : préparer une clé vierge
    def prepare_blank_drive(self, root: Any, ok: Optional[Callable[[Any], None]] = None,
                            err: Optional[Callable[[BaseException], None]] = None) -> None:
        """Pose le gabarit de clé vide (db/blank_key.py) sur une clé listée comme « vierge » par la détection,
        puis ouvre la clé. Tous les refus (PIONEER présent, disque système, système de fichiers) sont refaits
        ici, au moment d'écrire."""
        from ...db import blank_key, usb

        root = Path(str(root))

        def work() -> Any:
            listed = next((u for u in usb.find_unprepared_drives()
                           if _same_root(u.drive.root, root) and u.kind == "blank"), None)
            if listed is None:
                raise blank_key.PrepareError("not_listed", str(root))
            return blank_key.prepare_drive(listed.drive.root, listed.filesystem or None)

        def done(drive: Any) -> None:
            self.message("ok", t("prepare.done", name=drive.label or str(drive.root)))
            self.refresh_drives(then=lambda: self.connect(drive))
            if ok:
                ok(drive)

        def failed(exc: BaseException) -> None:
            if isinstance(exc, blank_key.PrepareError):
                log.warning("Drive not prepared: %s", exc)
                self.message("error", prepare_error_text(exc))
                self.refresh_drives()
            else:
                self._on_error(exc)
            if err:
                err(exc)

        self.message("info", t("prepare.running", name=str(root)))
        self.dispatcher.submit(work, done, failed, pool="db")

    def copy_playlist(self, playlist_id: int, target: Any, ok: Optional[Callable[[Any], None]] = None) -> None:
        src = self.library
        if src is None or self._tool_busy:
            return
        self._tool_busy = True
        self._copy_stop = False
        name = getattr(target, "label", "") or str(getattr(target, "root", target))
        last = [0.0]
        # 1.4.3 (C210) : une ligne dans « Tâches en cours » du volet (progression, arrêt) au lieu d'un message
        # réécrit à chaque son
        task = self.tasks.start("copy", "task.copy", icon="copy", can_stop=True, stop=self.copy_stop,
                                detail=name)

        def progress(i: int, total: int, title: str) -> None:
            now = time.monotonic()
            if now - last[0] > 0.3 or i == total:
                last[0] = now
                task.progress(i, total, title)

        def work() -> Any:
            from ...db.transfer import copy_playlist

            dst = self._open_target(target)
            try:
                with dst.batch():
                    return copy_playlist(src, playlist_id, dst, progress, lambda: self._copy_stop)
            finally:
                dst.close()

        def done(res: Any) -> None:
            self._tool_busy = False
            task.finish()
            kind = "warn" if res.failed else "ok"
            self.message(kind, t("copy.done", name=res.playlist_name, target=name, copied=res.copied,
                                 reused=res.reused, failed=res.failed))
            if res.problems:
                log.warning("Copy problems: %s", "; ".join(res.problems))
            if ok:
                ok(res)

        def fail(exc: BaseException) -> None:
            self._tool_busy = False
            task.fail(str(exc))
            self._on_error(exc)

        self.message("info", t("copy.start", target=name))
        self.dispatcher.submit(work, done, fail, pool="tools")

    # ------------------------------------------------------ métadonnées manquantes
    def complete_metadata(self, content_ids: Sequence[int], ok: Optional[Callable[[int], None]] = None) -> None:
        """Album, année, genre, label, n° de piste, ISRC (Deezer) pour les champs encore vides."""
        lib = self.library
        if lib is None or self._tool_busy or not content_ids:
            return
        self._tool_busy = True
        ids = list(content_ids)
        last = [0.0]

        def work() -> int:
            from ...core.metadata import lookup

            changed = 0
            with lib.batch():
                for i, cid in enumerate(ids, 1):
                    try:
                        tr = lib.get_track(cid)
                        found = lookup(tr.title, tr.artist or "", tr.duration_seconds)
                    except Exception as exc:  # noqa: BLE001 - hors ligne, son supprimé…
                        log.info("Metadata lookup failed for %s: %s", cid, exc)
                        continue
                    if found:
                        meta = {k: found.get(k) for k in ("year", "release_date", "genre", "label", "track_no", "isrc")}
                        try:
                            changed += bool(lib.complete_metadata(cid, meta, found.get("album")))
                        except Exception as exc:  # noqa: BLE001
                            log.warning("Metadata not saved for %s: %s", cid, exc)
                    now = time.monotonic()
                    if now - last[0] > 0.7:
                        last[0] = now
                        self.dispatcher.post(self.message, "info", t("meta.progress", i=i, n=len(ids)))
            return changed

        def done(n: int) -> None:
            self._tool_busy = False
            self.message("ok", t("meta.done", n=n, total=len(ids)))
            self._emit("library")
            if ok:
                ok(n)

        def fail(exc: BaseException) -> None:
            self._tool_busy = False
            self._on_error(exc)

        self.message("info", t("meta.start", n=len(ids)))
        self.dispatcher.submit(work, done, fail, pool="tools")


def _same_root(a: Any, b: Any) -> bool:
    import os

    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def prepare_error_text(exc: Any) -> str:
    """Message pour l'utilisateur d'un refus ou d'un échec de « Préparer cette clé » (C24)."""
    reason = getattr(exc, "reason", "")
    key = f"prepare.err_{reason}"
    text = t(key, fs=getattr(exc, "detail", ""), detail=getattr(exc, "detail", ""))
    return text if text != key else str(exc)
