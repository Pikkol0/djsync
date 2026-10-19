"""Détection de doublons : identifiant YouTube exact, puis similarité floue (titre + artiste).

La bibliothèque réelle (exportLibrary.db) se branche via `LibraryProvider.iter_tracks()`.
`exact_lookup` (optionnel) répond à : « ce video_id est-il déjà en bibliothèque ? » (cf.
RekordboxUsbLibrary.find_by_source_url).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Iterable, List, Optional, Protocol, Tuple

from rapidfuzz import fuzz

from ..models import TrackResult

# Mentions parasites entre () ou [] : "(Official Video)", "[Remastered 2011]"...
_BRACKETS = re.compile(r"[\(\[][^\)\]]*[\)\]]")
# "feat. X", "ft. X", "featuring X" jusqu'à la fin de la chaîne
_FEAT = re.compile(r"\b(feat\.?|ft\.?|featuring)\b.*$", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize(text: str) -> str:
    """Minuscules, sans accents, sans (…)/[…], sans feat., sans ponctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = _BRACKETS.sub(" ", text)
    text = _FEAT.sub(" ", text)
    text = text.replace("&", " and ")
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


class LibraryProvider(Protocol):
    """Contrat attendu de la classe DB."""

    def iter_tracks(self) -> Iterable[Tuple[str, str]]:
        """Renvoie des couples (titre, artiste) de tous les sons de la bibliothèque."""
        ...


class FakeLibrary:
    """Bibliothèque fictive pour tester sans clé USB (et état « aucune clé connectée »)."""

    def __init__(self, tracks: Iterable[Tuple[str, str]] = ()) -> None:
        self._tracks = list(tracks)

    def iter_tracks(self) -> Iterable[Tuple[str, str]]:
        return iter(self._tracks)


ExactLookup = Callable[[str], Optional[Any]]


class DuplicateChecker:
    def __init__(
        self,
        library: LibraryProvider,
        title_threshold: int = 88,
        artist_threshold: int = 75,
        exact_lookup: Optional[ExactLookup] = None,
    ) -> None:
        self._title_threshold = title_threshold
        self._artist_threshold = artist_threshold
        self._index: List[Tuple[str, str, str, str]] = []
        self._library = library
        self._exact = exact_lookup
        self.refresh()

    def set_library(self, library: LibraryProvider, exact_lookup: Optional[ExactLookup] = None) -> None:
        """Change de bibliothèque (clé branchée / débranchée / changée)."""
        self._library = library
        self._exact = exact_lookup
        self.refresh()

    def refresh(self) -> None:
        """Recharge l'index (à rappeler après un ajout/suppression en base)."""
        self._index = [
            (normalize(t), normalize(a), t, a) for t, a in self._library.iter_tracks()
        ]

    def find_duplicate(self, title: str, artist: str) -> Optional[str]:
        """Renvoie "Artiste - Titre" du son existant le plus proche, ou None."""
        n_title, n_artist = normalize(title), normalize(artist)
        best: Optional[Tuple[float, str]] = None

        for lib_title, lib_artist, raw_title, raw_artist in self._index:
            # ratio (et non token_set) sur le titre : évite que "Love" matche
            # "Love Me Like You Do" ; token_set reste utile pour les artistes
            # multiples ("A, B" vs "B & A").
            t_score = fuzz.ratio(n_title, lib_title)
            if t_score < self._title_threshold:
                continue
            a_score = fuzz.token_set_ratio(n_artist, lib_artist)
            if a_score < self._artist_threshold:
                continue
            score = (t_score + a_score) / 2
            if best is None or score > best[0]:
                best = (score, f"{raw_artist} - {raw_title}")

        return best[1] if best else None

    def annotate(self, results: Iterable[TrackResult]) -> List[TrackResult]:
        """Marque chaque résultat déjà présent en bibliothèque."""
        out: List[TrackResult] = []
        for r in results:
            match: Optional[str] = None
            if self._exact is not None:
                hit = self._exact(r.url)
                if hit is not None:
                    match = getattr(hit, "display_name", None) or str(hit)
            match = match or self.find_duplicate(r.title, r.artist)
            out.append(r.with_duplicate(match) if match else r)
        return out
