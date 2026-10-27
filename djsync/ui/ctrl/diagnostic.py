"""Diagnostic de bibliothèque (V1.1.0) : doublons + sons de mauvaise qualité / mauvaise source, et
remplacement par une version retéléchargée (YouTube Music, repli SoundCloud).

Remplacer = télécharger la nouvelle version (file des téléchargements habituelle), puis
`merge_duplicates(nouveau, anciens)` : le nouveau son prend la place des anciens dans toutes leurs
playlists, les anciens fichiers sont supprimés. Si l'ancien était analysé, le nouveau l'est aussi.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...i18n import t
from ...models import LOW_SCORE, Candidate, DownloadJob, LibraryTrack, SpotifyTrack, TrackResult

log = logging.getLogger(__name__)


@dataclass
class Diagnosis:
    duplicates: List[List[LibraryTrack]] = field(default_factory=list)
    issues: List[Any] = field(default_factory=list)          # core.quality.QualityIssue
    unmeasured: List[LibraryTrack] = field(default_factory=list)   # 1.4.0 (C46) : vraie qualité pas mesurée

    @property
    def total(self) -> int:
        return len(self.duplicates) + len(self.issues)


@dataclass
class MissingItem:
    """1.3.1 (C43) : son de la bibliothèque dont le fichier est introuvable."""

    track: LibraryTrack
    path: str                                      # chemin attendu (affiché)
    playlists: List[str] = field(default_factory=list)
    candidates: List[LibraryTrack] = field(default_factory=list)   # même son, fichier présent
    found: Optional[Path] = None                   # fichier du même nom trouvé ailleurs (dossier déplacé)
    offline: bool = False                          # disque du fichier non branché (bibliothèque du PC)


def volume_root(path: Path) -> Optional[Path]:
    """Disque d'un chemin absolu : « E:/ », « /Volumes/Clé », « /media/user/Clé » (None : inconnu)."""
    parts = path.parts
    if path.drive:
        return Path(path.anchor)
    if len(parts) > 2 and parts[1] == "Volumes":
        return Path(*parts[:3])
    if len(parts) > 4 and parts[1] == "run" and parts[2] == "media":
        return Path(*parts[:5])
    if len(parts) > 3 and parts[1] == "media":
        return Path(*parts[:4])
    if len(parts) > 2 and parts[1] == "mnt":
        return Path(*parts[:3])
    return None


def index_files(roots: Sequence[Path], names: set, limit: int = 200_000) -> dict:
    """{nom (casefold): chemin} des fichiers portant l'un des `names`, sous `roots` (parcours borné)."""
    import os

    out: dict = {}
    seen = 0
    for root in roots:
        if not root.is_dir():
            continue
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("PIONEER", "DJSync_Backups")]
            for f in files:
                seen += 1
                k = f.casefold()
                if k in names and k not in out:
                    out[k] = Path(folder) / f
            if seen > limit:
                return out
    return out


class DiagnosticMixin:
    def diagnose(self, ok: Callable[[Diagnosis], None],
                 progress: Optional[Callable[[int, int], None]] = None, duplicates: bool = True) -> None:
        """Analyse toute la bibliothèque active (thread « tools ») : doublons, puis qualité/source.
        Un son déjà dans un groupe de doublons n'est pas répété dans les problèmes de qualité.
        1.3.1 (C41) : `duplicates=False` pour l'onglet « Mauvaise qualité » (les doublons ont leur
        onglet) ; les fichiers introuvables sont laissés à l'onglet « Fichiers introuvables »."""
        lib = self.library
        if lib is None:
            ok(Diagnosis())
            return

        def work() -> Diagnosis:
            from ...core.duplicates import find_duplicate_groups
            from ...core.quality import find_issues

            tracks = lib.list_tracks()
            groups = find_duplicate_groups(tracks) if duplicates else []
            in_groups = {x.content_id for g in groups for x in g}
            rest = [x for x in tracks if x.content_id not in in_groups]
            if not duplicates:
                rest = [x for x in rest if _exists(lib, x)]
            report = (lambda i, n: self.dispatcher.post(progress, i, n)) if progress else None
            issues = find_issues(rest, lib.absolute_path, progress=report)
            unmeasured: List[LibraryTrack] = []
            if not duplicates:
                from ...analysis.spectrum import lookup

                unmeasured = [x for x in rest if lookup(Path(x.path).name, x.file_size) is None]
                self.diag_counts["quality"] = len(issues)
                self.dispatcher.post(self._emit, "diag_counts")
            return Diagnosis(groups, issues, unmeasured)

        self.dispatcher.submit(work, ok, lambda exc: (self._on_error(exc), ok(Diagnosis())), pool="tools")

    def measure_quality(self, tracks: Sequence[LibraryTrack], ok: Callable[[int], None],
                        progress: Optional[Callable[[int, int], None]] = None) -> None:
        """1.4.0 (C46) : mesure la vraie qualité (spectre) des sons donnés ; `ok(nombre de faux)`."""
        lib = self.library
        if lib is None:
            ok(0)
            return
        ffmpeg = self.settings.ffmpeg_location or None

        def work() -> int:
            from ...analysis.spectrum import measure_and_remember
            from ...core.quality import probe

            fakes = 0
            items = list(tracks)
            for i, x in enumerate(items, start=1):
                path = lib.absolute_path(x)
                if path.exists():
                    measure_and_remember(path, ffmpeg, x.duration_seconds or 0.0)
                    fakes += probe(path).fake
                if progress and (i % 5 == 0 or i == len(items)):
                    self.dispatcher.post(progress, i, len(items))
            return fakes

        self.dispatcher.submit(work, ok, lambda exc: (self._on_error(exc), ok(0)), pool="tools")

    # ------------------------------------------------- 1.3.1 (C41/C43) : onglets du Diagnostic
    @property
    def diag_counts(self) -> Dict[str, Optional[int]]:
        """Nombre de sons concernés par onglet (None : pas encore compté)."""
        if not hasattr(self, "_diag_counts"):
            self._diag_counts: Dict[str, Optional[int]] = {}
        return self._diag_counts

    def diag_quick_counts(self) -> None:
        """Compte rapide (sans lire le son) : introuvables, groupes de doublons, infos à uniformiser.
        La mauvaise qualité (lecture de chaque fichier) est comptée en ouvrant son onglet."""
        lib = self.library
        if lib is None:
            return

        def work() -> Dict[str, int]:
            from ...core.duplicates import find_duplicate_groups
            from ...core.uniformize import needs_review

            tracks = lib.list_tracks()
            return {"missing": sum(1 for x in tracks if not _exists(lib, x)),
                    "dup": len(find_duplicate_groups(tracks)),
                    "uniformize": sum(1 for x in tracks if needs_review(x))}

        def ok(counts: Dict[str, int]) -> None:
            if self.library is lib:
                self.diag_counts.update(counts)
                self._emit("diag_counts")

        self.dispatcher.submit(work, ok, lambda _e: None, pool="tools")

    def set_diag_count(self, tab: str, n: Optional[int]) -> None:
        self.diag_counts[tab] = n
        self._emit("diag_counts")

    def find_missing(self, ok: Callable[[List[MissingItem]], None]) -> None:
        """Sons dont le fichier est introuvable, avec leurs playlists, les versions identiques présentes
        dans la bibliothèque et un fichier du même nom trouvé ailleurs (dossier déplacé)."""
        lib = self.library
        if lib is None:
            ok([])
            return
        local = bool(getattr(lib, "is_local", False))

        def work() -> List[MissingItem]:
            from ...core.duplicates import find_duplicate_groups

            tracks = lib.list_tracks()
            present = {x.content_id: _exists(lib, x) for x in tracks}
            missing = [x for x in tracks if not present[x.content_id]]
            if not missing:
                return []
            same: Dict[int, List[LibraryTrack]] = {}
            for g in find_duplicate_groups(tracks):
                for x in g:
                    if not present[x.content_id]:
                        same[x.content_id] = [y for y in g if y.content_id != x.content_id and present[y.content_id]]
            names = {}
            try:
                names = {p.playlist_id: p.name for p in lib.list_playlists()}
                member = lib.playlists_of([x.content_id for x in missing])
            except Exception:  # noqa: BLE001 - la liste reste utile sans les playlists
                member = {}
            roots: List[Path] = [Path(lib.contents_root)]
            if not local:
                roots.append(Path(lib.drive.root))
            out: List[MissingItem] = []
            for x in missing:
                path = lib.absolute_path(x)
                vol = volume_root(path) if local else None
                out.append(MissingItem(x, str(path), [names[p] for p in member.get(x.content_id, []) if p in names],
                                       same.get(x.content_id, []), None, bool(vol is not None and not vol.exists())))
            wanted = {Path(i.path).name.casefold() for i in out if not i.offline}
            found = index_files(list(dict.fromkeys(roots)), wanted) if wanted else {}
            for i in out:
                f = found.get(Path(i.path).name.casefold())
                if f is not None and not i.offline and f.is_file():
                    i.found = f
            return out

        def done(items: List[MissingItem]) -> None:
            if self.library is lib:
                self.set_diag_count("missing", len(items))
            ok(items)

        self.dispatcher.submit(work, done, lambda exc: (self._on_error(exc), ok([])), pool="tools")

    def relink_missing(self, content_id: int, new_file: Path, ok: Optional[Callable[[Any], None]] = None,
                       err: Optional[Callable[[Any], None]] = None) -> None:
        self._write(lambda lib: lib.relink_track(content_id, new_file), ok, success=t("missing.relinked"), err=err)

    def remove_missing(self, content_ids: Sequence[int], ok: Optional[Callable[[Any], None]] = None,
                       err: Optional[Callable[[Any], None]] = None) -> None:
        """Retire les entrées (fichier déjà absent) ; playlists mises à jour."""
        ids = list(content_ids)
        self._write(lambda lib: lib.delete_tracks(ids, delete_files=False), ok,
                    success=t("missing.removed", n=len(ids)), err=err)

    def replace_missing(self, content_id: int, keep_id: int, ok: Optional[Callable[[Any], None]] = None,
                        err: Optional[Callable[[Any], None]] = None) -> None:
        """Remplace le son introuvable par une version présente : elle prend sa place dans ses playlists ;
        ses hot cues passent sur la version gardée si elle n'en a pas (même durée à 2 s près)."""
        def fn(lib: Any) -> Any:
            carried = 0
            try:
                src, dst = lib.get_track(content_id), lib.get_track(keep_id)
                if src.analysis_path and dst.analysis_path and not _hot_cue_count(lib, keep_id) \
                        and abs(int(src.duration_seconds or 0) - int(dst.duration_seconds or 0)) <= 2:
                    cues = list(lib.track_cues(content_id))
                    if cues:
                        lib.save_track_cues(keep_id, cues)
                        carried = len([c for c in cues if getattr(c, "is_hot", True)])
            except Exception as exc:  # noqa: BLE001 - le remplacement passe avant les cues
                log.info("Cues not carried from missing %s: %s", content_id, exc)
            lib.merge_duplicates(keep_id, [content_id], delete_files=False)
            return carried

        self._write(fn, ok, success=t("missing.replaced"), err=err)

    def track_quality(self, tracks: Sequence[LibraryTrack], ok: Callable[[dict], None]) -> None:
        """{content_id: AudioInfo} (format/débit des versions d'un groupe de doublons)."""
        lib = self.library
        if lib is None:
            ok({})
            return

        def work() -> dict:
            from ...core.quality import probe

            return {x.content_id: probe(lib.absolute_path(x)) for x in tracks}

        self.dispatcher.submit(work, ok, lambda _e: ok({}), pool="db")

    def find_alternatives(self, track: LibraryTrack, ok: Callable[[List[Candidate]], None]) -> None:
        """Versions propres à retélécharger : meilleurs « Titres » YouTube Music (audio officiel),
        puis vidéos propres, puis SoundCloud si YouTube Music ne trouve rien de fiable. Réseau."""
        service = self.service

        def work() -> List[Candidate]:
            from ...core.matcher import score_candidate
            from ...core.quality import acceptable_alternative, search_terms

            title, artist = search_terms(track)
            src = SpotifyTrack(title=title, artists=(artist,) if artist else (),
                               duration_seconds=track.duration_seconds)
            def fits(c: Candidate) -> bool:           # extrait SoundCloud de 30 s, version longue… : non
                d = c.track.duration_seconds
                return (c.score >= LOW_SCORE and acceptable_alternative(c.track.title) and d >= 60
                        and not (track.duration_seconds and abs(d - track.duration_seconds) > 45))

            found = [c for c in service.match_spotify(src, per_type=5) if fits(c)]
            found.sort(key=lambda c: (c.track.is_song, c.score), reverse=True)
            out = found[:3]
            if not any(c.track.is_song and c.score >= 75 for c in out):
                try:
                    for sc in soundcloud_search(f"{artist} {title}".strip()):
                        cand = Candidate(sc, round(score_candidate(src, sc), 1))
                        if fits(cand):
                            out.append(cand)
                except Exception as exc:  # noqa: BLE001 - SoundCloud est un bonus
                    log.info("SoundCloud search failed: %s", exc)
            return out[:4]

        def failed(exc: BaseException) -> None:
            from ..controller import is_offline_error

            self.message("error", t("error.offline") if is_offline_error(exc) else str(exc)[:200])
            ok([])

        self.dispatcher.submit(work, ok, failed, pool="net")

    def replace_with_download(self, track: TrackResult, old: Sequence[LibraryTrack]) -> Optional[DownloadJob]:
        """Télécharge `track` puis remplace les sons `old` (playlists, position) ; voir _finish_replace."""
        jobs = self.enqueue([track], [])
        if not jobs:
            return None
        job = jobs[0]
        job.replace_ids = [x.content_id for x in old]
        job.reanalyse = any(x.is_analysed for x in old)
        return job

    def _carry_to_replacement(self, job: DownloadJob, lib: Any) -> Any:
        """Hot cues de l'ancienne version (celle qui en a le plus) recalés sur le son téléchargé, qui est
        d'abord analysé. None si rien à reporter ou impossible (l'utilisateur est prévenu)."""
        counts = {cid: _hot_cue_count(lib, cid) for cid in job.replace_ids}
        src = max(counts, key=counts.get) if counts else None
        if src is None or not counts[src]:
            return None
        try:
            from ...core.duplicates import carry_cues

            if not lib.get_track(job.content_id).analysis_path:
                lib.analyze_tracks([job.content_id])
            old = lib.get_track(src)
            if not _exists(lib, old):
                # 1.3.1 (C43) : ancien fichier introuvable, rien à comparer : les cues passent tels quels
                # si la durée est la même (à 2 s près)
                new = lib.get_track(job.content_id)
                if abs(int(old.duration_seconds or 0) - int(new.duration_seconds or 0)) > 2:
                    raise ValueError("durations differ and the old file is missing")
                return list(lib.track_cues(src)), 0
            return carry_cues(lib, src, job.content_id, lambda x: self._fingerprint(lib, x))
        except Exception as exc:  # noqa: BLE001
            log.warning("Hot cues not carried over to %s: %s", job.content_id, exc)
            self.dispatcher.post(self.message, "warn", t("diag.cues_not_carried", title=job.track.title,
                                                         detail=str(exc)[:160]))
            return None

    def _finish_replace(self, job: DownloadJob, lib: Any) -> None:
        """Thread « dl », juste après l'ajout du nouveau son en base."""
        carried = self._carry_to_replacement(job, lib)          # 1.3.0 (C13) : avant de supprimer l'ancien
        try:
            removed, failures = lib.merge_duplicates(job.content_id, job.replace_ids, delete_files=True)
        except Exception as exc:  # noqa: BLE001 - le nouveau son est bien là : on prévient, sans échec
            log.warning("Replace %s failed: %s", job.replace_ids, exc)
            self.dispatcher.post(self.message, "warn", t("diag.replace_failed", title=job.track.title,
                                                         detail=str(exc)[:200]))
            return
        log.info("Replaced %s by %s (%d removed, %d files kept)", job.replace_ids, job.content_id, removed, failures)
        text = t("diag.replaced", title=job.track.title)
        if carried is not None:
            try:
                lib.save_track_cues(job.content_id, carried[0])
                text += " " + (t("msg.cues_carried_lost", n=len(carried[0]), lost=carried[1]) if carried[1]
                               else t("msg.cues_carried", n=len(carried[0])))
            except Exception as exc:  # noqa: BLE001
                log.warning("Hot cues not written on %s: %s", job.content_id, exc)
        self.dispatcher.post(self.message, "ok", text)
        if carried is not None:
            return                                                # déjà analysé pour recevoir les cues
        if job.reanalyse:
            self.dispatcher.post(lambda: self.library is lib and self.analyze([job.content_id]))


def _hot_cue_count(lib: Any, cid: int) -> int:
    try:
        return sum(1 for c in lib.track_cues(cid) if c.slot)
    except Exception:  # noqa: BLE001 - pas analysé
        return 0


def soundcloud_search(query: str, limit: int = 3) -> List[TrackResult]:
    """Recherche SoundCloud via yt-dlp (« scsearch »), sans télécharger."""
    import yt_dlp

    from ...core.engine import ydl_options
    from ...core.urlimport import entry_to_track
    from ...models import UrlKind

    opts = ydl_options(quiet=True, no_warnings=True, skip_download=True, extract_flat="in_playlist")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"scsearch{limit}:{query}", download=False) or {}
    out = []
    for e in info.get("entries") or []:
        tr = entry_to_track(e or {}, UrlKind.SOUNDCLOUD) if e else None
        if tr:
            out.append(tr)
    return out


def _exists(lib: Any, track: LibraryTrack) -> bool:
    try:
        return lib.absolute_path(track).is_file()
    except (OSError, ValueError):
        return False
