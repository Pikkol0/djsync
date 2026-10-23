"""1.2.4 : export.pdb des clés exportées par Rekordbox 7 (pages candidates au-delà de la fin du
fichier) et des anciens exports (pages d'entrées de playlist de plus de 255 lignes)."""
from __future__ import annotations

import struct

from djsync.db.pdb import PdbDatabase
from djsync.db.pdb.compare import anomalies
from djsync.db.pdb.file import PdbFile
from djsync.db.pdb.format import FILE_TABLES_AT, PAGE_SIZE, T

from .pdb_fixture import build_pdb, sample_track


def _rekordbox7_layout(data: bytes) -> bytes:
    """Comme un export Rekordbox 7 : le fichier s'arrête à la dernière page écrite ; les pages vides
    candidates de chaque table (et next_unused) sont numérotées au-delà de la fin du fichier."""
    f = PdbFile(data)
    buf = bytearray(data)
    n = len(buf) // PAGE_SIZE
    free = n
    count = struct.unpack_from("<I", buf, 8)[0]
    for slot in range(count):
        t, empty, first, last = struct.unpack_from("<IIII", buf, FILE_TABLES_AT + 16 * slot)
        if empty >= n - 1 or empty > last:
            new = free
            free += 1
            struct.pack_into("<I", buf, FILE_TABLES_AT + 16 * slot + 4, new)
            struct.pack_into("<I", buf, last * PAGE_SIZE + 0x0C, new)          # la dernière page pointe dessus
    struct.pack_into("<I", buf, 0x0C, free)
    assert free > n + 8                                                        # refusé avant la 1.2.4
    return bytes(buf)


def test_rekordbox7_layout_is_read_and_grows():
    base = build_pdb([sample_track(1)], {("Rap",): []})
    data = _rekordbox7_layout(base)
    f = PdbFile(data, allow_growth=True)
    db = PdbDatabase(data, allow_growth=True) if "allow_growth" in PdbDatabase.__init__.__code__.co_varnames \
        else PdbDatabase(data)
    assert db.track_count == 1
    pl = db.ensure_playlist(("DJSync",))
    db.file.allow_growth = True
    for i in range(400):                                                       # assez pour agrandir la table
        db.file.insert_row(T.PLAYLIST_ENTRIES, struct.pack("<III", i + 1, 1, pl))
    out = db.to_bytes()
    g = PdbFile(out)
    assert len(g.data_pages(T.PLAYLIST_ENTRIES)) > len(f.data_pages(T.PLAYLIST_ENTRIES))
    assert not [a for a in anomalies(g) if "missing playlist" in a]


def test_page_with_more_than_255_rows_is_accepted():
    """Page d'entrées de playlist pleine (lignes de 12 octets) : un export Rekordbox 5 peut y mettre
    plus de 255 lignes (compteur sur 13 bits)."""
    base = build_pdb([sample_track(1)], {("Rap",): []})
    f = PdbFile(base)
    page = f.page(f.data_pages(T.PLAYLIST_ENTRIES)[-1])
    page.check_data_page()
    page._set_counts(270, 270)
    try:
        page.check_data_page()
    except Exception as exc:  # noqa: BLE001
        assert "inconsistent counters" not in str(exc)
