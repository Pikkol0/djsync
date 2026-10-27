"""« Ajouter des fichiers… » (1.4.0, C26 sens A) et dossier surveillé (C10.3) : fichiers audio de
l'ordinateur ajoutés à la bibliothèque.

* formats : WAV, AIFF, FLAC, MP3, M4A / AAC (ceux que Rekordbox et les platines connaissent) ;
* titre, artiste, album, genre, label, année, n° de piste, ISRC lus dans les tags du fichier, sinon
  « Artiste - Titre » tiré du nom ;
* clé USB : le fichier est COPIÉ dans `Contents/Artiste/Album/` (l'original n'est jamais touché) ; un
  fichier déjà sur la clé est pris sur place ; bibliothèque de l'ordinateur : référencé là où il est.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger(__name__)

AUDIO_EXTS = (".wav", ".aiff", ".aif", ".flac", ".mp3", ".m4a", ".aac")
LOSSLESS_EXTS = (".wav", ".aiff", ".aif", ".flac")
_SPLIT = re.compile(r"\s+[-–—]\s+")


@dataclass
class ImportInfo:
    path: Path
    title: str
    artist: str = ""
    album: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)      # year, genre, label, track_no, isrc

    @property
    def lossless(self) -> bool:
        return self.path.suffix.lower() in LOSSLESS_EXTS


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS and not path.name.startswith(".")


def collect(paths: Iterable[Any], limit: int = 5000) -> List[Path]:
    """Fichiers audio parmi `paths` (dossiers parcourus), sans doublon, dans l'ordre donné."""
    out: List[Path] = []
    seen = set()

    def add(p: Path) -> None:
        key = str(p.resolve()).casefold() if p.exists() else str(p).casefold()
        if key not in seen and is_audio(p) and p.is_file():
            seen.add(key)
            out.append(p)

    for raw in paths:
        p = Path(str(raw))
        if p.is_dir():
            for folder, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for f in sorted(files):
                    add(Path(folder) / f)
                    if len(out) >= limit:
                        return out
        else:
            add(p)
        if len(out) >= limit:
            break
    return out


def _first(tags: Any, *keys: str) -> str:
    for k in keys:
        try:
            v = tags.get(k)
        except Exception:  # noqa: BLE001 - tags exotiques
            v = None
        if v:
            v = v[0] if isinstance(v, (list, tuple)) else v
            text = str(v).strip()
            if text:
                return text
    return ""


def read_info(path: Path) -> ImportInfo:
    """Infos du fichier : tags (mutagen, mode « easy »), sinon le nom « Artiste - Titre »."""
    path = Path(path)
    title = artist = album = genre = label = year = track = isrc = ""
    try:
        import mutagen

        audio = mutagen.File(str(path), easy=True)
        tags = getattr(audio, "tags", None) if audio is not None else None
        if tags is not None:
            title = _first(tags, "title")
            artist = _first(tags, "artist", "albumartist")
            album = _first(tags, "album")
            genre = _first(tags, "genre")
            label = _first(tags, "organization", "label", "publisher")
            year = _first(tags, "date", "originaldate", "year")
            track = _first(tags, "tracknumber")
            isrc = _first(tags, "isrc")
    except Exception as exc:  # noqa: BLE001 - fichier sans tags lisibles : le nom suffit
        log.info("Tags not read (%s): %s", path.name, exc)
    if not title:
        parts = _SPLIT.split(path.stem, maxsplit=1)
        if len(parts) == 2:
            artist, title = artist or parts[0].strip(), parts[1].strip()
        else:
            title = path.stem
    meta: Dict[str, Any] = {}
    if genre:
        meta["genre"] = genre
    if label:
        meta["label"] = label
    m = re.match(r"(\d{4})", year or "")
    if m:
        meta["year"] = int(m.group(1))
    m = re.match(r"(\d+)", track or "")
    if m:
        meta["track_no"] = int(m.group(1))
    if isrc:
        meta["isrc"] = isrc
    return ImportInfo(path, title.strip(), artist.strip(), album.strip() or None, meta)


def check_audio(path: Path) -> None:
    """Lève ValueError si le fichier n'est pas un fichier audio lisible (en-tête invalide, tronqué…)."""
    try:
        import mutagen

        audio = mutagen.File(str(path))
    except Exception as exc:  # noqa: BLE001 - mutagen lève des erreurs variées
        raise ValueError(f"Unreadable audio file: {exc}") from exc
    if audio is None or getattr(audio, "info", None) is None or not getattr(audio.info, "length", 0):
        raise ValueError("Unreadable audio file (invalid header).")


def _safe(name: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip()).strip(" .")
    return cleaned[:120] or fallback


def destination(lib: Any, info: ImportInfo) -> Path:
    """Où le fichier doit être dans la bibliothèque (voir l'en-tête du module)."""
    src = info.path
    if getattr(lib, "is_local", False):
        return src
    root = Path(lib.drive.root).resolve()
    try:
        src.resolve().relative_to(root)
        return src                                              # déjà sur la clé : sur place
    except ValueError:
        pass
    folder = lib.default_download_dir(info.artist or "Unknown Artist", info.album)
    name = _safe(src.stem, "track") + src.suffix.lower()
    target = Path(folder) / name
    k = 2
    while target.exists() and not _same_file(src, target):
        target = Path(folder) / f"{_safe(src.stem, 'track')} ({k}){src.suffix.lower()}"
        k += 1
    return target


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_size == b.stat().st_size and a.read_bytes()[:65536] == b.read_bytes()[:65536]
    except OSError:
        return False


def place(src: Path, target: Path) -> Path:
    """Copie `src` vers `target` (fichier temporaire puis renommage : jamais de fichier à moitié copié)."""
    if src.resolve() == target.resolve() or (target.exists() and _same_file(src, target)):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".djsync-part")
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return target


@dataclass
class ImportReport:
    added: List[Any] = field(default_factory=list)       # LibraryTrack
    already: List[Any] = field(default_factory=list)     # déjà dans la bibliothèque (même fichier)
    failed: List[tuple] = field(default_factory=list)    # (Path, raison)
    duplicates: List[Any] = field(default_factory=list)  # ajoutés mais qui ressemblent à un son présent


def import_files(lib: Any, files: Iterable[Path], playlist_ids: Iterable[int] = (),
                 progress: Optional[Any] = None, should_stop: Optional[Any] = None) -> ImportReport:
    """Ajoute les fichiers à la bibliothèque (sans analyse : elle suit, comme après un téléchargement)."""
    from ..core.duplicates import find_duplicate_groups

    files = list(files)
    pids = list(playlist_ids)
    report = ImportReport()
    try:
        before = {x.path.casefold(): x for x in lib.list_tracks()}
        known = list(before.values())
    except Exception:  # noqa: BLE001
        before, known = {}, []
    batch = lib.batch() if hasattr(lib, "batch") else None
    ctx = batch if batch is not None else _Null()
    with ctx:
        for i, f in enumerate(files, start=1):
            if should_stop and should_stop():
                break
            copied: Optional[Path] = None
            try:
                check_audio(f)                                # illisible : refusé avant toute copie
                info = read_info(f)
                dest = destination(lib, info)
                fresh = not dest.exists()
                target = place(f, dest)
                copied = target if fresh and target.resolve() != f.resolve() else None
                rel_key = _db_key(lib, target)
                was = before.get(rel_key)
                track = lib.add_track(target, info.title, info.artist, info.album, None, pids, meta=info.meta)
                copied = None
                if was is not None:
                    report.already.append(track)
                else:
                    report.added.append(track)
            except Exception as exc:  # noqa: BLE001 - un fichier illisible n'arrête pas les autres
                log.warning("Import failed (%s): %s", f, exc)
                if copied is not None:                        # copie faite pour rien : retirée
                    copied.unlink(missing_ok=True)
                    _prune(copied.parent, Path(getattr(lib, "contents_root", copied.parent)))
                report.failed.append((f, str(exc)[:200]))
            if progress:
                progress(i, len(files))
    if report.added and known:
        new_ids = {x.content_id for x in report.added}
        for g in find_duplicate_groups(known + report.added):
            if any(x.content_id in new_ids for x in g) and any(x.content_id not in new_ids for x in g):
                report.duplicates += [x for x in g if x.content_id in new_ids]
    return report


def _prune(folder: Path, stop: Path) -> None:
    """Retire les dossiers vides laissés par une copie annulée (jusqu'à `stop`, exclu)."""
    try:
        stop = stop.resolve()
        folder = folder.resolve()
        while folder != stop and stop in folder.parents and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    except OSError:
        pass


def _db_key(lib: Any, target: Path) -> str:
    if getattr(lib, "is_local", False):
        return target.resolve().as_posix().casefold()
    try:
        return ("/" + target.resolve().relative_to(Path(lib.drive.root).resolve()).as_posix()).casefold()
    except ValueError:
        return str(target).casefold()


class _Null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_a: Any) -> None:
        return None
