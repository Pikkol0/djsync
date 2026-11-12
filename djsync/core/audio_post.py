"""Après le téléchargement : conversion en MP3 au débit choisi (1.4.1, C143), sinon rien.

* Choix « sans conversion » (m4a) : le fichier téléchargé est gardé tel quel.
* MP3 320 / 256 / 192 / 128 : LAME, depuis le meilleur flux téléchargé. Un fichier déjà en MP3 n'est jamais
  ré-encodé (une conversion MP3 -> MP3 perd sans rien gagner).
* « Même volume » (gain fixe + ré-encodage) est retiré (décision du 05/11) : le volume égal reviendra avec
  C109, sans modifier le fichier.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

FORMATS = ("m4a", "mp3")


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def finalize(path: Path, ffmpeg: Optional[str], audio_format: str = "m4a", mp3_bitrate: str = "320k") -> Path:
    """Convertit en MP3 (`audio_format="mp3"`, au débit `mp3_bitrate`) ; renvoie le fichier final (l'original
    est remplacé). Sans FFmpeg, ou si rien n'est à faire (m4a, ou déjà un MP3), le fichier est rendu tel quel."""
    path = Path(path)
    want_mp3 = audio_format == "mp3" and path.suffix.lower() != ".mp3"
    if not ffmpeg or not want_mp3:
        return path
    tmp = path.with_name(path.stem + ".djsync-tmp.mp3")
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-y", "-i", str(path), "-map", "0:a:0", "-vn", "-map_metadata", "0",
           "-c:a", "libmp3lame", "-b:a", mp3_bitrate, "-id3v2_version", "3", str(tmp)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=_no_window())
    if proc.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Conversion failed: {proc.stderr.strip()[-200:] or 'FFmpeg error'}")
    final = path.with_suffix(".mp3")
    if final.exists() and final != path:
        final = path.with_name(f"{path.stem} (1).mp3")
    os.replace(tmp, final)
    if final != path:
        path.unlink(missing_ok=True)
    return final
