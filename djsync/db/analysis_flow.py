"""1.4.3 (A3-7, option B) : déroulé commun de l'analyse, de la grille et de la reprise d'analyse, pour la clé
(exportLibrary.db, SQL) et l'ordinateur (master.db, pyrekordbox).

Chaque bibliothèque garde ses lectures et ses écritures ; ce module porte ce qui était copié des deux côtés :
la boucle d'analyse (compteurs, progression, arrêt, lots), la lecture et la vérification d'une grille,
la sauvegarde des fichiers ANLZ avant une grille corrigée (et leur retour en cas d'échec), l'écriture des
fichiers d'une analyse reprise. Une correction faite ici vaut pour les deux.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .errors import LibraryError, TrackNotFoundError

log = logging.getLogger(__name__)

Progress = Callable[[int, int, Any, str], None]

# Issues d'une étape d'analyse
SKIP, DONE, FAILED, PENDING, PENDING_FAILED = "skip", "done", "failed", "pending", "pending_failed"


@dataclass
class Step:
    """Résultat de l'analyse d'un son : `kind` (voir plus haut), problème lisible, travail à enregistrer."""
    kind: str
    problem: str = ""
    job: Any = None


def run_analysis(content_ids: Sequence[int], step: Callable[[int], Step], get_track: Callable[[int], Any],
                 flush: Optional[Callable[[List[Any]], List[bool]]] = None, chunk: int = 8,
                 on_progress: Optional[Progress] = None,
                 should_stop: Optional[Callable[[], bool]] = None) -> Tuple[int, int, int]:
    """Analyse une liste de sons (doublons retirés, ordre gardé). `step(cid)` calcule (hors verrou) et
    renvoie un Step ; les Step « pending » sont enregistrés par `flush(jobs)` par lots de `chunk`
    (`flush` renvoie un booléen par travail). LibraryError dans `step` = échec expliqué.
    Renvoie (analysés, ignorés, échecs). Arrêt propre entre deux sons."""
    ids = list(dict.fromkeys(int(c) for c in content_ids))
    done = skipped = failed = 0
    pending: List[Tuple[Any, bool]] = []          # (travail, compte comme analysé)

    def save() -> None:
        nonlocal done, failed
        if not pending:
            return
        jobs = [j for j, _c in pending]
        ok = flush(jobs) if flush is not None else [True] * len(jobs)
        for (_j, counts), good in zip(pending, ok):
            if counts:
                if good:
                    done += 1
                else:
                    failed += 1
        pending.clear()

    for i, cid in enumerate(ids, start=1):
        if should_stop and should_stop():
            break
        problem = ""
        try:
            res = step(cid)
            problem = res.problem
            if res.kind == SKIP:
                skipped += 1
            elif res.kind == DONE:
                done += 1
            elif res.kind == FAILED:
                failed += 1
            elif res.kind == PENDING:
                pending.append((res.job, True))
            elif res.kind == PENDING_FAILED:                # analyse ratée, pochette quand même enregistrée
                failed += 1
                pending.append((res.job, False))
        except LibraryError as exc:
            failed += 1
            problem = str(exc)
        if len(pending) >= max(1, chunk):
            save()
        if on_progress:
            try:
                track = get_track(cid)
            except LibraryError:
                track = None
            on_progress(i, len(ids), track, problem)
    save()
    return done, skipped, failed


# ------------------------------------------------------------------------------------------- grille
def read_grid(content_id: int, row: Optional[Tuple[Any, Any]], absolute_path: Callable[[str], Path],
              native: Callable[[], bool]) -> Any:
    """Grille d'un son à partir de (chemin ANLZ, durée en s) lus par la bibliothèque (None = son inconnu)."""
    from ..analysis.anlz import read_beats
    from .library.metadata import BeatGrid

    if row is None:
        raise TrackNotFoundError(f"Track not found (id {content_id}).")
    anlz, length = row
    if not anlz:
        raise LibraryError("This track is not analysed yet: run the analysis first.")
    dat = absolute_path(anlz)
    try:
        beats = read_beats(dat.read_bytes())
    except (OSError, ValueError) as exc:
        raise LibraryError(f"Unreadable analysis file: {exc}") from exc
    if not beats:
        raise LibraryError("This track has no beat grid.")
    return BeatGrid(content_id, beats, int(length or 0) * 1000, dat, bool(native()))


def check_beats(beats: Sequence[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    out = [(int(n), int(t), int(ms)) for n, t, ms in beats]
    if len(out) < 2 or any(b[2] >= c[2] for b, c in zip(out, out[1:])):
        raise LibraryError("Invalid grid (at least two beats, increasing positions).")
    return out


@dataclass
class GridChange:
    """Fichiers d'une grille corrigée : originaux (gardés en copie), nouveaux contenus, BPM médian."""
    originals: Dict[Path, bytes]
    new: Dict[Path, bytes]
    bpmx100: int
    backup: Path
    written: List[Path] = field(default_factory=list)

    def write(self) -> None:
        from ..analysis.anlz import _write_atomic

        for f, data in self.new.items():
            _write_atomic(f, data)
            self.written.append(f)

    def restore(self) -> None:
        """Retour à l'état d'origine (après un échec de la base)."""
        from ..analysis.anlz import _write_atomic

        for f, data in self.originals.items():
            try:
                _write_atomic(f, data)
            except OSError:
                log.error("Could not restore %s (copy in %s)", f, self.backup)


def prepare_grid(grid: Any, beats: Sequence[Tuple[int, int, int]], backup_dir: Path, content_id: int) -> GridChange:
    """.DAT réécrit (PQTZ), grille étendue PQT2 retirée des .EXT/.2EX ; copie des originaux dans
    `backup_dir/anlz/<date>-<id>/` AVANT toute écriture (les plus anciennes copies sont élaguées)."""
    from ..analysis.anlz import drop_extended_grid, replace_beats
    from .library.metadata import ANLZ_BACKUPS_KEEP, prune_folders

    beats = check_beats(beats)
    files = [f for f in [grid.dat_path] + [grid.dat_path.with_suffix(s) for s in (".EXT", ".2EX")] if f.is_file()]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / "anlz" / f"{stamp}-{content_id}"
    backup.mkdir(parents=True, exist_ok=True)
    prune_folders(backup.parent, ANLZ_BACKUPS_KEEP)
    originals = {f: f.read_bytes() for f in files}
    for f, data in originals.items():
        (backup / f.name).write_bytes(data)
    new = {grid.dat_path: replace_beats(originals[grid.dat_path], beats)}
    for f in files[1:]:
        changed = drop_extended_grid(originals[f])
        if changed != originals[f]:
            new[f] = changed
    tempos = sorted(b[1] for b in beats)
    return GridChange(originals, new, tempos[len(tempos) // 2], backup)


# --------------------------------------------------------------------------------- analyse reprise
def write_imported(files: Dict[str, bytes], target_of: Callable[[str], Path], anlz_ref: str) -> List[Path]:
    """Écrit les fichiers d'une analyse reprise (chemin du son réécrit dedans) ; en cas d'échec, ceux déjà
    écrits sont retirés et l'erreur remonte. Renvoie les fichiers écrits."""
    from ..analysis.anlz import _write_atomic, retarget

    written: List[Path] = []
    try:
        for ext, data in files.items():
            target = target_of(ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(target, retarget(data, anlz_ref))
            written.append(target)
    except BaseException:
        discard(written)
        raise
    return written


def discard(paths: Sequence[Path]) -> None:
    for p in paths:
        try:
            Path(p).unlink()
        except OSError:
            log.debug("Not removed: %s", p, exc_info=True)
