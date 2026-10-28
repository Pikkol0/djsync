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
from .format import PAGE_SIZE, PdbCapacityError, PdbFormatError, T
from . import rows
from ...core.camelot import to_camelot

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
    tracks_updated: int = 0                             # V1.1-A4 : analyse/pochette ajoutée à une piste existante
    keys_added: int = 0
    artworks_added: int = 0
    names_added: int = 0                  # 1.3.1 (C38) : genres et labels
    skipped: List[str] = field(default_factory=list)   # éléments ignorés (piste absente d'export.pdb…)


class PdbDatabase:
    def __init__(self, data: bytes, allow_growth: bool = False) -> None:
        self.original = bytes(data)
        self.file = PdbFile(data, allow_growth=allow_growth)
        self.summary = Summary()
        self._tracks: Dict[str, _Ref] = {}
        # 1.2.4 : un même fichier peut avoir PLUSIEURS lignes (ids) dans un export Rekordbox ancien, et les
        # playlists pointer vers l'une ou l'autre : id -> id retenu pour ce chemin.
        self._alias: Dict[int, int] = {}
        self._alias_rows: Dict[int, List[_Ref]] = {}           # id retenu -> autres lignes du même fichier
        self._artists: Dict[str, int] = {}
        self._artist_names: Dict[int, str] = {}              # 1.3.0-rc.2 : id -> nom (comparaison des infos)
        self._albums: Dict[Tuple[str, int], int] = {}
        self._trees: Dict[int, _Tree] = {}
        self._entries: Dict[int, List[_Entry]] = {}
        self._keys: Dict[str, int] = {}                     # nom exact (casefold) -> id
        self._key_codes: Dict[str, int] = {}                # code Camelot -> id (« Am » et « 8A » = même clé)
        self._artworks: Dict[str, int] = {}                 # chemin (casefold) -> id
        self._max = {"track": 0, "artist": 0, "album": 0, "playlist": 0, "key": 0, "artwork": 0,
                     T.GENRES: 0, T.LABELS: 0}
        # 1.3.1 (C38) : genres et labels, {table: {nom (casefold): id}} et {table: {id: nom}}
        self._named: Dict[int, Dict[str, int]] = {T.GENRES: {}, T.LABELS: {}}
        self._named_names: Dict[int, Dict[int, str]] = {T.GENRES: {}, T.LABELS: {}}
        self._template: Optional[rows.TrackTemplate] = None
        self._load()

    # ---------------------------------------------------------------- index mémoire
    def _load(self) -> None:
        f, d = self.file, self.file.data
        for p, slot, off in f.iter_rows(T.TRACKS):
            r = rows.read_track(d, p * PAGE_SIZE + off)
            k = _key(r["path"])                                              # type: ignore[arg-type]
            if k in self._tracks:
                self._alias[r["id"]] = self._tracks[k].id                    # type: ignore[index]
                self._alias_rows.setdefault(self._tracks[k].id, []).append(_Ref(r["id"], p, slot, off))  # type: ignore[arg-type]
            else:
                self._tracks[k] = _Ref(r["id"], p, slot, off)                # type: ignore[arg-type]
            self._max["track"] = max(self._max["track"], r["id"])            # type: ignore[type-var]
            if self._template is None:
                self._template = rows.make_template(r)
        for p, slot, off in f.iter_rows(T.ARTISTS):
            r = rows.read_artist(d, p * PAGE_SIZE + off)
            self._artists.setdefault(_key(r["name"]), r["id"])               # type: ignore[arg-type]
            self._artist_names[r["id"]] = r["name"]                           # type: ignore[index]
            self._max["artist"] = max(self._max["artist"], r["id"])          # type: ignore[type-var]
        for p, slot, off in f.iter_rows(T.ALBUMS):
            r = rows.read_album(d, p * PAGE_SIZE + off)
            self._albums.setdefault((_key(r["name"]), r["artist_id"]), r["id"])   # type: ignore[arg-type]
            self._max["album"] = max(self._max["album"], r["id"])            # type: ignore[type-var]
        if T.KEYS in f.tables:
            for p, slot, off in f.iter_rows(T.KEYS):
                r = rows.read_key(d, p * PAGE_SIZE + off)
                self._keys.setdefault(_key(r["name"]), r["id"])               # type: ignore[arg-type]
                code = to_camelot(r["name"])                                 # type: ignore[arg-type]
                if code:
                    self._key_codes.setdefault(code, r["id"])                # type: ignore[arg-type]
                self._max["key"] = max(self._max["key"], r["id"])            # type: ignore[type-var]
        if T.ARTWORK in f.tables:
            for p, slot, off in f.iter_rows(T.ARTWORK):
                r = rows.read_artwork(d, p * PAGE_SIZE + off)
                self._artworks.setdefault(_key(r["path"]), r["id"])           # type: ignore[arg-type]
                self._max["artwork"] = max(self._max["artwork"], r["id"])    # type: ignore[type-var]
        for ttype in (T.GENRES, T.LABELS):
            if ttype in f.tables:
                for p, slot, off in f.iter_rows(ttype):
                    r = rows.read_named(d, p * PAGE_SIZE + off)
                    self._named[ttype].setdefault(_key(r["name"]), r["id"])     # type: ignore[arg-type]
                    self._named_names[ttype][r["id"]] = r["name"]               # type: ignore[index]
                    self._max[ttype] = max(self._max[ttype], r["id"])           # type: ignore[type-var]
        for p, slot, off in f.iter_rows(T.PLAYLIST_TREE):
            r = rows.read_tree(d, p * PAGE_SIZE + off)
            self._trees[r["id"]] = _Tree(r["id"], p, slot, off, r["parent"], r["sort"], r["folder"], r["name"])  # type: ignore[arg-type]
            self._max["playlist"] = max(self._max["playlist"], r["id"])      # type: ignore[type-var]
        for p, slot, off in f.iter_rows(T.PLAYLIST_ENTRIES):
            r = rows.read_entry(d, p * PAGE_SIZE + off)
            e = _Entry(0, p, slot, off, r["index"], r["track"], r["playlist"])
            self._entries.setdefault(r["playlist"], []).append(e)

    # ------------------------------------------------------------------ lecture
    def _pos(self, ref: _Ref) -> int:
        """Position absolue de la ligne, relue à chaque fois : un compactage de page (V0.2.4) peut
        déplacer une ligne dans sa page (son numéro, lui, ne change jamais)."""
        return ref.page * PAGE_SIZE + self.file.page(ref.page).row_offset(ref.slot)

    def _off(self, ref: _Ref) -> int:
        return self.file.page(ref.page).row_offset(ref.slot)

    def _canon(self, track_id: int) -> int:
        return self._alias.get(track_id, track_id)

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
            # 1.2.4 : nom exact d'abord (Rekordbox accepte « dBs » et « dbs » côte à côte), puis sans
            # tenir compte des majuscules / espaces seulement s'il n'y a aucun nom identique.
            kids = [t for t in self._trees.values() if t.parent == parent]
            node = next((t for t in kids if t.name == name), None)
            if node is None:
                loose = [t for t in kids if _key(t.name) == _key(name)]
                node = loose[0] if len(loose) == 1 else None
            if node is None:
                return None
            parent = node.id
        return node

    def track_info(self, path: str) -> Optional[Dict[str, object]]:
        """1.3.0-rc.2 : titre, nom d'artiste, BPM×100 et chemin d'analyse de la piste (None si absente)."""
        row = self.track_row(path)
        if row is None:
            return None
        return {"title": row["title"], "artist": self._artist_names.get(row["artist_id"], ""),  # type: ignore[arg-type]
                "bpmx100": row["bpmx100"], "analyze_path": row["strings"]["analyze_path"],     # type: ignore[index]
                "artwork_id": row["artwork_id"],
                "genre": self.genre_name(row["genre_id"]), "label": self.label_name(row["label_id"])}  # type: ignore[arg-type]

    def playlist_tracks(self, path: PlaylistPath) -> Optional[List[Optional[str]]]:
        """1.3.0-rc.2 : chemins des pistes de la playlist, dans l'ordre (None pour une entrée qui pointe
        vers une piste absente de la table). None si la playlist n'existe pas."""
        node = self.find_playlist(path)
        if node is None:
            return None
        by_id = {ref.id: k for k, ref in self._tracks.items()}
        return [by_id.get(self._canon(e.track)) for e in self._ordered_entries(node.id)]

    def playlists(self) -> List[Tuple[PlaylistPath, bool]]:
        """1.3.0-rc.2 : toutes les playlists et dossiers (chemin de noms, dossier ?)."""
        def path_of(t: _Tree) -> PlaylistPath:
            names, seen, node = [], set(), t
            while node is not None and node.id not in seen:
                seen.add(node.id)
                names.append(node.name)
                node = self._trees.get(node.parent)
            return tuple(reversed(names))
        return [(path_of(t), t.folder) for t in self._trees.values()]

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
        self._artist_names[new_id] = name
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

    # ------------------------------------------------------------- tonalités / pochettes
    def key_id(self, name: str) -> int:
        """Id de la tonalité si elle existe déjà (même nom, ou même code Camelot : « Am » = « 8A »), sinon 0."""
        name = (name or "").strip()
        if not name:
            return 0
        if _key(name) in self._keys:
            return self._keys[_key(name)]
        code = to_camelot(name)
        return self._key_codes.get(code, 0) if code else 0

    def _ensure_key(self, name: str) -> int:
        """Réutilise la tonalité équivalente existante, sinon ajoute une ligne. 0 si la table est pleine
        (la piste est quand même ajoutée, sans tonalité : jamais d'échec pour un détail)."""
        name = (name or "").strip()
        found = self.key_id(name)
        if found or not name or T.KEYS not in self.file.tables:
            return found
        new_id = self._max["key"] + 1
        try:
            self.file.insert_row(T.KEYS, rows.build_key(new_id, name))
        except PdbCapacityError as exc:
            self.summary.skipped.append(f"key \"{name}\" not added: {exc}")
            return 0
        self._max["key"] = new_id
        self._keys[_key(name)] = new_id
        code = to_camelot(name)
        if code:
            self._key_codes.setdefault(code, new_id)
        self.summary.keys_added += 1
        return new_id

    def artwork_id(self, path: str) -> int:
        return self._artworks.get(_key(path or ""), 0)

    def _ensure_artwork(self, path: str) -> int:
        path = (path or "").strip()
        found = self.artwork_id(path)
        if found or not path or T.ARTWORK not in self.file.tables:
            return found
        new_id = self._max["artwork"] + 1
        try:
            self.file.insert_row(T.ARTWORK, rows.build_artwork(new_id, path))
        except PdbCapacityError as exc:
            self.summary.skipped.append(f"artwork not added: {exc}")
            return 0
        self._max["artwork"] = new_id
        self._artworks[_key(path)] = new_id
        self.summary.artworks_added += 1
        return new_id

    def _ensure_named(self, ttype: int, name: str) -> int:
        """1.3.1 (C38) : id du genre / label (ajouté s'il manque). 0 si vide, table absente ou pleine
        (la piste est quand même écrite, sans genre : jamais d'échec pour un détail)."""
        name = (name or "").strip()
        if not name or ttype not in self.file.tables:
            return 0
        found = self._named[ttype].get(_key(name))
        if found:
            return found
        new_id = self._max[ttype] + 1
        try:
            self.file.insert_row(ttype, rows.build_named(new_id, name))
        except PdbCapacityError as exc:
            self.summary.skipped.append(f"{'genre' if ttype == T.GENRES else 'label'} \"{name}\" not added: {exc}")
            return 0
        self._max[ttype] = new_id
        self._named[ttype][_key(name)] = new_id
        self._named_names[ttype][new_id] = name
        self.summary.names_added += 1
        return new_id

    @property
    def stores_names(self) -> bool:
        """Le fichier a des tables de genres et de labels (toujours le cas d'un export Rekordbox)."""
        return T.GENRES in self.file.tables and T.LABELS in self.file.tables

    def genre_name(self, genre_id: int) -> str:
        return self._named_names[T.GENRES].get(genre_id, "")

    def label_name(self, label_id: int) -> str:
        return self._named_names[T.LABELS].get(label_id, "")

    def artwork_paths(self) -> List[str]:
        return sorted(self._artworks)

    # ------------------------------------------------------------------- pistes
    def track_row(self, path: str) -> Optional[Dict[str, object]]:
        """Champs décodés de la piste (None si absente)."""
        ref = self._tracks.get(_key(path))
        if ref is None:
            return None
        return rows.read_track(self.file.data, self._pos(ref))

    def add_track(self, meta: rows.TrackMeta) -> int:
        """Ajoute la piste. Renvoie son id dans export.pdb.

        Idempotent : même chemin = rien à faire, SAUF si la piste existante n'a pas d'analyse
        (`analyze_path` vide : piste ajoutée par une version précédente de DJSync) et que `meta` en
        apporte une ; la ligne est alors réécrite avec le MÊME id (les playlists restent valides).
        Les pistes analysées par Rekordbox ne sont jamais réécrites."""
        existing = self._tracks.get(_key(meta.path))
        if existing:
            if meta.analyze_path or meta.artwork_path:
                self._upgrade_track(existing, meta)
            return existing.id
        return self._insert_track(meta, self._max["track"] + 1)

    def _build_track(self, meta: rows.TrackMeta, track_id: int) -> bytes:
        artist_id = self._ensure_artist(meta.artist)
        album_id = self._ensure_album(meta.album, artist_id)
        key_id = self._ensure_key(meta.key)
        art_id = self._ensure_artwork(meta.artwork_path)
        return rows.build_track(meta, track_id, artist_id, album_id, self._shift(T.TRACKS), self._template,
                                key_id=key_id, artwork_id=art_id, genre_id=self._ensure_named(T.GENRES, meta.genre),
                                label_id=self._ensure_named(T.LABELS, meta.label))

    def _insert_track(self, meta: rows.TrackMeta, track_id: int) -> int:
        page, slot = self.file.insert_row(T.TRACKS, self._build_track(meta, track_id))
        off = self.file.page(page).row_offset(slot)
        self._tracks[_key(meta.path)] = _Ref(track_id, page, slot, off)
        self._max["track"] = max(self._max["track"], track_id)
        self.summary.tracks_added += 1
        return track_id

    def _upgrade_track(self, ref: _Ref, meta: rows.TrackMeta) -> None:
        row = rows.read_track(self.file.data, self._pos(ref))
        strings = row["strings"]                                             # type: ignore[index]
        if strings["analyze_path"]:                                          # type: ignore[index]
            return                                                           # déjà analysée (Rekordbox ou DJSync)
        if not meta.analyze_path and (row["artwork_id"] or not meta.artwork_path):
            return
        # Même id ; sur place si possible, sinon nouvelle ligne puis suppression de l'ancienne (une page
        # pleine lève l'exception AVANT toute suppression).
        page, slot = self.file.replace_row(T.TRACKS, ref.page, ref.slot, self._build_track(meta, ref.id))
        self._tracks[_key(meta.path)] = _Ref(ref.id, page, slot, self.file.page(page).row_offset(slot))
        self.summary.tracks_updated += 1

    def rebuild_track(self, meta: rows.TrackMeta) -> bool:
        """1.3.0-rc.6 (B27) : réécrit en entier la ligne d'une piste AJOUTÉE PAR DJSYNC (l'appelant le
        garantit : marque du journal posée pour un son sans masterDbId), même id : playlists intactes.
        Sert quand son analyse change de dossier et pour mettre ses champs au format de Rekordbox."""
        ref = self._tracks.get(_key(meta.path))
        if ref is None:
            self.summary.skipped.append(meta.path)
            return False
        page, slot = self.file.replace_row(T.TRACKS, ref.page, ref.slot, self._build_track(meta, ref.id))
        self._tracks[_key(meta.path)] = _Ref(ref.id, page, slot, self.file.page(page).row_offset(slot))
        self.summary.tracks_updated += 1
        return True

    def update_track(self, path: str, title: Optional[str] = None, artist: Optional[str] = None,
                     bpmx100: Optional[int] = None, genre: Optional[str] = None, label: Optional[str] = None) -> bool:
        """Modifie titre / artiste / BPM d'une piste existante, MÊME id (playlists intactes), autres
        champs conservés à l'octet près. False si la piste est absente."""
        ref = self._tracks.get(_key(path))
        if ref is None:
            self.summary.skipped.append(path)
            return False
        row = rows.read_track(self.file.data, self._pos(ref))
        strings = {"title": title} if title is not None else {}
        artist_id = self._ensure_artist(artist) if artist is not None else None
        genre_id = self._ensure_named(T.GENRES, genre) if genre is not None else None
        label_id = self._ensure_named(T.LABELS, label) if label is not None else None
        new = rows.patch_track(row, artist_id=artist_id, bpmx100=bpmx100, genre_id=genre_id, label_id=label_id,
                               **strings)
        # V0.2.4 : sur place quand la ligne ne grandit pas (BPM, titre plus court…) : aucune place consommée
        page, slot = self.file.replace_row(T.TRACKS, ref.page, ref.slot, new)
        self._tracks[_key(path)] = _Ref(ref.id, page, slot, self.file.page(page).row_offset(slot))
        self.summary.tracks_updated += 1
        return True

    def delete_track(self, path: str) -> bool:
        ref = self._tracks.pop(_key(path), None)
        if ref is None:
            return False
        for pl_id, entries in list(self._entries.items()):
            keep = []
            for e in entries:
                if self._canon(e.track) == ref.id:
                    self.file.delete_row(e.page, e.slot)
                    self.summary.entries_removed += 1
                else:
                    keep.append(e)
            if len(keep) != len(entries):
                self._entries[pl_id] = keep
                self._renumber(pl_id)
        self.file.delete_row(ref.page, ref.slot)
        for extra in self._alias_rows.pop(ref.id, []):          # 1.2.4 : autres lignes du même fichier
            self.file.delete_row(extra.page, extra.slot)
            self._alias.pop(extra.id, None)
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
            self.summary.skipped.append("playlist not found: " + "/".join(path))
            return False
        page, slot = self.file.replace_row(
            T.PLAYLIST_TREE, node.page, node.slot,
            rows.build_tree(node.parent, node.sort, node.id, node.folder, new_name.strip()))
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
                self.file.patch_u32(e.page, self._off(e), 0, n)
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
            t = self._canon(e.track)
            if t in wanted and t not in seen:
                seen.add(t)
                keep.append(e)
            else:
                self.file.delete_row(e.page, e.slot)
                self.summary.entries_removed += 1
        have = {self._canon(e.track): e for e in keep}
        entries: List[_Entry] = []
        for n, track_id in enumerate(wanted, start=1):
            e = have.get(track_id)
            if e is None:
                page, slot = self.file.insert_row(T.PLAYLIST_ENTRIES, rows.build_entry(n, track_id, pl_id))
                e = _Entry(0, page, slot, self.file.page(page).row_offset(slot), n, track_id, pl_id)
                self.summary.entries_added += 1
            elif e.index != n:
                self.file.patch_u32(e.page, self._off(e), 0, n)
                e.index = n
            entries.append(e)
        self._entries[pl_id] = entries

    def playlist_add(self, path: PlaylistPath, track_paths: Sequence[str]) -> None:
        """Ajoute en fin de playlist les pistes absentes (l'ordre existant n'est pas modifié)."""
        pl_id = self.ensure_playlist(path)
        present = {self._canon(e.track) for e in self._entries.get(pl_id, [])}
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
            if self._canon(e.track) in gone:
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
