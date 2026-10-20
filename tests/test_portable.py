"""Mode portable : DJSync.exe sur la clé."""
import os
from pathlib import Path

from djsync import portable
from djsync.settings import Settings, settings_dir


def make_key(root: Path) -> Path:
    (root / "PIONEER" / "rekordbox").mkdir(parents=True)
    (root / "PIONEER" / "rekordbox" / "exportLibrary.db").write_bytes(b"x")
    app = root / "DJSync"
    app.mkdir()
    return app


def test_exe_on_a_key_is_portable_and_finds_its_drive(tmp_path):
    app = make_key(tmp_path)
    assert portable.is_portable(app)
    assert portable.own_drive_root(app) == tmp_path
    assert portable.portable_data_dir(app) == app / "DJSync_Data"


def test_exe_elsewhere_is_not_portable_without_flag(tmp_path):
    app = tmp_path / "apps" / "DJSync"
    app.mkdir(parents=True)
    assert not portable.is_portable(app) and portable.own_drive_root(app) is None
    (app / "portable.flag").write_text("")
    assert portable.is_portable(app) and portable.own_drive_root(app) is None


def test_tools_are_added_to_path(tmp_path):
    app = make_key(tmp_path)
    (app / "tools").mkdir()
    old = os.environ["PATH"]
    try:
        assert portable.prepare_environment(app) == [str(app / "tools")]
        assert os.environ["PATH"].startswith(str(app / "tools"))
    finally:
        os.environ["PATH"] = old


def test_settings_defaults_and_normalisation(tmp_path):
    s = Settings()
    assert s.pdb_sync == "auto" and s.pdb_allow_growth is False
    s.pdb_sync = "bizarre"
    assert s.normalize().pdb_sync == "auto"
    path = tmp_path / "s.json"
    s.pdb_allow_growth = True
    s.save(path)
    assert Settings.load(path).pdb_allow_growth is True


def test_djsync_home_override_wins(tmp_path):
    os.environ["DJSYNC_HOME"] = str(tmp_path / "h")
    try:
        assert settings_dir() == tmp_path / "h"
    finally:
        del os.environ["DJSYNC_HOME"]
