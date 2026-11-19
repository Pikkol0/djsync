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
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

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
        log.debug("Handled error in _analysis", exc_info=True)  # 1.4.3 (A3-4)
        return {}
    files: Dict[str, bytes] = {}
    for path in (dat, ext, dat.with_suffix(".2EX") if dat else None):
        if path is not None and path.is_file():
            try:
                files[path.suffix.upper()] = path.read_bytes()
            except OSError:
                log.debug("Ignored error in _analysis", exc_info=True)  # 1.4.3 (A3-4)
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
                log.debug("Ignored error in copy_playlist", exc_info=True)  # 1.4.3 (A3-4)
    probe_dir = Path(dst.default_download_dir("DJSync", None))
    if needed and needed > _free_space(probe_dir) - 50 * 1024 * 1024:
        raise LibraryError(f"Not enough free space: {needed / 1e6:.0f} MB needed.")

    result.playlist_id = _target_playlist(dst, source.name)
    already = {t.content_id for t in dst.get_playlist_tracks(result.playlist_id)}
    ids: List[int] = []
    analyze = dst.analyze
    # 1.4.2 (A1-3) : écritures regroupées par lots de COPY_CHUNK sons (une sauvegarde et UNE réécriture
    # d'export.pdb par lot, au lieu de deux par son) ; la progression et l'arrêt restent son par son.
    batch = dst.long_batch if hasattr(dst, "long_batch") else getattr(dst, "batch", None)
    stopped = False
    for start in range(0, len(plan), COPY_CHUNK):
        if stopped:
            break
        with (batch() if batch is not None else _no_batch()):
            for i, (t, found) in enumerate(plan[start:start + COPY_CHUNK], start + 1):
                if should_stop and should_stop():
                    stopped = True
                    break
                if on_progress:
                    on_progress(i, len(plan), t.display_name)
                try:
                    if found is not None:
                        result.reused += 1
                        ids.append(found.content_id)
                        continue
                    # 1.4.2 (A3-1, A6-3) : même voie que le transfert C23 : jamais par-dessus le fichier
                    # d'un autre son (« nom (2) »), cues d'un son de l'ordinateur reprises.
                    added = _send_track(src, dst, t, analyze=analyze)
                    result.copied += 1
                    ids.append(added.content_id)
                except Exception as exc:  # noqa: BLE001 - un son en échec n'arrête pas la copie
                    result.failed += 1
                    result.problems.append(f"{t.display_name}: {exc}")
                    log.warning("Copy of %s failed: %s", t.display_name, exc)
    new = [cid for cid in dict.fromkeys(ids) if cid not in already]
    if new:
        dst.add_to_playlist(result.playlist_id, new)
    return result


COPY_CHUNK = 25


@contextmanager
def _no_batch() -> Iterator[None]:
    yield


# =====================================================================================================
# 1.4.2 (C23) : transfert en lot, avec l'arborescence, dans les 4 sens
# =====================================================================================================
# Deux temps : compare() ne fait que LIRE et renvoie une Comparison (une ligne par playlist) ; apply() écrit ce
# que l'utilisateur a laissé coché, avec son choix pour les playlists présentes des deux côtés. « Synchroniser
# les deux » = deux Comparison (une par sens) calculées avant toute écriture, appliquées l'une après l'autre.
#
# Règles (spec du 15/11/2026, options A) :
#   - playlist « la même » = même nom dans le même dossier, casse exacte ; un nom qui ne diffère que par la
#     casse est signalé et la playlist arrive sous un nom à part (deux playlists) ;
#   - dossiers du même nom fusionnés ; son « le même » = règles de copy_playlist (lien d'origine, artiste +
#     titre, fichier + titre) ;
#   - Fusionner : l'arrivée garde son ordre et reçoit à la fin les sons qui lui manquent ; Garder les deux :
#     la copie qui arrive est renommée « Nom (origine) » ; Garder l'arrivée : rien ;
#   - rien n'est jamais retiré, renommé ni remplacé à l'arrivée ; un son déjà présent n'est pas touché (les
#     différences de titre, de cues et de grille sont seulement comptées) ; le départ n'est jamais écrit ;
#   - playlists intelligentes : non copiées ;
#   - arrivée sur clé : UNE seule réconciliation d'export.pdb pour tout le lot (long_batch), point de
#     restauration avant ; arrivée sur l'ordinateur : master.db sauvegardé avant la première écriture.

MERGE, KEEP_BOTH, KEEP_DEST = "merge", "both", "keep"
ACTIONS = (MERGE, KEEP_BOTH, KEEP_DEST)
NEW, CONFLICT, SAME, SMART = "new", "conflict", "same", "smart"
SPACE_MARGIN = 50 * 1024 * 1024


@dataclass
class PlaylistLine:
    """Une playlist du départ dans la revue."""
    src_id: int
    path: Tuple[str, ...]                 # dossiers puis nom, côté départ
    status: str                           # NEW | CONFLICT (présente des deux côtés, sons à ajouter) | SAME | SMART
    src_track_ids: List[int] = field(default_factory=list)     # contenu du départ, dans l'ordre, à la comparaison
    dst_id: int = 0                       # playlist d'arrivée du même nom (0 : aucune)
    src_count: int = 0
    dst_count: int = 0
    common: int = 0                       # sons déjà dans la playlist d'arrivée
    add: int = 0                          # sons qui seraient ajoutés (nouvelle : tous ; fusion : les manquants)
    dst_only: int = 0                     # sons que seule l'arrivée a (information)
    copy_ids: List[int] = field(default_factory=list)          # sons du départ absents de la bibliothèque d'arrivée
    add_names: List[str] = field(default_factory=list)         # sons ajoutés par une fusion (détail de la revue)
    case_clash: str = ""                  # nom d'arrivée qui ne diffère que par la casse (ou pris par autre chose)
    selected: bool = True
    action: str = ""                      # CONFLICT : MERGE | KEEP_BOTH | KEEP_DEST ("" : pas encore choisi)

    @property
    def name(self) -> str:
        return self.path[-1] if self.path else ""

    @property
    def selectable(self) -> bool:
        return self.status in (NEW, CONFLICT)

    @property
    def needs_choice(self) -> bool:
        return self.selected and self.status == CONFLICT and self.action not in ACTIONS

    @property
    def will_write(self) -> bool:
        if not self.selected:
            return False
        return self.status == NEW or (self.status == CONFLICT and self.action in (MERGE, KEEP_BOTH))


@dataclass
class Comparison:
    """Résultat de compare() : rien n'a été écrit. `origin` : nom du départ, pour « Nom (origine) »."""
    origin: str = ""
    lines: List[PlaylistLine] = field(default_factory=list)
    sizes: Dict[int, int] = field(default_factory=dict)        # son du départ à copier -> octets
    free: int = 0                                              # espace libre à l'arrivée (octets)
    new_folders: List[Tuple[str, ...]] = field(default_factory=list)

    def needed(self) -> int:
        """Octets à copier pour les lignes cochées, avec les choix actuels (chaque son compté une fois)."""
        ids = {cid for line in self.lines if line.will_write for cid in line.copy_ids}
        return sum(self.sizes.get(cid, 0) for cid in ids)

    def tracks_to_copy(self) -> int:
        return len({cid for line in self.lines if line.will_write for cid in line.copy_ids})

    @property
    def enough_space(self) -> bool:
        need = self.needed()
        return not need or need <= self.free - SPACE_MARGIN

    @property
    def missing_choices(self) -> int:
        return sum(1 for line in self.lines if line.needs_choice)

    @property
    def ready(self) -> bool:
        return any(line.will_write for line in self.lines) and not self.missing_choices and self.enough_space

    def set_action(self, action: str) -> None:
        """Choix global : appliqué à toutes les playlists présentes des deux côtés."""
        if action not in ACTIONS:
            raise ValueError(action)
        for line in self.lines:
            if line.status == CONFLICT:
                line.action = action


@dataclass
class LineResult:
    path: Tuple[str, ...]
    outcome: str                          # "created" | "merged" | "both" | "failed"
    added: int = 0
    name: str = ""                        # nom donné à l'arrivée s'il diffère (Garder les deux, casse)
    error: str = ""


@dataclass
class BatchResult:
    created: int = 0                      # playlists créées (dont « Garder les deux »)
    merged: int = 0
    folders: int = 0                      # dossiers créés
    added: int = 0                        # sons ajoutés à des playlists
    copied: int = 0                       # fichiers copiés
    reused: int = 0                       # sons déjà présents à l'arrivée, réutilisés tels quels
    failed: int = 0                       # sons en échec
    different: int = 0                    # sons présents des deux côtés mais différents (non touchés)
    different_detail: Dict[str, int] = field(default_factory=dict)      # info / cues / grid
    stopped: bool = False
    lines: List[LineResult] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    restore_point: str = ""
    pdb_state: str = ""

    @property
    def done(self) -> int:
        return self.created + self.merged


def _is_local(lib: Any) -> bool:
    return bool(getattr(getattr(lib, "drive", None), "is_local", False))


def _tree(lib: Any) -> Tuple[Dict[int, Any], Dict[int, List[Any]]]:
    by_id: Dict[int, Any] = {}
    kids: Dict[int, List[Any]] = {}
    for p in lib.list_playlists():
        by_id[p.playlist_id] = p
        kids.setdefault(p.parent_id, []).append(p)
    for group in kids.values():
        group.sort(key=lambda p: (p.sequence, p.playlist_id))
    return by_id, kids


def playlist_path(by_id: Dict[int, Any], p: Any) -> Tuple[str, ...]:
    names: List[str] = []
    seen = set()
    cur: Optional[Any] = p
    while cur is not None and cur.playlist_id not in seen:
        seen.add(cur.playlist_id)
        names.append(cur.name)
        cur = by_id.get(cur.parent_id)
    return tuple(reversed(names))


def expand_selection(lib: Any, ids: Any) -> List[int]:
    """Playlists (pas les dossiers) désignées par `ids` : un dossier vaut tout ce qu'il contient. Dans l'ordre
    de l'arbre."""
    by_id, kids = _tree(lib)
    wanted = {int(i) for i in ids}
    out: List[int] = []

    def walk(parent: int, inside: bool, depth: int = 0) -> None:
        if depth > 32:
            return
        for p in sorted(kids.get(parent, []), key=lambda p: (not p.is_folder, p.sequence, p.playlist_id)):
            hit = inside or p.playlist_id in wanted
            if p.is_folder:
                walk(p.playlist_id, hit, depth + 1)
            elif hit:
                out.append(p.playlist_id)

    walk(0, False)
    return out


class _Matcher:
    """Retrouve à l'arrivée le son d'un son du départ (règles de copy_playlist), et retient les sons ajoutés
    pendant le lot pour ne copier chaque fichier qu'une fois."""

    def __init__(self, src: Any, dst: Any) -> None:
        self.src, self.dst = src, dst
        existing = dst.list_tracks()
        self.by_key: Dict[Tuple[str, str], LibraryTrack] = {}
        self.files: Dict[str, LibraryTrack] = {}
        for t in existing:
            self._index(t)
        self.known: Dict[int, Optional[LibraryTrack]] = {}

    def _index(self, t: LibraryTrack) -> None:
        self.by_key[_key(t)] = t
        try:
            self.files[Path(self.dst.absolute_path(t)).name.lower()] = t
        except Exception:  # noqa: BLE001 - chemin illisible : cette règle ne s'applique pas à ce son
            log.debug("Ignored error in _index", exc_info=True)  # 1.4.3 (A3-4)

    def find(self, t: LibraryTrack) -> Optional[LibraryTrack]:
        if t.content_id in self.known:
            return self.known[t.content_id]
        found = (self.dst.find_by_source_url(t.source_url) if t.source_url else None) or self.by_key.get(_key(t))
        if found is None:
            try:
                cand = self.files.get(Path(self.src.absolute_path(t)).name.lower())
            except Exception:  # noqa: BLE001
                log.debug("Handled error in find", exc_info=True)  # 1.4.3 (A3-4)
                cand = None
            if cand is not None and _norm(cand.title) == _norm(t.title):
                found = cand
        self.known[t.content_id] = found
        return found

    def learn(self, t: LibraryTrack, added: LibraryTrack) -> None:
        self.known[t.content_id] = added
        self._index(added)


def _child(kids: Dict[int, List[Any]], parent: int, name: str, folder: Optional[bool] = None,
           exact: bool = True) -> Optional[Any]:
    """Enfant de `parent` nommé `name` (casse exacte, ou sans la casse) ; `folder` : True dossier, False
    playlist classique, None n'importe quoi."""
    for p in kids.get(parent, []):
        same = p.name == name if exact else p.name.lower() == name.lower()
        if not same:
            continue
        if folder is None or (folder and p.is_folder) or (folder is False and p.is_editable):
            return p
    return None


def _dst_parent(kids: Dict[int, List[Any]], folders: Tuple[str, ...]) -> Tuple[Optional[int], int]:
    """(dossier d'arrivée où ranger, nombre de dossiers du chemin qui existent déjà). None : il manque au moins
    un dossier (la playlist est donc nouvelle)."""
    parent = 0
    for depth, name in enumerate(folders):
        node = _child(kids, parent, name, folder=True) or _child(kids, parent, name, folder=True, exact=False)
        if node is None:
            return None, depth
        parent = node.playlist_id
    return parent, len(folders)


def compare(src: Any, dst: Any, playlist_ids: Any, origin: str = "", on_progress: Optional[Progress] = None,
            should_stop: Optional[Callable[[], bool]] = None) -> Comparison:
    """Compare les playlists choisies du départ avec l'arrivée. LECTURE SEULE des deux côtés."""
    comp = Comparison(origin=origin)
    s_by_id, _s_kids = _tree(src)
    _d_by_id, d_kids = _tree(dst)
    ids = expand_selection(src, playlist_ids)
    matcher = _Matcher(src, dst)
    seen_folders: set = set()
    for i, pid in enumerate(ids, 1):
        if should_stop and should_stop():
            break
        p = s_by_id.get(pid)
        if p is None:
            continue
        path = playlist_path(s_by_id, p)
        if on_progress:
            on_progress(i, len(ids), " / ".join(path))
        if not p.is_editable:                                  # playlist intelligente : jamais copiée
            comp.lines.append(PlaylistLine(pid, path, SMART, src_count=p.track_count, selected=False))
            continue
        tracks = src.get_playlist_tracks(pid)
        line = PlaylistLine(pid, path, NEW, [t.content_id for t in tracks], src_count=len(tracks))
        parent, depth = _dst_parent(d_kids, path[:-1])
        for n in range(depth, len(path) - 1):                  # dossiers à créer
            folder = path[:n + 1]
            if folder not in seen_folders:
                seen_folders.add(folder)
                comp.new_folders.append(folder)
        target = _child(d_kids, parent, line.name, folder=False) if parent is not None else None
        in_target: set = set()
        if target is not None:
            dst_tracks = dst.get_playlist_tracks(target.playlist_id)
            in_target = {t.content_id for t in dst_tracks}
            line.dst_id, line.dst_count = target.playlist_id, len(dst_tracks)
        elif parent is not None:
            other = _child(d_kids, parent, line.name) or _child(d_kids, parent, line.name, exact=False)
            if other is not None:                              # même nom à la casse près, ou pris par un dossier
                line.case_clash = other.name
        hit: set = set()
        seen_src: set = set()
        for t in tracks:
            if t.content_id in seen_src:
                continue
            seen_src.add(t.content_id)
            found = matcher.find(t)
            if found is None:
                line.copy_ids.append(t.content_id)
                if t.content_id not in comp.sizes:
                    try:
                        comp.sizes[t.content_id] = Path(src.absolute_path(t)).stat().st_size
                    except OSError:
                        comp.sizes[t.content_id] = 0
            if found is not None and found.content_id in in_target:
                hit.add(found.content_id)
            else:
                line.add += 1
                if target is not None and len(line.add_names) < 200:
                    line.add_names.append(t.display_name)
        line.common = len(hit)
        line.dst_only = len(in_target - hit)
        if target is not None:
            line.status = CONFLICT if line.add else SAME
            line.selected = line.status == CONFLICT
        comp.lines.append(line)
    try:
        comp.free = _free_space(Path(dst.default_download_dir("DJSync", None)))
    except Exception:  # noqa: BLE001 - espace inconnu : on ne bloque pas
        log.debug("Handled error in compare", exc_info=True)  # 1.4.3 (A3-4)
        comp.free = 1 << 62
    return comp


def _free_name(kids: Dict[int, List[Any]], parent: int, base: str, origin: str) -> str:
    """« Nom (origine) », puis « Nom (origine) 2 »… : premier nom libre dans ce dossier (sans la casse)."""
    taken = {p.name.lower() for p in kids.get(parent, [])}
    stem = f"{base} ({origin})" if origin else f"{base} 2"
    name, n = stem, 2
    while name.lower() in taken:
        name = f"{stem} {n}"
        n += 1
    return name


def _differences(src: Any, s: LibraryTrack, dst: Any, d: LibraryTrack) -> List[str]:
    """En quoi un son présent des deux côtés diffère ("info", "cues", "grid"). Lecture seule ; jamais d'erreur."""
    out: List[str] = []
    if (s.title or "").strip() != (d.title or "").strip() or (s.artist or "").strip() != (d.artist or "").strip():
        out.append("info")
    if not (s.is_analysed and d.is_analysed):
        return out
    try:
        a = sorted((c.slot, c.ms, c.loop_ms or 0) for c in src.track_cues(s.content_id))
        b = sorted((c.slot, c.ms, c.loop_ms or 0) for c in dst.track_cues(d.content_id))
        if a != b:
            out.append("cues")
    except Exception as exc:  # noqa: BLE001 - 1.4.3 (A3-4) : illisible = montré comme différence
        log.info("Cues of %s not compared (shown as different): %s", s.display_name, exc)
        out.append("cues")
    try:
        ga, gb = src.beat_grid(s.content_id).beats, dst.beat_grid(d.content_id).beats
        if len(ga) != len(gb) or (ga and (abs(ga[0][2] - gb[0][2]) > 1 or abs(ga[-1][2] - gb[-1][2]) > 1)):
            out.append("grid")
    except Exception as exc:  # noqa: BLE001 - 1.4.3 (A3-4) : illisible = montré comme différence
        log.info("Beat grid of %s not compared (shown as different): %s", s.display_name, exc)
        out.append("grid")
    return out


def _target_file(folder: Path, src_file: Path) -> Path:
    """Où poser le fichier : jamais par-dessus un autre fichier (même nom mais taille différente → « nom (2) »)."""
    size = src_file.stat().st_size
    target = folder / src_file.name
    n = 2
    while target.exists() and not (target.is_file() and target.stat().st_size == size):
        target = folder / f"{src_file.stem} ({n}){src_file.suffix}"
        n += 1
    return target


def _send_track(src: Any, dst: Any, t: LibraryTrack, analyze: Optional[bool] = None) -> LibraryTrack:
    """Copie un son absent de l'arrivée : fichier, fiche, analyse reprise telle quelle (chemin réécrit), cues.
    `analyze` (« Copier vers… ») : un son sans analyse reprise est analysé à l'arrivée si c'est vrai."""
    from ..analysis.cues import write_cues

    src_file = Path(src.absolute_path(t))
    if not src_file.is_file():
        raise LibraryError(f"file missing ({src_file.name})")
    folder = Path(dst.default_download_dir(t.artist or "Unknown", t.album))
    folder.mkdir(parents=True, exist_ok=True)
    target = _target_file(folder, src_file)
    if not target.exists():
        tmp = target.with_name(target.name + ".djsync-tmp")
        shutil.copyfile(src_file, tmp)
        tmp.replace(target)
    anlz = _analysis(src, t)
    cues: List[Any] = []
    if anlz:
        try:
            cues = list(src.track_cues(t.content_id))
        except Exception as exc:  # noqa: BLE001 - cues illisibles : l'analyse est reprise sans y toucher
            log.info("Cues of %s not read: %s", t.display_name, exc)
        if cues and _is_local(src):                            # ordinateur : les cues sont dans master.db
            try:
                dat, ext = write_cues(anlz[".DAT"], anlz.get(".EXT"), cues)
                anlz[".DAT"] = dat
                if ext is not None:
                    anlz[".EXT"] = ext
            except Exception as exc:  # noqa: BLE001
                log.warning("Cues of %s not written to the analysis files: %s", t.display_name, exc)
    # 1.4.3 (A3-3) : passé à add_track, l'attribut partagé `dst.analyze` n'est plus modifié ; analyse reprise :
    # pas de recalcul ; transfert (analyze None) : jamais d'analyse ici
    want = bool(analyze) and not anlz
    added = dst.add_track(target, t.title, t.artist or "", t.album, t.source_url, [], analyze=want)
    if anlz and not added.is_analysed:
        added = dst.import_analysis(added.content_id, anlz, t.bpm, to_musical(t.key))
        if cues and _is_local(dst):                            # ordinateur : Rekordbox lit les cues dans master.db
            try:
                added = dst.save_track_cues(added.content_id, cues)
            except Exception as exc:  # noqa: BLE001 - le son est là, avec son analyse
                log.warning("Cues of %s not saved: %s", t.display_name, exc)
    return added


def apply(src: Any, dst: Any, comp: Comparison, on_progress: Optional[Progress] = None,
          should_stop: Optional[Callable[[], bool]] = None, backup_label: str = "",
          count_differences: bool = True) -> BatchResult:
    """Écrit à l'arrivée les lignes cochées de `comp`. Le départ n'est que lu. Lève LibraryError AVANT toute
    écriture si un choix manque, si l'espace manque ou si l'arrivée n'est pas modifiable ; ensuite, un son ou
    une playlist en échec n'arrête pas le lot. Arrêt (`should_stop`) entre deux playlists."""
    res = BatchResult()
    todo = [line for line in comp.lines if line.will_write]
    if comp.missing_choices:
        raise LibraryError("Choose what to do with the playlists that exist on both sides.")
    if not todo:
        return res
    if getattr(dst, "read_only", False):
        raise LibraryError("The destination library is opened read-only.")
    if hasattr(dst, "ensure_writable"):
        dst.ensure_writable()                                  # ordinateur : Rekordbox fermé exigé
    try:
        free = _free_space(Path(dst.default_download_dir("DJSync", None)))
    except Exception:  # noqa: BLE001
        log.debug("Handled error in apply", exc_info=True)  # 1.4.3 (A3-4)
        free = 1 << 62
    need = comp.needed()
    if need and need > free - SPACE_MARGIN:
        raise LibraryError(f"Not enough free space: {need / 1e6:.0f} MB needed.")
    if hasattr(dst, "create_backup") and not _is_local(dst):   # clé : point de restauration complet, nommé
        point = dst.create_backup(backup_label or "Before playlist transfer")
        res.restore_point = getattr(point, "id", "") or ""
    total = sum(len(line.src_track_ids) for line in todo)
    done = 0
    matcher = _Matcher(src, dst)
    src_tracks: Dict[int, LibraryTrack] = {}
    counted: set = set()
    batch = dst.long_batch if hasattr(dst, "long_batch") else dst.batch
    with batch():                                          # l'analyse est reprise, jamais recalculée ici
        for line in todo:
            if should_stop and should_stop():
                res.stopped = True
                break
            out = LineResult(line.path, "failed")
            res.lines.append(out)
            try:
                _d_by_id, kids = _tree(dst)
                parent = 0
                for name in line.path[:-1]:                # dossiers : fusionnés, créés s'ils manquent
                    node = (_child(kids, parent, name, folder=True)
                            or _child(kids, parent, name, folder=True, exact=False))
                    if node is None:
                        taken = _child(kids, parent, name, exact=False)
                        made = dst.create_folder(_free_name(kids, parent, name, comp.origin) if taken else name,
                                                 parent)
                        kids.setdefault(parent, []).append(made)
                        res.folders += 1
                        node = made
                    parent = node.playlist_id
                target = _child(kids, parent, line.name, folder=False)
                if target is not None and line.status == CONFLICT and line.action == KEEP_BOTH:
                    target = None
                    name = _free_name(kids, parent, line.name, comp.origin)
                elif target is None and _child(kids, parent, line.name, exact=False) is not None:
                    name = _free_name(kids, parent, line.name, comp.origin)    # casse, ou nom pris
                else:
                    name = line.name
                if target is None:
                    target = dst.create_playlist(name, parent)
                    out.outcome = "both" if line.action == KEEP_BOTH and line.status == CONFLICT else "created"
                    out.name = name if name != line.name else ""
                    already: set = set()
                else:
                    out.outcome = "merged"
                    already = {t.content_id for t in dst.get_playlist_tracks(target.playlist_id)}
                missing = [cid for cid in line.src_track_ids if cid not in src_tracks]
                if missing:
                    for t in src.get_playlist_tracks(line.src_id):
                        src_tracks.setdefault(t.content_id, t)
                ids: List[int] = []
                for cid in line.src_track_ids:
                    done += 1
                    t = src_tracks.get(cid)
                    if t is None:                          # retiré du départ depuis la comparaison
                        continue
                    if on_progress:
                        on_progress(done, total, t.display_name)
                    try:
                        found = matcher.find(t)
                        if found is None:
                            found = _send_track(src, dst, t)
                            matcher.learn(t, found)
                            res.copied += 1
                            counted.add(cid)
                        elif cid not in counted:
                            counted.add(cid)
                            res.reused += 1
                            if count_differences:
                                diff = _differences(src, t, dst, found)
                                if diff:
                                    res.different += 1
                                    for kind in diff:
                                        res.different_detail[kind] = res.different_detail.get(kind, 0) + 1
                        ids.append(found.content_id)
                    except Exception as exc:  # noqa: BLE001 - un son en échec n'arrête pas le lot
                        res.failed += 1
                        res.problems.append(f"{t.display_name}: {exc}")
                        log.warning("Transfer of %s failed: %s", t.display_name, exc)
                new = [cid for cid in dict.fromkeys(ids) if cid not in already]
                if new:
                    dst.add_to_playlist(target.playlist_id, new)
                out.added = len(new)
                res.added += len(new)
                if out.outcome == "merged":
                    res.merged += 1
                else:
                    res.created += 1
            except Exception as exc:  # noqa: BLE001 - une playlist en échec n'arrête pas le lot
                out.outcome, out.error = "failed", str(exc)
                res.problems.append(f"{' / '.join(line.path)}: {exc}")
                log.warning("Transfer of playlist %s failed: %s", " / ".join(line.path), exc)
    res.pdb_state = str(getattr(dst, "pdb_state", "") or "")
    log.info("Playlist transfer: %d created, %d merged, %d folders, %d files copied, %d reused, %d failed%s",
             res.created, res.merged, res.folders, res.copied, res.reused, res.failed,
             " (stopped)" if res.stopped else "")
    return res
