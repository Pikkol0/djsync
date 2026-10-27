"""Écriture des tags (Titre, Artiste, Album, pochette) avec mutagen : m4a (AAC) et mp3."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from mutagen.id3 import APIC, ID3, TALB, TCON, TIT2, TPE1, TPUB, TRCK, TSRC, TYER, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

from ..models import TrackResult

log = logging.getLogger(__name__)

# Les URLs googleusercontent portent la taille demandée (=w60-h60...) : on l'agrandit.
_SIZE_SUFFIX = re.compile(r"=w\d+-h\d+.*$")


def _fetch_cover(url: Optional[str]) -> Optional[bytes]:
    if not url:
        return None
    url = _SIZE_SUFFIX.sub("=w600-h600", url)
    try:
        import requests                  # import tardif : démarrage plus rapide

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as exc:
        log.warning("Artwork unavailable (%s): continuing without it.", exc)
        return None


def _square(data: Optional[bytes]) -> Optional[bytes]:
    """Les vignettes de VIDÉOS sont en 16:9/4:3 : on recadre au centre en carré (JPEG)."""
    if not data:
        return data
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = img.size
        if w == h:
            return data
        s = min(w, h)
        img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=92)
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - Pillow absent ou image illisible : on garde l'original
        log.debug("Artwork not cropped: %s", exc)
        return data


def tag_m4a(file_path: str, track: TrackResult) -> None:
    """Tags iTunes/MP4 (atomes ©nam, ©ART, ©alb, covr), reconnus par Rekordbox."""
    mp4 = MP4(file_path)
    if mp4.tags is None:
        mp4.add_tags()
    mp4["\xa9nam"] = [track.title]
    mp4["\xa9ART"] = [track.artist]
    if track.album:
        mp4["\xa9alb"] = [track.album]
    if track.release_date or track.year:
        mp4["\xa9day"] = [track.release_date or str(track.year)]
    if track.genre:
        mp4["\xa9gen"] = [track.genre]
    if track.track_no:
        mp4["trkn"] = [(int(track.track_no), 0)]
    cover = _square(_fetch_cover(track.thumbnail_url))
    if cover:
        fmt = MP4Cover.FORMAT_PNG if cover.startswith(b"\x89PNG") else MP4Cover.FORMAT_JPEG
        mp4["covr"] = [MP4Cover(cover, imageformat=fmt)]
    mp4.save()


def tag_mp3(file_path: str, track: TrackResult) -> None:
    """ID3v2.3 / UTF-16 : le plus compatible avec Rekordbox et les CDJ."""
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.add(TIT2(encoding=1, text=track.title))
    tags.add(TPE1(encoding=1, text=track.artist))
    if track.album:
        tags.delall("TALB")
        tags.add(TALB(encoding=1, text=track.album))
    if track.year:                               # ID3v2.3 : année (TYER)
        tags.delall("TYER")
        tags.add(TYER(encoding=1, text=str(track.year)))
    for frame, value in ((TCON, track.genre), (TPUB, track.label), (TSRC, track.isrc),
                         (TRCK, str(track.track_no) if track.track_no else None)):
        if value:
            tags.delall(frame.__name__)
            tags.add(frame(encoding=1, text=value))

    cover = _square(_fetch_cover(track.thumbnail_url))
    if cover:
        mime = "image/png" if cover.startswith(b"\x89PNG") else "image/jpeg"
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))

    tags.save(file_path, v2_version=3)


def tag_flac(file_path: str, track: TrackResult) -> None:
    """Tags Vorbis d'un FLAC (titre, artiste, album, année, genre, label, n° de piste, ISRC)."""
    from mutagen.flac import FLAC

    audio = FLAC(file_path)
    values = {"title": track.title, "artist": track.artist, "album": track.album or "",
              "date": str(track.year) if track.year else "", "genre": track.genre or "",
              "organization": track.label or "", "tracknumber": str(track.track_no) if track.track_no else "",
              "isrc": track.isrc or ""}
    for k, v in values.items():
        if v:
            audio[k] = v
    audio.save()


def tag_audio(file_path: str, track: TrackResult) -> None:
    """Choisit le bon format de tags selon l'extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix in (".m4a", ".mp4", ".aac"):
        tag_m4a(file_path, track)
    elif suffix == ".mp3":
        tag_mp3(file_path, track)
    elif suffix == ".flac":                       # 1.4.0 (C10.1) : fichier d'origine SoundCloud
        tag_flac(file_path, track)
    else:
        log.warning("Format %s: tags not written.", suffix)
