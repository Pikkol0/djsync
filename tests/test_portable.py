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
    assert s.pdb_sync == "auto" and s.pdb_allow_growth is True          # V1.0.0 : agrandissement par défaut
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
    assert f"**Release {v}**" in out and "**DJSync.exe**" in out and notes.history_row(v)
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


def test_hide_sets_hidden_and_system_on_windows(tmp_path, monkeypatch):
    """Windows simulé : caché + système (invisible même avec « Éléments masqués »), une seule fois."""
    import ctypes
    import sys

    folder = tmp_path / ".djsync"
    folder.mkdir()
    attrs = {str(folder): 0x10}                              # FILE_ATTRIBUTE_DIRECTORY
    calls = []

    class Fn:
        def __init__(self, impl):
            self.impl = impl

        def __call__(self, *a):
            return self.impl(*a)

    class K32:
        GetFileAttributesW = Fn(lambda p: attrs.get(p, 0xFFFFFFFF))

        def _set(p, v):
            calls.append(v)
            attrs[p] = v
            return 1
        SetFileAttributesW = Fn(_set)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: K32, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    assert portable.hide(folder) is True and attrs[str(folder)] == 0x10 | 0x2 | 0x4
    assert portable.hide(folder) is True and len(calls) == 1          # déjà caché : rien à refaire
    attrs.clear()
    assert portable.hide(folder) is False                             # attributs illisibles : signalé, sans planter


def test_selftest_report(tmp_path):
    """Autotest de l'exe (CI) : rapport JSON, yt-dlp et ses extracteurs YouTube / SoundCloud chargés."""
    import json

    from djsync.selftest import run

    target = tmp_path / "selftest.json"
    code = run(str(target))
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["checks"]["yt_dlp"]["ok"] and report["checks"]["yt_dlp"]["value"]["extractors"] > 100
    assert report["checks"]["miniaudio"]["ok"] and report["checks"]["sqlcipher3"]["ok"]
    assert code == (0 if report["ok"] else 1)          # FFmpeg absent du PATH (CI) : signalé, sans planter


def test_single_file_launcher_layout(tmp_path, monkeypatch):
    """V1.0.0 : DJSync.exe (lanceur) extrait l'application dans .djsync/app et transmet son dossier."""
    usb = tmp_path / "usb"
    (usb / portable.CONTENTS / "app" / "tools").mkdir(parents=True)
    monkeypatch.setenv("DJSYNC_APP_DIR", str(usb))
    assert portable.app_dir() == usb and portable.is_portable(usb)
    assert portable.portable_data_dir() == usb / portable.CONTENTS / "data"
    assert portable.tool_dirs() == [usb / portable.CONTENTS / "app" / "tools"]


def test_pack_single_exe(tmp_path):
    """Le lanceur trouve l'application grâce au bloc de fin : zip complet, version, position."""
    import importlib.util
    import struct
    import zipfile
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "pack", Path(__file__).resolve().parent.parent / "packaging" / "pack_single_exe.py")
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    app = tmp_path / "app"
    (app / "_internal" / "sub").mkdir(parents=True)
    (app / "DJSync.exe").write_bytes(b"MZ inner")
    (app / "_internal" / "sub" / "café.txt").write_text("x", encoding="utf-8")
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 1000)
    out = tmp_path / "usb" / "DJSync.exe"
    assert pack.pack(launcher, app, "1.0.0", out) == 2
    data = out.read_bytes()
    magic, start, size = data[-56:-48], *struct.unpack("<QQ", data[-48:-32])
    assert magic == b"DJSYNCPK" and data[-32:].rstrip(b"\0") == b"1.0.0" and start == 1002
    import io

    names = zipfile.ZipFile(io.BytesIO(data[start:start + size])).namelist()
    assert sorted(names) == ["DJSync.exe", "_internal/sub/café.txt"]
