"""Écrire le BPM et la tonalité dans les tags des fichiers audio (1.4.3, S05).

Réglage (désactivé par défaut, car le fichier est modifié) : Paramètres ▸ Analyse ▸ « Écrire le BPM et la
tonalité dans les fichiers ». Après une analyse réussie, le tempo et la tonalité sont écrits dans les tags que
lisent les autres logiciels (Serato, Traktor, Mixed In Key, explorateurs) :

* MP3 / AIFF / WAV (ID3) : TBPM, TKEY ;
* M4A : « tmpo », « ----:com.apple.iTunes:initialkey » ;
* FLAC / Ogg : BPM, INITIALKEY.

Le son lui-même n'est pas touché (mutagen réécrit seulement les tags, en gardant la marge déjà réservée
quand elle suffit). Rien n'est écrit si les valeurs y sont déjà. La taille du fichier peut changer : la
bibliothèque la met à jour (fileSize / FileSize) et le registre de la vraie qualité suit.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

log = logging.getLogger(__name__)


def _bpm_text(bpm: float) -> str:
    return str(int(round(bpm))) if bpm > 0 else ""


def write_analysis_tags(path: Union[str, Path], bpm: float, key: Optional[str]) -> Optional[int]:
    """Écrit BPM et tonalité ; renvoie la nouvelle taille du fichier si quelque chose a été écrit, sinon None.
    Ne lève jamais (fichier en lecture seule, format inconnu : noté au journal)."""
    path = Path(path)
    bpm_s, key = _bpm_text(bpm), (key or "").strip()
    if not bpm_s and not key:
        return None
    try:
        import mutagen

        audio = mutagen.File(str(path))
        if audio is None:
            return None
        changed = _apply(audio, bpm_s, key)
        if not changed:
            return None
        audio.save()
        size = path.stat().st_size
        log.info("Tags written (%s): BPM %s, key %s", path.name, bpm_s or "-", key or "-")
        return size
    except Exception as exc:  # noqa: BLE001 - le son reste tel quel
        log.warning("Tags not written (%s): %s", path.name, exc)
        return None


def _apply(audio, bpm_s: str, key: str) -> bool:
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4, MP4FreeForm

    if isinstance(audio, MP4):
        tags = audio.tags if audio.tags is not None else audio.add_tags() or audio.tags
        changed = False
        if bpm_s and tags.get("tmpo") != [int(bpm_s)]:
            tags["tmpo"] = [int(bpm_s)]
            changed = True
        name = "----:com.apple.iTunes:initialkey"
        if key and [bytes(v).decode("utf-8", "replace") for v in tags.get(name, [])] != [key]:
            tags[name] = [MP4FreeForm(key.encode("utf-8"))]
            changed = True
        return changed
    tags = getattr(audio, "tags", None)
    if isinstance(audio, FLAC) or (tags is not None and hasattr(tags, "keys") and type(tags).__name__ in
                                   ("VCFLACDict", "VComment", "OggVCommentDict")):
        if tags is None:
            audio.add_tags()
            tags = audio.tags
        changed = False
        for field, value in (("BPM", bpm_s), ("INITIALKEY", key)):
            if value and list(tags.get(field, [])) != [value]:
                tags[field] = [value]
                changed = True
        return changed
    # ID3 (MP3, AIFF, WAV)
    from mutagen.id3 import ID3, TBPM, TKEY

    if tags is None:
        audio.add_tags()
        tags = audio.tags
    if not isinstance(tags, ID3):
        return False
    changed = False
    if bpm_s and [str(x) for x in (tags.get("TBPM").text if tags.get("TBPM") else [])] != [bpm_s]:
        tags.setall("TBPM", [TBPM(encoding=3, text=[bpm_s])])
        changed = True
    if key and [str(x) for x in (tags.get("TKEY").text if tags.get("TKEY") else [])] != [key]:
        tags.setall("TKEY", [TKEY(encoding=3, text=[key])])
        changed = True
    return changed


def after_analysis(path: Union[str, Path], analysis) -> Optional[int]:
    """Appelé par les bibliothèques après une analyse réussie (réglage actif) : écrit les tags et garde la
    vraie qualité mesurée sous la nouvelle taille du fichier."""
    try:
        from ..analysis import spectrum

        before = spectrum.known(path)
    except Exception:  # noqa: BLE001
        before = None
    size = write_analysis_tags(path, analysis.bpm, analysis.key.name)
    if size is not None:
        cutoff = analysis.cutoff if analysis.cutoff is not None else before
        if cutoff is not None:
            try:
                from ..analysis import spectrum

                spectrum.remember(path, cutoff)
            except Exception:  # noqa: BLE001
                log.debug("Ignored error in after_analysis", exc_info=True)
    return size
