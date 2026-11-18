"""1.4.2 (B113) : numéro de transaction d'export.pdb.

Rekordbox garde le numéro du fichier (page 0, 0x14) strictement supérieur à celui de chaque page
(0x10). Pages et fichier au même numéro : Rekordbox prend la dernière transaction pour inachevée et
ignore ses lignes (2e playlist absente de Device Library, 25 sons sur 29 sur la clé de l'auteur).
"""
import struct

from djsync.db.pdb import sync as pdb_sync
from djsync.db.pdb.database import PdbDatabase
from djsync.db.pdb.file import PAGE_SIZE, PdbFile, validate_against

from .pdb_fixture import build_pdb, sample_track


def _tracks(n=3):
    return [sample_track(i) for i in range(1, n + 1)]


def _broken(data: bytes) -> bytes:
    """Clé écrite par DJSync avant B113 : chaque page en usage porte le numéro du fichier."""
    d = bytearray(data)
    head = struct.unpack_from("<I", d, 0x14)[0]
    for i in range(1, len(d) // PAGE_SIZE):
        if struct.unpack_from("<I", d, i * PAGE_SIZE + 4)[0] == i:
            struct.pack_into("<I", d, i * PAGE_SIZE + 0x10, head)
    return bytes(d)


def _target(tracks, playlists):
    return pdb_sync.Target(tracks=tracks, playlists=[(path, False, paths) for path, paths in playlists.items()])


def test_write_keeps_file_number_above_every_page():
    tracks = _tracks()
    data = build_pdb(tracks, {("A",): [tracks[0].path]})
    db = PdbDatabase(data)
    db.ensure_playlist(("B",), False)
    db.playlist_set(("B",), [tracks[1].path])
    new = db.to_bytes()
    f = PdbFile(new)
    assert f.seq_problems() == []
    assert f.seq > max(f.page_seqs())
    validate_against(data, new, db.file.touched)


def test_broken_key_is_detected_and_repaired_by_changing_only_page_0():
    tracks = _tracks()
    playlists = {("test",): [tracks[0].path], ("set",): [tracks[1].path, tracks[2].path]}
    data = _broken(build_pdb(tracks, playlists))
    assert PdbFile(data).seq_problems()
    db = PdbDatabase(data)
    p = pdb_sync.plan(db, _target(tracks, playlists))
    assert p.repair_seq and not p.empty
    assert "transaction number to repair" in p.describe()
    pdb_sync.apply(db, p)
    new = db.to_bytes()
    validate_against(data, new, db.file.touched)
    fixed = PdbFile(new)
    assert fixed.seq_problems() == []
    assert struct.unpack_from("<I", new, 0x14)[0] == struct.unpack_from("<I", data, 0x14)[0] + 1
    assert new[PAGE_SIZE:] == data[PAGE_SIZE:]          # aucune page de données touchée
    again = PdbDatabase(new)
    assert pdb_sync.plan(again, _target(tracks, playlists)).empty


def test_key_already_right_is_not_rewritten():
    tracks = _tracks()
    playlists = {("A",): [tracks[0].path]}
    data = build_pdb(tracks, playlists)
    assert PdbFile(data).seq_problems() == []
    assert pdb_sync.plan(PdbDatabase(data), _target(tracks, playlists)).empty


def test_writing_on_a_broken_key_repairs_it_too():
    tracks = _tracks()
    data = _broken(build_pdb(tracks, {("A",): [tracks[0].path]}))
    db = PdbDatabase(data)
    db.add_track(sample_track(9))
    new = db.to_bytes()
    validate_against(data, new, db.file.touched)
    assert PdbFile(new).seq_problems() == []
