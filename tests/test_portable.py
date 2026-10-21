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


def test_single_visible_file_layout(tmp_path):
    """Exe construit en mode dossier : tout vit dans `.djsync` (caché), réglages compris."""
    app = tmp_path / "anywhere"
    contents = app / portable.CONTENTS
    (contents / "tools").mkdir(parents=True)
    assert not portable.is_portable(app)
    (contents / "portable.flag").write_text("")
    assert portable.is_portable(app)
    assert portable.portable_data_dir(app) == contents / "data"
    assert portable.tool_dirs(app) == [contents / "tools"]
    (app / "DJSync_Data").mkdir()                          # ancienne version : ses réglages sont gardés
    assert portable.portable_data_dir(app) == app / "DJSync_Data"
    assert portable.hide(app / "nothing") is False         # sans effet hors Windows / fichier absent


def test_release_notes_match_version_and_history(capsys):
    """Le tag publié doit correspondre à djsync.__version__ ; les notes viennent du README."""
    import importlib.util
    from pathlib import Path

    import djsync

    spec = importlib.util.spec_from_file_location(
        "release_notes", Path(__file__).resolve().parent.parent / "packaging" / "release_notes.py")
    notes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notes)
    v = djsync.__version__
    assert notes.main(f"v{v}") == 0
    out = capsys.readouterr().out
    assert f"**Release {v}**" in out and f"DJSync-{v}-windows.zip" in out and notes.history_row(v)
    assert notes.main(f"v{v}-rc.1") == 0 and "Pre-release" in capsys.readouterr().out
    assert notes.main("v0.0.1") == 1                          # tag ≠ version : publication refusée


def test_release_notes_script_works_with_a_windows_console_encoding():
    """Sous Windows, une sortie redirigée est en cp1252 : le script doit quand même écrire ses notes."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    import djsync

    script = Path(__file__).resolve().parent.parent / "packaging" / "release_notes.py"
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    proc = subprocess.run([sys.executable, str(script), f"v{djsync.__version__}-rc.1"], capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    assert "▸" in proc.stdout.decode("utf-8")
