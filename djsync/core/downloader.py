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
from typing import Any, Callable, Optional

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


def cookie_error(exc: Any) -> bool:
    """1.4.0-rc.4 (B82) : connexion du navigateur illisible (Chrome verrouille et chiffre ses cookies)."""
    text = str(exc).lower()
    return "cookie" in text and any(k in text for k in ("could not copy", "failed to decrypt", "could not find",
                                                         "permission", "database", "dpapi"))


class Downloader:
    def __init__(self, ffmpeg_location: Optional[str] = None, fallback_bitrate: str = "256",
                 quality: str = "original") -> None:
        """
        ffmpeg_location  : dossier contenant ffmpeg(.exe) ; None/"" = chercher dans le PATH.
        fallback_bitrate : débit (kbps) de l'AAC produit si le flux natif est indisponible.
        quality          : 1.4.1 (C143) : original | yt_best | mp3_320 | mp3_256 | mp3_192 | mp3_128.
        """
        self._ffmpeg = ffmpeg_location or None
        self._fallback_bitrate = fallback_bitrate
        self.quality = quality
        self.soundcloud_auth: dict = {}       # 1.4.0 (C10.1) : options yt-dlp du compte SoundCloud
        self.youtube_auth: dict = {}          # cookies d'un navigateur connecté (YouTube Premium)

    @property
    def mp3_kbps(self) -> int:
        """Débit du MP3 voulu (0 : pas de conversion)."""
        return int(self.quality[4:]) if self.quality.startswith("mp3_") and self.quality[4:].isdigit() else 0

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
            path, original = self._fetch(track, dest, base, notify)
        except yt_dlp.utils.DownloadCancelled:
            # 1.4.1 (C145) : arrêt demandé pendant le téléchargement : morceaux partiels effacés
            remove_partials(dest, base)
            raise
        return self._finish(track, path, original, notify, tag)

    def _fetch(self, track: TrackResult, dest: Path, base: str, notify: ProgressCallback) -> "tuple[Path, bool]":
        import yt_dlp

        original = False
        try:
            try:
                native = _YT_NATIVE if track.source in ("ytmusic", "youtube") else _ANY_NATIVE
                extra: dict = {"format": native}
                if track.source in ("ytmusic", "youtube"):
                    extra.update(self.youtube_auth)
                    if self.quality == "yt_best":
                        extra["format"] = _YT_BEST
                        extra["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a",
                                                    "preferredquality": "256"}]
                    elif self.mp3_kbps:          # 1.4.1 (C143) : un MP3 est fait depuis le meilleur flux
                        extra["format"] = _YT_BEST
                if track.source == "soundcloud":
                    extra.update(self.soundcloud_auth)
                    if track.want_original:      # C10.1 : fichier d'origine d'abord, sinon le flux
                        extra["format"] = f"download/{native}"
                try:
                    path, fmt = self._run(track, dest, base, extra, notify)
                except Exception as exc:  # noqa: BLE001 - 1.4.0-rc.4 (B82) : cookies du navigateur illisibles
                    if track.source != "soundcloud" or not cookie_error(exc):
                        raise
                    log.warning("SoundCloud login unreadable (%s): downloading the stream instead.", exc)
                    notify(DownloadProgress("downloading", 0.0, "SoundCloud login unreadable: stream instead"))
                    path, fmt = self._run(track, dest, base, {"format": native}, notify)
                original = fmt == "download"
                # 1.4.0 (C45) : fichier sans perte d'une source libre (Internet Archive) : jamais transcodé
                if track.source in ("archive", "audius") and path.suffix.lower() in (".flac", ".wav", ".aiff", ".aif"):
                    original = True
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
        return path, original

    def _finish(self, track: TrackResult, path: Path, original: bool, notify: ProgressCallback,
                tag: bool) -> DownloadedTrack:
        if tag and not original and self.mp3_kbps and path.suffix.lower() != ".mp3":
            notify(DownloadProgress("converting", 100.0, "Converting…"))
            try:
                path = finalize(path, self._ffmpeg_exe(), "mp3", f"{self.mp3_kbps}k")
            except Exception as exc:  # noqa: BLE001 - le fichier d'origine reste utilisable…
                if path.suffix.lower() not in _READABLE:     # … sauf un flux que Rekordbox ne lit pas (Opus)
                    raise
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


def remove_partials(dest: Path, base: str) -> None:
    """1.4.1 (C145) : fichiers laissés par un téléchargement interrompu (« .part », « .ytdl », fragments)."""
    import glob

    for f in Path(dest).glob(glob.escape(base) + ".*"):
        name = f.name
        if name.endswith((".part", ".ytdl")) or ".part-Frag" in name or ".temp." in name:
            try:
                f.unlink()
            except OSError:
                pass
