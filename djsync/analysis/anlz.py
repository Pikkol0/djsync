"""Écriture (et relecture de contrôle) des fichiers d'analyse Pioneer ANLZ0000.DAT / .EXT.

Structure recopiée de VRAIS fichiers exportés par Rekordbox (constantes vérifiées octet par octet) :
  en-tête   « PMAI », 0x1C, taille totale, 1, 0x10000, 0x10000, 0 (entiers big-endian) ;
  .DAT      PPTH, PVBR, PQTZ, PWAV, PWV2, PCOB (hot cues), PCOB (mémoires)
  .EXT      PPTH, PWV3, PCOB, PCOB, PCO2, PCO2, PWV5, PWV4
  .2EX      PPTH, PWV7, PWV6, PWVC (formes d'onde 3 bandes, V0.3.0)
Chaque balise : code 4 lettres, longueur d'en-tête, longueur totale, puis contenu.

Non écrits (facultatifs) : PQT2 (grille étendue) et PSSI (phrases, nécessite l'analyse « phrase » de
Rekordbox). Le .2EX est écrit depuis la V0.3.0 : sans lui, Rekordbox 6/7 réglé sur « 3Band » montrait un
aperçu bleu (liste, aperçu du morceau entier) au lieu de l'aperçu 3 bandes des sons qu'il a analysés.
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


def build_2ex(track_path: str, wf: Waveforms) -> bytes:
    n = len(wf.band_detail) // 3
    return _file([
        _ppth(track_path),
        _pwv(b"PWV7", 3, n, 0x00960000, wf.band_detail),
        _tag(b"PWV6", struct.pack(">II", 3, len(wf.band_preview) // 3), wf.band_preview),
        _tag(b"PWVC", b"\x00\x00", struct.pack(">HHH", *wf.band_norm)),
    ])


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
        raise ValueError("not an ANLZ file (PMAI expected)")
    len_header, len_file = struct.unpack(">II", data[4:12])
    if len_file != len(data):
        raise ValueError("inconsistent declared size")
    out: Dict[str, List[Tuple[bytes, bytes]]] = {}
    i = len_header
    while i < len(data):
        code = data[i:i + 4].decode("ascii")
        lh, lt = struct.unpack(">II", data[i + 4:i + 12])
        if lh < 12 or lt < lh or i + lt > len(data):
            raise ValueError(f"tag {code}: inconsistent lengths")
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
    raise OSError("no free analysis folder found")


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
    """Écrit ANLZ0000.DAT, .EXT et .2EX ; renvoie le chemin de base à inscrire (…/ANLZ0000.DAT)."""
    rel_dir = rel_dir or choose_anlz_dir(drive_root, track_path)
    folder = Path(drive_root) / rel_dir.lstrip("/")
    dat = build_dat(track_path, beats, wf, total_samples)
    ext = build_ext(track_path, wf)
    two = build_2ex(track_path, wf) if wf.band_detail else b""
    for blob in (dat, ext) + ((two,) if two else ()):    # contrôle avant écriture : relisible
        parse(blob)
    _write_atomic(folder / "ANLZ0000.DAT", dat)
    _write_atomic(folder / "ANLZ0000.EXT", ext)
    if two:
        _write_atomic(folder / "ANLZ0000.2EX", two)
    return f"{rel_dir}/ANLZ0000.DAT"


# ---------------------------------------------------------- V0.2.0 : grille et aperçus
def iter_tags(data: bytes) -> List[Tuple[str, bytes]]:
    """[(code, octets bruts de la balise)] dans l'ordre du fichier (pour réécrire sans rien perdre)."""
    parse(data)                                  # validation
    len_header = struct.unpack(">I", data[4:8])[0]
    out, i = [], len_header
    while i < len(data):
        lt = struct.unpack(">I", data[i + 8:i + 12])[0]
        out.append((data[i:i + 4].decode("ascii"), data[i:i + lt]))
        i += lt
    return out


def rebuild(data: bytes, replace: Dict[str, Optional[bytes]]) -> bytes:
    """Réécrit un fichier ANLZ : chaque balise listée dans `replace` est remplacée (octets complets
    de la nouvelle balise) ou retirée (None) ; les autres sont recopiées à l'octet près, en-tête PMAI
    compris (seule la longueur totale change)."""
    len_header = struct.unpack(">I", data[4:8])[0]
    body = b"".join(replace.get(code, raw) or b"" if code in replace else raw for code, raw in iter_tags(data))
    head = bytearray(data[:len_header])
    struct.pack_into(">I", head, 8, len_header + len(body))
    out = bytes(head) + body
    parse(out)
    return out


def read_beats(data: bytes) -> List[Tuple[int, int, int]]:
    """Grille PQTZ d'un .DAT : [(n° du temps dans la mesure 1-4, tempo x100, position ms)]."""
    tags = parse(data)
    if "PQTZ" not in tags:
        return []
    head, body = tags["PQTZ"][0]
    count = struct.unpack(">I", head[8:12])[0] if len(head) >= 12 else len(body) // 8
    count = min(count, len(body) // 8)
    return [struct.unpack(">HHI", body[k * 8:k * 8 + 8]) for k in range(count)]


def replace_beats(data: bytes, beats: Sequence[Tuple[int, int, int]]) -> bytes:
    """.DAT avec une nouvelle grille (en-tête PQTZ d'origine conservé, sauf le nombre de temps)."""
    tags = parse(data)
    if "PQTZ" not in tags:
        raise ValueError("no beat grid (PQTZ) in this file")
    head = bytearray(tags["PQTZ"][0][0])
    if len(head) < 12:
        head = bytearray(struct.pack(">III", 0, 0x00080000, 0))
    struct.pack_into(">I", head, 8, len(beats))
    body = b"".join(struct.pack(">HHI", n, tempo, ms) for n, tempo, ms in beats)
    return rebuild(data, {"PQTZ": _tag(b"PQTZ", bytes(head), body)})


def drop_extended_grid(data: bytes) -> bytes:
    """Retire PQT2 (grille étendue, .EXT/.2EX) : sinon les platines récentes garderaient l'ancienne."""
    return rebuild(data, {"PQT2": None}) if "PQT2" in parse(data) else data


def read_overview(dat: Optional[bytes] = None, ext: Optional[bytes] = None) -> List[Tuple[float, str]]:
    """Aperçu de forme d'onde pour le lecteur : [(hauteur 0-1, couleur #RRGGBB)].

    PWV4 (aperçu couleur, .EXT) si présent, sinon PWAV (aperçu mono, .DAT)."""
    if ext:
        try:
            tags = parse(ext)
        except ValueError:
            tags = {}
        if "PWV4" in tags:
            b = tags["PWV4"][0][1]
            out = []
            for k in range(len(b) // 6):
                _d0, _d1, low, mid, high, _d5 = b[k * 6:k * 6 + 6]
                h = max(low, mid, high) / 127.0
                tot = (low + mid + high) or 1
                r = int(min(255, 70 + 185 * low / tot)); g = int(min(255, 70 + 185 * mid / tot))
                bl = int(min(255, 70 + 185 * high / tot))
                out.append((min(1.0, h), f"#{r:02X}{g:02X}{bl:02X}"))
            if out:
                return out
    if dat:
        try:
            tags = parse(dat)
        except ValueError:
            return []
        if "PWAV" in tags:
            return [((v & 0x1F) / 31.0, "#4A9EFF" if (v >> 5) < 4 else "#9CCBFF") for v in tags["PWAV"][0][1]]
    return []


def read_detail(ext: bytes) -> List[Tuple[float, str]]:
    """Forme d'onde détaillée (150 colonnes/s) pour l'éditeur de grille : PWV5 couleur, sinon PWV3."""
    tags = parse(ext)
    if "PWV5" in tags:
        b = tags["PWV5"][0][1]
        out = []
        for k in range(len(b) // 2):
            v = struct.unpack(">H", b[k * 2:k * 2 + 2])[0]
            r, g, bl, h = (v >> 13) & 7, (v >> 10) & 7, (v >> 7) & 7, (v >> 2) & 31
            out.append((h / 31.0, f"#{r * 36:02X}{g * 36:02X}{bl * 36:02X}"))
        return out
    if "PWV3" in tags:
        return [((v & 0x1F) / 31.0, "#4A9EFF") for v in tags["PWV3"][0][1]]
    return []
