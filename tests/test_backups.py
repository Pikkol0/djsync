"""V1.2.0 : points de restauration de la clé (origine, manuels, année / mois / semaine, 5 récents)."""
from __future__ import annotations

from datetime import datetime, timedelta

from djsync.db import RekordboxUsbLibrary, drive_from_letter
from djsync.db import backups as B
from tests.test_pdb_sync import make_usb, open_lib, pdb_of


def _names(usb):
    with open_lib(usb) as lib:
        return sorted(p.name for p in lib.list_playlists())


def test_origin_then_one_point_per_session_and_restore_in_one_click(tmp_path):
    usb = make_usb(tmp_path)
    bk = usb / "DJSync_Backups"
    rb = usb / "PIONEER" / "rekordbox"
    original = _names(usb)
    pdb_before = (rb / "export.pdb").read_bytes()
    with open_lib(usb) as lib:
        lib.create_playlist("Session 1")
        lib.create_playlist("Encore")
    assert [p.kind for p in B.list_points(bk)] == ["origin"]          # 1re session : l'origine seulement
    with open_lib(usb) as lib:
        lib.create_playlist("Session 2")
    points = B.list_points(bk)
    assert [p.kind for p in points] == ["auto", "origin"]
    assert set(points[0].tags) == {"year", "month", "week"}
    origin = points[1]
    assert origin.has_pdb and origin.playlists is not None and not origin.approx

    before = B.restore(rb, bk, origin)
    assert _names(usb) == original
    assert (rb / "export.pdb").read_bytes() == pdb_before
    assert before.kind == "restore"                                  # l'état remplacé est gardé : annulable
    B.restore(rb, bk, before)
    assert {"Session 1", "Encore", "Session 2"} <= set(_names(usb))
    assert pdb_of(usb).find_playlist(("Session 2",)) is not None


def test_manual_backup_is_kept_and_named(tmp_path):
    usb = make_usb(tmp_path)
    bk = usb / "DJSync_Backups"
    with open_lib(usb) as lib:
        lib.create_playlist("x")
        point = lib.create_backup("  Avant la soirée  ")
    assert point.kind == "manual" and point.label == "Avant la soirée"
    for _ in range(12):
        B.prune(bk)
    assert any(p.kind == "manual" for p in B.list_points(bk))
    B.delete_point(point)
    assert not any(p.kind == "manual" for p in B.list_points(bk))


def test_retention_keeps_origin_year_month_week_and_five_recent(tmp_path):
    usb = make_usb(tmp_path)
    bk, rb = usb / "DJSync_Backups", usb / "PIONEER" / "rekordbox"
    B.snapshot(rb, bk, "origin", now=datetime(2021, 3, 1, 10))
    start = datetime(2024, 12, 20, 9)
    for day in range(60):                                       # une session par jour pendant 2 mois
        B.snapshot(rb, bk, "auto", now=start + timedelta(days=day))
    points = B.list_points(bk)
    autos = [p for p in points if p.kind == "auto"]
    last = start + timedelta(days=59)                           # 2025-02-17
    assert [p.kind for p in points].count("origin") == 1
    assert len([p for p in autos if p.created >= last - timedelta(days=4)]) == 5   # 5 plus récents
    year = next(p for p in autos if "year" in p.tags and p.created.year == 2025)
    assert year.created == datetime(2025, 1, 1, 9)              # 1er de l'année en cours ; 2024 remplacé
    assert not any("year" in p.tags and p.created.year == 2024 for p in autos)
    assert any("month" in p.tags and p.created == datetime(2025, 2, 1, 9) for p in autos)
    assert any("week" in p.tags and p.created == datetime(2025, 2, 17, 9) for p in autos)
    assert len(autos) <= 8


def test_origin_rebuilt_from_backups_of_an_older_version(tmp_path):
    usb = make_usb(tmp_path)
    bk, rb = usb / "DJSync_Backups", usb / "PIONEER" / "rekordbox"
    bk.mkdir()
    import shutil

    shutil.copy2(rb / "exportLibrary.db", bk / "exportLibrary-20250101-101010-000-session.db")
    shutil.copy2(rb / "export.pdb", bk / "export-20250101-101011-000-session.pdb")
    with open_lib(usb) as lib:
        lib.create_playlist("Nouvelle")
    origin = next(p for p in B.list_points(bk) if p.kind == "origin")
    assert origin.approx and origin.created == datetime(2025, 1, 1, 10, 10, 10) and origin.has_pdb
    assert any(p.kind == "auto" for p in B.list_points(bk))


def test_pdb_repair_on_connect_is_backed_up_first(tmp_path):
    usb = make_usb(tmp_path)
    bk = usb / "DJSync_Backups"
    with open_lib(usb, pdb_sync="off") as lib:                  # son ajouté sans toucher export.pdb
        lib.create_playlist("Hors pdb")
    with open_lib(usb) as lib:
        lib.pdb_catch_up()
    assert [p.kind for p in B.list_points(bk)] == ["auto", "origin"]


def test_failed_point_cancels_the_write(tmp_path):
    usb = make_usb(tmp_path)
    (usb / "DJSync_Backups").mkdir()
    (usb / "DJSync_Backups" / "Points").write_text("pas un dossier")
    with RekordboxUsbLibrary(drive_from_letter(str(usb))).connect() as lib:
        try:
            lib.create_playlist("refusée")
        except Exception as exc:  # noqa: BLE001
            assert "Backup failed" in str(exc)
        assert "refusée" not in [p.name for p in lib.list_playlists()]
