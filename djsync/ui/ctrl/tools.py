"""Outils de bibliothèque V0.5.0 : copie de playlists vers une autre bibliothèque (clé USB ↔
ordinateur, clé ↔ clé) et complétion des métadonnées (Deezer) des sons déjà présents.

Ces tâches longues ont leur propre thread (« tools ») : la bibliothèque reste utilisable.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

from ...i18n import t

log = logging.getLogger(__name__)


class ToolsMixin:
    _tool_busy = False

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

    def _open_target(self, target: Any) -> Any:
        from ...db.local_library import LocalRekordbox, LocalRekordboxLibrary
        from ...db import RekordboxUsbLibrary

        s = self.settings
        common = dict(backup_keep=s.backup_keep, analyze=False, artwork=True,
                      ffmpeg_location=s.ffmpeg_location or None, key_notation=s.key_notation)
        if isinstance(target, LocalRekordbox):
            lib: Any = LocalRekordboxLibrary(target, **common).connect()
        else:
            lib = RekordboxUsbLibrary(target, contents_dir=s.contents_dir, pdb_sync=s.pdb_sync,
                                      pdb_allow_growth=s.pdb_allow_growth, **common).connect()
        lib.auto_cue = s.auto_cue
        return lib

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
        name = getattr(target, "label", "") or str(getattr(target, "root", target))
        last = [0.0]

        def progress(i: int, total: int, title: str) -> None:
            now = time.monotonic()
            if now - last[0] > 0.7 or i == total:
                last[0] = now
                self.dispatcher.post(self.message, "info", t("copy.progress", i=i, n=total, title=title))

        def work() -> Any:
            from ...db.transfer import copy_playlist

            dst = self._open_target(target)
            try:
                with dst.batch():
                    return copy_playlist(src, playlist_id, dst, progress)
            finally:
                dst.close()

        def done(res: Any) -> None:
            self._tool_busy = False
            kind = "warn" if res.failed else "ok"
            self.message(kind, t("copy.done", name=res.playlist_name, target=name, copied=res.copied,
                                 reused=res.reused, failed=res.failed))
            if res.problems:
                log.warning("Copy problems: %s", "; ".join(res.problems))
            if ok:
                ok(res)

        def fail(exc: BaseException) -> None:
            self._tool_busy = False
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
