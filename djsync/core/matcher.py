"""Correspondance morceau Spotify -> résultat YouTube Music (Titre ou Vidéo).

Chaque candidat reçoit un score 0-100 (titre 50 %, artiste 30 %, durée 20 %, pénalités pour
remix/live/karaoké… absents du morceau d'origine). Ensuite `choose()` applique la préférence :

  AUTO  : le Titre officiel, sauf si une Vidéo est nettement meilleure (+12) ; si aucun Titre
          n'est assez bon, bascule sur la meilleure Vidéo (bootlegs, versions introuvables…).
  SONG  : le meilleur Titre dès qu'il est plausible, sinon la meilleure Vidéo.
  VIDEO : l'inverse.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence

from rapidfuzz import fuzz

from ..models import (
    LOW_SCORE, OK_SCORE, PREFERENCE_LABELS, Candidate, MatchPreference, MatchResult, SearchMode,
    SpotifyTrack, TrackResult,
)
from .duplicates import normalize
from .search import plain

__all__ = ["LOW_SCORE", "OK_SCORE", "PREFERENCE_LABELS", "Candidate", "MatchPreference", "MatchResult",
           "SpotifyMatcher", "apply_preference", "choose", "score_candidate"]

_UNWANTED = (
    "remix", "live", "cover", "karaoke", "instrumental", "sped up", "slowed", "nightcore",
    "8d", "reverb", "acoustic", "mashup", "reaction", "tutorial", "bass boosted",
)
_TITLE_SPLIT = re.compile(r"\s[-–—|]\s")


# --------------------------------------------------------------------------- score
def _nospace(text: str) -> str:
    return text.replace(" ", "")


_BRACKET_GROUP = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")
_VERSION_WORDS = re.compile(
    r"\b(remix|live|edit|version|mix|vip|bootleg|cover|acoustic|instrumental|sped|slowed|rework|flip)\b", re.I
)


def _title_key(text: str) -> str:
    """normalize(), mais en CONSERVANT les parenthèses qui désignent une version
    ("(Remix)", "[Live]", "(Radio Edit)") : un remix n'est pas l'original.
    Les autres ("(feat. X)", "(Official Video)", "[Lyrics]") sont ignorées."""
    kept = _BRACKET_GROUP.sub(lambda m: f" {m.group(1)} " if _VERSION_WORDS.search(m.group(1)) else " ", text)
    return normalize(kept)


def score_candidate(src: SpotifyTrack, cand: TrackResult) -> float:
    # --- titre : on compare aussi chaque morceau de "Artiste - Titre (Official Video)"
    wanted = _title_key(src.title)
    cand_norm = _title_key(cand.title)
    variants = {cand_norm}
    variants |= {_title_key(p) for p in _TITLE_SPLIT.split(cand.title)}
    artist_norm = normalize(cand.artist)
    if artist_norm:
        variants.add(cand_norm.replace(artist_norm, " ").strip())
    variants.discard("")
    title_score = max((fuzz.ratio(wanted, v) for v in variants), default=0.0)

    # --- artiste : sous-chaîne (couvre "DaftPunkVEVO", "X - Topic", artiste présent dans le titre)
    if src.artists:
        hay_title, hay_artist = _nospace(cand_norm), _nospace(artist_norm)
        artist_score = 0.0
        for name in src.artists:
            n = _nospace(normalize(name))
            if not n:
                continue
            if len(n) >= 3 and (n in hay_title or n in hay_artist):
                s = 100.0
            else:
                s = fuzz.ratio(n, hay_artist)
            artist_score = max(artist_score, s)
    else:
        artist_score = 60.0  # liste collée sans artiste : neutre

    # --- durée (les vidéos ont souvent une intro : tolérance progressive)
    if src.duration_seconds and cand.duration_seconds:
        delta = abs(src.duration_seconds - cand.duration_seconds)
        duration_score = 100 if delta <= 2 else 85 if delta <= 5 else 65 if delta <= 10 else 40 if delta <= 20 else 10
    else:
        duration_score = 60.0

    # --- pénalités : version différente de celle demandée
    # (symétrique : le remix demandé n'est pas satisfait par l'original, et inversement)
    wanted_plain = " " + plain(f"{src.title} {src.album or ''}") + " "
    cand_plain = " " + plain(f"{cand.title} {cand.album or ''}") + " "
    penalty = 0.0
    for word in _UNWANTED:
        needle = f" {word} "
        if (needle in cand_plain) != (needle in wanted_plain):
            penalty += 25.0
    penalty = min(penalty, 45.0)

    return max(0.0, min(100.0, 0.5 * title_score + 0.3 * artist_score + 0.2 * duration_score - penalty))


def choose(candidates: Sequence[Candidate], preference: MatchPreference) -> Optional[int]:
    """Index du candidat retenu selon la préférence, ou None (introuvable)."""
    def best(is_song: bool) -> Optional[int]:
        idx = [i for i, c in enumerate(candidates) if c.track.is_song == is_song]
        return max(idx, key=lambda i: candidates[i].score) if idx else None

    song, video = best(True), best(False)
    score = lambda i: candidates[i].score  # noqa: E731

    if preference == MatchPreference.AUTO:
        if song is not None and score(song) >= OK_SCORE:
            if video is not None and score(video) >= OK_SCORE and score(video) >= score(song) + 12:
                return video
            return song
        pool = [i for i in (song, video) if i is not None]
        top = max(pool, key=score, default=None)
        return top if top is not None and score(top) >= LOW_SCORE else None

    first, second = (song, video) if preference == MatchPreference.SONG else (video, song)
    for i in (first, second):
        if i is not None and score(i) >= LOW_SCORE:
            return i
    return None


def apply_preference(result: MatchResult, preference: MatchPreference) -> None:
    """Applique la préférence à un résultat, sauf si l'utilisateur a choisi à la main."""
    if not result.manual:
        result.chosen = choose(result.candidates, preference)


class SpotifyMatcher:
    def __init__(self, searcher: Any) -> None:
        self._searcher = searcher

    def find_candidates(self, src: SpotifyTrack, per_type: int = 5) -> List[Candidate]:
        """Cherche Titres ET Vidéos, score, trie. Les deux familles sont toujours gardées
        pour que changer de préférence ne demande aucune nouvelle recherche."""
        found: List[TrackResult] = []
        for mode in (SearchMode.SONGS, SearchMode.VIDEOS):
            found += self._searcher.search(src.query, limit=per_type, mode=mode)
        seen, out = set(), []
        for track in found:
            if track.video_id in seen:
                continue
            seen.add(track.video_id)
            out.append(Candidate(track, round(score_candidate(src, track), 1)))
        out.sort(key=lambda c: c.score, reverse=True)
        return out
