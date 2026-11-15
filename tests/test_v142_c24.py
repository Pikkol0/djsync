"""1.4.2 (C24) : préparer une clé vierge depuis DJSync, à partir du gabarit de clé vide embarqué."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from djsync.db import blank_key
from djsync.db.blank_key import PrepareError, prepare_drive, refusal, template_files
from djsync.db.usb import DB_RELATIVE_PATH, UnpreparedDrive, drive_from_letter

from .test_local_library import make_wav

GABARIT = {   # tailles et empreintes relevées sur la clé vide de Rekordbox 7.0.5 (claude/c24-cle-vide.md)
    "PIONEER/rekordbox/exportLibrary.db": (118784, "b95346bf5aae9d9c"),
    "PIONEER/rekordbox/export.pdb": (167936, "c080960e32639e7a"),
    "PIONEER/rekordbox/exportExt.pdb": (73728, "6c44e7dccd8414c1"),
    "PIONEER/DEVSETTING.DAT": (140, "6e042b68afa4dd30"),
}


@pytest.fixture(autouse=True)
def not_system_disk(monkeypatch):
    """Les dossiers temporaires des tests sont sur le disque système : le refus est testé à part."""
    monkeypatch.setattr(blank_key, "_is_system_disk", lambda root: False)


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ------------------------------------------------------------------ gabarit
def test_template_is_the_blank_key_without_journal_or_profile():
    files = template_files()
    assert set(files) == set(GABARIT)
    for name, (size, digest) in GABARIT.items():
        assert len(files[name]) == size
        assert hashlib.sha256(files[name]).hexdigest().startswith(digest)
    assert not any(n.endswith(("-wal", "-shm", ".nxs")) for n in files)


def test_template_opens_and_matches_export_pdb(tmp_path):
    from sqlcipher3 import dbapi2 as sqlcipher

    from djsync.db._key import get_default_key
    from djsync.db.pdb import PdbDatabase
    from djsync.db.pdb.check import report

    prepare_drive(tmp_path, "FAT32")
    rb = tmp_path / "PIONEER" / "rekordbox"
    conn = sqlcipher.connect(str(rb / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 22
    counts = {tb: conn.execute(f"SELECT count(*) FROM {tb}").fetchone()[0]
              for tb in ("color", "menuItem", "category", "sort", "content", "playlist")}
    conn.close()
    assert counts == {"color": 8, "menuItem": 27, "category": 22, "sort": 17, "content": 0, "playlist": 0}
    lines = report(rb / "export.pdb")
    assert lines[-1].startswith("=> Layout recognised")
    pdb = PdbDatabase((rb / "export.pdb").read_bytes())
    assert pdb.track_count == 0 and pdb.playlist_count() == 0


# ------------------------------------------------------------------ préparation
def test_prepare_writes_only_the_four_files_and_keeps_personal_files(tmp_path):
    (tmp_path / "Photos").mkdir()
    (tmp_path / "Photos" / "a.jpg").write_bytes(b"jpeg" * 100)
    (tmp_path / "set.mp3").write_bytes(b"mp3" * 500)
    before = _tree(tmp_path)
    drive = prepare_drive(tmp_path, "FAT32")
    after = _tree(tmp_path)
    assert {k: v for k, v in after.items() if not k.startswith("PIONEER/")} == before
    assert {k for k in after if k.startswith("PIONEER/")} == set(GABARIT)
    for name, (_size, digest) in GABARIT.items():
        assert after[name].startswith(digest)
    assert not (tmp_path / blank_key.TMP_NAME).exists()
    assert not (tmp_path / "PIONEER" / "djprofile.nxs").exists()
    assert drive.db_path == tmp_path / DB_RELATIVE_PATH
    assert drive_from_letter(str(tmp_path)).db_path.is_file()


@pytest.mark.parametrize("name", ["PIONEER", "pioneer", "Pioneer"])
def test_refused_when_a_pioneer_folder_exists_whatever_it_holds(tmp_path, name):
    (tmp_path / name).mkdir()
    (tmp_path / name / "note.txt").write_text("x")
    before = _tree(tmp_path)
    with pytest.raises(PrepareError) as exc:
        prepare_drive(tmp_path, "FAT32")
    assert exc.value.reason == "pioneer_exists"
    assert _tree(tmp_path) == before and not (tmp_path / blank_key.TMP_NAME).exists()


def test_refused_on_old_rekordbox_drive(tmp_path):
    rb = tmp_path / "PIONEER" / "rekordbox"
    rb.mkdir(parents=True)
    (rb / "export.pdb").write_bytes(b"\0" * 4096)
    before = _tree(tmp_path)
    assert refusal(tmp_path, "FAT32").reason == "pioneer_exists"
    with pytest.raises(PrepareError):
        prepare_drive(tmp_path, "FAT32")
    assert _tree(tmp_path) == before


def test_refused_on_system_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(blank_key, "_is_system_disk", lambda root: True)
    with pytest.raises(PrepareError) as exc:
        prepare_drive(tmp_path, "FAT32")
    assert exc.value.reason == "system_disk" and list(tmp_path.iterdir()) == []


def test_system_disk_is_detected_for_real(monkeypatch):
    monkeypatch.undo()
    assert blank_key._is_system_disk(Path.home())


@pytest.mark.parametrize("fs,ok", [("FAT32", True), ("exFAT", True), ("HFS+", True), ("", True),
                                   ("NTFS", False), ("APFS", False), ("ext4", False)])
def test_refused_when_players_cannot_read_the_filesystem(tmp_path, fs, ok):
    if ok:
        prepare_drive(tmp_path, fs)
        assert (tmp_path / DB_RELATIVE_PATH).is_file()
    else:
        with pytest.raises(PrepareError) as exc:
            prepare_drive(tmp_path, fs)
        assert exc.value.reason == "filesystem" and exc.value.detail == fs
        assert list(tmp_path.iterdir()) == []


def test_interrupted_preparation_leaves_no_half_made_drive(tmp_path):
    (tmp_path / "keep.txt").write_text("mine")

    def boom(_tmp: Path) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        prepare_drive(tmp_path, "FAT32", before_rename=boom)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.txt"]


def test_write_error_leaves_the_drive_as_before(tmp_path, monkeypatch):
    real = blank_key._write
    calls = []

    def flaky(path: Path, data: bytes) -> None:
        calls.append(path)
        if len(calls) == 3:
            raise OSError("disk unplugged")
        real(path, data)

    monkeypatch.setattr(blank_key, "_write", flaky)
    with pytest.raises(PrepareError) as exc:
        prepare_drive(tmp_path, "FAT32")
    assert exc.value.reason == "write" and list(tmp_path.iterdir()) == []


def test_damaged_copy_is_caught_by_the_check(tmp_path, monkeypatch):
    real = blank_key._write

    def corrupt(path: Path, data: bytes) -> None:
        real(path, data[:-1] + b"\x01" if path.name == "DEVSETTING.DAT" else data)

    monkeypatch.setattr(blank_key, "_write", corrupt)
    with pytest.raises(PrepareError) as exc:
        prepare_drive(tmp_path, "FAT32")
    assert exc.value.reason == "check" and list(tmp_path.iterdir()) == []


def test_leftover_of_a_killed_preparation_is_replaced(tmp_path):
    tmp = tmp_path / blank_key.TMP_NAME / "rekordbox"
    tmp.mkdir(parents=True)
    (tmp / "export.pdb").write_bytes(b"half")
    prepare_drive(tmp_path, "FAT32")
    assert not (tmp_path / blank_key.TMP_NAME).exists() and (tmp_path / DB_RELATIVE_PATH).is_file()


def test_foreign_folder_with_the_temporary_name_is_never_removed(tmp_path):
    tmp = tmp_path / blank_key.TMP_NAME
    tmp.mkdir()
    (tmp / "mine.txt").write_text("not ours")
    with pytest.raises(PrepareError) as exc:
        prepare_drive(tmp_path, "FAT32")
    assert exc.value.reason == "leftover"
    assert (tmp / "mine.txt").read_text() == "not ours" and not (tmp_path / "PIONEER").exists()


# ------------------------------------------------------------------ la clé préparée se remplit
def test_prepared_drive_opens_and_fills_like_any_drive(tmp_path):
    from djsync.db import RekordboxUsbLibrary
    from djsync.db.pdb import PdbDatabase

    key = tmp_path / "key"
    key.mkdir()
    drive = prepare_drive(key, "FAT32")
    lib = RekordboxUsbLibrary(drive, analyze=True).connect()
    try:
        assert lib.track_count() == 0 and lib.list_playlists() == []
        folder = lib.create_folder("Dossier é")
        inside = lib.create_playlist("Dedans", parent_id=folder.playlist_id)
        top = lib.create_playlist("Racine")
        track = lib.add_track(make_wav(lib.default_download_dir("Artiste"), "Mon son", 8.0, bpm=124), "Mon son",
                              "Artiste")
        lib.add_to_playlist(inside.playlist_id, [track.content_id])
        lib.add_to_playlist(top.playlist_id, [track.content_id])
        assert lib.pdb_status().state == "ok"
        assert lib.get_track(track.content_id).is_analysed
    finally:
        lib.close()
    rb = key / "PIONEER" / "rekordbox"
    pdb = PdbDatabase((rb / "export.pdb").read_bytes())
    assert pdb.track_count == 1 and pdb.playlist_count() == 3
    assert (key / "Contents").is_dir() and (key / "PIONEER" / "USBANLZ").is_dir()
    assert hashlib.sha256((rb / "exportExt.pdb").read_bytes()).hexdigest().startswith(
        GABARIT["PIONEER/rekordbox/exportExt.pdb"][1])                     # jamais modifié
    again = RekordboxUsbLibrary(drive_from_letter(str(key))).connect()
    try:
        assert again.track_count() == 1
        assert [p.name for p in again.list_playlists() if not p.is_folder] and again.pdb_status().state == "ok"
    finally:
        again.close()


# ------------------------------------------------------------------ contrôleur et Accueil
@pytest.fixture
def app(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    import djsync.ui.controller as controller
    from djsync.db import usb
    from djsync.settings import Settings

    from .qt_util import close_window, make_window

    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    blank, legacy, ntfs = tmp_path / "blank", tmp_path / "legacy", tmp_path / "ntfs"
    blank.mkdir(), ntfs.mkdir()
    (legacy / "PIONEER").mkdir(parents=True)

    def unprepared():
        out = []
        for root, fs in ((blank, "FAT32"), (legacy, "FAT32"), (ntfs, "NTFS")):
            if not (root / DB_RELATIVE_PATH).is_file():
                kind = "legacy" if (root / "PIONEER").is_dir() else "blank"
                out.append(UnpreparedDrive(usb._make_drive(root), kind, fs))
        return out

    def drives():
        return [usb._make_drive(r) for r in (blank, legacy, ntfs) if (r / DB_RELATIVE_PATH).is_file()]

    monkeypatch.setattr(controller, "find_usb_drives", drives)
    monkeypatch.setattr(controller, "find_unprepared_drives", unprepared)
    monkeypatch.setattr(usb, "find_unprepared_drives", unprepared)
    monkeypatch.setattr(controller.AppController, "find_local", lambda self: None)
    window = make_window(Settings(), monkeypatch)
    window.roots = (blank, legacy, ntfs)
    yield window
    close_window(window)


def test_controller_only_prepares_a_drive_listed_as_blank(app, tmp_path):
    from .qt_util import pump

    blank, legacy, ntfs = app.roots
    for root, reason in ((legacy, "not_listed"), (tmp_path / "elsewhere", "not_listed"), (ntfs, "filesystem")):
        errors = []
        app.ctrl.prepare_blank_drive(root, err=errors.append)
        assert pump(app, 5, lambda: errors)
        assert errors[0].reason == reason
    assert list((legacy / "PIONEER").iterdir()) == [] and list(ntfs.iterdir()) == []
    assert not (tmp_path / "elsewhere").exists()
    app.ctrl.prepare_blank_drive(blank)
    assert pump(app, 10, lambda: app.ctrl.has_library), app.errors            # la clé s'ouvre, vide
    assert str(app.ctrl.drive.root) == str(blank) and app.ctrl.library.track_count() == 0
    assert not app.errors


def test_home_card_offers_the_button_only_where_it_can_work(app):
    from PySide6.QtWidgets import QPushButton

    from djsync.i18n import t
    from djsync.ui.dialogs import ConfirmDialog

    from .qt_util import find, pump

    home = app.views["home"]
    app.show_view("home")
    assert pump(app, 5, lambda: home.cards_lay.count() == 3)
    texts = [[b.text() for b in home.cards_lay.itemAt(i).widget().findChildren(QPushButton)]
             for i in range(home.cards_lay.count())]
    assert sum(t("prepare.button") in row for row in texts) == 1               # ni la vieille clé, ni la NTFS
    button = next(b for b in home.findChildren(QPushButton) if b.objectName() == "prepare_drive")
    button.click()
    assert pump(app, 3, lambda: find(app, ConfirmDialog) is not None)
    dlg = find(app, ConfirmDialog)
    assert not (app.roots[0] / "PIONEER").exists()                            # rien avant la confirmation
    dlg._ok()
    assert pump(app, 10, lambda: app.ctrl.has_library), app.errors
    assert (app.roots[0] / DB_RELATIVE_PATH).is_file() and not app.errors


def test_prepare_tile_leads_to_the_blank_drive(app):
    from djsync.ui.dialogs import ConfirmDialog

    from .qt_util import find, pump

    home = app.views["home"]
    assert pump(app, 5, lambda: len(app.ctrl.unprepared) == 3)
    home.act_prepare()
    assert pump(app, 3, lambda: find(app, ConfirmDialog) is not None)
    find(app, ConfirmDialog).close()
