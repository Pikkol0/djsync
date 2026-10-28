"""1.3.1 : désinstaller depuis l'app, aussi depuis l'ordinateur (C88) ; Paramètres rangés par usage,
section Avancé, cartes repliables et « Tout vérifier » (C89)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from .test_v130rc3 import _demo_app  # noqa: E402


# ------------------------------------------------------------------ C88
def test_computer_uninstall_targets_keep_music_and_backups(tmp_path):
    from djsync import uninstall

    app = tmp_path / "app"
    (app / ".djsync" / "app").mkdir(parents=True)
    data = tmp_path / "appdata" / "DJSync"
    for sub in ("cache/grid", "engine", "Backups/rekordbox"):
        (data / sub).mkdir(parents=True)
    (data / "settings.json").write_text("{}")
    (data / "Backups" / "rekordbox" / "master.db.bak").write_text("x")
    keep = uninstall.computer_targets(data, keep_backups=True, app_dir=app, frozen=False)
    assert app / ".djsync" in keep
    assert data / "settings.json" in keep and data / "cache" in keep and data / "engine" in keep
    assert data not in keep and data / "Backups" not in keep              # sauvegardes gardées
    drop = uninstall.computer_targets(data, keep_backups=False, app_dir=app, frozen=False)
    assert data in drop
    # un dossier qui contient de la musique ou une bibliothèque n'est jamais supprimé
    (data / "PIONEER").mkdir()
    assert data not in uninstall.computer_targets(data, keep_backups=False, app_dir=app, frozen=False)
    # réglages dans .djsync (version portable) : le dossier part avec .djsync
    inside = app / ".djsync" / "data"
    inside.mkdir()
    assert uninstall.computer_targets(inside, keep_backups=False, app_dir=app, frozen=False) == [app / ".djsync"]


def test_uninstall_mode_and_backups_put_aside(tmp_path, monkeypatch):
    from djsync import uninstall

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert uninstall.mode() == "source"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(uninstall.portable, "own_drive_root", lambda *a: None)
    assert uninstall.mode() == "computer"
    monkeypatch.setattr(uninstall.portable, "own_drive_root", lambda *a: tmp_path)
    assert uninstall.mode() == "drive"
    data = tmp_path / "data"
    (data / "Backups").mkdir(parents=True)
    (data / "Backups" / "b1").write_text("x")
    uninstall.keep_computer_backups(data, tmp_path / "home" / "DJSync_Backups")
    assert (tmp_path / "home" / "DJSync_Backups" / "Ordinateur" / "b1").exists()


def test_uninstall_button_always_in_djsync_section(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.show_view("settings")
        view = app.views["settings"]
        view.show_section("djsync")
        pump(app, 0.2)
        assert view.app_uninstall_btn.isVisibleTo(view)
        assert not view.app_uninstall_btn.isEnabled()                       # tests = code source
        # depuis l'ordinateur : fenêtre avec la liste, puis désinstallation (simulée)
        from djsync.ui.backups_dialog import UninstallDialog

        calls = []
        monkeypatch.setattr(app.ctrl, "computer_uninstall_plan",
                            lambda keep_backups=True: ([Path("/x/DJSync.exe"), Path("/x/.djsync")], True))
        monkeypatch.setattr(app.ctrl, "uninstall_computer", lambda delete: calls.append(delete))
        dlg = UninstallDialog(view, app.ctrl, mode="computer")
        assert "DJSync.exe" in dlg.paths.text() and dlg.backups_var is not None
        dlg._go()
        assert calls == [False]
        assert not app.errors
    finally:
        close_window(app)


# ------------------------------------------------------------------ C89
def test_advanced_section_and_folded_cards(tmp_path, monkeypatch):
    from djsync.ui.views.settings_view import SECTIONS

    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.resize(1400, 900)
        app.show_view("settings")
        view = app.views["settings"]
        assert [k for k, _i in SECTIONS][-1] == "advanced"
        view.show_section("general")
        pump(app, 0.2)
        assert not view.latency_box.isVisibleTo(view) and not view.ffmpeg.isVisibleTo(view)
        view.show_section("download")
        assert view.format_menu.isVisibleTo(view) and not view.ffmpeg_card.isVisibleTo(view)
        view.show_section("advanced")
        assert view.ffmpeg_card.isVisibleTo(view) and view.pdb_var.isVisibleTo(view)
        assert view.forced.isVisibleTo(view) and view.latency_box.isVisibleTo(view)
        # FFmpeg trouvé : carte repliée, une ligne d'état ; un clic la déplie
        folded = view._folds[view.ffmpeg_card]
        found, _txt = app.ctrl.ffmpeg_status(view.ffmpeg.text().strip())
        if found:
            assert not folded[3] and not view.ffmpeg.isVisibleTo(view) and folded[2].text()
        view.set_folded(view.ffmpeg_card, True)
        assert view.ffmpeg.isVisibleTo(view)
        view.set_folded(view.ffmpeg_card, False)
        # la recherche trouve aussi le contenu replié
        view.search.setText("ffmpeg")
        assert view.ffmpeg.isVisibleTo(view)
        view.search.setText("")
        assert not view.ffmpeg.isVisibleTo(view)
        assert not app.errors
    finally:
        close_window(app)


def test_check_everything(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.show_view("settings")
        view = app.views["settings"]
        ctrl = app.ctrl
        calls = []

        class Rel:
            version = "2099.1.1"

            def newer_than(self, _cur):
                return True

        class St:
            state = "stale"
            pdb_tracks = missing_tracks = missing_playlists = 1
            detail = ""

        monkeypatch.setattr(ctrl, "app_update_check",
                            lambda manual=False, force=False, result=None: (calls.append("app"), result(None, None)))
        monkeypatch.setattr(ctrl, "engine_check", lambda done: (calls.append("engine"), done(Rel(), "2025.1.1", None)))
        monkeypatch.setattr(ctrl, "engine_install", lambda *a: calls.append("INSTALL"))
        monkeypatch.setattr(ctrl, "pdb_status", lambda ok: ok(St()))
        monkeypatch.setattr(ctrl, "pdb_sync_now", lambda ok=None, failed=None: (calls.append("pdb"), ok and ok(None)))
        monkeypatch.setattr(view.space, "compute", lambda force=False, done=None: done and done(None))
        view.check_all()
        assert pump(app, 5, lambda: "busy" not in view.check_states().values())
        st = view.check_states()
        assert st["app"] == "ok" and st["engine"] == "update"
        assert set(st) == set(view.CHECKS)
        if ctrl.library is not None and not ctrl.is_local:                 # export.pdb pas à jour : rattrapé
            assert st["pdb"] in ("ok", "warn") and calls.count("pdb") == 1
        else:
            assert st["pdb"] == "skip" and "pdb" not in calls
        assert "INSTALL" not in calls                                      # rien installé sans clic
        # clé ouverte avec export.pdb pas à jour : rattrapé une fois, ligne « mis à jour »
        class Lib:
            pdb_state = "ok"

            def list_tracks(self):
                return []

        monkeypatch.setattr(ctrl, "library", Lib())
        monkeypatch.setattr(ctrl, "diag_quick_counts", lambda: ctrl._emit("diag_counts"))
        calls.clear()
        view.check_all()
        assert pump(app, 5, lambda: "busy" not in view.check_states().values())
        assert view.check_states()["pdb"] == "ok" and calls.count("pdb") == 1
        assert view.check_states()["diag"] == "ok"
        assert view.engine_install_btn.isVisibleTo(view) or not view.engine_card.isVisibleTo(view)
        assert not app.errors
    finally:
        close_window(app)


# ------------------------------------------------------------------ C90
def test_check_list_closes_and_folds_away_when_all_is_well(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.show_view("settings")
        view = app.views["settings"]
        ctrl = app.ctrl
        monkeypatch.setattr(ctrl, "app_update_check", lambda manual=False, force=False, result=None: result(None, None))
        monkeypatch.setattr(ctrl, "engine_check", lambda done: done(None, "2025.1.1", None))
        monkeypatch.setattr(view.space, "compute", lambda force=False, done=None: done and done(None))
        view.check_all()
        assert view.check_panel.isVisibleTo(view)
        assert {"local", "space"} <= set(view.check_states())             # bibliothèque du PC et espace
        view.check_close.click()                                          # ✕
        assert not view.check_panel.isVisibleTo(view)
        view._check_timer.setInterval(200)
        view.check_all()
        assert pump(app, 5, lambda: "busy" not in view.check_states().values())
        if all(x in ("ok", "skip") for x in view.check_states().values()):
            assert pump(app, 3, lambda: not view.check_panel.isVisibleTo(view))      # repliée seule
        # un ↑ ou un ⚠ : la liste reste
        view._check_row("engine", "update", "x", go="advanced")
        view.check_panel.show()
        pump(app, 0.5)
        assert view.check_panel.isVisibleTo(view)
        assert not app.errors
    finally:
        close_window(app)
