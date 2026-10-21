"""Diagnostic de bibliothèque (V1.1.0) : doublons + sons de mauvaise qualité / mauvaise source, et
remplacement par une version retéléchargée (YouTube Music, repli SoundCloud).

Remplacer = télécharger la nouvelle version (file des téléchargements habituelle), puis
`merge_duplicates(nouveau, anciens)` : le nouveau son prend la place des anciens dans toutes leurs
playlists, les anciens fichiers sont supprimés. Si l'ancien était analysé, le nouveau l'est aussi.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from ...i18n import t
from ...models import LOW_SCORE, Candidate, DownloadJob, LibraryTrack, SpotifyTrack, TrackResult

log = logging.getLogger(__name__)


@dataclass
class Diagnosis:
    duplicates: List[List[LibraryTrack]] = field(default_factory=list)
    issues: List[Any] = field(default_factory=list)          # core.quality.QualityIssue

    @property
    def total(self) -> int:
        return len(self.duplicates) + len(self.issues)


class DiagnosticMixin:
    def diagnose(self, ok: Callable[[Diagnosis], None],
                 progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Analyse toute la bibliothèque active (thread « tools ») : doublons, puis qualité/source.
        Un son déjà dans un groupe de doublons n'est pas répété dans les problèmes de qualité."""
        lib = self.library
        if lib is None:
            ok(Diagnosis())
            return

        def work() -> Diagnosis:
            from ...core.duplicates import find_duplicate_groups
            from ...core.quality import find_issues

            tracks = lib.list_tracks()
            groups = find_duplicate_groups(tracks)
            in_groups = {x.content_id for g in groups for x in g}
            rest = [x for x in tracks if x.content_id not in in_groups]
            report = (lambda i, n: self.dispatcher.post(progress, i, n)) if progress else None
            issues = find_issues(rest, lib.absolute_path, progress=report)
            return Diagnosis(groups, issues)

        self.dispatcher.submit(work, ok, lambda exc: (self._on_error(exc), ok(Diagnosis())), pool="tools")

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

    def _finish_replace(self, job: DownloadJob, lib: Any) -> None:
        """Thread « dl », juste après l'ajout du nouveau son en base."""
        try:
            removed, failures = lib.merge_duplicates(job.content_id, job.replace_ids, delete_files=True)
        except Exception as exc:  # noqa: BLE001 - le nouveau son est bien là : on prévient, sans échec
            log.warning("Replace %s failed: %s", job.replace_ids, exc)
            self.dispatcher.post(self.message, "warn", t("diag.replace_failed", title=job.track.title,
                                                         detail=str(exc)[:200]))
            return
        log.info("Replaced %s by %s (%d removed, %d files kept)", job.replace_ids, job.content_id, removed, failures)
        self.dispatcher.post(self.message, "ok", t("diag.replaced", title=job.track.title))
        if job.reanalyse:
            self.dispatcher.post(lambda: self.library is lib and self.analyze([job.content_id]))


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
