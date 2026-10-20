"""Constantes et primitives du format DeviceSQL (PIONEER/rekordbox/export.pdb).

Le format n'est pas documenté officiellement : tout ce module repose sur l'analyse publique de
Deep Symmetry (« DJ Link Ecosystem Analysis », Crate Digger) et sur le travail de rétro-ingénierie
de la communauté. Rien ici n'a été validé sur une platine : voir docs/export_pdb.md.

PRINCIPE DE SÉCURITÉ : DJSync ne CRÉE jamais de export.pdb et ne réécrit jamais ce qu'il ne
comprend pas. Il charge un fichier produit par Rekordbox, vérifie qu'il correspond au modèle
ci-dessous, n'ajoute/retire que des lignes, et laisse tous les autres octets intacts. Au moindre
écart avec le modèle : PdbFormatError, le fichier n'est pas touché.
"""
from __future__ import annotations

import struct
from typing import Tuple

PAGE_SIZE = 4096          # seule taille de page connue des exports Rekordbox
HEADER = 0x28             # début du tas de lignes dans une page
GROUP = 0x24              # un groupe d'index = 16 offsets (u2) + masque présence (u2) + masque (u2)
MAX_SLOTS = 255           # num_rows_small est un octet
EMPTY_ENTRY = 0x1FFFFFF8  # entrée libre d'une page d'index
FILE_TABLES_AT = 0x1C     # début du tableau des tables dans la page 0


class T:
    """Types de table (page_type)."""

    TRACKS = 0
    GENRES = 1
    ARTISTS = 2
    ALBUMS = 3
    LABELS = 4
    KEYS = 5
    COLORS = 6
    PLAYLIST_TREE = 7
    PLAYLIST_ENTRIES = 8
    ARTWORK = 13


class PdbError(Exception):
    """Erreur de base du module export.pdb."""


class PdbFormatError(PdbError):
    """Le fichier ne correspond pas au modèle connu : on n'écrit RIEN."""


class PdbCapacityError(PdbError):
    """Plus de place dans la dernière page de la table (et l'agrandissement est désactivé/impossible)."""


def u16(buf, pos: int) -> int:
    return struct.unpack_from("<H", buf, pos)[0]


def u32(buf, pos: int) -> int:
    return struct.unpack_from("<I", buf, pos)[0]


def index_size(num_rows: int) -> int:
    """Octets occupés en fin de page par l'index de `num_rows` lignes."""
    full, rest = divmod(num_rows, 16)
    return GROUP * full + (4 + 2 * rest if rest else 0)


def pad4(data: bytes) -> bytes:
    return data + b"\x00" * (-len(data) % 4)


# ------------------------------------------------------------------ chaînes DeviceSQL
def encode_string(text: str) -> bytes:
    """ASCII court (<= 126 car.) : 1 octet d'en-tête ; ASCII long : 0x40 ; sinon UTF-16LE : 0x90."""
    text = text.replace("\x00", "")
    if text.isascii():
        if len(text) <= 126:
            return bytes([((len(text) + 1) << 1) | 1]) + text.encode("ascii")
        text = text[: 0xFFFF - 4]
        return b"\x40" + struct.pack("<H", len(text) + 4) + b"\x00" + text.encode("ascii")
    text = text[: (0xFFFF - 4) // 2]
    raw = text.encode("utf-16-le")
    return b"\x90" + struct.pack("<H", len(raw) + 4) + b"\x00" + raw


def decode_string(buf, pos: int, strict: bool = True) -> str:
    """Lit une chaîne DeviceSQL. strict=False : un codage inconnu donne \"\" (champs sans importance)."""
    try:
        flag = buf[pos]
        if flag & 1:
            return bytes(buf[pos + 1: pos + (flag >> 1)]).decode("latin-1")
        length = u16(buf, pos + 1)
        if flag == 0x40:
            return bytes(buf[pos + 4: pos + length]).decode("latin-1")
        if flag == 0x90:
            return bytes(buf[pos + 4: pos + length]).decode("utf-16-le", "replace")
    except (IndexError, struct.error):
        pass
    if strict:
        raise PdbFormatError(f"chaîne DeviceSQL illisible à l'octet {pos}")
    return ""


def string_span(buf, pos: int) -> int:
    """Nombre d'octets occupés par la chaîne DeviceSQL située à `pos`."""
    flag = buf[pos]
    if flag & 1:
        return max(flag >> 1, 1)
    if flag in (0x40, 0x90):
        return u16(buf, pos + 1)
    raise PdbFormatError(f"chaîne DeviceSQL inconnue (octet {flag:#x}) à {pos}")


def split_name(path: Tuple[str, ...]) -> Tuple[Tuple[str, ...], str]:
    return path[:-1], path[-1]
