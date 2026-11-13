"""Onglet « Qualité » (1.4.1, C135 ; « Améliorer », 1.4.0, C47) : qualité de chaque son de la portée,
recherche d'une meilleure version, remplacement validé (playlists gardées, hot cues recalés : la fonction
de remplacement existante, `replace_with_download`, sans modification)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...i18n import t

log = logging.getLogger(__name__)


class ImproveMixin:
    # ------------------------------------------------------------------ portée et lecture
    def quality_scan(self, ok: Callable[[List[Any]], None], progress: Callable[[int, int], None],
                     ids: Optional[Sequence[int]] = None) -> None:
        """Lignes Qualité (core.improve.QualityRow) des sons de la portée : toute la bibliothèque (`ids`
        None) ou les sons donnés (playlist, sélection). Fil « tools » ; qualité lue dans l'en-tête et dans
        le cache du spectre (jamais de mesure ici)."""
        lib = self.library
        if lib is None:
            ok([])
            return
        wanted = None if ids is None else {int(i) for i in ids}

        def work() -> List[Any]:
            from ...core.improve import assess
            from ...core.quality import probe
            from ...models import source_from_url

            tracks = [x for x in lib.list_tracks() if wanted is None or x.content_id in wanted]
            infos = {}
            for i, x in enumerate(tracks, start=1):
                path = lib.absolute_path(x)
                if Path(path).exists():
                    info = probe(path)
                    info.source = source_from_url(getattr(x, "source_url", None)) or info.source
                    infos[x.content_id] = info
                if i % 25 == 0 or i == len(tracks):
                    self.dispatcher.post(progress, i, len(tracks))
            return assess(tracks, infos)

        self.dispatcher.submit(work, ok, lambda exc: (self._on_error(exc), ok([])), pool="tools")

    def improve_scan(self, ok: Callable[[List[Any]], None], progress: Callable[[int, int], None],
                     lossless_only: bool = False) -> None:
        """1.4.0 (C47) : sons sous le seuil de toute la bibliothèque."""
        from ...core.improve import LOSSLESS_RANK, select

        limit = LOSSLESS_RANK if lossless_only else int(self.settings.improve_threshold or 256)
        self.quality_scan(lambda rows: ok(select(rows, under=limit)), progress)

    def quality_playlist_ids(self, playlist_id: int) -> List[int]:
        lib = self.library
        if lib is None:
            return []
        try:
            return [x.content_id for x in lib.get_playlist_tracks(playlist_id)]
        except Exception as exc:  # noqa: BLE001
            log.info("Playlist unreadable: %s", exc)
            return []

    # ------------------------------------------------------------------ recherche
    def quality_search(self, row: Any, ok: Callable[[Any], None], query: Optional[str] = None) -> None:
        """Meilleures versions de `row` : sources libres (Internet Archive, Audius), Soulseek s'il est
        activé, et pour un son venant d'une vidéo, YouTube Music et SoundCloud (version audio propre).
        `query` : artiste + titre modifiés dans le détail. ok(row) quand toutes les sources ont répondu."""
        from ...core.improve import better_finds
        from ...core.quality import search_terms

        if query is None:
            title, artist = search_terms(row.track)
            query = f"{artist} {title}".strip()
        found: List[Any] = []
        sources = 1 + (1 if self.slsk_ready else 0) + (1 if row.video else 0)
        state = {"left": sources}

        def done() -> None:
            state["left"] -= 1
            if state["left"] <= 0:
                row.results = list(found)
                row.finds = better_finds(row, found)
                row.searched = True
                ok(row)

        def got_free(rs: Sequence[Any]) -> None:
            found.extend(rs)
            done()

        def got_slsk(rs: Sequence[Any]) -> None:
            from .soulseek import track_of

            found.extend(track_of(r) for r in rs)
            done()

        def got_clean(cands: Sequence[Any]) -> None:
            found.extend(c.track for c in cands)
            done()

        self.free_search(query, got_free)
        if self.slsk_ready:
            self.slsk_search(query, got_slsk, duration=int(row.track.duration_seconds or 0))
        if row.video:
            self.find_alternatives(row.track, got_clean)

    def improve_search(self, weak: Any, ok: Callable[[Any], None]) -> None:
        self.quality_search(weak, ok)

    # ------------------------------------------------------------------ remplacement
    def quality_apply(self, rows: Sequence[Any]) -> int:
        """Remplace chaque son par la version choisie (choix automatique du lot : core.improve.choose_batch),
        avec la fonction de remplacement existante ; renvoie le nombre de remplacements lancés."""
        from ...core.improve import choose_batch

        picks: Dict[int, Any] = choose_batch(rows)
        n = 0
        alts = self.__dict__.setdefault("_slsk_alts", {})
        for w in rows:
            best = picks.get(w.track.content_id)
            if best is None:
                continue
            job = self.replace_with_download(best, [w.track])
            if job is None:
                continue
            n += 1
            if getattr(best, "slsk", None) is not None:
                # 1.4.0-rc.3 (B72) : les autres trouvailles Soulseek du son servent de pairs de secours
                spare = [f.slsk for f in (getattr(w, "finds", None) or [])
                         if getattr(f, "slsk", None) is not None and f.slsk is not best.slsk]
                if hasattr(job, "id"):
                    alts.setdefault(job.id, []).extend(self.slsk_order(spare))
        if n:
            self.message("info", t("improve.started", n=n))
        return n

    def improve_apply(self, weaks: Sequence[Any]) -> int:
        return self.quality_apply(weaks)
