"""Réconciliation d'export.pdb avec exportLibrary.db (1.3.0-rc.2, fiche P02).

Avant la 1.3.0-rc.2, chaque écriture dans exportLibrary.db mettait en file des opérations
(« ajouter ce son », « renommer cette playlist »…) rejouées sur export.pdb. Une écriture qui
échouait perdait ses opérations, et seul un rattrapage ADDITIF existait : suppressions,
renommages, ordres et titres manqués restaient faux pour toujours, alors que l'état affiché
pouvait dire « à jour ».

Désormais exportLibrary.db fait foi et export.pdb est RÉCONCILIÉ avec lui : on compare l'état
complet des deux bases, on calcule un plan d'écarts, puis on l'applique en une seule écriture.
Une écriture qui échoue est donc rattrapée à la suivante, et le même plan, calculé sans rien
écrire, donne l'état affiché (« à jour » veut dire « aucun écart »).

Règle de prudence : rien n'est RETIRÉ d'export.pdb sur la seule foi d'une absence dans
exportLibrary.db. Un son ou une playlist n'en est supprimé que si DJSync l'a supprimé (ou
renommé) lui-même : ces suppressions sont notées dans un journal sur la clé
(DJSync_Backups/pdb-journal.json) au moment de l'écriture dans exportLibrary.db, et le journal
n'est vidé qu'une fois export.pdb à jour. Ce que DJSync ne connaît pas est conservé tel quel.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .database import PdbDatabase, PlaylistPath, _key
from .rows import TrackMeta

log = logging.getLogger(__name__)

TRACK_DELETED = "track_deleted"        # son supprimé de la bibliothèque : à retirer d'export.pdb
PLAYLIST_DELETED = "playlist_deleted"  # playlist supprimée ou renommée (ancien chemin) : à retirer
TRACK_FIELDS = "track_fields"          # titre / artiste / BPM modifiés : à recopier
TRACK_REBUILT = "track_rebuilt"        # 1.3.0-rc.6 (B27) : son de DJSync dont la ligne est à réécrire
                                       # (analyse déplacée, champs mis au format de Rekordbox)
KINDS = (TRACK_DELETED, PLAYLIST_DELETED, TRACK_FIELDS, TRACK_REBUILT)


# --------------------------------------------------------------------------------- journal
@dataclass(frozen=True)
class Mark:
    kind: str
    path: Tuple[str, ...]      # (chemin du son,) ou suite des noms de la playlist

    def to_json(self) -> Dict[str, object]:
        return {"kind": self.kind, "path": list(self.path)}

    @staticmethod
    def from_json(d: Dict[str, object]) -> Optional["Mark"]:
        kind, path = d.get("kind"), d.get("path")
        if kind not in KINDS or not isinstance(path, list) or not all(isinstance(x, str) for x in path) or not path:
            return None
        return Mark(str(kind), tuple(path))


class Journal:
    """Marques en attente, gardées sur la clé (survivent à un plantage ou à une clé retirée)."""

    NAME = "pdb-journal.json"

    def __init__(self, folder: Path) -> None:
        self.path = Path(folder) / self.NAME
        self.marks: List[Mark] = []
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.warning("export.pdb journal unreadable, ignored: %s", exc)
            return
        for d in raw.get("marks", []) if isinstance(raw, dict) else []:
            m = Mark.from_json(d) if isinstance(d, dict) else None
            if m and m not in self.marks:
                self.marks.append(m)

    def add(self, marks: Sequence[Mark]) -> None:
        new = [m for m in marks if m not in self.marks]
        if new:
            self.marks.extend(new)
            self.save()

    def resolve(self, done: Sequence[Mark]) -> None:
        if not done:
            return
        self.marks = [m for m in self.marks if m not in done]
        self.save()

    def save(self) -> None:
        try:
            if not self.marks:
                self.path.unlink(missing_ok=True)
                return
            self.path.parent.mkdir(exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"),
                                       "marks": [m.to_json() for m in self.marks]}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:            # le journal est une aide : il ne bloque jamais une écriture
            log.warning("export.pdb journal not saved: %s", exc)


# ----------------------------------------------------------------------------------- cible
@dataclass
class Target:
    """État voulu, lu dans exportLibrary.db : les sons, et les playlists (chemin de noms, dossier ?,
    chemins des sons dans l'ordre), parents avant enfants."""

    tracks: List[TrackMeta]
    playlists: List[Tuple[PlaylistPath, bool, List[str]]]


# ------------------------------------------------------------------------------------ plan
@dataclass
class Plan:
    add_tracks: List[TrackMeta] = field(default_factory=list)
    upgrade_tracks: List[TrackMeta] = field(default_factory=list)       # analyse / pochette arrivée après coup
    rebuild_tracks: List[TrackMeta] = field(default_factory=list)       # B27 : lignes de DJSync à réécrire
    update_tracks: List[Tuple[str, Optional[str], Optional[str], Optional[int]]] = field(default_factory=list)
    delete_tracks: List[str] = field(default_factory=list)
    add_playlists: List[Tuple[PlaylistPath, bool]] = field(default_factory=list)
    set_entries: List[Tuple[PlaylistPath, List[str]]] = field(default_factory=list)
    delete_playlists: List[PlaylistPath] = field(default_factory=list)
    resolved: List[Mark] = field(default_factory=list)                  # marques du journal traitées par ce plan
    repair_index: List[str] = field(default_factory=list)               # B13 : liens d'index à remettre d'aplomb

    @property
    def changed_playlists(self) -> int:
        """Playlists EXISTANTES dont le contenu ou l'ordre diffère (les nouvelles sont comptées à part)."""
        new = {path for path, _f in self.add_playlists}
        return sum(1 for path, _t in self.set_entries if path not in new)

    @property
    def empty(self) -> bool:
        return not (self.add_tracks or self.upgrade_tracks or self.rebuild_tracks or self.update_tracks
                    or self.delete_tracks
                    or self.add_playlists or self.set_entries or self.delete_playlists or self.repair_index)

    def describe(self) -> str:
        """Résumé lisible (anglais : journal et rapports ; l'interface traduit à partir des nombres)."""
        parts = [(len(self.add_tracks), "track(s) missing"), (len(self.add_playlists), "playlist(s) missing"),
                 (self.changed_playlists, "playlist(s) with different content or order"),
                 (len(self.update_tracks), "track(s) with changed info"),
                 (len(self.upgrade_tracks), "track(s) without analysis"),
                 (len(self.rebuild_tracks), "track(s) to rewrite"),
                 (len(self.delete_tracks), "deleted track(s) still present"),
                 (len(self.delete_playlists), "deleted or renamed playlist(s) still present"),
                 (len(self.repair_index), "index page(s) to repair")]
        return ", ".join(f"{n} {label}" for n, label in parts if n) or "up to date"


def plan(db: PdbDatabase, target: Target, marks: Sequence[Mark] = ()) -> Plan:
    """Écarts entre export.pdb (`db`) et l'état voulu. Ne modifie rien."""
    p = Plan()
    p.repair_index = db.file.repairable_index_links()
    wanted_tracks = {_key(m.path): m for m in target.tracks if m.path}
    wanted_playlists = {tuple(path) for path, _f, _t in target.playlists}

    # 1. suppressions notées dans le journal (seulement si l'élément n'est plus voulu)
    for m in marks:
        if m.kind == TRACK_DELETED:
            if _key(m.path[0]) in wanted_tracks:
                p.resolved.append(m)                       # re-ajouté depuis : la marque n'a plus d'objet
            elif db.has_track(m.path[0]):
                p.delete_tracks.append(m.path[0])
                p.resolved.append(m)
            else:
                p.resolved.append(m)
        elif m.kind == PLAYLIST_DELETED:
            if m.path in wanted_playlists:
                p.resolved.append(m)
            elif db.find_playlist(m.path) is not None:
                if not any(m.path[:len(d)] == d for d in p.delete_playlists):
                    p.delete_playlists.append(m.path)
                p.resolved.append(m)
            else:
                p.resolved.append(m)

    # 2. sons : manquants, analyse arrivée après coup, infos modifiées (journal)
    fields_marked = {_key(m.path[0]) for m in marks if m.kind == TRACK_FIELDS}
    rebuild_marked = {_key(m.path[0]) for m in marks if m.kind == TRACK_REBUILT}
    for k, meta in wanted_tracks.items():
        info = db.track_info(meta.path)
        if info is None:
            p.add_tracks.append(meta)
            continue
        if k in rebuild_marked:
            p.rebuild_tracks.append(meta)                  # réécrite en entier : analyse comprise
        elif not info["analyze_path"] and (meta.analyze_path or (meta.artwork_path and not info["artwork_id"])):
            p.upgrade_tracks.append(meta)
        if k in fields_marked:
            title = meta.title if (meta.title or "") != (info["title"] or "") else None
            artist = meta.artist if (meta.artist or "").strip() != (info["artist"] or "").strip() else None
            bpm = meta.bpmx100 if meta.bpmx100 and meta.bpmx100 != info["bpmx100"] else None
            if title is not None or artist is not None or bpm is not None:
                p.update_tracks.append((meta.path, title, artist, bpm))
    for m in marks:
        if m.kind in (TRACK_FIELDS, TRACK_REBUILT):
            p.resolved.append(m)                           # traitée (recopiée, ou déjà identique / disparue)

    # 3. playlists : manquantes, puis contenu et ordre
    deleted_soon = p.delete_playlists
    for path, folder, tracks in target.playlists:
        path = tuple(path)
        if db.find_playlist(path) is None or any(path[:len(d)] == d for d in deleted_soon):
            p.add_playlists.append((path, folder))
            if not folder and tracks:
                p.set_entries.append((path, _dedup(tracks)))
            continue
        if folder:
            continue
        current = db.playlist_tracks(path) or []
        wanted = _dedup(tracks)
        # Prudence : une entrée qui pointe vers un son inconnu de exportLibrary.db (ou absent de la
        # table des pistes) est gardée, à sa place relative, en fin de liste.
        keep_unknown = [c for c in current if c is None or c not in wanted_tracks]
        if [c for c in current if c is not None and c in wanted_tracks] != [_key(t) for t in wanted] \
                or len(set(c for c in current if c)) != len([c for c in current if c]):
            p.set_entries.append((path, wanted + [c for c in keep_unknown if c]))
    return p


def _dedup(paths: Sequence[str]) -> List[str]:
    seen, out = set(), []
    for x in paths:
        if x and _key(x) not in seen:
            seen.add(_key(x))
            out.append(x)
    return out


def apply(db: PdbDatabase, p: Plan) -> None:
    """Applique le plan EN MÉMOIRE (l'écriture sur la clé reste celle de PdbStore)."""
    if p.repair_index:
        db.file._begin()                                         # répare les liens d'index (B13)
    for path in sorted(p.delete_playlists, key=len):           # libère la place d'abord
        db.delete_playlist(path)
    for path in p.delete_tracks:
        db.delete_track(path)
    for meta in p.add_tracks + p.upgrade_tracks:
        db.add_track(meta)                                       # idempotent ; réécrit si analyse manquante
    for meta in p.rebuild_tracks:
        db.rebuild_track(meta)                                   # B27 : même id, ligne refaite
    for path, title, artist, bpm in p.update_tracks:
        db.update_track(path, title=title, artist=artist, bpmx100=bpm)
    for path, folder in p.add_playlists:
        db.ensure_playlist(path, folder)
    for path, tracks in p.set_entries:
        db.playlist_set(path, tracks)
