"""Construction et lecture des lignes (pistes, artistes, albums, playlists) d'export.pdb.

Disposition des lignes (analyse Deep Symmetry) :
  piste    : 0x88 octets fixes (21 offsets de chaînes à 0x5e) puis les chaînes ;
  artiste  : [0x60][décalage][id u4][0x03][offset du nom u1] nom ;
  album    : [0x80][décalage][?][artist_id u4][id u4][?][0x03][offset du nom u1] nom ;
  arbre    : parent u4, 0, ordre u4, id u4, dossier u4, nom ;
  entrée   : numéro u4, piste u4, playlist u4 ;
  tonalité : id u4, id u4 (identique, constaté sur export réel), nom (« Am », « F#m », « 7A »…) ;
  pochette : id u4, chemin (« /PIONEER/Artwork/00001/a1.jpg »).
Les octets « inconnus » d'une nouvelle piste sont recopiés d'une piste existante du même fichier
(modèle), faute de quoi on utilise les valeurs les plus courantes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, Optional

from .format import PdbFormatError, T, decode_string, encode_string, pad4, string_span, u16, u32

TRACK_FIXED = 0x88
STR_NAMES = ("isrc", "texter", "unk2", "unk3", "unk4", "message", "kuvo_public", "autoload_hot_cues",
             "unk5", "unk6", "date_added", "release_date", "mix_name", "unk7", "analyze_path",
             "analyze_date", "comment", "title", "unk8", "filename", "file_path")
# Champs de chaîne que DJSync renseigne lui-même ; les autres viennent du modèle (ou restent vides).
OWN_STRINGS = ("isrc", "date_added", "release_date", "analyze_path", "analyze_date", "comment",
               "title", "filename", "file_path", "mix_name")
DEFAULT_BITMASK = 0x000C0700


@dataclass
class TrackMeta:
    path: str                 # "/Contents/Artiste/Album/fichier.mp3"
    title: str
    artist: str = ""
    album: str = ""
    length: int = 0
    bpmx100: int = 0
    file_size: int = 0
    bitrate: int = 0
    bit_depth: int = 16
    sample_rate: int = 44100
    file_type: int = 0
    date_added: str = ""
    comment: str = ""
    track_no: int = 0
    disc_no: int = 0
    year: int = 0
    # ---- V1.1-A4 : analyse et pochette (vides = son non analysé, comme avant)
    key: str = ""             # nom de tonalité tel qu'écrit dans la table des tonalités (« Am », « 8A »…)
    artwork_path: str = ""    # « /PIONEER/Artwork/00001/a1.jpg »
    analyze_path: str = ""    # « /PIONEER/USBANLZ/P0xx/xxxxxxxx/ANLZ0000.DAT »
    analyze_date: str = ""    # AAAA-MM-JJ

    @property
    def file_name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


# ------------------------------------------------------------------------- pistes
@dataclass
class TrackTemplate:
    fixed: bytes
    strings: Dict[str, str]


def read_track(data, pos: int) -> Dict[str, object]:
    """Décode une piste (champs utiles à DJSync). `pos` = offset absolu de la ligne dans le buffer."""
    offs = [u16(data, pos + 0x5E + 2 * k) for k in range(21)]
    if any(o < TRACK_FIXED for o in offs):
        raise PdbFormatError("ligne de piste : offsets de chaînes invalides")
    strings = {name: decode_string(data, pos + o, strict=name in ("file_path", "title"))
               for name, o in zip(STR_NAMES, offs)}
    return {
        "id": u32(data, pos + 0x48), "artist_id": u32(data, pos + 0x44), "album_id": u32(data, pos + 0x40),
        "path": strings["file_path"], "title": strings["title"], "strings": strings,
        "artwork_id": u32(data, pos + 0x1C), "key_id": u32(data, pos + 0x20), "bpmx100": u32(data, pos + 0x38),
        "fixed": bytes(data[pos: pos + TRACK_FIXED]),
    }


def make_template(row: Dict[str, object]) -> TrackTemplate:
    return TrackTemplate(fixed=row["fixed"], strings=dict(row["strings"]))  # type: ignore[arg-type]


def build_track(meta: TrackMeta, track_id: int, artist_id: int, album_id: int, index_shift: int,
                template: Optional[TrackTemplate] = None, key_id: int = 0, artwork_id: int = 0) -> bytes:
    fx = bytearray(template.fixed if template else bytes(TRACK_FIXED))
    if not template:
        struct.pack_into("<I", fx, 0x04, DEFAULT_BITMASK)
        struct.pack_into("<H", fx, 0x56, 41)
        struct.pack_into("<H", fx, 0x5C, 3)
    struct.pack_into("<HH", fx, 0x00, 0x24, index_shift & 0xFFFF)
    struct.pack_into("<I", fx, 0x08, meta.sample_rate)
    struct.pack_into("<I", fx, 0x0C, 0)                       # compositeur
    struct.pack_into("<I", fx, 0x10, meta.file_size)
    struct.pack_into("<IIIII", fx, 0x1C, artwork_id, key_id, 0, 0, 0)  # pochette, tonalité, artiste orig., label, remixeur
    struct.pack_into("<I", fx, 0x30, meta.bitrate)
    struct.pack_into("<I", fx, 0x34, meta.track_no)
    struct.pack_into("<I", fx, 0x38, meta.bpmx100)
    struct.pack_into("<III", fx, 0x3C, 0, album_id, artist_id)  # genre, album, artiste
    struct.pack_into("<I", fx, 0x48, track_id)
    struct.pack_into("<HHHH", fx, 0x4C, meta.disc_no, 0, meta.year, meta.bit_depth)
    struct.pack_into("<H", fx, 0x54, min(meta.length, 0xFFFF))
    fx[0x58], fx[0x59] = 0, 0                                  # couleur, note
    struct.pack_into("<H", fx, 0x5A, meta.file_type)

    own = {"isrc": "", "date_added": meta.date_added[:10], "release_date": "", "analyze_path": meta.analyze_path,
           "analyze_date": meta.analyze_date[:10] if meta.analyze_path else "", "comment": meta.comment, "title": meta.title,
           "filename": meta.file_name, "file_path": meta.path, "mix_name": ""}
    body = bytearray()
    for k, name in enumerate(STR_NAMES):
        text = own[name] if name in OWN_STRINGS else (template.strings.get(name, "") if template else "")
        struct.pack_into("<H", fx, 0x5E + 2 * k, TRACK_FIXED + len(body))
        body += encode_string(text)
    return pad4(bytes(fx) + bytes(body))


# ----------------------------------------------------------------- artistes / albums
def build_artist(artist_id: int, name: str, index_shift: int) -> bytes:
    return pad4(struct.pack("<HHIBB", 0x60, index_shift & 0xFFFF, artist_id, 3, 0x0A) + encode_string(name))


def read_artist(data, pos: int) -> Dict[str, object]:
    sub = u16(data, pos)
    ofs = u16(data, pos + 0x0A) if sub & 0x04 else data[pos + 0x09]
    return {"id": u32(data, pos + 4), "name": decode_string(data, pos + ofs)}


def build_album(album_id: int, artist_id: int, name: str, index_shift: int) -> bytes:
    return pad4(struct.pack("<HHIIIIBB", 0x80, index_shift & 0xFFFF, 0, artist_id, album_id, 0, 3, 0x16)
                + encode_string(name))


def read_album(data, pos: int) -> Dict[str, object]:
    sub = u16(data, pos)
    ofs = u16(data, pos + 0x16) if sub & 0x04 else data[pos + 0x15]
    return {"id": u32(data, pos + 0x0C), "artist_id": u32(data, pos + 8), "name": decode_string(data, pos + ofs)}


# --------------------------------------------------------------- tonalités / pochettes
def build_key(key_id: int, name: str) -> bytes:
    """Ligne de la table des tonalités (5) : id, id répété, nom. Relevé sur un export réel : 24 lignes
    « 01000000 01000000 07 436d » = id 1, id 1, « Cm »."""
    return pad4(struct.pack("<II", key_id, key_id) + encode_string(name))


def read_key(data, pos: int) -> Dict[str, object]:
    return {"id": u32(data, pos), "name": decode_string(data, pos + 8)}


def build_artwork(art_id: int, path: str) -> bytes:
    """Ligne de la table des pochettes (13) : id, chemin."""
    return pad4(struct.pack("<I", art_id) + encode_string(path))


def read_artwork(data, pos: int) -> Dict[str, object]:
    return {"id": u32(data, pos), "path": decode_string(data, pos + 4)}


# ------------------------------------------------------------------------ playlists
def build_tree(parent: int, sort_order: int, pl_id: int, is_folder: bool, name: str) -> bytes:
    return pad4(struct.pack("<IIIII", parent, 0, sort_order, pl_id, 1 if is_folder else 0) + encode_string(name))


def read_tree(data, pos: int) -> Dict[str, object]:
    return {"parent": u32(data, pos), "sort": u32(data, pos + 8), "id": u32(data, pos + 12),
            "folder": bool(u32(data, pos + 16)), "name": decode_string(data, pos + 0x14)}


def build_entry(entry_index: int, track_id: int, playlist_id: int) -> bytes:
    return struct.pack("<III", entry_index, track_id, playlist_id)


def read_entry(data, pos: int) -> Dict[str, int]:
    return {"index": u32(data, pos), "track": u32(data, pos + 4), "playlist": u32(data, pos + 8)}


def row_end(ttype: int, data, pos: int) -> int:
    """Offset absolu de la fin (alignée sur 4) d'une ligne existante : sert à prouver qu'une
    nouvelle ligne ne peut pas en écraser une autre."""
    if ttype == T.TRACKS:
        end = pos + TRACK_FIXED
        for k in range(21):
            o = u16(data, pos + 0x5E + 2 * k)
            end = max(end, pos + o + string_span(data, pos + o))
    elif ttype == T.ARTISTS:
        sub = u16(data, pos)
        o = u16(data, pos + 0x0A) if sub & 0x04 else data[pos + 0x09]
        end = pos + o + string_span(data, pos + o)
    elif ttype == T.ALBUMS:
        sub = u16(data, pos)
        o = u16(data, pos + 0x16) if sub & 0x04 else data[pos + 0x15]
        end = pos + o + string_span(data, pos + o)
    elif ttype == T.PLAYLIST_TREE:
        end = pos + 0x14 + string_span(data, pos + 0x14)
    elif ttype == T.PLAYLIST_ENTRIES:
        end = pos + 12
    elif ttype == T.KEYS:
        end = pos + 8 + string_span(data, pos + 8)
    elif ttype == T.ARTWORK:
        end = pos + 4 + string_span(data, pos + 4)
    else:
        raise PdbFormatError(f"table {ttype} non prise en charge")
    return end + (-(end - pos) % 4)
