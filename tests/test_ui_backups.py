"""V1.2.0 : fenêtre « Sauvegardes de la clé » (créer, restaurer) et désinstallation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from djsync import uninstall  # noqa: E402
from djsync.db import backups as B  # noqa: E402

from .qt_util import find, pump  # noqa: E402
from .test_ui_smoke import app  # noqa: E402,F401  (fixture)
from .test_usb_library import usb  # noqa: E402,F401  (fixture)


def test_backups_dialog_create_and_restore(app, usb):
    from djsync.ui.backups_dialog import BackupsDialog
    from djsync.ui.dialogs import ConfirmDialog, TextInputDialog

    assert pump(app, 5, lambda: app.ctrl.has_library)
    app.ctrl.library.create_playlist("Ajoutée par DJSync")
    view = app.views["settings"]
    assert view.points_btn.isEnabled()
    view._open_backups()
    dlg = find(app, BackupsDialog)
    assert pump(app, 5, lambda: len(dlg.points) == 1 and dlg.points[0].kind == "origin")

    dlg._create()
    entry = find(app, TextInputDialog)
    entry._entry.setText("Avant la soirée")
    entry._ok()
    assert pump(app, 5, lambda: [p.kind for p in dlg.points] == ["manual", "origin"]), dlg.points
    assert "Avant la soirée" in dlg.list.item(0).text()

    dlg.list.setCurrentRow(1)
    assert not dlg.delete_btn.isEnabled()                  # l'origine ne se supprime pas
    dlg._restore()
    confirm = [w for w in app.findChildren(ConfirmDialog) if w.isVisible()][-1]
    confirm._on_confirm()
    assert pump(app, 10, lambda: app.ctrl.has_library and app.ctrl.library is not None
                and "Ajoutée par DJSync" not in [p.name for p in app.ctrl.library.list_playlists()]), app.errors
    assert any(p.kind == "restore" for p in B.list_points(usb / "DJSync_Backups"))


def test_uninstall_targets_only_djsync_files(tmp_path, monkeypatch):
    (tmp_path / "PIONEER").mkdir()
    (tmp_path / "Contents").mkdir()
    (tmp_path / ".djsync" / "data").mkdir(parents=True)
    exe = tmp_path / "DJSync.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv("DJSYNC_LAUNCHER", str(exe))
    monkeypatch.setattr(sys, "executable", str(tmp_path / ".djsync" / "app" / "DJSync.exe"))
    found = uninstall.targets(tmp_path, frozen=True)
    assert set(found) == {exe, tmp_path / ".djsync"}
    script = uninstall.schedule_removal(found, pid=999999, run=False)
    text = script.read_text("utf-8")
    assert ".djsync" in text and "DJSync.exe" in text and "PIONEER" not in text and "Contents" not in text
    script.unlink()


def test_uninstall_never_removes_a_folder_holding_the_library(tmp_path, monkeypatch):
    monkeypatch.delenv("DJSYNC_LAUNCHER", raising=False)
    (tmp_path / ".djsync" / "PIONEER").mkdir(parents=True)          # cas absurde : on refuse
    assert uninstall.targets(tmp_path, frozen=False) == []


def test_computer_backups_are_kept_on_the_drive(tmp_path):
    data = tmp_path / ".djsync" / "data"
    (data / "Backups" / "rekordbox" / "master-1").mkdir(parents=True)
    uninstall.keep_computer_backups(data, tmp_path / "DJSync_Backups")
    assert (tmp_path / "DJSync_Backups" / "Ordinateur" / "rekordbox" / "master-1").is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="script POSIX")
def test_removal_script_runs_after_exit(tmp_path):
    import subprocess

    victim = tmp_path / ".djsync"
    (victim / "data").mkdir(parents=True)
    keep = tmp_path / "Contents"
    keep.mkdir()
    import threading

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"])
    threading.Thread(target=proc.wait, daemon=True).start()     # « DJSync » se ferme (et n'est pas zombie)
    script = uninstall.schedule_removal([victim], pid=proc.pid, run=False)
    subprocess.run(["/bin/sh", str(script)], timeout=30, check=True)
    assert not victim.exists() and keep.exists() and not script.exists()
