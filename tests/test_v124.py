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


def test_same_file_with_several_track_rows_is_not_added_twice():
    """Export Rekordbox ancien : un même fichier peut avoir plusieurs lignes (ids) dans la table des
    pistes, et les playlists pointer vers n'importe laquelle. Le rattrapage n'ajoutait alors une 2e fois
    le son à la playlist (vu sur une clé de 875 sons : 300 entrées en double)."""
    from dataclasses import replace

    t = sample_track(1)
    twin = replace(t)                                       # même chemin, 2e ligne
    data = build_pdb([t, twin, sample_track(2)], {("Rap",): [t.path]})
    db = PdbDatabase(data)
    assert db.track_count == 2
    db.playlist_add(("Rap",), [t.path])
    assert db.summary.entries_added == 0
    db.playlist_set(("Rap",), [t.path])
    assert db.summary.entries_added == 0 and db.summary.entries_removed == 0
    assert db.delete_track(t.path)
    out = PdbDatabase(db.to_bytes())
    assert out.track_count == 1 and not out._alias


def test_playlists_differing_only_by_case_stay_separate():
    t1, t2 = sample_track(1), sample_track(2)
    db = PdbDatabase(build_pdb([t1, t2], {("dBs",): [t1.path], ("dbs",): [t2.path]}))
    assert db.find_playlist(("dBs",)).name == "dBs" and db.find_playlist(("dbs",)).name == "dbs"
    db.playlist_add(("dbs",), [t2.path])
    assert db.summary.entries_added == 0
    assert db.find_playlist(("DBS",)) is None                # ambigu : on ne devine pas
    db2 = PdbDatabase(build_pdb([t1], {("House",): []}))
    assert db2.find_playlist(("house",)).name == "House"      # sans ambiguïté : toléré
