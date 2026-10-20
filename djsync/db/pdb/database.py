"""Opérations de haut niveau sur export.pdb, exprimées en CLÉS NATURELLES.

Les identifiants de export.pdb et ceux de exportLibrary.db sont indépendants : on ne s'appuie
donc jamais dessus. Une piste se retrouve par son chemin (« /Contents/… »), une playlist par la
suite de ses noms depuis la racine (« Rap », « Soirées », « 2026 »).

Toutes les opérations travaillent en mémoire sur une copie ; rien n'est écrit sur disque ici.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .file import PdbFile, validate_against
from .format import PAGE_SIZE, PdbFormatError, T
from . import rows

log = logging.getLogger(__name__)
PlaylistPath = Tuple[str, ...]


def _key(text: str) -> str:
    return text.strip().casefold()


@dataclass
class _Ref:
    id: int
    page: int
    slot: int
    off: int


@dataclass
class _Tree(_Ref):
    parent: int = 0
    sort: int = 0
    folder: bool = False
    name: str = ""


@dataclass
class _Entry(_Ref):
    index: int = 0
    track: int = 0
    playlist: int = 0


@dataclass
class Summary:
    tracks_added: int = 0
    tracks_removed: int = 0
    playlists_added: int = 0
    playlists_removed: int = 0
    entries_added: int = 0
    entries_removed: int = 0
    skipped: List[str] = field(default_factory=list)   # éléments ignorés (piste absente d'export.pdb…)


class PdbDatabase:
    def __init__(self, data: bytes, allow_growth: bool = False) -> None:
        self.original = bytes(data)
        self.file = PdbFile(data, allow_growth=allow_growth)
        self.summary = Summary()
        self._tracks: Dict[str, _Ref] = {}
        self._artists: Dict[str, int] = {}
        self._albums: Dict[Tuple[str, int], int] = {}
        self._trees: Dict[int, _Tree] = {}
        self._entries: Dict[int, List[_Entry]] = {}
        self._max = {"track": 0, "artist": 0, "album": 0, "playlist": 0}
        self._template: Optional[rows.TrackTemplate] = None
        self._load()

    # ---------------------------------------------------------------- index mémoire
    def _load(self) -> None:
        f, d = self.file, self.file.data
        for p, slot, off in f.iter_rows(T.TRACKS):
            r = rows.read_track(d, p * PAGE_SIZE + off)
            self._tracks[_key(r["path"])] = _Ref(r["id"], p, slot, off)      # type: ignore[arg-type]
            self._max["track"] = max(self._max["track"], r["id"])            # type: ignore[type-var]
            if self._template is None:
                self._template = rows.make_template(r)
        for p, slot, off in f.iter_rows(T.ARTISTS):
            r = rows.read_artist(d, p * PAGE_SIZE + off)
            self._artists.setdefault(_key(r["name"]), r["id"])               # type: ignore[arg-type]
            self._max["artist"] = max(self._max["artist"], r["id"])          # type: ignore[type-var]
        for p, slot, off in f.iter_rows(T.ALBUMS):
            r = rows.read_album(d, p * PAGE_SIZE + off)
            self._albums.setdefault((_key(r["name"]), r["artist_id"]), r["id"])   # type: ignore[arg-type]
            self._max["album"] = max(self._max["album"], r["id"])            # type: ignore[type-var]
        for p, slot, off in f.iter_rows(T.PLAYLIST_TREE):
            r = rows.read_tree(d, p * PAGE_SIZE + off)
            self._trees[r["id"]] = _Tree(r["id"], p, slot, off, r["parent"], r["sort"], r["folder"], r["name"])  # type: ignore[arg-type]
            self._max["playlist"] = max(self._max["playlist"], r["id"])      # type: ignore[type-var]
        for p, slot, off in f.iter_rows(T.PLAYLIST_ENTRIES):
            r = rows.read_entry(d, p * PAGE_SIZE + off)
            e = _Entry(0, p, slot, off, r["index"], r["track"], r["playlist"])
            self._entries.setdefault(r["playlist"], []).append(e)

    # ------------------------------------------------------------------ lecture
    def has_track(self, path: str) -> bool:
        return _key(path) in self._tracks

    def track_paths(self) -> List[str]:
        return sorted(self._tracks)

    @property
    def track_count(self) -> int:
        return len(self._tracks)

    def find_playlist(self, path: PlaylistPath) -> Optional[_Tree]:
        parent = 0
        node: Optional[_Tree] = None
        for name in path:
            node = next((t for t in self._trees.values() if t.parent == parent and _key(t.name) == _key(name)), None)
            if node is None:
                return None
            parent = node.id
        return node

    def playlist_count(self) -> int:
        return len(self._trees)

    def _ordered_entries(self, pl_id: int) -> List[_Entry]:
        return sorted(self._entries.get(pl_id, []), key=lambda e: (e.index, e.page, e.slot))

    # ------------------------------------------------------------- artistes / albums
    def _shift(self, ttype: int) -> int:
        pages = self.file.data_pages(ttype)
        return 0x20 * (self.file.page(pages[-1]).num_slots if pages else 0)

    def _ensure_artist(self, name: str) -> int:
        name = name.strip()
        if not name:
            return 0
        if _key(name) in self._artists:
            return self._artists[_key(name)]
        new_id = self._max["artist"] + 1
        self.file.insert_row(T.ARTISTS, rows.build_artist(new_id, name, self._shift(T.ARTISTS)))
        self._max["artist"] = new_id
        self._artists[_key(name)] = new_id
        return new_id

    def _ensure_album(self, name: str, artist_id: int) -> int:
        name = name.strip()
        if not name:
            return 0
        if (_key(name), artist_id) in self._albums:
            return self._albums[(_key(name), artist_id)]
        new_id = self._max["album"] + 1
        self.file.insert_row(T.ALBUMS, rows.build_album(new_id, artist_id, name, self._shift(T.ALBUMS)))
        self._max["album"] = new_id
        self._albums[(_key(name), artist_id)] = new_id
        return new_id

    # ------------------------------------------------------------------- pistes
    def add_track(self, meta: rows.TrackMeta) -> int:
        """Ajoute la piste (idempotent : même chemin = rien à faire). Renvoie son id dans export.pdb."""
        existing = self._tracks.get(_key(meta.path))
        if existing:
            return existing.id
        artist_id = self._ensure_artist(meta.artist)
        album_id = self._ensure_album(meta.album, artist_id)
        new_id = self._max["track"] + 1
        row = rows.build_track(meta, new_id, artist_id, album_id, self._shift(T.TRACKS), self._template)
        page, slot = self.file.insert_row(T.TRACKS, row)
        off = self.file.page(page).row_offset(slot)
        self._tracks[_key(meta.path)] = _Ref(new_id, page, slot, off)
        self._max["track"] = new_id
        self.summary.tracks_added += 1
        return new_id

    def delete_track(self, path: str) -> bool:
        ref = self._tracks.pop(_key(path), None)
        if ref is None:
            return False
        for pl_id, entries in list(self._entries.items()):
            keep = []
            for e in entries:
                if e.track == ref.id:
                    self.file.delete_row(e.page, e.slot)
                    self.summary.entries_removed += 1
                else:
                    keep.append(e)
            if len(keep) != len(entries):
                self._entries[pl_id] = keep
                self._renumber(pl_id)
        self.file.delete_row(ref.page, ref.slot)
        self.summary.tracks_removed += 1
        return True

    # ----------------------------------------------------------------- playlists
    def ensure_playlist(self, path: PlaylistPath, folder: bool = False) -> int:
        """Crée la playlist (et les dossiers parents manquants). Renvoie son id."""
        if not path:
            return 0
        node = self.find_playlist(path)
        if node:
            return node.id
        parent = self.ensure_playlist(path[:-1], folder=True) if len(path) > 1 else 0
        siblings = [t.sort for t in self._trees.values() if t.parent == parent]
        new_id = self._max["playlist"] + 1
        sort = (max(siblings) + 1) if siblings else 0
        page, slot = self.file.insert_row(T.PLAYLIST_TREE, rows.build_tree(parent, sort, new_id, folder, path[-1].strip()))
        off = self.file.page(page).row_offset(slot)
        self._trees[new_id] = _Tree(new_id, page, slot, off, parent, sort, folder, path[-1].strip())
        self._max["playlist"] = new_id
        self.summary.playlists_added += 1
        return new_id

    def rename_playlist(self, path: PlaylistPath, new_name: str) -> bool:
        node = self.find_playlist(path)
        if node is None:
            self.summary.skipped.append("playlist introuvable : " + "/".join(path))
            return False
        self.file.delete_row(node.page, node.slot)
        page, slot = self.file.insert_row(
            T.PLAYLIST_TREE, rows.build_tree(node.parent, node.sort, node.id, node.folder, new_name.strip()))
        node.page, node.slot, node.off = page, slot, self.file.page(page).row_offset(slot)
        node.name = new_name.strip()
        return True

    def delete_playlist(self, path: PlaylistPath) -> bool:
        node = self.find_playlist(path)
        if node is None:
            return False
        doomed, frontier = [node.id], [node.id]
        while frontier:
            frontier = [t.id for t in self._trees.values() if t.parent in frontier]
            doomed += frontier
        for pl_id in doomed:
            for e in self._entries.pop(pl_id, []):
                self.file.delete_row(e.page, e.slot)
                self.summary.entries_removed += 1
            tree = self._trees.pop(pl_id)
            self.file.delete_row(tree.page, tree.slot)
            self.summary.playlists_removed += 1
        return True

    # ------------------------------------------------------- contenu des playlists
    def _renumber(self, pl_id: int) -> None:
        for n, e in enumerate(self._ordered_entries(pl_id), start=1):
            if e.index != n:
                self.file.patch_u32(e.page, e.off, 0, n)
                e.index = n

    def _track_ids(self, track_paths: Sequence[str]) -> List[int]:
        ids: List[int] = []
        for path in track_paths:
            ref = self._tracks.get(_key(path))
            if ref is None:
                self.summary.skipped.append("piste absente d'export.pdb : " + path)
            elif ref.id not in ids:
                ids.append(ref.id)
        return ids

    def playlist_set(self, path: PlaylistPath, track_paths: Sequence[str]) -> None:
        """Contenu exact et ordre de la playlist."""
        pl_id = self.ensure_playlist(path)
        wanted = self._track_ids(track_paths)
        current = self._ordered_entries(pl_id)
        seen, keep = set(), []
        for e in current:
            if e.track in wanted and e.track not in seen:
                seen.add(e.track)
                keep.append(e)
            else:
                self.file.delete_row(e.page, e.slot)
                self.summary.entries_removed += 1
        have = {e.track: e for e in keep}
        entries: List[_Entry] = []
        for n, track_id in enumerate(wanted, start=1):
            e = have.get(track_id)
            if e is None:
                page, slot = self.file.insert_row(T.PLAYLIST_ENTRIES, rows.build_entry(n, track_id, pl_id))
                e = _Entry(0, page, slot, self.file.page(page).row_offset(slot), n, track_id, pl_id)
                self.summary.entries_added += 1
            elif e.index != n:
                self.file.patch_u32(e.page, e.off, 0, n)
                e.index = n
            entries.append(e)
        self._entries[pl_id] = entries

    def playlist_add(self, path: PlaylistPath, track_paths: Sequence[str]) -> None:
        """Ajoute en fin de playlist les pistes absentes (l'ordre existant n'est pas modifié)."""
        pl_id = self.ensure_playlist(path)
        present = {e.track for e in self._entries.get(pl_id, [])}
        n = len(self._entries.get(pl_id, []))
        for track_id in self._track_ids(track_paths):
            if track_id in present:
                continue
            n += 1
            page, slot = self.file.insert_row(T.PLAYLIST_ENTRIES, rows.build_entry(n, track_id, pl_id))
            self._entries.setdefault(pl_id, []).append(
                _Entry(0, page, slot, self.file.page(page).row_offset(slot), n, track_id, pl_id))
            present.add(track_id)
            self.summary.entries_added += 1

    def playlist_remove(self, path: PlaylistPath, track_paths: Sequence[str]) -> None:
        node = self.find_playlist(path)
        if node is None:
            return
        gone = {self._tracks[_key(p)].id for p in track_paths if _key(p) in self._tracks}
        keep = []
        for e in self._entries.get(node.id, []):
            if e.track in gone:
                self.file.delete_row(e.page, e.slot)
                self.summary.entries_removed += 1
            else:
                keep.append(e)
        self._entries[node.id] = keep
        self._renumber(node.id)

    # --------------------------------------------------------------------- sortie
    def to_bytes(self) -> bytes:
        """Fichier modifié, après contrôle : valide, et seules les pages touchées ont changé."""
        new = self.file.to_bytes()
        if new == self.original:
            return new
        validate_against(self.original, new, self.file.touched)
        PdbDatabase(new)         # relecture complète : toutes les lignes se décodent
        return new
