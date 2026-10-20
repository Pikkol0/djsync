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


# ======================================================================================
# V0.2.0 : doublons DANS la bibliothèque (outil « Doublons »)
# ======================================================================================

UNKNOWN_ARTISTS = {"", "unknown", "unknown artist", "artiste inconnu", "inconnu", "various artists",
                   "various", "va", "n a", "none"}
# suffixes de chaînes YouTube : « Daft Punk - Topic », « DaftPunkVEVO », « Daft Punk Official »
_CHANNEL = re.compile(r"(\s*-\s*topic|vevo|\s+official|\s+officiel)$", re.IGNORECASE)


def split_display(title: str, artist: str) -> Tuple[str, str]:
    """(titre, artiste) « réels » : un titre « Artiste - Titre » est découpé quand l'artiste est
    inconnu ou correspond à la partie gauche ; suffixes de chaîne (VEVO, - Topic) retirés."""
    artist = _CHANNEL.sub("", (artist or "").strip()).strip()
    title = (title or "").strip()
    if " - " in title:
        left, right = (s.strip() for s in title.split(" - ", 1))
        if normalize(artist) in UNKNOWN_ARTISTS or fuzz.token_set_ratio(normalize(left), normalize(artist)) >= 80:
            return right, left if normalize(artist) in UNKNOWN_ARTISTS else artist
    return title, artist


def _artists_match(a: str, b: str) -> bool:
    if a in UNKNOWN_ARTISTS or b in UNKNOWN_ARTISTS:
        return True
    return fuzz.token_set_ratio(a, b) >= 75


def find_duplicate_groups(tracks: Iterable[Any], title_threshold: int = 90,
                          max_duration_gap: int = 90) -> List[List[Any]]:
    """Groupes de sons qui semblent identiques (≥ 2 sons par groupe), du plus gros au plus petit.

    `tracks` : objets avec .title, .artist, .duration_seconds (LibraryTrack). Exemples reconnus :
    « Daft Punk - One More Time (Clip Officiel) » / artiste vide et « One More Time » / Daft Punk.
    Des durées trop différentes (> `max_duration_gap` s : version longue, remix) séparent les sons."""
    items = list(tracks)
    if len(items) < 2:
        return []
    keys = []
    for t in items:
        title, artist = split_display(t.title, t.artist)
        keys.append((normalize(title), normalize(artist)))
    titles = [k[0] for k in keys]
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    try:
        from rapidfuzz import process

        matrix = process.cdist(titles, titles, scorer=fuzz.ratio, score_cutoff=title_threshold, dtype="uint8")
        pairs = ((i, j) for i, j in zip(*matrix.nonzero()) if i < j)
    except Exception:  # noqa: BLE001 - repli sans numpy
        pairs = ((i, j) for i in range(len(items)) for j in range(i + 1, len(items))
                 if fuzz.ratio(titles[i], titles[j]) >= title_threshold)
    for i, j in pairs:
        if not titles[i] or not _artists_match(keys[i][1], keys[j][1]):
            continue
        di, dj = int(items[i].duration_seconds or 0), int(items[j].duration_seconds or 0)
        if di and dj and abs(di - dj) > max_duration_gap:
            continue
        parent[find(int(i))] = find(int(j))
    groups: dict = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(items[i])
    out = [g for g in groups.values() if len(g) > 1]
    out.sort(key=lambda g: (-len(g), normalize(g[0].title)))
    return out


def best_keeper(group: List[Any]) -> Any:
    """Son proposé par défaut : analysé, avec pochette, avec un vrai artiste, titre le plus propre."""
    def score(t: Any) -> Tuple[int, int, int, int]:
        clean = 0 if _BRACKETS.search(t.title or "") or " - " in (t.title or "") else 1
        return (int(bool(getattr(t, "is_analysed", False))), int(bool(getattr(t, "artwork_path", None))),
                int(normalize(t.artist or "") not in UNKNOWN_ARTISTS), clean)
    return max(group, key=score)
