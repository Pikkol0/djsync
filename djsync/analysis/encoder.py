"""1.4.3 (A04) : ce que dit le fichier sur son encodage (en-tête LAME / Xing des MP3, encodeur des AAC / M4A).

Le spectre (spectrum.py, C46) estime la vraie qualité ; l'en-tête dit comment le fichier a été encodé. Les deux
ensemble donnent une CONFIANCE (core.quality.AudioInfo.confidence) :
* MP3 encodé par LAME : l'en-tête garde le mode (CBR, ABR, VBR), le débit et le filtre passe-bas réglé
  (20,5 kHz pour un 320, 17 kHz pour un 128…). Un spectre qui monte jusqu'à ce filtre : le fichier est bien
  ce qu'il dit (« sûr ») ; un spectre qui coupe bien avant : le son a été encodé depuis une source plus pauvre
  (« faux 320 », sûr aussi) ;
* MP3 écrit par FFmpeg (« Lavc… ») : même en-tête, mais sans filtre ni mode : seulement le nom et CBR / VBR ;
* AAC / M4A : nom de l'encodeur (« ©too » : FFmpeg, iTunes, Nero…) et profil (AAC LC, HE-AAC).

Lecture seule, quelques Ko en tête du fichier (MP3) ou les boîtes MP4 (mutagen) : ~1 ms par son. Le
résultat est gardé dans un petit registre (`encoder.json` dans le dossier des réglages, clé « nom|taille »),
comme la coupure du spectre, pour que la Bibliothèque l'affiche sans toucher au disque.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

log = logging.getLogger(__name__)

# débit (kbit/s) selon l'indice de l'en-tête de trame, couche III
_MPEG1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MPEG2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
# méthode de l'en-tête LAME (4 bits faibles de l'octet 9)
_LAME_MODES = {1: "CBR", 8: "CBR", 2: "ABR", 9: "ABR", 3: "VBR", 4: "VBR", 5: "VBR", 6: "VBR"}
MP4_SUFFIXES = (".m4a", ".mp4", ".m4b", ".aac")


@dataclass
class EncoderInfo:
    codec: str = ""          # "mp3" | "aac"
    name: str = ""           # « LAME 3.100 », « FFmpeg (Lavc60.31) », « iTunes 12.9 », « Lavf60.16 »…
    mode: str = ""           # "CBR" | "VBR" | "ABR" | "" (inconnu)
    kbps: int = 0            # débit annoncé par l'en-tête (CBR : le débit ; ABR : la cible ; VBR : le minimum)
    lowpass: int = 0         # filtre passe-bas réglé à l'encodage (Hz), 0 si inconnu (LAME seulement)
    profile: str = ""        # AAC : « AAC LC », « HE-AAC »…
    mean: int = 0            # 1.4.3-rc.2 (B123) : débit moyen (données audio ÷ durée), MP3 seulement, 0 inconnu

    @property
    def lame(self) -> bool:
        return self.name.upper().startswith("LAME")

    def to_list(self) -> list:
        return [self.codec, self.name, self.mode, int(self.kbps), int(self.lowpass), self.profile, int(self.mean)]

    @classmethod
    def from_list(cls, v: Optional[list]) -> Optional["EncoderInfo"]:
        if not v:
            return None
        try:
            return cls(str(v[0]), str(v[1]), str(v[2]), int(v[3]), int(v[4]), str(v[5]) if len(v) > 5 else "",
                       int(v[6]) if len(v) > 6 else 0)
        except (TypeError, ValueError, IndexError):
            return None


def _id3_end(data: bytes) -> int:
    if data[:3] == b"ID3" and len(data) > 10:
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        return 10 + size + (10 if data[5] & 0x10 else 0)
    return 0


def _frame_at(data: bytes, pos: int) -> Optional[tuple]:
    """(MPEG-1 ?, mono ?, débit kbit/s) si une en-tête de trame MP3 valide commence à `pos`."""
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    version = (data[pos + 1] >> 3) & 3
    layer = (data[pos + 1] >> 1) & 3
    idx = data[pos + 2] >> 4
    if version == 1 or layer != 1 or idx in (0, 15) or ((data[pos + 2] >> 2) & 3) == 3:
        return None
    mpeg1 = version == 3
    return mpeg1, (data[pos + 3] >> 6) == 3, (_MPEG1_L3 if mpeg1 else _MPEG2_L3)[idx]


def read_mp3(path: Union[str, Path]) -> Optional[EncoderInfo]:
    try:
        with open(path, "rb") as fh:
            data = fh.read(256 * 1024)
    except OSError:
        return None
    pos = _id3_end(data)
    frame = None
    while pos + 4 < len(data):
        frame = _frame_at(data, pos)
        if frame is not None:
            break
        pos += 1
    if frame is None:
        return None
    mpeg1, mono, kbps = frame
    info = EncoderInfo(codec="mp3", kbps=kbps)
    x = pos + 4 + ((17 if mono else 32) if mpeg1 else (9 if mono else 17))
    tag = data[x:x + 4]
    if tag in (b"Xing", b"Info") and x + 8 <= len(data):
        info.mode = "CBR" if tag == b"Info" else "VBR"
        flags = int.from_bytes(data[x + 4:x + 8], "big")
        y = x + 8 + (4 if flags & 1 else 0) + (4 if flags & 2 else 0) + (100 if flags & 4 else 0) + \
            (4 if flags & 8 else 0)
        if y + 24 <= len(data):
            raw = data[y:y + 9]
            name = raw.split(b"\0")[0].decode("ascii", "replace").strip()
            if name.upper().startswith("LAME"):
                info.name = "LAME " + name[4:].strip(" .") if len(name) > 4 else "LAME"
                info.mode = _LAME_MODES.get(data[y + 9] & 0x0F, info.mode)
                info.lowpass = data[y + 10] * 100
                if info.mode == "ABR":                  # débit visé (255 : 255 ou plus)
                    info.kbps = data[y + 20] or kbps
                elif info.mode == "CBR":
                    info.kbps = kbps                    # débit de la trame d'en-tête (l'octet LAME plafonne à 255)
                else:
                    info.kbps = 0                       # VBR : l'octet ne donne que le minimum
            elif name.startswith("Lavc") or name.startswith("Lavf"):
                info.name = f"FFmpeg ({name})"
            elif name and name.isprintable():
                info.name = name
        if info.mode == "VBR" and not info.lame:
            info.kbps = 0
    elif tag == b"VBRI":                       # en-tête Fraunhofer (anciens encodeurs)
        info.mode, info.name, info.kbps = "VBR", "Fraunhofer", 0
    else:
        info.mode = "CBR" if _next_same_bitrate(data, pos, frame) else ""
    if not info.name:
        info.name = _id3_software(path)
    info.mean = mean_mp3_kbps(path)
    return info


# 1.4.3-rc.2 (B123) : écart au-delà duquel le débit de l'en-tête n'est pas cru (débit moyen affiché à la place)
MEAN_GAP = 0.25


def mean_mp3_kbps(path: Union[str, Path], length: float = 0.0) -> int:
    """Débit moyen d'un MP3 : octets audio (sans les étiquettes ID3v2 / ID3v1) ÷ durée, 0 si inconnu.

    1.4.3-rc.2 (B123) : certains MP3 VBR ont une en-tête Xing sans le nombre d'octets : la durée est juste
    (nombre de trames), mais le débit lu est celui de la trame d'en-tête, souvent 32 kbps."""
    try:
        p = Path(path)
        size = p.stat().st_size
        with open(p, "rb") as fh:
            head = fh.read(10)
            tail = b""
            if size >= 128:
                fh.seek(size - 128)
                tail = fh.read(3)
        if not length:
            from mutagen.mp3 import MP3

            length = float(MP3(str(p)).info.length or 0.0)
    except Exception:  # noqa: BLE001 - fichier illisible : pas de débit moyen
        return 0
    audio = size - _id3_end(head) - (128 if tail == b"TAG" else 0)
    if length <= 0.5 or audio <= 0:
        return 0
    return int(round(audio * 8 / length / 1000))


def trusted_kbps(header: int, mean: int) -> int:
    """Débit à afficher : celui de l'en-tête, sauf s'il manque ou s'écarte de plus de 25 % du débit moyen."""
    if mean and (not header or abs(header - mean) > MEAN_GAP * mean):
        return mean
    return header


def _next_same_bitrate(data: bytes, pos: int, frame: tuple) -> bool:
    """Sans en-tête Xing : les trames suivantes ont-elles le même débit (CBR) ? (8 trames regardées)"""
    mpeg1, _mono, kbps = frame
    sr_idx = (data[pos + 2] >> 2) & 3
    rates = (44100, 48000, 32000) if mpeg1 else (22050, 24000, 16000)
    rate = rates[sr_idx]
    seen = 0
    while seen < 8:
        f = _frame_at(data, pos)
        if f is None:
            return seen >= 3
        if f[2] != kbps:
            return False
        pad = (data[pos + 2] >> 1) & 1
        size = (144000 if mpeg1 else 72000) * f[2] // rate + pad
        if size <= 0:
            return False
        pos += size
        seen += 1
    return True


def _id3_software(path: Union[str, Path]) -> str:
    try:
        from mutagen.id3 import ID3

        tags = ID3(str(path))
        frame = tags.get("TSSE") or tags.get("TENC")
        return str(frame.text[0]).strip()[:60] if frame and frame.text else ""
    except Exception:  # noqa: BLE001 - pas d'étiquette, fichier illisible
        return ""


def read_mp4(path: Union[str, Path]) -> Optional[EncoderInfo]:
    try:
        from mutagen.mp4 import MP4

        mp4 = MP4(str(path))
    except Exception:  # noqa: BLE001
        return None
    info = EncoderInfo(codec="aac")
    codec = str(getattr(mp4.info, "codec", "") or "")
    if codec == "alac":
        return None                            # sans perte : rien à dire de plus
    info.profile = str(getattr(mp4.info, "codec_description", "") or "")
    info.kbps = int(round((getattr(mp4.info, "bitrate", 0) or 0) / 1000))
    tags = mp4.tags or {}
    too = tags.get("\xa9too")
    if too:
        name = str(too[0]).strip()
        info.name = f"FFmpeg ({name})" if name.startswith(("Lavf", "Lavc")) else name[:60]
    elif any(k.endswith(":iTunSMPB") for k in tags.keys()):
        info.name = "iTunes"
    return info


def read(path: Union[str, Path]) -> Optional[EncoderInfo]:
    """Ce que l'en-tête dit de l'encodage, None pour un fichier sans perte ou illisible. Ne lève jamais."""
    try:
        suffix = Path(path).suffix.lower()
        if suffix == ".mp3":
            return read_mp3(path)
        if suffix in MP4_SUFFIXES:
            return read_mp4(path)
    except Exception:  # noqa: BLE001
        log.debug("Ignored error in encoder.read", exc_info=True)
    return None


# ------------------------------------------------------------------------------- registre
_lock = threading.Lock()
_cache: Optional[Dict[str, list]] = None
_store_path: Optional[Path] = None


def _file() -> Path:
    if _store_path is not None:
        return _store_path
    from ..settings import settings_dir

    return settings_dir() / "encoder.json"


def use_store(path: Optional[Path]) -> None:
    """Tests : registre dans un autre fichier (None = celui des réglages)."""
    global _store_path, _cache
    with _lock:
        _store_path, _cache = (Path(path) if path else None), None


def _load() -> Dict[str, list]:
    global _cache
    if _cache is None:
        try:
            _cache = {k: list(v) for k, v in json.loads(_file().read_text("utf-8")).items()}
        except (OSError, ValueError, AttributeError, TypeError):
            _cache = {}
    return _cache


def _key(path: Path) -> Optional[str]:
    try:
        return f"{path.name.casefold()}|{path.stat().st_size}"
    except OSError:
        return None


def lookup(name: str, size: int) -> Optional[EncoderInfo]:
    """Sans accès au disque : nom du fichier et taille connus par la bibliothèque."""
    if not name or not size:
        return None
    with _lock:
        return EncoderInfo.from_list(_load().get(f"{name.casefold()}|{int(size)}"))


def remember(path: Union[str, Path], info: Optional[EncoderInfo]) -> None:
    if info is None:
        return
    key = _key(Path(path))
    if key is None:
        return
    with _lock:
        data = _load()
        if data.get(key) == info.to_list():
            return
        data[key] = info.to_list()
        try:
            f = _file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f.name + ".djsync-tmp")
            tmp.write_text(json.dumps(data), "utf-8")
            tmp.replace(f)
        except OSError as exc:
            log.info("Encoder register not saved: %s", exc)


def read_and_remember(path: Union[str, Path]) -> Optional[EncoderInfo]:
    info = read(path)
    remember(path, info)
    return info
