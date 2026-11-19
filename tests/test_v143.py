"""1.4.3 : rapidité (A3-6, B98, A1-2, A1-4, A1-12, A1-13) et sûreté des données (A6-1, A6-2, A6-9)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from djsync.db import backups
from djsync.db.pdb import store as pdb_store

from .test_pdb_sync import make_usb, open_lib, pdb_of
from .test_usb_library import make_wav


# ------------------------------------------------------------------ A3-6 : lecture pendant une écriture
def test_a3_6_read_does_not_wait_for_a_write(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        held, release, got = threading.Event(), threading.Event(), {}

        def writer():
            with lib._lock:                     # une écriture longue (sauvegarde, export.pdb) tient le verrou
                held.set()
                release.wait(5)

        th = threading.Thread(target=writer)
        th.start()
        held.wait(2)
        start = time.monotonic()
        got["track"] = lib.find_by_source_url("https://www.youtube.com/watch?v=xxxxxxxxxxx")
        got["n"] = lib.track_count()
        got["t"] = lib.get_track(a.content_id)
        took = time.monotonic() - start
        release.set()
        th.join()
        assert took < 1.0 and got["n"] == 1 and got["t"].title == "a"
        # dans une écriture, la lecture voit ce que la transaction en cours a écrit (connexion principale)
        with lib._write() as conn:
            conn.execute("UPDATE content SET title = 'inside' WHERE content_id = ?", (a.content_id,))
            assert lib.get_track(a.content_id).title == "inside"
        assert lib.get_track(a.content_id).title == "inside"
    assert not lib._reader


def test_a3_6_checkpoint_still_empties_the_wal(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        lib.track_count()                       # la connexion de lecture est ouverte
        lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        wal = Path(str(lib.db_path) + "-wal")
        assert not wal.exists() or wal.stat().st_size == 0


# ------------------------------------------------------------------ B98 : une requête pour toute la liste
def test_b98_grouped_lookup_matches_one_by_one(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None,
                          "https://www.youtube.com/watch?v=abcdefghijk", [1])
        urls = ["https://www.youtube.com/watch?v=abcdefghijk", "https://music.youtube.com/watch?v=zzzzzzzzzzz",
                "abcdefghijk", "https://soundcloud.com/x/y"]
        many = lib.find_by_source_urls(urls)
        for u in urls:
            one = lib.find_by_source_url(u)
            assert (many.get(u) is None) == (one is None)
        assert many[urls[0]].content_id == a.content_id


def test_b98_annotate_uses_one_query():
    from djsync.core.duplicates import DuplicateChecker, FakeLibrary
    from djsync.models import TrackResult

    calls = []

    def many(urls):
        calls.append(list(urls))
        return {urls[0]: type("T", (), {"display_name": "A - a"})()}

    def one(_url):
        raise AssertionError("one by one")

    dc = DuplicateChecker(FakeLibrary(), exact_lookup=one, exact_many=many)
    res = [TrackResult(video_id=f"id{i:09d}", title=f"t{i}", artist="x", duration_seconds=10) for i in range(5)]
    out = dc.annotate(res)
    assert len(calls) == 1 and out[0].is_duplicate and not any(x.is_duplicate for x in out[1:])


# ------------------------------------------------------------------ A1-2 : export.pdb lu une fois
def test_a1_2_one_read_per_write(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        store = lib._pdb_store()
        before = store.reads
        lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        assert store.reads - before == 1           # la relecture de contrôle seulement
        assert lib.pdb_status().state == "ok"


def test_a1_2_file_changed_elsewhere_is_read_again(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        store = lib._pdb_store()
        p = store.path
        data = p.read_bytes()
        p.write_bytes(data)                            # autre programme : même contenu, autre date
        os.utime(p, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
        before = store.reads
        lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        assert store.reads - before == 2


def test_a1_2_burst_is_written_once_after_the_delay(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        lib.pdb_delay = 0.4
        writes = []
        real = pdb_store.PdbStore._write_atomic

        def counted(self, data):
            writes.append(1)
            return real(self, data)

        pdb_store.PdbStore._write_atomic = counted
        try:
            for name in "abc":
                lib.add_track(make_wav(lib, name.upper(), name), name, name.upper(), None, None, [1])
            assert writes == [] and lib.pdb_pending
            time.sleep(1.0)
            assert len(writes) == 1 and not lib.pdb_pending
        finally:
            pdb_store.PdbStore._write_atomic = real
        assert lib.pdb_status().state == "ok"


def test_a1_2_pending_write_is_done_before_status_and_close(tmp_path):
    usb = make_usb(tmp_path)
    lib = open_lib(usb).connect()
    lib.pdb_delay = 30
    a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
    assert lib.pdb_pending
    assert lib.pdb_status().state == "ok" and not lib.pdb_pending        # état lu : réécriture faite d'abord
    b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
    assert lib.pdb_pending
    lib.close()                                                            # fermeture / éjection
    pdb = pdb_of(usb)
    assert pdb.has_track(a.path) and pdb.has_track(b.path)


# ------------------------------------------------------------------ A6-9 : marques avant le COMMIT
def test_a6_9_marks_are_in_the_journal_before_commit(tmp_path):
    usb = make_usb(tmp_path)
    journal = usb / "DJSync_Backups" / "pdb-journal.json"
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        seen = {}
        conn = lib._db()

        class Spy:
            def __getattr__(self, n):
                return getattr(conn, n)

            def execute(self, sql, *args):
                if sql == "COMMIT":
                    seen["marks"] = json.loads(journal.read_text("utf-8"))["marks"] if journal.exists() else []
                return conn.execute(sql, *args)

        lib._conn = Spy()
        try:
            lib.delete_track(a.content_id)
        finally:
            lib._conn = conn
        assert [m["kind"] for m in seen["marks"]] == ["track_deleted"]
        assert lib.pdb_status().state == "ok"
    assert not pdb_of(usb).has_track(a.path) and not journal.exists()


def test_a6_9_mark_of_a_cancelled_transaction_is_dropped(tmp_path):
    from sqlcipher3 import dbapi2 as sqlcipher

    usb = make_usb(tmp_path)
    journal = usb / "DJSync_Backups" / "pdb-journal.json"
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        conn = lib._db()

        class Spy:                                       # le COMMIT échoue (coupure, clé pleine…)
            def __getattr__(self, n):
                return getattr(conn, n)

            def execute(self, sql, *args):
                if sql == "COMMIT":
                    raise sqlcipher.OperationalError("disk I/O error")
                return conn.execute(sql, *args)

        lib._conn = Spy()
        try:
            with pytest.raises(sqlcipher.OperationalError):
                lib.delete_track(a.content_id)
        finally:
            lib._conn = conn
        assert journal.exists()                          # la marque est restée…
        lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        assert lib.pdb_status().state == "ok"
    assert pdb_of(usb).has_track(a.path) and not journal.exists()     # … sans effet, puis retirée


# ------------------------------------------------------------------ A6-1 : remplacement interrompu
def _rb(usb):
    return usb / "PIONEER" / "rekordbox"


def test_a6_1_pdb_put_back_from_a_valid_leftover(tmp_path):
    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
    pdb = _rb(usb) / "export.pdb"
    pdb.rename(pdb.with_name("export.pdb.djsync-tmp"))          # retrait entre l'effacement et le renommage
    lib = open_lib(usb).connect()
    try:
        assert lib.recovery.restored == ["export.pdb"] and pdb.is_file()
        assert lib.pdb_status().state == "ok"
    finally:
        lib.close()


def test_a6_1_library_put_back_at_detection(tmp_path):
    from djsync.db.usb import drive_from_letter

    usb = make_usb(tmp_path)
    db = _rb(usb) / "exportLibrary.db"
    db.rename(db.with_name("exportLibrary.db.djsync-tmp"))
    drive_from_letter(str(usb))                                 # la clé est reconnue
    assert db.is_file()


def test_a6_1_unreadable_leftover_nothing_deleted_then_restore(tmp_path):
    from djsync.db import recover
    from djsync.db.usb import DriveNotFoundError, drive_from_letter

    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])   # point de session créé
    db = _rb(usb) / "exportLibrary.db"
    tmp = db.with_name("exportLibrary.db.djsync-tmp")
    tmp.write_bytes(db.read_bytes()[:3000])                    # copie tronquée
    db.unlink()
    with pytest.raises(DriveNotFoundError):
        drive_from_letter(str(usb))
    assert tmp.is_file() and recover.damaged_library(usb)
    point = recover.restore_latest(usb)
    assert point and db.is_file() and not tmp.exists()
    assert list((usb / "DJSync_Backups").glob("exportLibrary.db-leftover-*"))
    with open_lib(usb) as lib:
        assert lib.track_count() == 0                          # état du point (avant le premier ajout)


def test_a6_1_leftover_next_to_the_file_is_moved_not_deleted(tmp_path):
    usb = make_usb(tmp_path)
    tmp = _rb(usb) / "export.pdb.djsync-tmp"
    tmp.write_bytes(b"half")
    with open_lib(usb) as lib:
        assert lib.recovery.moved == ["export.pdb"]
    assert not tmp.exists() and list((usb / "DJSync_Backups").glob("export.pdb-leftover-*"))


# ------------------------------------------------------------------ A6-2 : restauration tout ou rien
def _point_and_change(usb):
    with open_lib(usb) as lib:
        lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        point = lib.create_backup("before B")
        lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1])
        return point, lib.backup_dir


def test_a6_2_refused_when_a_file_cannot_be_replaced(tmp_path, monkeypatch):
    usb = make_usb(tmp_path)
    point, bdir = _point_and_change(usb)
    monkeypatch.setattr(backups, "_not_replaceable", lambda p: "locked" if p.name == "export.pdb" else "")
    db = _rb(usb) / "exportLibrary.db"
    before = db.read_bytes()
    with pytest.raises(backups.RestoreBusyError):
        backups.restore(_rb(usb), bdir, point)
    assert db.read_bytes() == before


def test_a6_2_database_put_back_when_export_pdb_fails(tmp_path, monkeypatch):
    usb = make_usb(tmp_path)
    point, bdir = _point_and_change(usb)
    real = backups._replace

    def failing(src, dst):
        if dst.name == "export.pdb" and src.parent == point.path:
            raise PermissionError("export.pdb locked")
        return real(src, dst)

    monkeypatch.setattr(backups, "_replace", failing)
    with pytest.raises(backups.RestoreBusyError):
        backups.restore(_rb(usb), bdir, point)
    with open_lib(usb) as lib:
        assert lib.track_count() == 2                         # rien n'a changé


# ------------------------------------------------------------------ A1-12, A1-13
def test_a1_12_import_logs_duration_and_rate(tmp_path, caplog):
    import logging

    from djsync.core import importer

    usb = make_usb(tmp_path)
    src = tmp_path / "in"
    src.mkdir()
    from .test_v140 import _wav

    _wav(src / "x.wav")
    with open_lib(usb) as lib, caplog.at_level(logging.INFO, logger="djsync.core.importer"):
        importer.import_files(lib, [src / "x.wav"])
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("Import finished"))
    assert "1 files (1 added" in line and "MB/s" in line


def test_a1_13_which_and_sessions_are_kept(monkeypatch):
    import shutil

    from djsync.core import nettools

    nettools.clear()
    calls = []
    monkeypatch.setattr(shutil, "which", lambda n: calls.append(n) or None)
    for _ in range(3):
        assert nettools.which("deno-missing") is None
    assert calls == ["deno-missing"]
    assert nettools.session("artwork") is nettools.session("artwork")
    assert nettools.session("artwork") is not nettools.session("freesources")
    nettools.clear()
