"""« Améliorer ma bibliothèque » (1.4.0, C47) : sons faibles, recherche d'une meilleure version,
remplacement validé (playlists gardées, hot cues recalés : même mécanisme que le Diagnostic)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, List, Sequence

from ...i18n import t

log = logging.getLogger(__name__)


class ImproveMixin:
    def improve_scan(self, ok: Callable[[List[Any]], None], progress: Callable[[int, int], None],
                     lossless_only: bool = False) -> None:
        """Sons sous le seuil (fil « tools ») : qualité lue dans l'en-tête et dans le registre du spectre."""
        lib = self.library
        if lib is None:
            ok([])
            return

        def work() -> List[Any]:
            from ...core.improve import weak_tracks
            from ...core.quality import probe

            tracks = [x for x in lib.list_tracks()]
            infos = {}
            for i, x in enumerate(tracks, start=1):
                path = lib.absolute_path(x)
                if Path(path).exists():
                    infos[x.content_id] = probe(path)
                if i % 25 == 0 or i == len(tracks):
                    self.dispatcher.post(progress, i, len(tracks))
            return weak_tracks(tracks, infos, threshold=int(self.settings.improve_threshold or 256),
                               lossless_only=lossless_only)

        self.dispatcher.submit(work, ok, lambda exc: (self._on_error(exc), ok([])), pool="tools")

    def improve_search(self, weak: Any, ok: Callable[[Any], None]) -> None:
        """Meilleures versions de `weak` : sources libres, puis Soulseek s'il est activé ; ok(weak)."""
        from ...core.improve import better_finds
        from ...core.quality import search_terms

        title, artist = search_terms(weak.track)
        query = f"{artist} {title}".strip()
        found: List[Any] = []
        state = {"left": 2 if self.slsk_ready else 1}

        def done() -> None:
            state["left"] -= 1
            if state["left"] <= 0:
                weak.finds = better_finds(weak, found)
                weak.searched = True
                ok(weak)

        def got_free(rs: Sequence[Any]) -> None:
            found.extend(rs)
            done()

        def got_slsk(rs: Sequence[Any]) -> None:
            from .soulseek import track_of

            found.extend(track_of(r) for r in rs)
            done()

        self.free_search(query, got_free)
        if self.slsk_ready:
            self.slsk_search(query, got_slsk, duration=int(weak.track.duration_seconds or 0))

    def improve_apply(self, weaks: Sequence[Any]) -> int:
        """Remplace chaque son par sa meilleure trouvaille (téléchargement, puis remplacement)."""
        n = 0
        for w in weaks:
            if w.best is not None and self.replace_with_download(w.best, [w.track]) is not None:
                n += 1
        if n:
            self.message("info", t("improve.started", n=n))
        return n
