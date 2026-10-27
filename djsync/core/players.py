"""Conversion pour les platines (1.4.0, C26 sens C).

Les CDJ et XDJ d'avant la série NXS2 (CDJ-2000NXS, CDJ-900NXS, XDJ-1000, XDJ-700…) ne lisent pas le
FLAC, ni plus de 48 kHz. Sur une clé USB, DJSync peut donc enregistrer les FLAC en WAV ou en AIFF :
même son (décodage sans perte, même nombre de bits), fichier environ deux fois plus lourd. Au-delà de
48 kHz, le son est ramené à 44,1 ou 48 kHz, la seule perte (inaudible) acceptée pour être lu partout.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

FORMATS = ("", "wav", "aiff")          # "" = garder le FLAC
CONVERTED = (".flac",)
MAX_RATE = 48000


def needs(path: Path, fmt: str) -> bool:
    return bool(fmt) and Path(path).suffix.lower() in CONVERTED


def target_path(path: Path, fmt: str) -> Path:
    return Path(path).with_suffix(".aiff" if fmt == "aiff" else ".wav")


def _probe(path: Path) -> "tuple[int, int]":
    """(bits, fréquence) du fichier source, (16, 44100) si inconnus."""
    try:
        import mutagen

        info = mutagen.File(str(path)).info
        return int(getattr(info, "bits_per_sample", 0) or 16), int(getattr(info, "sample_rate", 0) or 44100)
    except Exception:  # noqa: BLE001
        return 16, 44100


def ffmpeg_args(src: Path, out: Path, fmt: str) -> List[str]:
    bits, rate = _probe(src)
    depth = 24 if bits > 16 else 16
    codec = f"pcm_s{depth}{'be' if fmt == 'aiff' else 'le'}"
    args = ["-loglevel", "error", "-y", "-i", str(src), "-map", "0:a:0", "-c:a", codec]
    if rate > MAX_RATE:
        args += ["-ar", "44100" if rate % 44100 == 0 else "48000"]
    if fmt == "aiff":
        args += ["-write_id3v2", "1", "-map_metadata", "0"]
    return args + [str(out)]


def convert(src: Path, out: Path, fmt: str, ffmpeg: Optional[str] = None) -> Path:
    """Écrit `src` en WAV / AIFF dans `out` (fichier temporaire puis renommage). `src` n'est pas touché."""
    from ..analysis.decode import find_ffmpeg

    exe = find_ffmpeg(ffmpeg)
    if not exe:
        raise RuntimeError("FFmpeg is needed to convert FLAC for the players.")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".djsync-part" + out.suffix)    # extension gardée : ffmpeg choisit le format
    try:
        subprocess.run([exe] + ffmpeg_args(src, tmp, fmt), check=True, capture_output=True)
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("Converted for the players: %s -> %s", Path(src).name, out.name)
    return out
