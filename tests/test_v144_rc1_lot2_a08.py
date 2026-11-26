"""1.4.4-rc.1 (lot 2) : A08 option A — bibliothèques gardées ouvertes en arrière-plan (bascule rapide)."""
from __future__ import annotations

import shutil
import threading

import pytest

from .test_v122 import demo, usb  # noqa: F401  (fixtures)


def _a08_second_key(tmp_path):
    from sqlcipher3 import dbapi2 as sqlcipher

    from djsync.db import UsbDrive
    from djsync.db._key import get_default_key
    from tests.demo_fixture import make_demo_usb

    base = tmp_path / "second"
    base.mkdir()
    root = make_demo_usb(base)
    conn = sqlcipher.connect(str(root / "PIONEER" / "rekordbox" / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("CREATE TABLE genre(genre_id integer primary key, name varchar)")
    conn.commit()
    conn.close()
    return UsbDrive(root=root, label="SECOND")


def _a08_roomy(window, monkeypatch, free_mb=8000):
    """Mode léger coupé (la machine de test n'a que 2 cœurs : « auto » le mettrait) et mémoire libre fixée."""
    from djsync.analysis import pool

    window.ctrl.settings.light_mode = "off"
    monkeypatch.setattr(pool, "free_memory_mb", lambda: free_mb)


def _a08_opens(monkeypatch):
    """Espion sur l'ouverture des bases des clés."""
    from djsync.db import RekordboxUsbLibrary

    calls = []
    real = RekordboxUsbLibrary.connect

    def spy(self):
        if self._conn is None:
            calls.append(str(self.db_path))
        return real(self)

    monkeypatch.setattr(RekordboxUsbLibrary, "connect", spy)
    return calls


def _a08_switch(window, drive):
    from tests.qt_util import pump

    ctrl = window.ctrl
    ctrl.connect(drive)
    assert pump(window, 8, lambda: not ctrl._connecting and ctrl.drive is not None
                and str(ctrl.drive.root) == str(drive.root))
    return ctrl.library


def _a08_names(window):
    from tests.qt_util import pump

    view = window.views["library"]
    key = view._drive_key()
    pump(window, 6, lambda: view._loaded_for == key)
    return {p.name for p in view.playlists}


def _a08_has(window, name, present=True):
    """La vue se relit en tâche de fond (lente sous macOS) : attendre le résultat voulu."""
    from tests.qt_util import pump

    view = window.views["library"]
    pump(window, 8, lambda: (name in {p.name for p in view.playlists}) == present)
    return (name in _a08_names(window)) == present


def test_a08_switch_back_without_reopening(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.db import UsbDrive

    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    first_drive, first = ctrl.drive, ctrl.library
    second_drive = _a08_second_key(tmp_path)
    opens = _a08_opens(monkeypatch)

    second = _a08_switch(demo, second_drive)
    assert second is not first and len(opens) == 1                    # B : ouverte une fois
    assert first._conn is not None and ctrl.libraries.holds(first_drive)   # A : gardée, pas fermée
    assert first.kept_background and not getattr(second, "kept_background", False)

    again = _a08_switch(demo, UsbDrive(root=first_drive.root, label="DEMO"))
    assert again is first and len(opens) == 1                           # A reprise : pas de réouverture
    assert ctrl.libraries.holds(second_drive) and second._conn is not None
    assert not first.kept_background

    back = _a08_switch(demo, second_drive)
    assert back is second and len(opens) == 1                           # B reprise aussi
    assert not demo.errors


def test_a08_views_follow_the_active_library(demo, tmp_path, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    first_drive = ctrl.drive
    second_drive = _a08_second_key(tmp_path)
    demo.show_view("library")

    second = _a08_switch(demo, second_drive)
    second.create_playlist("Only on B")
    ctrl._emit("library")
    assert _a08_has(demo, "Only on B")

    _a08_switch(demo, first_drive)
    assert _a08_has(demo, "Only on B", present=False)                  # vues relues depuis A gardée

    _a08_switch(demo, second_drive)
    assert _a08_has(demo, "Only on B")
    assert not demo.errors


def test_a08_only_the_active_library_writes(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.db.errors import LibraryError
    from tests.qt_util import pump

    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    first = ctrl.library
    second = _a08_switch(demo, _a08_second_key(tmp_path))
    assert ctrl.libraries.holds(first.drive)
    with pytest.raises(LibraryError):
        first.create_playlist("Written in the background")              # gardée : aucune écriture
    assert "Written in the background" not in {p.name for p in first.list_playlists()}

    done = []
    ctrl.create_playlist("Written in the active one", ok=lambda *_a: done.append(1))
    assert pump(demo, 6, lambda: done)
    assert "Written in the active one" in {p.name for p in second.list_playlists()}
    assert "Written in the active one" not in {p.name for p in first.list_playlists()}
    assert first.journal_mode and not first._conn.in_transaction       # aucune transaction gardée


def test_a08_unplugged_key_is_closed_at_once(demo, tmp_path, monkeypatch):  # noqa: F811
    from tests.qt_util import pump

    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    first_drive = ctrl.drive
    second_drive = _a08_second_key(tmp_path)
    second = _a08_switch(demo, second_drive)
    _a08_switch(demo, first_drive)
    assert ctrl.libraries.holds(second_drive)

    second.close()                          # Windows refuse de déplacer un fichier ouvert : on simule la clé
    second._conn = None                     # retirée en fermant d'abord, puis le dossier disparaît
    shutil.rmtree(second_drive.root)
    ctrl.libraries.watch(False)
    assert pump(demo, 6, lambda: not ctrl.libraries.holds(second_drive))


def test_a08_unplugged_key_closes_its_connection(demo, tmp_path, monkeypatch):  # noqa: F811
    """Même chose, connexion encore ouverte au moment du retrait (Linux / macOS : dossier supprimable)."""
    import sys

    from tests.qt_util import pump

    if sys.platform == "win32":
        pytest.skip("Windows: an open database cannot be removed")
    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    first_drive = ctrl.drive
    second_drive = _a08_second_key(tmp_path)
    second = _a08_switch(demo, second_drive)
    _a08_switch(demo, first_drive)
    shutil.rmtree(second_drive.root)
    ctrl.libraries.watch(False)
    assert pump(demo, 6, lambda: not ctrl.libraries.holds(second_drive) and second._conn is None)


def test_a08_light_mode_keeps_nothing(demo, tmp_path, monkeypatch):  # noqa: F811
    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    ctrl.settings.light_mode = "on"
    first = ctrl.library
    _a08_switch(demo, _a08_second_key(tmp_path))
    assert len(ctrl.libraries) == 0 and first._conn is None             # fermée comme avant


def test_a08_low_free_memory_keeps_nothing(demo, tmp_path, monkeypatch):  # noqa: F811
    from djsync.ui import kept_libraries as K
    from tests.qt_util import pump

    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch, free_mb=K.MIN_FREE_MB - 100)
    first = ctrl.library
    _a08_switch(demo, _a08_second_key(tmp_path))
    assert len(ctrl.libraries) == 0 and first._conn is None

    # gardée, puis la mémoire libre baisse : refermée à la surveillance suivante
    _a08_roomy(demo, monkeypatch, free_mb=8000)
    second = ctrl.library
    _a08_switch(demo, first.drive)
    assert ctrl.libraries.holds(second.drive)
    _a08_roomy(demo, monkeypatch, free_mb=K.MIN_FREE_MB - 100)
    ctrl.libraries.watch(False)
    assert pump(demo, 6, lambda: len(ctrl.libraries) == 0 and second._conn is None)


def test_a08_at_most_two_kept_and_one_when_memory_is_short(tmp_path, monkeypatch):
    from djsync.analysis import pool
    from djsync.ui import kept_libraries as K

    ctrl = _A08Ctrl()
    kept = K.KeptLibraries(ctrl)
    monkeypatch.setattr(pool, "free_memory_mb", lambda: 8000)
    libs = [_A08Lib(tmp_path, f"k{i}") for i in range(4)]
    for lib in libs:
        assert kept.park(lib.drive, lib)
    assert len(kept) == K.MAX_KEPT == 2
    assert [lib.closed for lib in libs] == [True, True, False, False]   # les plus anciennes refermées
    monkeypatch.setattr(pool, "free_memory_mb", lambda: K.TWO_FREE_MB - 1)
    kept.trim()
    assert len(kept) == 1 and libs[2].closed and not libs[3].closed


def test_a08_computer_library_not_kept_with_rekordbox_open(tmp_path, monkeypatch):
    from djsync.analysis import pool
    from djsync.db import local_library
    from djsync.ui import kept_libraries as K

    monkeypatch.setattr(pool, "free_memory_mb", lambda: 8000)
    ctrl = _A08Ctrl()
    kept = K.KeptLibraries(ctrl)
    monkeypatch.setattr(local_library, "rekordbox_running", lambda: True)
    lib = _A08Local(tmp_path)
    assert not kept.park(lib.drive, lib) and lib.closed

    monkeypatch.setattr(local_library, "rekordbox_running", lambda: False)
    lib = _A08Local(tmp_path)
    assert kept.park(lib.drive, lib) and not lib.closed and lib.rolled_back
    kept.watch(True)                                                     # Rekordbox s'ouvre : refermée
    assert lib.closed and len(kept) == 0


def test_a08_busy_or_downloading_library_is_closed_as_before(tmp_path, monkeypatch):
    from djsync.analysis import pool
    from djsync.ui import kept_libraries as K

    monkeypatch.setattr(pool, "free_memory_mb", lambda: 8000)
    ctrl = _A08Ctrl()
    kept = K.KeptLibraries(ctrl)
    lib = _A08Lib(tmp_path, "busy")
    lib._batch_depth = 1
    assert not kept.park(lib.drive, lib) and lib.closed
    lib = _A08Lib(tmp_path, "dl")
    ctrl.jobs = [type("Job", (), {"library": lib, "is_finished": False})()]
    assert not kept.park(lib.drive, lib) and lib.closed


def test_a08_app_exit_closes_everything(demo, tmp_path, monkeypatch):  # noqa: F811
    from tests.qt_util import close_window

    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    first = ctrl.library
    second = _a08_switch(demo, _a08_second_key(tmp_path))
    assert ctrl.libraries.holds(first.drive)
    close_window(demo)
    assert first._conn is None and second._conn is None and len(ctrl.libraries) == 0


def test_a08_memory_noted_when_the_count_changes(demo, tmp_path, monkeypatch, caplog):  # noqa: F811
    import logging

    ctrl = demo.ctrl
    _a08_roomy(demo, monkeypatch)
    with caplog.at_level(logging.INFO, logger="djsync.memory"):
        _a08_switch(demo, _a08_second_key(tmp_path))
    lines = [r.getMessage() for r in caplog.records if r.name == "djsync.memory"]
    assert any(x.startswith("Open libraries: 2 (1 kept in the background") and "RSS" in x for x in lines)
    assert ctrl.libraries


# ------------------------------------------------------------------ doublures (service seul)
class _A08Ctrl:
    def __init__(self):
        from djsync.settings import Settings

        self.settings = Settings()
        self.settings.light_mode = "off"
        self.jobs = []
        self.library = None
        self.dispatcher = self

    def submit(self, fn, ok=None, err=None, pool="net"):
        try:
            result = fn()
        except BaseException as exc:  # noqa: BLE001
            if err:
                err(exc)
            return
        if ok:
            ok(result)


class _A08Lib:
    is_local = False

    def __init__(self, tmp_path, name):
        from djsync.db import UsbDrive

        root = tmp_path / name
        (root / "PIONEER" / "rekordbox").mkdir(parents=True)
        (root / "PIONEER" / "rekordbox" / "exportLibrary.db").write_bytes(b"")
        self.drive = UsbDrive(root=root, label=name)
        self.db_path = self.drive.db_path
        self._lock = threading.RLock()
        self._conn = type("Conn", (), {"in_transaction": False})()
        self._batch_depth = 0
        self.closed = False

    def close(self):
        self.closed = True
        self._conn = None


class _A08Local:
    is_local = True

    def __init__(self, tmp_path):
        from djsync.db.local_library import LocalRekordbox

        self.drive = LocalRekordbox(db_dir=tmp_path / "rb", music_dir=tmp_path / "music")
        self._lock = threading.RLock()
        self._writing = self._batch_depth = 0
        self.rolled_back = False
        self.closed = False
        outer = self

        class _Session:
            def rollback(self):
                outer.rolled_back = True

        self._db = type("Db", (), {"session": _Session()})()

    @property
    def db_path(self):
        return self.drive.db_dir / "master.db"

    def close(self):
        self.closed = True
        self._db = None
