"""Fabrique un export.pdb SYNTHÉTIQUE conforme au modèle décrit dans djsync/db/pdb/format.py.

ATTENTION : ce fichier n'est pas un vrai export Rekordbox. Il prouve que DJSync est cohérent avec
SON modèle du format ; il ne prouve pas qu'une platine accepte le résultat. L'assemblage des pages
est volontairement réécrit ici (sans réutiliser djsync.db.pdb.file) pour ne pas tester le code par lui-même.
"""
from __future__ import annotations

import struct
from typing import Dict, List, Optional

from djsync.db.pdb import rows
from djsync.db.pdb.format import EMPTY_ENTRY, T

L = 4096
ALL_TABLES = list(range(20))


def _data_page(index: int, ttype: int, next_page: int, rowbytes: List[bytes], seq: int = 7) -> bytes:
    page = bytearray(L)
    heap = bytearray()
    offsets = []
    for r in rowbytes:
        offsets.append(len(heap))
        heap += r
    n = len(rowbytes)
    groups = (n + 15) // 16
    idx_size = 0x24 * (n // 16) + ((4 + 2 * (n % 16)) if n % 16 else 0)
    assert 0x28 + len(heap) + idx_size <= L, "trop de lignes pour une page"
    struct.pack_into("<IIIIII", page, 0, 0, index, ttype, next_page, seq, 0)
    page[0x18] = n
    page[0x1B] = 0x34
    struct.pack_into("<HH", page, 0x1C, L - idx_size - 0x28 - len(heap), len(heap))
    struct.pack_into("<HHHH", page, 0x20, 1, 0x1FFF, 0, 0)
    page[0x28:0x28 + len(heap)] = heap
    for g in range(groups):
        base = L - g * 0x24
        mask = 0
        for k in range(min(16, n - g * 16)):
            struct.pack_into("<H", page, base - 6 - 2 * k, offsets[g * 16 + k])
            mask |= 1 << k
        struct.pack_into("<HH", page, base - 4, mask, 0)
    return bytes(page)


def _index_page(index: int, ttype: int, next_page: int, data_pages: List[int], seq: int = 7) -> bytes:
    page = bytearray(L)
    struct.pack_into("<IIIIII", page, 0, 0, index, ttype, next_page, seq, 0)
    page[0x1B] = 0x64
    struct.pack_into("<HHIIIIII", page, 0x28, 0x1FFF, 0x1FFF, 0x03EC0000, index, next_page, 0x03FFFFFF, 0, 0)
    n = len(data_pages)
    struct.pack_into("<HH", page, 0x48, n, n)           # compteurs puis entrées
    pos = 0x4C
    for p in data_pages:
        struct.pack_into("<I", page, pos, p << 3)
        pos += 4
    while pos < 0x1F0:
        struct.pack_into("<I", page, pos, EMPTY_ENTRY)
        pos += 4
    return bytes(page)


def pack_rows(rowbytes: List[bytes], first_free_bytes: int = 0) -> List[List[bytes]]:
    """Répartit les lignes en pages (glouton)."""
    pages: List[List[bytes]] = [[]]
    used = 0
    for r in rowbytes:
        n = len(pages[-1])
        need = used + len(r) + 0x28 + (0x24 * ((n + 1) // 16) + ((4 + 2 * ((n + 1) % 16)) if (n + 1) % 16 else 0))
        if need > L or n + 1 > 255:
            pages.append([])
            used = 0
        pages[-1].append(r)
        used += len(r)
    return pages


def build_pdb(tracks: Optional[List[rows.TrackMeta]] = None, playlists: Optional[Dict[tuple, List[str]]] = None,
              extra_rows: Optional[Dict[int, List[bytes]]] = None) -> bytes:
    tracks = tracks or []
    playlists = playlists or {}
    table_rows: Dict[int, List[bytes]] = {t: [] for t in ALL_TABLES}
    artists: Dict[str, int] = {}
    albums: Dict[tuple, int] = {}
    track_ids: Dict[str, int] = {}
    for n, m in enumerate(tracks, start=1):
        a = artists.setdefault(m.artist, len(artists) + 1) if m.artist else 0
        if m.artist and len(artists) and a == len(artists) and len(table_rows[T.ARTISTS]) < len(artists):
            table_rows[T.ARTISTS].append(rows.build_artist(a, m.artist, 0x20 * len(table_rows[T.ARTISTS])))
        b = 0
        if m.album:
            b = albums.setdefault((m.album, a), len(albums) + 1)
            if len(table_rows[T.ALBUMS]) < len(albums):
                table_rows[T.ALBUMS].append(rows.build_album(b, a, m.album, 0x20 * len(table_rows[T.ALBUMS])))
        table_rows[T.TRACKS].append(rows.build_track(m, n, a, b, 0x20 * (n - 1)))
        track_ids[m.path] = n
    pl_id = 0
    ids: Dict[tuple, int] = {}
    for path in sorted(playlists, key=lambda p: (len(p), p)):
        for depth in range(1, len(path) + 1):
            sub = path[:depth]
            if sub not in ids:
                pl_id += 1
                ids[sub] = pl_id
                parent = ids.get(sub[:-1], 0)
                table_rows[T.PLAYLIST_TREE].append(
                    rows.build_tree(parent, len(table_rows[T.PLAYLIST_TREE]), pl_id, depth < len(path), sub[-1]))
        for k, tpath in enumerate(playlists[path], start=1):
            table_rows[T.PLAYLIST_ENTRIES].append(rows.build_entry(k, track_ids[tpath], ids[path]))
    for t, extra in (extra_rows or {}).items():
        table_rows[t] += extra

    pages: List[bytes] = [b""]   # page 0 remplie à la fin
    tables = []
    next_free = 1
    plan = []
    for t in ALL_TABLES:
        packed = pack_rows(table_rows[t])
        packed = [p for p in packed if p] or ([[]] if t <= T.PLAYLIST_ENTRIES else [])   # une page de données (même vide)
        n_data = len(packed)
        index_no = next_free
        data_nos = list(range(index_no + 1, index_no + 1 + n_data))
        empty_candidate = index_no + 1 + n_data
        next_free = empty_candidate + 1
        plan.append((t, index_no, data_nos, empty_candidate, packed))
    for t, index_no, data_nos, empty, packed in plan:
        first_data_next = data_nos[0] if data_nos else empty
        pages.append(_index_page(index_no, t, first_data_next, data_nos))
        for k, (no, rws) in enumerate(zip(data_nos, packed)):
            nxt = data_nos[k + 1] if k + 1 < len(data_nos) else empty
            pages.append(_data_page(no, t, nxt, rws))
        pages.append(bytes(L))       # page vide candidate : zéros
        last = data_nos[-1] if data_nos else index_no
        tables.append((t, empty, index_no, last))
    head = bytearray(L)
    struct.pack_into("<IIIIIII", head, 0, 0, L, len(ALL_TABLES), next_free, 5, 6, 0)
    for k, (t, empty, first, last) in enumerate(tables):
        struct.pack_into("<IIII", head, 0x1C + 16 * k, t, empty, first, last)
    pages[0] = bytes(head)
    return b"".join(pages)


def sample_track(n: int, artist: str = "Artiste", album: str = "Album", title: Optional[str] = None) -> rows.TrackMeta:
    return rows.TrackMeta(
        path=f"/Contents/{artist}/{album}/t{n}.mp3", title=title or f"Titre {n}", artist=artist, album=album,
        length=200 + n, bpmx100=12800 + n, file_size=5_000_000 + n, bitrate=320, bit_depth=16, sample_rate=44100,
        file_type=1, date_added="2026-01-01", comment="", track_no=n)
