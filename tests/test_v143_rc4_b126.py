"""1.4.3-rc.4 (B126) : rapidfuzz en Python pur dans l'exe Windows (DLL msvcp140-… de rapidfuzz.libs absente,
gardée seulement dans numpy.libs), mesuré sur la tour le 25/11 : doublons recalculés en ~19 s à l'ouverture et
après chaque suppression."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _py(code: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=dict(os.environ, **env),
                          capture_output=True, text=True, timeout=120)


# ------------------------------------------------------------------ journal : quelle partie, et pourquoi
def test_b126_rc4_describe_compiled_and_forced_python():
    from djsync.core.fuzzy import describe

    assert describe() == "compiled"
    out = _py("from djsync.core.fuzzy import describe; print(describe())", RAPIDFUZZ_IMPLEMENTATION="python")
    assert out.stdout.strip() == "python", out.stderr


def test_b126_rc4_describe_gives_the_import_error():
    """Partie compilée introuvable (comme dans l'exe) : le journal dit laquelle et pourquoi."""
    code = (
        "import sys, importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.startswith('rapidfuzz') and '_cpp' in name:\n"
        "            raise ImportError('DLL load failed while importing ' + name.rsplit('.', 1)[-1])\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "from djsync.core.fuzzy import describe; print(describe())\n")
    out = _py(code)
    line = out.stdout.strip()
    assert line.startswith("python (rapidfuzz.fuzz_cpp: ImportError: DLL load failed"), (line, out.stderr)


# ------------------------------------------------------------------ B : dossiers .libs ajoutés au démarrage
def test_b126_rc4_wheel_dll_dirs_added(tmp_path, monkeypatch):
    from djsync import portable

    (tmp_path / "rapidfuzz.libs").mkdir()
    (tmp_path / "numpy.libs").mkdir()
    (tmp_path / "other.libs").write_text("not a folder")
    (tmp_path / "PySide6").mkdir()
    added = []
    monkeypatch.setattr(portable.os, "add_dll_directory", lambda p: added.append(Path(p).name) or object(),
                        raising=False)
    assert portable.add_wheel_dll_dirs(tmp_path) == ["numpy.libs", "rapidfuzz.libs"]
    assert added == ["numpy.libs", "rapidfuzz.libs"]
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert portable.add_wheel_dll_dirs() == []             # depuis les sources : rien à faire


# ------------------------------------------------------------------ A : autotest dans l'ordre de l'app
def test_b126_rc4_selftest_checks_rapidfuzz_before_numpy():
    ok = _py("from djsync.selftest import _rapidfuzz_first; print(_rapidfuzz_first())")
    assert "'backend': 'compiled'" in ok.stdout, ok.stderr
    late = _py("import numpy\nfrom djsync.selftest import _rapidfuzz_first\n"
               "try:\n    _rapidfuzz_first()\nexcept RuntimeError as e:\n    print('ERR', e)\n")
    assert "ERR checked too late: numpy" in late.stdout, late.stderr
    py = _py("from djsync.selftest import _rapidfuzz_first\n"
             "try:\n    _rapidfuzz_first()\nexcept RuntimeError as e:\n    print('ERR', e)\n",
             RAPIDFUZZ_IMPLEMENTATION="python")
    assert "ERR rapidfuzz runs its pure-Python fallback: python" in py.stdout, py.stderr


def test_b126_rc4_selftest_report_has_the_first_check(tmp_path):
    report = tmp_path / "st.json"
    out = subprocess.run([sys.executable, "app.py"], cwd=ROOT, capture_output=True, text=True, timeout=300,
                         env=dict(os.environ, DJSYNC_SELFTEST=str(report), QT_QPA_PLATFORM="offscreen"))
    import json

    checks = json.loads(report.read_text(encoding="utf-8"))["checks"]
    assert checks["rapidfuzz_compiled"] == {"ok": True, "value": {"backend": "compiled"}}, out.stderr
    assert checks["rapidfuzz_after_imports"]["ok"]


def test_b126_rc4_spec_copies_wheel_libs():
    spec = (ROOT / "packaging" / "DJSync.spec").read_text(encoding="utf-8")
    assert 'for pkg in ("rapidfuzz", "numpy"):' in spec and 'pkg + ".libs"' in spec


# ------------------------------------------------------------------ calcul lourd au journal
def test_b126_rc4_slow_duplicate_search_is_logged(monkeypatch, caplog):
    from djsync.core import duplicates as D

    class T:
        def __init__(self, i, title):
            self.content_id, self.path, self.title, self.artist, self.duration_seconds = i, f"/{i}", title, "A", 200

    items = [T(i, f"Song number {i // 2}") for i in range(20)]
    D._GROUPS_CACHE.clear()
    monkeypatch.setattr(D, "SLOW_GROUPS_S", 0.0)
    with caplog.at_level(logging.INFO, logger="djsync.core.duplicates"):
        D.find_duplicate_groups(items)
        D.find_duplicate_groups(items)                     # même liste : repris du cache, pas de 2e ligne
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Duplicate groups:")]
    assert len(lines) == 1 and lines[0].startswith("Duplicate groups: 20 tracks, ") \
        and lines[0].endswith("s, rapidfuzz compiled"), lines
    D._GROUPS_CACHE.clear()
    monkeypatch.setattr(D, "SLOW_GROUPS_S", 60.0)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="djsync.core.duplicates"):
        D.find_duplicate_groups(items)
    assert not [r for r in caplog.records if r.getMessage().startswith("Duplicate groups:")]
