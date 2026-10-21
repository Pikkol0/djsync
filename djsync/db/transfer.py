"""Copie de playlists d'une bibliothèque à l'autre (V0.5.0) : clé USB ↔ Rekordbox de l'ordinateur,
ou clé ↔ clé.

Pour chaque son : le fichier audio est copié (sauf s'il est déjà dans la bibliothèque d'arrivée :
même lien d'origine, même artiste + titre, ou même fichier), puis ajouté à la collection et à une
playlist du même nom. L'ANALYSE EST REPRISE telle quelle (fichiers ANLZ : grille corrigée à la main,
formes d'onde Rekordbox) avec seulement le chemin du son réécrit — rien n'est recalculé. Un son qui
n'était pas analysé le sera à l'arrivée si l'analyse à l'ajout est activée.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.camelot import to_musical
from ..models import LibraryTrack
from .errors import LibraryError

log = logging.getLogger(__name__)

Progress = Callable[[int, int, str], None]


@dataclass
class TransferResult:
    playlist_id: int = 0
    playlist_name: str = ""
    copied: int = 0              # fichiers copiés
    reused: int = 0              # déjà présents à l'arrivée
    failed: int = 0
    problems: List[str] = field(default_factory=list)


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def _key(t: LibraryTrack) -> Tuple[str, str]:
    return _norm(t.artist), _norm(t.title)


def _analysis(src: Any, track: LibraryTrack) -> Dict[str, bytes]:
    if not track.analysis_path:
        return {}
    try:
        dat, ext = src.analysis_files(track)
    except Exception:  # noqa: BLE001
        return {}
    files: Dict[str, bytes] = {}
    for path in (dat, ext, dat.with_suffix(".2EX") if dat else None):
        if path is not None and path.is_file():
            try:
                files[path.suffix.upper()] = path.read_bytes()
            except OSError:
                pass
    return files if ".DAT" in files else {}


def _target_playlist(dst: Any, name: str) -> int:
    for p in dst.list_playlists():
        if p.name == name and p.is_editable and p.parent_id == 0:
            return p.playlist_id
    return dst.create_playlist(name).playlist_id


def _free_space(path: Path) -> int:
    for folder in (path, *path.parents):
        if folder.exists():
            return shutil.disk_usage(folder).free
    return 1 << 62


def copy_playlist(src: Any, playlist_id: int, dst: Any, on_progress: Optional[Progress] = None,
                  should_stop: Optional[Callable[[], bool]] = None) -> TransferResult:
    """Copie la playlist `playlist_id` de `src` vers `dst` (bibliothèques ouvertes en écriture)."""
    source = src.get_playlist(playlist_id)
    tracks = src.get_playlist_tracks(playlist_id)
    result = TransferResult(playlist_name=source.name)
    if not tracks:
        raise LibraryError("This playlist is empty.")

    existing = dst.list_tracks()
    by_key = {_key(t): t for t in existing}
    files = {Path(dst.absolute_path(t)).name.lower(): t for t in existing}

    plan: List[Tuple[LibraryTrack, Optional[LibraryTrack]]] = []
    needed = 0
    for t in tracks:
        found = (dst.find_by_source_url(t.source_url) if t.source_url else None) or by_key.get(_key(t))
        if found is None:
            name = Path(src.absolute_path(t)).name.lower()
            cand = files.get(name)
            if cand is not None and _norm(cand.title) == _norm(t.title):
                found = cand
        plan.append((t, found))
        if found is None:
            try:
                needed += Path(src.absolute_path(t)).stat().st_size
            except OSError:
                pass
    probe_dir = Path(dst.default_download_dir("DJSync", None))
    if needed and needed > _free_space(probe_dir) - 50 * 1024 * 1024:
        raise LibraryError(f"Not enough free space: {needed / 1e6:.0f} MB needed.")

    result.playlist_id = _target_playlist(dst, source.name)
    already = {t.content_id for t in dst.get_playlist_tracks(result.playlist_id)}
    ids: List[int] = []
    analyze = dst.analyze
    try:
        for i, (t, found) in enumerate(plan, 1):
            if should_stop and should_stop():
                break
            if on_progress:
                on_progress(i, len(plan), t.display_name)
            try:
                if found is not None:
                    result.reused += 1
                    ids.append(found.content_id)
                    continue
                src_file = Path(src.absolute_path(t))
                if not src_file.is_file():
                    raise LibraryError(f"file missing ({src_file.name})")
                folder = Path(dst.default_download_dir(t.artist or "Unknown", t.album))
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / src_file.name
                if not (target.is_file() and target.stat().st_size == src_file.stat().st_size):
                    tmp = target.with_name(target.name + ".djsync-tmp")
                    shutil.copyfile(src_file, tmp)
                    tmp.replace(target)
                anlz = _analysis(src, t)
                dst.analyze = analyze and not anlz          # analyse reprise : pas de recalcul
                added = dst.add_track(target, t.title, t.artist or "", t.album, t.source_url, [])
                if anlz and not added.is_analysed:
                    added = dst.import_analysis(added.content_id, anlz, t.bpm, to_musical(t.key))
                result.copied += 1
                ids.append(added.content_id)
            except Exception as exc:  # noqa: BLE001 - un son en échec n'arrête pas la copie
                result.failed += 1
                result.problems.append(f"{t.display_name}: {exc}")
                log.warning("Copy of %s failed: %s", t.display_name, exc)
    finally:
        dst.analyze = analyze
    new = [cid for cid in dict.fromkeys(ids) if cid not in already]
    if new:
        dst.add_to_playlist(result.playlist_id, new)
    return result
