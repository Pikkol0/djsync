"""Téléchargement audio via yt-dlp : flux AAC/m4a NATIF de YouTube, sans ré-encodage.

YouTube Music sert de l'AAC (m4a) et de l'Opus (webm). Rekordbox lit l'AAC mais pas l'Opus.
On demande donc d'abord le m4a tel quel (qualité d'origine, aucune perte de génération).
Repli : si seul un flux Opus est disponible, on le convertit en AAC (un ré-encodage, signalé
dans DownloadProgress.message) pour que le fichier reste lisible par Rekordbox.

FFmpeg reste utile : yt-dlp s'en sert pour réparer le conteneur m4a, et pour le repli.
V0.5.0 : format de sortie au choix (m4a natif / MP3 320) et normalisation du volume (audio_post).
yt-dlp est importé au premier téléchargement (démarrage plus rapide, et une version mise à jour
par core.engine est prise en compte sans redémarrer).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional

from ..models import DownloadedTrack, DownloadProgress, TrackResult
from .audio_post import finalize
from .engine import ydl_options
from .tagger import tag_audio

log = logging.getLogger(__name__)

ProgressCallback = Callable[[DownloadProgress], None]

# Caractères interdits sous Windows (et sur FAT32/exFAT, formats courants des clés USB)
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Flux natif SANS conversion. YouTube / YouTube Music : AAC (m4a). SoundCloud et autres : on
# accepte aussi le MP3 d'origine (une conversion MP3 -> AAC serait une perte inutile).
_YT_NATIVE = "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]"
_ANY_NATIVE = "bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio[ext=flac]/bestaudio[ext=wav]"
# 1.4.0 (C48) : « meilleur flux YouTube » (réglage, désactivé par défaut). AAC 256 (itag 141, comptes
# Premium) s'il existe, sinon Opus ~160 converti en AAC 256 ; le flux AAC ~128 natif en dernier recours.
_YT_BEST = "141/bestaudio[acodec^=mp4a][abr>=200]/bestaudio[acodec=opus]/bestaudio[acodec^=mp4a]/bestaudio"
_READABLE = (".m4a", ".mp3", ".flac", ".wav", ".aiff")  # lisibles par Rekordbox


def sanitize_filename(name: str, max_len: int = 150) -> str:
    name = _FORBIDDEN.sub("_", name).strip(" .")
    return name[:max_len] or "sans_titre"


class Downloader:
    def __init__(self, ffmpeg_location: Optional[str] = None, fallback_bitrate: str = "256",
                 audio_format: str = "m4a", normalize: bool = False) -> None:
        """
        ffmpeg_location  : dossier contenant ffmpeg(.exe) ; None/"" = chercher dans le PATH.
        fallback_bitrate : débit (kbps) de l'AAC produit si le flux natif est indisponible.
        """
        self._ffmpeg = ffmpeg_location or None
        self._fallback_bitrate = fallback_bitrate
        self.audio_format = audio_format
        self.normalize = normalize
        self.soundcloud_auth: dict = {}       # 1.4.0 (C10.1) : options yt-dlp du compte SoundCloud
        self.youtube_best = False             # 1.4.0 (C48) : meilleur flux YouTube (plus lourd)
        self.youtube_auth: dict = {}          # cookies d'un navigateur connecté (YouTube Premium)

    def _ffmpeg_exe(self) -> Optional[str]:
        from ..analysis.decode import find_ffmpeg

        return find_ffmpeg(self._ffmpeg)

    def download(
        self,
        track: TrackResult,
        dest_dir: str | Path,
        on_progress: Optional[ProgressCallback] = None,
        tag: bool = True,
    ) -> DownloadedTrack:
        """Télécharge (m4a natif), puis tagge (sauf tag=False : préécoute). Renvoie le chemin."""
        import yt_dlp

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        base = sanitize_filename(f"{track.artist} - {track.title}")
        # Même nom, autre vidéo (ex. version Titre ET version clip) : on ne réutilise pas
        # le fichier d'une autre source, on suffixe avec l'identifiant YouTube.
        if any((dest / f"{base}{ext}").exists() for ext in (".m4a", ".mp3", ".webm", ".mp4", ".opus", ".wav",
                                                            ".flac", ".aiff")):
            base = f"{base} [{track.video_id}]"
        notify = on_progress or (lambda _p: None)

        original = False
        try:
            try:
                native = _YT_NATIVE if track.source in ("ytmusic", "youtube") else _ANY_NATIVE
                extra: dict = {"format": native}
                if track.source in ("ytmusic", "youtube"):
                    extra.update(self.youtube_auth)
                    if self.youtube_best:
                        extra["format"] = _YT_BEST
                        extra["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a",
                                                    "preferredquality": "256"}]
                if track.source == "soundcloud":
                    extra.update(self.soundcloud_auth)
                    if track.want_original:      # C10.1 : fichier d'origine d'abord, sinon le flux
                        extra["format"] = f"download/{native}"
                path, fmt = self._run(track, dest, base, extra, notify)
                original = fmt == "download"
                if original and path.suffix.lower() not in _READABLE:
                    path = self._to_wav(path)
            except yt_dlp.utils.DownloadError as exc:
                if "format is not available" not in str(exc).lower():
                    raise
                log.warning("No native m4a stream for %s: falling back to converted AAC.", track.video_id)
                notify(DownloadProgress("converting", 0.0, "No native AAC stream: converting to AAC…"))
                path, _fmt = self._run(
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

        if tag and not original and (self.normalize or self.audio_format != "m4a"):
            notify(DownloadProgress("converting", 100.0, "Converting…"))
            try:
                path = finalize(path, self._ffmpeg_exe(), self.audio_format, self.normalize)
            except Exception as exc:  # noqa: BLE001 - le fichier d'origine reste utilisable
                log.warning("Post-processing failed for %s: %s", path, exc)
        if tag:
            notify(DownloadProgress("tagging", 100.0, "Writing tags…"))
            tag_audio(str(path), track)
        notify(DownloadProgress("done", 100.0))
        log.info("Downloaded: %s%s", path, " (original file)" if original else "")
        return DownloadedTrack(track=track, file_path=str(path), original=original)

    def _to_wav(self, path: Path) -> Path:
        """Fichier d'origine dans un format que Rekordbox ne lit pas (ogg, opus…) : décodé en WAV, sans
        nouvelle perte."""
        import subprocess

        exe = self._ffmpeg_exe()
        if not exe:
            raise RuntimeError(f"FFmpeg is needed to convert {path.suffix} to WAV.")
        out = path.with_suffix(".wav")
        subprocess.run([exe, "-loglevel", "error", "-y", "-i", str(path), str(out)], check=True)
        path.unlink(missing_ok=True)
        return out

    def _run(self, track: TrackResult, dest: Path, base: str, extra: dict,
             notify: ProgressCallback) -> "tuple[Path, str]":
        def hook(d: dict) -> None:
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                pct = d.get("downloaded_bytes", 0) / total * 100 if total else 0.0
                notify(DownloadProgress("downloading", pct))

        import yt_dlp

        opts = {
            "js_runtimes": ydl_options()["js_runtimes"],
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
            final = next((dest / f"{base}{ext}" for ext in _READABLE if (dest / f"{base}{ext}").exists()), None)
        if final is None:
            raise FileNotFoundError(f"Expected file not found in {dest}")
        return final, str((info or {}).get("format_id") or "")
