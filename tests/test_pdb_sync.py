"""Répercussion des écritures de exportLibrary.db dans export.pdb (clé synthétique, sans platine)."""
from pathlib import Path

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

from djsync.db import RekordboxUsbLibrary, drive_from_letter
from djsync.db.pdb import PdbDatabase
from djsync.db.pdb.file import PdbFile
from djsync.db.pdb.format import T
from djsync.db._key import get_default_key

from .pdb_fixture import build_pdb, sample_track
from .test_usb_library import DDL, make_wav


def make_usb(tmp_path: Path, pdb: bool = True, pdb_bytes: bytes = None) -> Path:
    db_dir = tmp_path / "PIONEER" / "rekordbox"
    db_dir.mkdir(parents=True)
    (tmp_path / "Contents").mkdir()
    conn = sqlcipher.connect(str(db_dir / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("PRAGMA journal_mode = WAL")
    for ddl in DDL:
        conn.execute(ddl)
    conn.execute("INSERT INTO property VALUES ('', '1000', 0, '2026-01-01', 0, 1)")
    conn.execute("INSERT INTO playlist VALUES (1, 0, 'Rap', NULL, 0, 0)")
    conn.execute("INSERT INTO playlist VALUES (2, 1, 'House', NULL, 0, 0)")
    conn.execute("INSERT INTO playlist VALUES (3, 2, 'Dossier', NULL, 1, 0)")
    conn.commit()
    conn.close()
    if pdb_bytes is not None:
        (db_dir / "export.pdb").write_bytes(pdb_bytes)
    elif pdb:
        (db_dir / "export.pdb").write_bytes(build_pdb([sample_track(1)], {("Rap",): [], ("House",): [], ("Dossier",): []}))
    return tmp_path


def open_lib(usb: Path, **kw) -> RekordboxUsbLibrary:
    return RekordboxUsbLibrary(drive_from_letter(str(usb)), **kw).connect()


def pdb_of(usb: Path) -> PdbDatabase:
    return PdbDatabase((usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes())


def test_add_track_is_mirrored_with_playlists(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        t = lib.add_track(make_wav(lib, "Leto", "Leto - Macaroni"), "Macaroni", "Leto", "100 visages",
                          "https://music.youtube.com/watch?v=BBBBBBBBBBB", [1, 2])
        assert lib.pdb_state == "ok" and lib.pdb_last_summary.tracks_added == 1
    pdb = pdb_of(usb)
    assert pdb.has_track(t.path) and pdb.track_count == 2
    for name in ("Rap", "House"):
        node = pdb.find_playlist((name,))
        assert [e.track for e in pdb._ordered_entries(node.id)] == [pdb._tracks[t.path.casefold()].id]
    assert pdb.find_playlist(("Dossier",)) is not None
    backups = list((usb / "DJSync_Backups").glob("export-*-session.pdb"))
    assert len(backups) == 1 and PdbDatabase(backups[0].read_bytes()).track_count == 1


def test_all_playlist_operations_follow(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        c = lib.add_track(make_wav(lib, "C", "c"), "c", "C", None, None, [1])
        lib.reorder_track(1, c.content_id, 1)
        pdb = pdb_of(usb)
        order = [e.track for e in pdb._ordered_entries(pdb.find_playlist(("Rap",)).id)]
        assert order == [pdb._tracks[x.path.casefold()].id for x in (c, a, b)]
        lib.move_tracks([a.content_id], 1, 2)
        lib.rename_playlist(2, "Deep House")
        lib.remove_from_playlist(1, [b.content_id])
        pdb = pdb_of(usb)
        assert [e.index for e in pdb._ordered_entries(pdb.find_playlist(("Rap",)).id)] == [1]
        assert len(pdb._ordered_entries(pdb.find_playlist(("Deep House",)).id)) == 1
        assert pdb.find_playlist(("House",)) is None
        lib.create_playlist("Warmup")
        lib.delete_playlist(2)
        pdb = pdb_of(usb)
        assert pdb.find_playlist(("Warmup",)) is not None and pdb.find_playlist(("Deep House",)) is None
        assert lib.pdb_state == "ok"


def test_delete_tracks_batch_rewrites_pdb_once(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        ts = [lib.add_track(make_wav(lib, f"X{i}", f"x{i}"), f"x{i}", f"X{i}", None, None, [1]) for i in range(4)]
        before = len(list((usb / "DJSync_Backups").glob("export-*.pdb")))
        removed, failures = lib.delete_tracks([t.content_id for t in ts], delete_files=True)
        after = len(list((usb / "DJSync_Backups").glob("export-*.pdb")))
        assert removed == 4 and failures == 0
        assert after == before + 1                                   # un seul lot = une seule écriture/sauvegarde
    pdb = pdb_of(usb)
    assert pdb.track_count == 1 and not any(pdb.has_track(t.path) for t in ts)
    assert pdb._ordered_entries(pdb.find_playlist(("Rap",)).id) == []


def test_no_export_pdb_nothing_is_created(tmp_path):
    usb = make_usb(tmp_path, pdb=False)
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        assert lib.pdb_state == "absent"
    assert not (usb / "PIONEER" / "rekordbox" / "export.pdb").exists()


def test_unrecognised_pdb_is_left_alone_and_database_write_still_succeeds(tmp_path):
    usb = make_usb(tmp_path, pdb_bytes=b"\0" * 9000)
    with open_lib(usb) as lib:
        assert lib.pdb_state == "unsupported"
        t = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        assert lib.get_track(t.content_id).title == "a"            # exportLibrary.db a bien reçu le son
    assert (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes() == b"\0" * 9000
    assert not list((usb / "DJSync_Backups").glob("export-*.pdb"))


def test_pdb_sync_off_never_touches_the_file(tmp_path):
    usb = make_usb(tmp_path)
    raw = (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes()
    with open_lib(usb, pdb_sync="off") as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        assert lib.pdb_state == "off"
    assert (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes() == raw


def test_full_page_marks_stale_then_catch_up_with_growth_heals(tmp_path):
    from .test_pdb import fill_tracks_page
    full, _n = fill_tracks_page()
    usb = make_usb(tmp_path, pdb_bytes=full)
    raw = full
    with open_lib(usb) as lib:                                     # agrandissement désactivé (défaut)
        for i in range(12):
            lib.add_track(make_wav(lib, f"F{i}", f"f{i}"), f"f{i}", f"F{i}", None, None, [1])
            if lib.pdb_state == "stale":
                break
        assert lib.pdb_state == "stale" and "full" in lib.pdb_problem
        assert lib.track_count() >= 1                              # la base OneLibrary, elle, est à jour
        status = lib.pdb_status()
        assert status.state == "stale" and status.missing_tracks >= 1
    lib2 = RekordboxUsbLibrary(drive_from_letter(str(usb)), pdb_allow_growth=True).connect()
    try:
        summary = lib2.pdb_catch_up()
        assert summary.tracks_added >= 1 and lib2.pdb_state == "ok"
        assert lib2.pdb_status().missing_tracks == 0
        assert len(PdbFile((usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes()).data_pages(T.TRACKS)) >= 2
    finally:
        lib2.close()
    assert raw != (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes()


def test_catch_up_is_additive_and_idempotent(tmp_path):
    usb = make_usb(tmp_path, pdb=False)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", "Alb", None, [1, 2])
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [2])
    # export.pdb créé APRÈS coup, ne connaissant que le son 1 (ancienne clé, DJSync V1.1-A)
    pdb_path = usb / "PIONEER" / "rekordbox" / "export.pdb"
    pdb_path.write_bytes(build_pdb([sample_track(1), sample_track(2)], {("Rap",): [sample_track(1).path]}))
    with open_lib(usb) as lib:
        st = lib.pdb_status()
        assert st.state == "stale" and st.missing_tracks == 2 and st.missing_playlists >= 1
        lib.pdb_catch_up()
        raw = pdb_path.read_bytes()
        assert lib.pdb_catch_up().tracks_added == 0 and pdb_path.read_bytes() == raw     # idempotent
        pdb = pdb_of(usb)
        assert pdb.has_track(a.path) and pdb.has_track(b.path) and pdb.has_track(sample_track(1).path)  # rien de retiré
        assert len(pdb._ordered_entries(pdb.find_playlist(("Rap",)).id)) == 2          # entrée existante conservée + ajout
        assert lib.pdb_status().state == "ok"


def test_read_only_library_never_writes_pdb(tmp_path):
    usb = make_usb(tmp_path)
    raw = (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes()
    with RekordboxUsbLibrary(drive_from_letter(str(usb)), read_only=True) as lib:
        lib.pdb_status()
        with pytest.raises(Exception):
            lib.pdb_catch_up()
    assert (usb / "PIONEER" / "rekordbox" / "export.pdb").read_bytes() == raw
