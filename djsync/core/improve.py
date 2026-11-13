"""Onglet « Qualité » (1.4.1, C135 ; d'abord « Améliorer ma bibliothèque », 1.4.0, C47).

Un seul modèle pour tous les sons de la portée (bibliothèque, playlist ou sélection) : qualité annoncée,
qualité mesurée (spectre, C46), drapeaux (vient d'une vidéo, faux sans perte, sous le seuil), meilleure
version trouvée et gain. Rien n'est remplacé sans validation.

La classe d'un fichier et son libellé viennent d'UNE seule source : `AudioInfo` (core/quality.py), qui
lit la mesure du spectre (analysis/spectrum.py, C46). Ce module n'a aucun seuil de qualité à lui ; le seuil
« sous X kbps réels » est un filtre choisi par l'utilisateur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

LOSSLESS_RANK = 10_000
SURE_GAP_S = 3                 # même durée à ± 3 s : remplacement « sûr », version sans pair-à-pair suffisante
MAX_GAP_S = 10                 # au-delà : autre version (live, edit), jamais proposée
SUFFICIENT_RANK = 256          # classe ≥ 256 : une version gratuite suffit, avant Soulseek
YOUTUBE_SOURCES = ("ytmusic", "youtube", "YouTube", "YouTube Music")


def rank_of(info: Any) -> int:
    """Rang de qualité d'un fichier de la bibliothèque (AudioInfo) : sans perte réel > débit réel."""
    if info is None or not getattr(info, "codec", ""):
        return 0
    if info.real_lossless:
        return LOSSLESS_RANK
    return int(info.effective_kbps or info.bitrate or 0)


def label_of(info: Any) -> str:
    """Qualité annoncée (format et débit écrits dans le fichier), avec « (≈) » si elle est fausse."""
    if info is None or not getattr(info, "codec", ""):
        return "?"
    if info.real_lossless:
        return info.codec.upper()
    kbps = info.effective_kbps or info.bitrate
    real = " (≈)" if info.fake else ""
    return f"{info.codec.upper()} {kbps}{real}" if kbps else info.codec.upper()


def announced_label(info: Any) -> str:
    """Ce que le fichier annonce, sans correction (« FLAC », « MP3 320 »)."""
    if info is None or not getattr(info, "codec", ""):
        return "?"
    if info.lossless:
        return info.codec.upper()
    return f"{info.codec.upper()} {info.bitrate}" if info.bitrate else info.codec.upper()


def measured_label(info: Any) -> str:
    """Qualité mesurée d'après le spectre (C46) : « Sans perte », « ≈ 192 », « » si pas encore mesurée."""
    from ..analysis.spectrum import LOSSLESS as REAL_LOSSLESS
    from ..i18n import t

    real = int(getattr(info, "real_kbps", 0) or 0) if info is not None else 0
    if not real:
        return ""
    return t("quality.lossless") if real >= REAL_LOSSLESS else f"≈ {real}"


def is_youtube(track: Any) -> bool:
    return (getattr(track, "source", "") or "") in YOUTUBE_SOURCES


def candidate_rank(track: Any) -> int:
    """Rang de qualité annoncé d'un résultat (TrackResult). YouTube : jamais plus de ≈ 192 (B75)."""
    from .quality import YOUTUBE_CEILING

    r = getattr(track, "slsk", None)
    if r is not None:
        return LOSSLESS_RANK if r.lossless else int(r.bitrate or 0)
    if is_youtube(track):
        return YOUTUBE_CEILING
    q = (getattr(track, "quality", "") or "").upper()
    if q in ("FLAC", "WAV", "AIFF"):
        return LOSSLESS_RANK
    import re

    m = re.search(r"\b(\d{2,4})\b", q)                # « MP3 320 » -> 320 (le 3 de « MP3 » ne compte pas)
    return int(m.group(1)) if m else 0


def candidate_label(track: Any) -> str:
    r = getattr(track, "slsk", None)
    if r is not None:
        return r.quality_label()
    if is_youtube(track) and not (getattr(track, "quality", "") or ""):
        return "YouTube"
    return getattr(track, "quality", "") or "?"


def is_p2p(track: Any) -> bool:
    return getattr(track, "slsk", None) is not None


@dataclass
class QualityRow:
    track: Any                   # LibraryTrack
    info: Any                    # AudioInfo
    video: str = ""              # mention de mauvaise source (« clip officiel ») ou source YouTube, « » sinon
    finds: List[Any] = field(default_factory=list)      # TrackResult, du meilleur au moins bon
    results: List[Any] = field(default_factory=list)    # tout ce que la recherche a rendu (détail d'un son)
    searched: bool = False
    chosen: Optional[Any] = None                        # version choisie à la main dans le détail

    @property
    def best(self) -> Optional[Any]:
        if self.chosen is not None:
            return self.chosen
        return self.finds[0] if self.finds else None

    @property
    def gain(self) -> str:
        b = self.best
        return f"{label_of(self.info)} → {candidate_label(b)}" if b is not None else ""

    @property
    def rank(self) -> int:
        return rank_of(self.info)

    @property
    def fake(self) -> bool:
        return bool(getattr(self.info, "fake", False))

    @property
    def fake_lossless(self) -> bool:
        return bool(self.fake and getattr(self.info, "lossless", False))

    @property
    def measured(self) -> bool:
        return bool(getattr(self.info, "cutoff", 0))

    def under(self, kbps: int) -> bool:
        r = self.rank
        return bool(r) and r < int(kbps)

    def flags(self, kbps: int) -> List[str]:
        """Drapeaux du son (clés) : « video », « fake », « under »."""
        out = []
        if self.video:
            out.append("video")
        if self.fake:
            out.append("fake")
        if self.under(kbps):
            out.append("under")
        return out


Weak = QualityRow               # 1.4.0 (C47) : ancien nom


def video_reason(track: Any, info: Any) -> str:
    """Le son vient d'une vidéo : mention dans le titre (« Clip officiel »…) ou source YouTube connue."""
    from .quality import bad_source

    reason = bad_source(getattr(track, "title", "") or "")
    if reason:
        return reason
    src = getattr(info, "source", "") or ""
    return src if src == "YouTube" else ""            # YouTube Music : piste audio, pas une vidéo


def assess(tracks: Iterable[Any], infos: Dict[int, Any]) -> List[QualityRow]:
    """Une ligne par son dont le fichier a été lu (info connue), du plus faible au meilleur."""
    out = []
    for x in tracks:
        info = infos.get(x.content_id)
        if rank_of(info) == 0:
            continue
        out.append(QualityRow(x, info, video_reason(x, info)))
    out.sort(key=lambda w: (w.rank, str(getattr(w.track, "title", ""))))
    return out


def select(rows: Sequence[QualityRow], under: Optional[int] = None, video: bool = False,
           fake: bool = False) -> List[QualityRow]:
    """Filtres de l'onglet (un son passe s'il répond à AU MOINS un filtre coché) ; aucun filtre : tous."""
    if under is None and not video and not fake:
        return list(rows)
    return [w for w in rows
            if (under is not None and w.under(under)) or (video and w.video) or (fake and w.fake_lossless)]


def weak_tracks(tracks: Sequence[Any], infos: dict, threshold: int = 256, lossless_only: bool = False) -> List[QualityRow]:
    """1.4.0 (C47) : sons sous le seuil (kbps réels) ; `lossless_only` : tout ce qui n'est pas un vrai sans perte."""
    rows = assess(tracks, infos)
    return select(rows, under=LOSSLESS_RANK if lossless_only else threshold)


def duration_gap(row: QualityRow, find: Any) -> Optional[int]:
    dur = int(getattr(row.track, "duration_seconds", 0) or 0)
    d = int(getattr(find, "duration_seconds", 0) or 0)
    return d - dur if dur and d else None


def sufficient_free(row: QualityRow, find: Any) -> bool:
    """Version gratuite, sans pair-à-pair, qui suffit : classe ≥ 256 et même durée à ± 3 s."""
    gap = duration_gap(row, find)
    return (not is_p2p(find) and not is_youtube(find) and candidate_rank(find) >= SUFFICIENT_RANK
            and gap is not None and abs(gap) <= SURE_GAP_S)


def order_key(row: QualityRow, find: Any) -> tuple:
    """Tri par défaut : versions sans pair-à-pair suffisantes d'abord (meilleure classe en tête), puis
    Soulseek (pastille « pair-à-pair »), puis le reste (durée moins sûre, YouTube) ; par classe dans chaque
    groupe."""
    group = 0 if sufficient_free(row, find) else 1 if is_p2p(find) else 2
    return (group, -candidate_rank(find))


def better_finds(row: QualityRow, finds: Sequence[Any], max_gap: int = MAX_GAP_S) -> List[Any]:
    """Résultats meilleurs que le son actuel, de même durée (± `max_gap` s), dans l'ordre par défaut.
    YouTube / YouTube Music : seulement pour un son venant d'une vidéo (une version audio officielle vaut
    mieux qu'un clip, quel que soit le format du fichier), et jamais une vidéo elle-même."""
    from .quality import acceptable_alternative

    current = row.rank
    keep = []
    for f in finds:
        if getattr(f, "is_album", False):
            continue
        youtube = is_youtube(f)
        if youtube:
            if not row.video or not acceptable_alternative(getattr(f, "title", "") or ""):
                continue                    # son venant d'une vidéo : la version audio propre suffit
                                            # (un fichier tiré d'un clip ne vaut pas mieux, même en WAV)
        elif candidate_rank(f) <= current:
            continue
        gap = duration_gap(row, f)
        if gap is not None and abs(gap) > max_gap:
            continue
        keep.append(f)
    keep.sort(key=lambda f: order_key(row, f))
    return keep


def sure(row: QualityRow) -> bool:
    """Remplacement « sûr » (« Remplacer tout ce qui est sûr ») : sans perte vérifiable, même durée (± 3 s).
    Jamais YouTube (plafond ≈ 192)."""
    b = row.best
    if b is None or is_youtube(b) or candidate_rank(b) < LOSSLESS_RANK:
        return False
    gap = duration_gap(row, b)
    return gap is not None and abs(gap) <= SURE_GAP_S


def peer_of(find: Any) -> str:
    r = getattr(find, "slsk", None)
    return (getattr(r, "user", "") or "") if r is not None else ""


def choose_batch(rows: Sequence[QualityRow]) -> Dict[int, Any]:
    """Choix automatique pour un lot : par son, la meilleure version ; à qualité équivalente, la source sans
    pair-à-pair ; et des pairs variés d'un son à l'autre (un pair déjà pris passe après un autre de même
    qualité). Renvoie {content_id: version}."""
    used: Dict[str, int] = {}
    out: Dict[int, Any] = {}
    for row in rows:
        if row.chosen is not None:
            out[row.track.content_id] = row.chosen
            continue
        if not row.finds:
            continue
        top = candidate_rank(row.finds[0])
        same = [f for f in row.finds if candidate_rank(f) == top]
        free = [f for f in same if not is_p2p(f)]
        if free:
            pick = free[0]
        else:
            pick = min(same, key=lambda f: (used.get(peer_of(f), 0), same.index(f)))
        if is_p2p(pick):
            used[peer_of(pick)] = used.get(peer_of(pick), 0) + 1
        out[row.track.content_id] = pick
    return out
