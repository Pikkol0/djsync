"""V0.5.0 dans l'interface : version portable (bibliothèque du PC proposée, pas ouverte d'office),
réglages (format, normalisation, mémoire cue, moteur de téléchargement), proposition de mise à jour
quand un téléchargement échoue, copie de playlist vers une autre bibliothèque."""
from __future__ import annotations

import shutil

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyrekordbox")

from djsync.settings import Settings  # noqa: E402

from .qt_util import close_window, find, make_window, pump  # noqa: E402
from .test_local_library import DATA  # noqa: E402
from .test_ui_smoke import FakeService  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.db.local_library as L
    import djsync.ui.controller as controller

    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    s = Settings()
    s.local_db_dir, s.local_music_dir = str(db_dir), str(tmp_path / "Music")
    return s, monkeypatch


def test_portable_asks_before_opening_the_computer_library(env):
    from djsync import portable
    from djsync.ui.dialogs import ConfirmDialog

    s, monkeypatch = env
    monkeypatch.setattr(portable, "is_portable", lambda start=None: True)
    app = make_window(s, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: find(app, ConfirmDialog) is not None)
        assert not ctrl.has_library                              # rien d'ouvert sans accord
        dlg = find(app, ConfirmDialog)
        dlg._ok()
        assert pump(app, 6, lambda: ctrl.has_library and ctrl.is_local)
        assert ctrl.host_name() in ctrl.settings.local_hosts      # accord retenu pour ce PC
        assert ctrl.local_allowed()
        assert not app.errors
    finally:
        close_window(app)


def test_settings_engine_offer_and_copy_menu(env, tmp_path):
    from djsync.core import engine
    from djsync.ui.dialogs import ConfirmDialog

    s, monkeypatch = env
    app = make_window(s, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        # ---- réglages V0.5.0
        app.show_view("settings")
        view = app.views["settings"]
        assert "yt-dlp" in view.engine_state.text() and not view.eject_btn.isEnabled()   # PC : rien à éjecter
        view.format_menu.setCurrentText(view._format_labels["mp3"])
        view.normalize_var.setChecked(True)
        view.cue_var.setChecked(False)
        view._save()
        assert (ctrl.settings.audio_format, ctrl.settings.normalize_volume, ctrl.settings.auto_cue) == ("mp3", True, False)
        assert ctrl.library.auto_cue is False
        loaded = Settings.load()
        assert loaded.audio_format == "mp3" and loaded.normalize_volume
        # ---- vérification manuelle : nouvelle version proposée
        monkeypatch.setattr(engine, "latest", lambda fetch=None: engine.Release("2099.1.1", {}))
        view._engine_check()
        assert pump(app, 4, lambda: view.engine_install_btn.isVisible())
        assert "2099.1.1" in view.engine_install_btn.text()
        # ---- échec « YouTube a changé » : une seule proposition par session
        ctrl.engine_failure("ERROR: [youtube] x: Network is unreachable")
        assert not ctrl._engine_checked                              # réseau : pas de proposition
        ctrl.engine_failure("ERROR: [youtube] x: Signature extraction failed")
        assert pump(app, 4, lambda: find(app, ConfirmDialog) is not None)
        dlg = find(app, ConfirmDialog)
        assert any("2099.1.1" in w.text() for w in dlg.findChildren(type(view.engine_state)))
        dlg.close()
        ctrl.engine_failure("ERROR: [youtube] x: Signature extraction failed")
        pump(app, 0.3)
        assert find(app, ConfirmDialog) is None
        # ---- copie de playlist : une entrée par autre bibliothèque
        assert ctrl.copy_targets() == []                             # aucune clé branchée
        assert not app.errors
    finally:
        close_window(app)
