"""Détection de doublons : identifiant YouTube exact, puis similarité floue (titre + artiste).

La bibliothèque réelle (exportLibrary.db) se branche via `LibraryProvider.iter_tracks()`.
`exact_lookup` (optionnel) répond à : « ce video_id est-il déjà en bibliothèque ? » (cf.
RekordboxUsbLibrary.find_by_source_url).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple

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


# 1.3.0-rc.5 (C62) : numéro de partie / volume, ou version (remix, live…) différents = pas le même son,
# même si les titres se ressemblent à 90 % (« Afro Trap Pt. 3 » / « Afro Trap Pt. 7 »).
_PART = re.compile(r"(?:\b(?:pt|part|partie|parte|vol|volume|chapter|chapitre|episode|ep|no|n°)\s*\.?\s*|#\s*)(\d+|[ivxlc]+\b)",
                   re.IGNORECASE)
_VERSION = re.compile(r"\b(remix|rmx|extended|live|edit|instrumental|acapella|a cappella|bootleg|vip|rework|dub|"
                      r"sped up|slowed)\b", re.IGNORECASE)


def variant_tokens(title: str) -> frozenset:
    """Numéros de partie et mots de version d'un titre (« pt 3 », « remix ») ; vide si aucun."""
    text = unicodedata.normalize("NFKD", title or "").lower()
    parts = {"p:" + m.group(1).lower() for m in _PART.finditer(text)}
    versions = {"v:" + m.group(1).lower().replace("rmx", "remix")
                for m in _VERSION.finditer(text)}
    return frozenset(parts | versions)


def ignore_key(track: Any) -> str:
    """Identifiant stable d'un son pour la mémoire « pas un doublon » (chemin du fichier)."""
    return (getattr(track, "path", "") or f"#{getattr(track, 'content_id', '')}").replace("\\", "/").lower()


def ignored_pair(a: Any, b: Any) -> frozenset:
    return frozenset((ignore_key(a), ignore_key(b)))


def find_duplicate_groups(tracks: Iterable[Any], title_threshold: int = 90,
                          max_duration_gap: int = 90, ignored: Optional[set] = None) -> List[List[Any]]:
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
    ignored = ignored or set()
    variants = [variant_tokens(t.title) for t in items]
    for i, j in pairs:
        if not titles[i] or not _artists_match(keys[i][1], keys[j][1]):
            continue
        if variants[i] != variants[j]:                     # rc.5 (C62) : Pt. 3 / Pt. 7, original / remix
            continue
        if ignored and ignored_pair(items[i], items[j]) in ignored:
            continue
        di, dj = int(items[i].duration_seconds or 0), int(items[j].duration_seconds or 0)
        if di and dj and abs(di - dj) > max_duration_gap:
            continue
        parent[find(int(i))] = find(int(j))
    groups: dict = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(items[i])
    out: List[List[Any]] = []
    for g in groups.values():
        out += _split_ignored(g, ignored) if ignored else [g]
    out = [g for g in out if len(g) > 1]
    out.sort(key=lambda g: (-len(g), normalize(g[0].title)))
    return out


def _split_ignored(group: List[Any], ignored: set) -> List[List[Any]]:
    """Un groupe relié « en chaîne » peut encore contenir deux sons déclarés différents : ceux qui le
    sont du son de référence forment un autre groupe (même règle, une fois de plus)."""
    if len(group) < 2:
        return [group]
    ref = best_keeper(group)
    kept = [x for x in group if x is ref or ignored_pair(ref, x) not in ignored]
    rest = [x for x in group if x not in kept]
    if not rest:
        return [kept]
    return [kept] + (_split_ignored(rest, ignored) if len(rest) < len(group) else [])


def best_keeper(group: List[Any]) -> Any:
    """Son proposé par défaut : analysé, avec pochette, avec un vrai artiste, titre le plus propre."""
    def score(t: Any) -> Tuple[int, int, int, int]:
        clean = 0 if _BRACKETS.search(t.title or "") or " - " in (t.title or "") else 1
        return (int(bool(getattr(t, "is_analysed", False))), int(bool(getattr(t, "artwork_path", None))),
                int(normalize(t.artist or "") not in UNKNOWN_ARTISTS), clean)
    return max(group, key=score)


# ------------------------------------------------------------------ 1.3.0 (B02) : par le son
def refine_by_audio(groups: List[List[Any]], fingerprint_of: Any, progress: Any = None
                    ) -> Tuple[List[List[Any]], Dict[int, Any]]:
    """Le titre propose des candidats, l'empreinte audio décide. Chaque membre est comparé au son de
    référence du groupe (plus de regroupement en chaîne) : « same » ou « variant » restent dans le
    groupe, « different » en sort (les sons sortis sont comparés entre eux une fois de plus).

    `fingerprint_of(track)` -> empreinte ou None (fichier illisible : le son reste, sans verdict).
    Renvoie (groupes, {content_id: Match relatif à la référence de son groupe ; None = non comparé}).
    """
    from ..analysis.fingerprint import compare, is_usable

    total = sum(len(g) for g in groups)
    done = [0]
    cache: Dict[int, Any] = {}

    def fp(track: Any) -> Any:
        cid = int(track.content_id)
        if cid not in cache:
            got = fingerprint_of(track)
            cache[cid] = got if is_usable(got) else None
            done[0] += 1
            if progress is not None:
                progress(min(done[0], total), total)
        return cache[cid]

    out: List[List[Any]] = []
    matches: Dict[int, Any] = {}

    def split(group: List[Any], depth: int) -> None:
        ref = best_keeper(group)
        ref_fp = fp(ref)
        if ref_fp is None:
            out.append(group)
            matches.update({int(x.content_id): None for x in group})
            return
        kept, rest = [ref], []
        found: Dict[int, Any] = {}
        for x in group:
            if x is ref:
                continue
            other = fp(x)
            if other is None:
                kept.append(x)
                found[int(x.content_id)] = None
                continue
            m = compare(ref_fp, other, float(ref.duration_seconds or 0), float(x.duration_seconds or 0))
            if m.verdict == "different":
                rest.append(x)
            else:
                kept.append(x)
                found[int(x.content_id)] = m
        if len(kept) > 1:
            out.append(kept)
            matches.update(found)
            matches[int(ref.content_id)] = "reference"
        if len(rest) > 1 and depth < 1:
            split(rest, depth + 1)

    for g in groups:
        split(list(g), 0)

    def rank(g: List[Any]) -> Tuple[int, int, str]:
        verdicts = [matches.get(int(x.content_id)) for x in g]
        same = any(getattr(v, "verdict", "") == "same" for v in verdicts)
        return (0 if same else 1, -len(g), normalize(g[0].title))

    out.sort(key=rank)
    return out, matches


def shift_cues(cues: List[Any], shift_ms: float, duration_ms: int) -> Tuple[List[Any], int]:
    """1.3.0 (C13) : cues d'une version reportés sur une autre (position + décalage). Renvoie (cues
    reportés, nombre de cues tombés hors du nouveau fichier)."""
    import copy

    out, lost = [], 0
    for c in cues:
        n = copy.copy(c)
        n.ms = int(round(c.ms + shift_ms))
        if c.is_loop:
            n.loop_ms = int(round(c.loop_ms + shift_ms))
        end = n.loop_ms if n.is_loop else n.ms
        if n.ms < 0 or (duration_ms and end > duration_ms):
            lost += 1
            continue
        out.append(n)
    return out, lost


def carry_cues(lib: Any, src_id: int, dst_id: int, fingerprint_of: Any) -> Tuple[List[Any], int]:
    """1.3.0 (C13) : hot cues, boucles et mémoires de `src_id` recalés sur `dst_id` par alignement du
    son. Variante (intro différente, edit) : seuls les cues posés sur un passage identique suivent.
    Renvoie (cues pour dst, nombre de cues non reportés) ; lève LibraryError si impossible."""
    from ..analysis.fingerprint import compare, is_usable, matches_at
    from ..db.errors import LibraryError

    src, dst = lib.get_track(src_id), lib.get_track(dst_id)
    if not dst.analysis_path:
        raise LibraryError("Analyse the kept version first: its hot cues are stored in its analysis files.")
    cues = list(lib.track_cues(src_id))
    a, b = fingerprint_of(src), fingerprint_of(dst)
    if not is_usable(a) or not is_usable(b):
        raise LibraryError("Cannot compare the two versions (unreadable audio): hot cues not carried over.")
    m = compare(a, b, float(src.duration_seconds or 0), float(dst.duration_seconds or 0))
    if m.verdict == "different":
        raise LibraryError("The two versions do not line up: hot cues not carried over.")
    ok_cues = [c for c in cues if m.verdict == "same" or matches_at(a, b, m.shift_ms, c.ms)]
    moved, lost = shift_cues(ok_cues, m.shift_ms, int(dst.duration_seconds or 0) * 1000)
    return moved, lost + len(cues) - len(ok_cues)
