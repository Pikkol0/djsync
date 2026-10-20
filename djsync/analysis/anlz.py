"""Écriture (et relecture de contrôle) des fichiers d'analyse Pioneer ANLZ0000.DAT / .EXT.

Structure recopiée de VRAIS fichiers exportés par Rekordbox (constantes vérifiées octet par octet) :
  en-tête   « PMAI », 0x1C, taille totale, 1, 0x10000, 0x10000, 0 (entiers big-endian) ;
  .DAT      PPTH, PVBR, PQTZ, PWAV, PWV2, PCOB (hot cues), PCOB (mémoires)
  .EXT      PPTH, PWV3, PCOB, PCOB, PCO2, PCO2, PWV5, PWV4
Chaque balise : code 4 lettres, longueur d'en-tête, longueur totale, puis contenu.

Non écrits (facultatifs, absents des exports de Rekordbox 5) : PQT2 (grille étendue), PSSI
(phrases, nécessite l'analyse « phrase » de Rekordbox) et le fichier .2EX (forme d'onde 3 bandes
du CDJ-3000, dont une balise reste non décodée publiquement). Les platines utilisent alors les
formes d'onde du .EXT, comme pour une clé exportée par Rekordbox 5.
"""
from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .waveform import Waveforms

ANLZ_ROOT = "PIONEER/USBANLZ"


# ------------------------------------------------------------------------ balises
def _tag(code: bytes, header_rest: bytes, body: bytes) -> bytes:
    len_header = 12 + len(header_rest)
    return code + struct.pack(">II", len_header, len_header + len(body)) + header_rest + body


def _ppth(track_path: str) -> bytes:
    raw = track_path.encode("utf-16-be") + b"\x00\x00"
    return _tag(b"PPTH", struct.pack(">I", len(raw)), raw)


def _pvbr(total_samples: int) -> bytes:
    # 400 entrées d'index à 0 (comme les fichiers réels) + nombre total d'échantillons (mp3 ; 0 sinon)
    return _tag(b"PVBR", struct.pack(">I", 0), b"\x00" * 1600 + struct.pack(">I", total_samples & 0xFFFFFFFF))


def _pqtz(beats: Sequence[Tuple[int, int, int]]) -> bytes:
    body = b"".join(struct.pack(">HHI", n, tempo, ms) for n, tempo, ms in beats)
    return _tag(b"PQTZ", struct.pack(">III", 0, 0x00080000, len(beats)), body)


def _pwav(code: bytes, data: bytes) -> bytes:
    return _tag(code, struct.pack(">II", len(data), 0x00010000), data)


def _pcob(kind: int) -> bytes:
    return _tag(b"PCOB", struct.pack(">IHHi", kind, 0, 0, -1), b"")


def _pco2(kind: int) -> bytes:
    return _tag(b"PCO2", struct.pack(">IHH", kind, 0, 0), b"")


def _pwv(code: bytes, entry_bytes: int, count: int, unknown: int, data: bytes) -> bytes:
    return _tag(code, struct.pack(">III", entry_bytes, count, unknown), data)


def _file(tags: List[bytes]) -> bytes:
    body = b"".join(tags)
    return b"PMAI" + struct.pack(">IIIIII", 0x1C, 0x1C + len(body), 1, 0x00010000, 0x00010000, 0) + body


def build_dat(track_path: str, beats: Sequence[Tuple[int, int, int]], wf: Waveforms, total_samples: int = 0) -> bytes:
    return _file([_ppth(track_path), _pvbr(total_samples), _pqtz(beats), _pwav(b"PWAV", wf.preview),
                  _pwav(b"PWV2", wf.tiny_preview), _pcob(1), _pcob(0)])


def build_ext(track_path: str, wf: Waveforms) -> bytes:
    n = wf.detail_count
    return _file([
        _ppth(track_path),
        _pwv(b"PWV3", 1, n, 0x00960000, wf.detail),
        _pcob(1), _pcob(0), _pco2(1), _pco2(0),
        _pwv(b"PWV5", 2, n, 0x00960305, wf.color_detail),
        _pwv(b"PWV4", 6, len(wf.color_preview) // 6, 0, wf.color_preview),
    ])


# ------------------------------------------------------------------- relecture
def parse(data: bytes) -> Dict[str, List[Tuple[bytes, bytes]]]:
    """{code: [(en-tête après les 12 octets communs, contenu)]}. Lève ValueError si incohérent."""
    if data[:4] != b"PMAI":
        raise ValueError("pas un fichier ANLZ (PMAI attendu)")
    len_header, len_file = struct.unpack(">II", data[4:12])
    if len_file != len(data):
        raise ValueError("taille déclarée incohérente")
    out: Dict[str, List[Tuple[bytes, bytes]]] = {}
    i = len_header
    while i < len(data):
        code = data[i:i + 4].decode("ascii")
        lh, lt = struct.unpack(">II", data[i + 4:i + 12])
        if lh < 12 or lt < lh or i + lt > len(data):
            raise ValueError(f"balise {code} : longueurs incohérentes")
        out.setdefault(code, []).append((data[i + 12:i + lh], data[i + lh:i + lt]))
        i += lt
    return out


def read_path(data: bytes) -> str:
    tags = parse(data)
    if "PPTH" not in tags:
        return ""
    return tags["PPTH"][0][1].decode("utf-16-be").rstrip("\x00")


# -------------------------------------------------------------------- emplacement
def anlz_dir_for(track_path: str, salt: int = 0) -> str:
    """Dossier « /PIONEER/USBANLZ/Pxxx/xxxxxxxx » déterministe pour un chemin de son.

    Rekordbox dérive ce nom d'un hachage interne non documenté ; seule compte la référence écrite
    dans la base (analysisDataFilePath / analyze_path), que les platines suivent telle quelle.
    """
    h = zlib.crc32(f"{salt}:{track_path.casefold()}".encode("utf-8"))
    return f"/{ANLZ_ROOT}/P{h & 0x3FF:03X}/{(h >> 10) & 0x3FFFFF:08X}"


def choose_anlz_dir(drive_root: Path, track_path: str) -> str:
    """Dossier libre (ou déjà attribué à CE son) : jamais l'analyse d'un autre son écrasée."""
    for salt in range(64):
        rel = anlz_dir_for(track_path, salt)
        dat = Path(drive_root) / rel.lstrip("/") / "ANLZ0000.DAT"
        if not dat.exists():
            return rel
        try:
            if read_path(dat.read_bytes()).casefold() == track_path.casefold():
                return rel
        except (OSError, ValueError, UnicodeDecodeError):
            continue
    raise OSError("aucun dossier d'analyse libre trouvé")


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".djsync-tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def write_files(drive_root: Path, track_path: str, beats: Sequence[Tuple[int, int, int]], wf: Waveforms,
                total_samples: int = 0, rel_dir: Optional[str] = None) -> str:
    """Écrit ANLZ0000.DAT et .EXT ; renvoie le chemin de base à inscrire (…/ANLZ0000.DAT)."""
    rel_dir = rel_dir or choose_anlz_dir(drive_root, track_path)
    folder = Path(drive_root) / rel_dir.lstrip("/")
    dat = build_dat(track_path, beats, wf, total_samples)
    ext = build_ext(track_path, wf)
    for blob in (dat, ext):                      # contrôle avant écriture : relisible
        parse(blob)
    _write_atomic(folder / "ANLZ0000.DAT", dat)
    _write_atomic(folder / "ANLZ0000.EXT", ext)
    return f"{rel_dir}/ANLZ0000.DAT"
