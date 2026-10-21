"""Après le téléchargement : format de sortie (m4a natif ou MP3 320) et normalisation du volume.

* m4a (défaut) : le flux AAC d'origine, sans ré-encodage — rien n'est touché.
* mp3 : MP3 320 kbit/s (LAME), pour les vieux lecteurs/platines qui ne lisent pas l'AAC.
* normalisation (option) : on MESURE la sonie (EBU R128, une passe de décodage) puis on applique un
  gain fixe vers la cible, plafonné pour que les crêtes réelles restent sous -1 dBTP. C'est un simple
  gain : la dynamique du morceau n'est pas modifiée (pas de compresseur). Le fichier est ré-encodé
  (AAC 256 kbit/s ou MP3 320), sauf si le gain est négligeable.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

TARGET_LUFS = -9.0           # niveau typique d'un morceau club masterisé
MAX_TRUE_PEAK = -1.0         # dBTP après gain
MIN_GAIN = 0.5               # dB : en dessous, on ne ré-encode pas pour rien
FORMATS = ("m4a", "mp3")


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


@dataclass
class Loudness:
    integrated: float        # LUFS
    true_peak: float         # dBTP

    def gain_to(self, target: float = TARGET_LUFS, ceiling: float = MAX_TRUE_PEAK) -> float:
        """Gain (dB) vers la cible, limité par la marge de crête disponible."""
        return round(min(target - self.integrated, ceiling - self.true_peak), 1)


def measure(path: Path, ffmpeg: str) -> Optional[Loudness]:
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0", "-vn",
           "-af", "ebur128=peak=true", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=_no_window())
    summary = proc.stderr.rsplit("Summary:", 1)[-1]
    i = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
    p = re.search(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary)
    if not i or not p or "inf" in i.group(1):
        return None
    return Loudness(float(i.group(1)), float(p.group(1)) if "inf" not in p.group(1) else -99.0)


def finalize(path: Path, ffmpeg: Optional[str], audio_format: str = "m4a", normalize: bool = False,
             mp3_bitrate: str = "320k", aac_bitrate: str = "256k") -> Path:
    """Applique le format et la normalisation demandés ; renvoie le fichier final (l'original est
    remplacé). Sans FFmpeg, ou si rien n'est à faire, le fichier est rendu tel quel."""
    path = Path(path)
    want_mp3 = audio_format == "mp3" and path.suffix.lower() != ".mp3"
    if not ffmpeg or (not want_mp3 and not normalize):
        return path
    gain = 0.0
    if normalize:
        loud = measure(path, ffmpeg)
        if loud is not None:
            gain = loud.gain_to()
    if not want_mp3 and abs(gain) < MIN_GAIN:
        return path
    out_ext = ".mp3" if (want_mp3 or path.suffix.lower() == ".mp3") else ".m4a"
    tmp = path.with_name(path.stem + ".djsync-tmp" + out_ext)
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-y", "-i", str(path), "-map", "0:a:0", "-vn", "-map_metadata", "0"]
    if abs(gain) >= MIN_GAIN:
        cmd += ["-af", f"volume={gain:+.1f}dB"]
    if out_ext == ".mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", mp3_bitrate, "-id3v2_version", "3"]
    else:
        cmd += ["-c:a", "aac", "-b:a", aac_bitrate, "-movflags", "+faststart"]
    cmd.append(str(tmp))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=_no_window())
    if proc.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Conversion failed: {proc.stderr.strip()[-200:] or 'FFmpeg error'}")
    final = path.with_suffix(out_ext)
    if final.exists() and final != path:
        final = path.with_name(f"{path.stem} (1){out_ext}")
    os.replace(tmp, final)
    if final != path:
        path.unlink(missing_ok=True)
    return final
