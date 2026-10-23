"""Playlists par genre (1.2.2, C07, fiches S07-S09).

Désactivées par défaut. Une fois activées : un dossier « DJSync » ▸ « Genres » et une playlist par
groupe ; un groupe = un nom + un ou plusieurs genres (« Rap » = « Rap/Hip Hop » + « Rap français »),
modifiable à la main ; chaque groupe peut être coché ou non. Les playlists sont reconnues par leur
identifiant : on peut les déplacer ou les renommer dans la bibliothèque, elles restent tenues à jour.

Synchronisation : les sons du genre manquants sont AJOUTÉS (à la fin, du plus ancien au plus récent) ;
un son n'est RETIRÉ que si DJSync l'avait lui-même ajouté et qu'il n'est plus de ce genre (un son mis à
la main reste). Une playlist supprimée par l'utilisateur n'est pas recréée : son groupe est décoché.
Le genre est lu dans la bibliothèque (exportLibrary.db / master.db) ; les playlists, elles, vont aussi
dans export.pdb comme toutes les playlists de DJSync.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

ROOT_FOLDER = "DJSync"
GENRES_FOLDER = "Genres"
OTHERS = "Autres"
MIN_TRACKS = 3


def default_config() -> Dict[str, Any]:
    return {"enabled": False, "auto": True, "groups": [], "folder_id": 0, "root_id": 0}


def genre_counts(track_genres: Dict[int, str]) -> Counter:
    return Counter(g for g in track_genres.values() if g)


def default_groups(track_genres: Dict[int, str], min_tracks: int = MIN_TRACKS,
                   others_name: str = OTHERS) -> List[Dict[str, Any]]:
    """Un groupe par genre d'au moins `min_tracks` sons, les autres réunis dans « Autres »."""
    counts = genre_counts(track_genres)
    groups = [{"name": g, "genres": [g], "enabled": True, "playlist_id": 0, "members": []}
              for g, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())) if n >= min_tracks]
    rest = sorted((g for g, n in counts.items() if n < min_tracks), key=str.lower)
    if rest:
        groups.append({"name": others_name, "genres": rest, "enabled": True, "playlist_id": 0, "members": []})
    return groups


def merge_new_genres(config: Dict[str, Any], track_genres: Dict[int, str]) -> List[str]:
    """Genres présents dans la bibliothèque mais dans aucun groupe (proposés dans les réglages)."""
    known = {g.casefold() for grp in config.get("groups", []) for g in grp.get("genres", [])}
    return sorted({g for g in track_genres.values() if g and g.casefold() not in known}, key=str.lower)


@dataclass
class SyncReport:
    created: int = 0
    added: int = 0
    removed: int = 0
    disabled: List[str] = None        # groupes dont la playlist a été supprimée par l'utilisateur

    def __post_init__(self) -> None:
        self.disabled = self.disabled or []


def _folder(lib: Any, playlists: List[Any], wanted_id: int, name: str, parent_id: int) -> int:
    ids = {p.playlist_id: p for p in playlists}
    if wanted_id and wanted_id in ids and ids[wanted_id].is_folder:
        return wanted_id
    found = next((p for p in playlists if p.is_folder and p.name == name and p.parent_id == parent_id), None)
    if found is not None:
        return found.playlist_id
    created = lib.create_folder(name, parent_id)
    playlists.append(created)
    return created.playlist_id


def sync(lib: Any, config: Dict[str, Any], track_genres: Optional[Dict[int, str]] = None) -> SyncReport:
    """Crée / met à jour les playlists des groupes cochés. Modifie `config` (identifiants, membres).
    À appeler hors thread UI, bibliothèque modifiable (Rekordbox fermé pour le PC)."""
    report = SyncReport()
    if not config.get("enabled"):
        return report
    genres = track_genres if track_genres is not None else lib.track_genres()
    playlists = list(lib.list_playlists())
    existing = {p.playlist_id: p for p in playlists}
    order = {t.content_id: (t.date_added or "", t.content_id) for t in lib.list_tracks()}
    groups = [g for g in config.get("groups", []) if g.get("enabled")]
    batch = getattr(lib, "batch", None)
    ctx = batch() if batch is not None else _Null()
    with ctx:
        for grp in groups:
            pid = int(grp.get("playlist_id") or 0)
            if pid and pid not in existing:                 # supprimée par l'utilisateur : on n'insiste pas
                grp["enabled"], grp["playlist_id"], grp["members"] = False, 0, []
                report.disabled.append(grp.get("name", ""))
                continue
            wanted_genres = {g.casefold() for g in grp.get("genres", [])}
            wanted = {cid for cid, g in genres.items() if g and g.casefold() in wanted_genres and cid in order}
            if not pid:
                if not wanted:
                    continue                                 # pas de playlist vide
                root = _folder(lib, playlists, int(config.get("root_id") or 0), ROOT_FOLDER, 0)
                folder = _folder(lib, playlists, int(config.get("folder_id") or 0), GENRES_FOLDER, root)
                config["root_id"], config["folder_id"] = root, folder
                created = lib.create_playlist(grp.get("name") or "?", folder)
                pid = grp["playlist_id"] = created.playlist_id
                existing[pid] = created
                report.created += 1
            current = [t.content_id for t in lib.get_playlist_tracks(pid)]
            members = {int(c) for c in grp.get("members", [])}
            to_add = sorted(wanted - set(current), key=lambda c: order.get(c, ("", c)))
            to_remove = [c for c in current if c in members and c not in wanted]
            if to_remove:
                lib.remove_from_playlist(pid, to_remove)
                report.removed += len(to_remove)
            if to_add:
                lib.add_to_playlist(pid, to_add)
                report.added += len(to_add)
            grp["members"] = sorted(((members - set(to_remove)) | set(to_add)) & set(order))
    return report


def disable(lib: Any, config: Dict[str, Any], playlist_ids: Optional[Sequence[int]] = None) -> int:
    """Supprime les playlists données (toutes celles de DJSync si None) ; le dossier « Genres »
    (puis « DJSync ») aussi s'il est vide. Renvoie le nombre de playlists supprimées."""
    ids = None if playlist_ids is None else {int(i) for i in playlist_ids}
    if ids is None:
        ids = {int(g.get("playlist_id") or 0) for g in config.get("groups", [])} - {0}
    existing = {p.playlist_id for p in lib.list_playlists()}
    n = 0
    for pid in ids:
        if pid in existing:
            lib.delete_playlist(pid)
            n += 1
    for grp in config.get("groups", []):
        if int(grp.get("playlist_id") or 0) in ids:
            grp["playlist_id"], grp["members"] = 0, []
    playlists = lib.list_playlists()
    for key in ("folder_id", "root_id"):
        fid = int(config.get(key) or 0)
        if fid and not any(p.parent_id == fid for p in playlists) and any(p.playlist_id == fid for p in playlists):
            lib.delete_playlist(fid)
            playlists = lib.list_playlists()
            config[key] = 0
    return n


class _Null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None
