"""Échelle de qualité commune (1.3.1, C29) : Bon · Moyen · Attention · Problème · Neutre.

Un seul endroit pour les seuils, utilisés partout où une couleur aide à lire (ressemblance de deux sons,
qualité audio, confiance d'une correspondance, écart de BPM…). Couleurs du thème (theme.LEVELS),
indépendantes de la couleur d'accent ; toujours doublées d'un mot ou d'un nombre (lisibles par les
daltoniens). Léger : couleur du texte ou petite pastille, jamais de grands aplats.
"""
from __future__ import annotations

from typing import Optional

GOOD, FAIR, WARN, BAD, NEUTRAL = "good", "fair", "warn", "bad", "neutral"
CHIP_ROLE = {GOOD: "chip_good", FAIR: "chip_fair", WARN: "chip_warn", BAD: "chip_bad", NEUTRAL: "chip"}


def similarity(pct: float) -> str:
    """Part commune de deux sons (Doublons) : ≥ 90 % bon, 70–90 moyen, 50–70 attention, < 50 problème."""
    return GOOD if pct >= 90 else FAIR if pct >= 70 else WARN if pct >= 50 else BAD


def match_score(score: float) -> str:
    """Score d'une correspondance (Import, Deezer, recherche) : ≥ 90 bon, 75–90 moyen, 60–75 attention."""
    return GOOD if score >= 90 else FAIR if score >= 75 else WARN if score >= 60 else BAD


def audio_quality(kbps: Optional[int], lossless: bool = False) -> str:
    """Qualité audio : sans perte / ≥ 320 bon, 192–320 moyen, 128–192 attention, < 128 problème."""
    if lossless:
        return GOOD
    if not kbps:
        return NEUTRAL
    return GOOD if kbps >= 300 else FAIR if kbps >= 190 else WARN if kbps >= 125 else BAD


def quality_rank(kbps: Optional[int], lossless: bool = False) -> int:
    """Rang pour comparer deux versions (plus grand = meilleur) : sans perte > 320 > 256 > 192 > 128."""
    return 10_000 if lossless else int(kbps or 0)


def bpm_gap(pct: float) -> str:
    """Écart de tempo entre deux sons (suggestions) : ≤ 2 % bon, ≤ 4 moyen, ≤ 6 attention."""
    a = abs(pct)
    return GOOD if a <= 2 else FAIR if a <= 4 else WARN if a <= 6 else BAD


def color(level: str) -> str:
    from . import theme

    return theme.LEVELS.get(level, theme.DIM)


# ------------------------------------------------------------- C42 : format et débit lisibles
_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


def audio_text(info, file_type: int = 0, missing: bool = False):
    """(« AAC · 256 kbps · 44,1 kHz », niveau) pour une version ; « ? » si le fichier manque, le format
    de la base seulement tant que le fichier n'a pas été lu."""
    if missing:
        return "?", NEUTRAL
    if info is not None and getattr(info, "codec", ""):
        parts = [info.codec.upper()]
        if info.lossless:
            parts.append("lossless")
        elif info.bitrate:
            parts.append(f"{info.bitrate} kbps")
        if info.sample_rate:
            parts.append(f"{info.sample_rate / 1000:g} kHz")
        return " · ".join(parts), audio_quality(info.bitrate, info.lossless)
    return _FORMATS.get(file_type, ""), NEUTRAL


def expected_download(source: str, audio_format: str):
    """C42 : qualité attendue d'une version à retélécharger (YouTube Music / YouTube ≈ AAC 128 kbps,
    SoundCloud ≈ 128 kbps) ; un MP3 320 réencodé n'en contient pas plus que sa source."""
    src_kbps = 128
    if audio_format == "mp3":
        return f"MP3 320 (source ~{src_kbps} kbps)", audio_quality(src_kbps)
    return f"m4a · ~{src_kbps} kbps", audio_quality(src_kbps)


def html(text: str, level: str) -> str:
    from html import escape

    if not text:
        return ""
    if level == NEUTRAL:
        return escape(text)
    return f'<span style="color:{color(level)}">{escape(text)}</span>'
