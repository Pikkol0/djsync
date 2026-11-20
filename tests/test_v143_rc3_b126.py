"""1.4.3-rc.3 (B126) (gel à l'ouverture et après une suppression : doublons en Python pur dans l'exe)."""
from __future__ import annotations

import os
import subprocess
import sys

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: F401  (fixtures)


# ------------------------------------------------------------------ B126 A : partie compilée de rapidfuzz
def test_b126_fuzzy_backend_detects_pure_python():
    from djsync.core.duplicates import fuzzy_backend

    assert fuzzy_backend() == "compiled"
    env = dict(os.environ, RAPIDFUZZ_IMPLEMENTATION="python")
    out = subprocess.run([sys.executable, "-c", "from djsync.core.duplicates import fuzzy_backend;"
                          "print(fuzzy_backend())"], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "python"


def test_b126_spec_bundles_rapidfuzz():
    from pathlib import Path

    spec = (Path(__file__).resolve().parent.parent / "packaging" / "DJSync.spec").read_text(encoding="utf-8")
    assert '"rapidfuzz")' in spec


# ------------------------------------------------------------------ B126 D : colonne Doublon masquée
def test_b126_no_duplicate_search_while_dup_column_hidden(demo, monkeypatch):
    import djsync.core.duplicates as D

    calls = []
    real = D.find_duplicate_groups
    monkeypatch.setattr(D, "find_duplicate_groups", lambda *a, **k: calls.append(1) or real(*a, **k))
    view = demo.views["library"]
    demo.show_view("library")
    view.table.set_column_visible("dup", False)
    calls.clear()
    view.reload(full=True)
    assert pump(demo, 10, lambda: getattr(view, "_extras", None) is not None and view._extras_dups is False)
    pump(demo, 0.3)
    assert not calls                                     # rien calculé tant que la colonne est masquée
    view.table.set_column_visible("dup", True)           # affichée : doublons calculés tout de suite
    assert pump(demo, 10, lambda: bool(calls) and view._extras_dups is True)
    assert pump(demo, 10, lambda: any(r.values.get("dup") for r in view.table.all_rows()))
    assert not demo.errors
