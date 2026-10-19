"""Téléchargement audio via yt-dlp : flux AAC/m4a NATIF de YouTube, sans ré-encodage.

YouTube Music sert de l'AAC (m4a) et de l'Opus (webm). Rekordbox lit l'AAC mais pas l'Opus.
On demande donc d'abord le m4a tel quel (qualité d'origine, aucune perte de génération).
Repli : si seul un flux Opus est disponible, on le convertit en AAC (un ré-encodage, signalé
dans DownloadProgress.message) pour que le fichier reste lisible par Rekordbox.

FFmpeg reste utile : yt-dlp s'en sert pour réparer le conteneur m4a, et pour le repli.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from .models import DownloadedTrack, DownloadProgress, TrackResult
from .tagger import tag_audio

log = logging.getLogger(__name__)

ProgressCallback = Callable[[DownloadProgress], None]

# Caractères interdits sous Windows (et sur FAT32/exFAT, formats courants des clés USB)
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Flux m4a (AAC) natif, sans aucune conversion
_NATIVE_FORMAT = "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]"


def sanitize_filename(name: str, max_len: int = 150) -> str:
    name = _FORBIDDEN.sub("_", name).strip(" .")
    return name[:max_len] or "sans_titre"


class Downloader:
    def __init__(self, ffmpeg_location: Optional[str] = None, fallback_bitrate: str = "256") -> None:
        """
        ffmpeg_location  : dossier contenant ffmpeg(.exe) ; None/"" = chercher dans le PATH.
        fallback_bitrate : débit (kbps) de l'AAC produit si le flux natif est indisponible.
        """
        self._ffmpeg = ffmpeg_location or None
        self._fallback_bitrate = fallback_bitrate

    def download(
        self,
        track: TrackResult,
        dest_dir: str | Path,
        on_progress: Optional[ProgressCallback] = None,
        tag: bool = True,
    ) -> DownloadedTrack:
        """Télécharge (m4a natif), puis tagge (sauf tag=False : préécoute). Renvoie le chemin."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        base = sanitize_filename(f"{track.artist} - {track.title}")
        # Même nom, autre vidéo (ex. version Titre ET version clip) : on ne réutilise pas
        # le fichier d'une autre source, on suffixe avec l'identifiant YouTube.
        if any((dest / f"{base}{ext}").exists() for ext in (".m4a", ".mp3", ".webm", ".mp4", ".opus")):
            base = f"{base} [{track.video_id}]"
        notify = on_progress or (lambda _p: None)

        try:
            try:
                path = self._run(track, dest, base, {"format": _NATIVE_FORMAT}, notify)
            except yt_dlp.utils.DownloadError as exc:
                if "format is not available" not in str(exc).lower():
                    raise
                log.warning("Pas de flux m4a natif pour %s : repli en AAC converti.", track.video_id)
                notify(DownloadProgress("converting", 0.0, "Pas de flux AAC natif : conversion en AAC…"))
                path = self._run(
                    track, dest, base,
                    {
                        "format": "bestaudio/best",
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "m4a",
                            "preferredquality": self._fallback_bitrate,
                        }],
                    },
                    notify,
                )
        except yt_dlp.utils.DownloadError as exc:
            notify(DownloadProgress("error", message=str(exc)))
            raise

        if tag:
            notify(DownloadProgress("tagging", 100.0, "Écriture des tags…"))
            tag_audio(str(path), track)
        notify(DownloadProgress("done", 100.0))
        log.info("Téléchargé : %s", path)
        return DownloadedTrack(track=track, file_path=str(path))

    def _run(self, track: TrackResult, dest: Path, base: str, extra: dict,
             notify: ProgressCallback) -> Path:
        def hook(d: dict) -> None:
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                pct = d.get("downloaded_bytes", 0) / total * 100 if total else 0.0
                notify(DownloadProgress("downloading", pct))

        opts = {
            "outtmpl": str(dest / f"{base}.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [hook],
            **extra,
        }
        if self._ffmpeg:
            opts["ffmpeg_location"] = self._ffmpeg

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(track.url, download=True)

        # Chemin réel donné par yt-dlp (après d'éventuels post-traitements)
        downloads = (info or {}).get("requested_downloads") or []
        final = Path(downloads[0]["filepath"]) if downloads and downloads[0].get("filepath") else None
        if final is None or not final.exists():
            final = dest / f"{base}.m4a"
        if not final.exists():
            raise FileNotFoundError(f"Fichier attendu introuvable : {final}")
        return final
