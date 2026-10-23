"""1.3.0 : format de la clé et export.pdb (T01), hot cues et boucles (C22), report des cues (C13),
doublons par empreinte audio (B02)."""
from __future__ import annotations

from pathlib import Path

import pytest


# ============================================================================ T01
def test_filesystem_names_and_compat():
    from djsync.db.usb import filesystem_compat, normalize_fs

    assert normalize_fs("vfat") == "FAT32" and normalize_fs("msdos") == "FAT32" and normalize_fs("exfat") == "exFAT"
    assert normalize_fs("NTFS") == "NTFS" and normalize_fs("hfsplus") == "HFS+" and normalize_fs("") == ""
    assert filesystem_compat("FAT32") == "ok" and filesystem_compat("HFS+") == "ok"
    assert filesystem_compat("exFAT") == "recent_only"
    assert filesystem_compat("NTFS") == "unsupported" and filesystem_compat("") == ""


def test_drive_filesystem_from_mount_table(monkeypatch, tmp_path):
    import djsync.db.usb as usb

    if usb.os.name == "nt":
        pytest.skip("POSIX mount table")
    key = tmp_path / "KEY"
    key.mkdir()
    monkeypatch.setattr(usb, "_mount_table", lambda: [("/", "ext4"), (str(tmp_path), "tmpfs"), (str(key), "exfat")])
    assert usb.drive_filesystem(key) == "exFAT"
    assert usb.drive_filesystem(key / "PIONEER") == "exFAT"
    assert usb.drive_filesystem(tmp_path) == "tmpfs"


def test_diagnostic_report_warns_about_exfat_and_missing_pdb():
    from djsync.db.diagnose import DiagnosticReport

    rep = DiagnosticReport(drive="E:", journal_mode="wal", filesystem="exFAT", integrity="ok")
    assert any("E-8307" in p for p in rep.problems)
    assert any("Device Library" in line for line in rep.lines())
    assert not DiagnosticReport(drive="E:", journal_mode="wal", filesystem="FAT32", integrity="ok").problems


def _pdb_pair(tmp_path):
    from djsync.db.pdb import PdbDatabase
    from tests.pdb_fixture import build_pdb, sample_track

    ref = build_pdb([sample_track(1), sample_track(2)], {("Rap",): [], ("House",): []})
    (tmp_path / "ref.pdb").write_bytes(ref)
    db = PdbDatabase(ref)
    db.ensure_playlist(("DJSync",))
    db.playlist_set(("DJSync",), list(db.track_paths()))
    (tmp_path / "new.pdb").write_bytes(db.to_bytes())
    return tmp_path / "ref.pdb", tmp_path / "new.pdb"


def test_pdb_compare_report(tmp_path):
    from djsync.db.pdb import compare

    ref, new = _pdb_pair(tmp_path)
    text = "\n".join(compare.compare(ref, new, "DJSync"))
    assert "playlist only in compared file" in text and "'DJSync'" in text
    assert "entries of 'DJSync'" in text and "anomalies: none" in text
    assert compare.main([str(ref), str(new), "-o", str(tmp_path / "r.txt")]) == 0
    assert (tmp_path / "r.txt").read_text(encoding="utf-8").startswith("Reference")


def test_pdb_compare_finds_dangling_entries(tmp_path):
    import struct

    from djsync.db.pdb import compare
    from djsync.db.pdb.file import PdbFile
    from djsync.db.pdb.format import T

    _ref, new = _pdb_pair(tmp_path)
    f = PdbFile(new.read_bytes())
    p, _i, off = next(iter(f.iter_rows(T.PLAYLIST_ENTRIES)))
    struct.pack_into("<I", f.data, f.page(p).base + off + 4, 999)          # son inexistant
    bad = compare.anomalies(f)
    assert any("missing tracks" in b for b in bad)
