"""1.4.3-rc.1, lot 4 : tests ciblés de B105, A07 (avec C156), C213 et C214."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

from djsync.db import RekordboxUsbLibrary, drive_from_letter
from djsync.db._key import get_default_key
from djsync.db.errors import DatabaseLockedError, DatabaseOpenError, ShmRepairError
from djsync.db.library import base as base_mod

from .test_usb_library import usb  # noqa: F401 (fixture)


# ------------------------------------------------------------------------------ B105 : -shm illisible
def _raw(path: Path) -> sqlcipher.Connection:
    c = sqlcipher.connect(str(path), isolation_level=None)
    c.execute("PRAGMA key = '%s'" % get_default_key())
    return c


@pytest.fixture
def shm_key(usb, tmp_path_factory):  # noqa: F811
    """Clé copiée pendant qu'une connexion la tient ouverte : -wal non fusionné (playlist « FromWal ») et -shm
    présent, comme une clé retirée d'un autre ordinateur sans être éjectée."""
    db = usb / "PIONEER" / "rekordbox" / "exportLibrary.db"
    c = _raw(db)
    c.execute("PRAGMA wal_autocheckpoint = 0")
    c.execute("INSERT INTO playlist VALUES (9, 0, 'FromWal', NULL, 0, 0)")
    dest = tmp_path_factory.mktemp("shmkey")
    shutil.copytree(usb, dest, dirs_exist_ok=True)
    c.close()
    rb = dest / "PIONEER" / "rekordbox"
    assert (rb / "exportLibrary.db-shm").is_file() and (rb / "exportLibrary.db-wal").stat().st_size > 0
    return dest


class _Fault:
    """Remplace `sqlcipher` dans db/library/base.py : tant que `fault` est vrai, le premier accès d'une connexion
    partagée échoue comme un -shm illisible ; une connexion ouverte en mode exclusif n'utilise pas le -shm et
    marche ; `heal` : le checkpoint exclusif répare (sinon l'erreur reste)."""

    def __init__(self, message: str = "disk I/O error", heal: bool = True) -> None:
        self.fault, self.heal, self.message, self.calls = True, heal, message, []
        self.mod = types.SimpleNamespace(connect=self.connect, Error=sqlcipher.Error,
                                         OperationalError=sqlcipher.OperationalError,
                                         DatabaseError=sqlcipher.DatabaseError)

    def connect(self, *a, **k):
        return _FaultConn(sqlcipher.connect(*a, **k), self)


class _FaultConn:
    def __init__(self, real, owner: _Fault) -> None:
        self._c, self._o, self._excl = real, owner, False

    def execute(self, sql, *args):
        low = sql.lower().replace(" ", "")
        if "locking_mode=exclusive" in low:
            self._excl = True
            self._o.calls.append("exclusive")
        if "sqlite_master" in low and "type='table'" in low:
            self._o.calls.append("open-exclusive" if self._excl else "open-shared")
            if self._o.fault and not self._excl:
                raise sqlcipher.OperationalError(self._o.message)
        out = self._c.execute(sql, *args)
        if self._excl and "wal_checkpoint" in low:
            self._o.calls.append("checkpoint")
            if self._o.heal:
                self._o.fault = False
        return out

    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture
def no_unlink(monkeypatch):
    """Enregistre toute suppression de fichier faite par DJSync pendant l'ouverture."""
    import os

    gone: list = []
    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        gone.append(str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(os, "remove", lambda p, *a, **k: gone.append(str(p)))
    monkeypatch.setattr(os, "unlink", lambda p, *a, **k: gone.append(str(p)))
    return gone


def test_b105_exclusive_repair_then_shared_mode(shm_key, monkeypatch, no_unlink):
    fault = _Fault()
    monkeypatch.setattr(base_mod, "sqlcipher", fault.mod)
    lib = RekordboxUsbLibrary(drive_from_letter(str(shm_key))).connect()
    try:
        assert fault.calls[:4] == ["open-shared", "exclusive", "open-exclusive", "checkpoint"]
        assert fault.calls[4] == "open-shared"
        assert "FromWal" in [p.name for p in lib.list_playlists()]               # lignes du -wal reprises
        assert lib._conn.execute("PRAGMA locking_mode").fetchone()[0].lower() == "normal"
        assert lib.journal_mode.lower() == "wal"
        assert lib._read_side("SELECT name FROM playlist WHERE playlist_id = 9", ()) == [("FromWal",)]  # A3-6
        assert lib._reader is not None
        other = _raw(shm_key / "PIONEER" / "rekordbox" / "exportLibrary.db")  # un autre programme lit aussi
        assert other.execute("SELECT count(*) FROM playlist").fetchone()[0] >= 4
        other.close()
        assert (shm_key / "PIONEER" / "rekordbox" / "exportLibrary.db-shm").exists()
    finally:
        lib.close()
    assert not [p for p in no_unlink if "exportLibrary" in p]                # aucun fichier supprimé par DJSync


def test_b105_wal_rows_merged_into_the_main_file(shm_key, monkeypatch):
    fault = _Fault(heal=False)                  # la réparation ne suffit pas : le checkpoint est quand même fait
    monkeypatch.setattr(base_mod, "sqlcipher", fault.mod)
    lib = RekordboxUsbLibrary(drive_from_letter(str(shm_key)))
    with pytest.raises(ShmRepairError) as err:
        lib.connect()
    assert err.value.reason == "still" and str(drive_from_letter(str(shm_key))) in str(err.value)
    rb = shm_key / "PIONEER" / "rekordbox"
    wal = rb / "exportLibrary.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    ro = sqlcipher.connect("file:" + (rb / "exportLibrary.db").as_posix() + "?immutable=1", uri=True)
    ro.execute("PRAGMA key = '%s'" % get_default_key())
    assert ro.execute("SELECT name FROM playlist WHERE playlist_id = 9").fetchone() == ("FromWal",)
    ro.close()
    assert (rb / "exportLibrary.db-shm").exists()


def test_b105_read_only_library_is_not_repaired(shm_key, monkeypatch):
    fault = _Fault()
    monkeypatch.setattr(base_mod, "sqlcipher", fault.mod)
    wal = shm_key / "PIONEER" / "rekordbox" / "exportLibrary.db-wal"
    size = wal.stat().st_size
    with pytest.raises(ShmRepairError) as err:
        RekordboxUsbLibrary(drive_from_letter(str(shm_key)), read_only=True).connect()
    assert err.value.reason == "read_only" and "exclusive" not in fault.calls
    assert wal.stat().st_size == size


def test_b105_exclusive_refused_when_another_program_writes(shm_key, monkeypatch):
    """Rekordbox ouvert (une autre connexion tient le verrou d'écriture) : message clair qui nomme la clé."""
    fault = _Fault()
    monkeypatch.setattr(base_mod, "sqlcipher", fault.mod)
    other = _raw(shm_key / "PIONEER" / "rekordbox" / "exportLibrary.db")
    other.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ShmRepairError) as err:
            RekordboxUsbLibrary(drive_from_letter(str(shm_key)), busy_timeout_ms=200).connect()
    finally:
        other.execute("ROLLBACK")
        other.close()
    assert err.value.reason == "exclusive" and "exclusive" in fault.calls


def test_b105_read_only_drive_message(shm_key, monkeypatch):
    """Clé en lecture seule (taquet) : fichier ouvert en lecture seule, le checkpoint exclusif est refusé : message
    clair qui nomme la clé, rien n'est changé."""
    fault = _Fault()

    def connect(path, *a, **k):
        uri = "file:" + Path(path).as_posix() + "?mode=ro"
        return _FaultConn(sqlcipher.connect(uri, *a, uri=True, **k), fault)

    fault.mod.connect = connect
    monkeypatch.setattr(base_mod, "sqlcipher", fault.mod)
    wal = shm_key / "PIONEER" / "rekordbox" / "exportLibrary.db-wal"
    size = wal.stat().st_size
    with pytest.raises(ShmRepairError) as err:
        RekordboxUsbLibrary(drive_from_letter(str(shm_key))).connect()
    assert err.value.reason == "exclusive" and "exclusive" in fault.calls
    assert wal.stat().st_size == size


@pytest.mark.parametrize("message, shm, expected", [
    ("database is locked", True, DatabaseLockedError),
    ("disk I/O error", False, DatabaseOpenError),
])
def test_b105_other_errors_unchanged(shm_key, monkeypatch, message, shm, expected):
    fault = _Fault(message)
    monkeypatch.setattr(base_mod, "sqlcipher", fault.mod)
    if not shm:
        (shm_key / "PIONEER" / "rekordbox" / "exportLibrary.db-shm").unlink()
    with pytest.raises(expected) as err:
        RekordboxUsbLibrary(drive_from_letter(str(shm_key))).connect()
    assert not isinstance(err.value, ShmRepairError) and "exclusive" not in fault.calls


def test_b105_message_names_the_drive_in_both_languages():
    from djsync.i18n import get_language, set_language, t

    exc = ShmRepairError("E:\\ (DJ_USB)", "exclusive")
    before = get_language()
    try:
        for lang in ("en", "fr"):
            set_language(lang)
            for reason in ("exclusive", "read_only", "still"):
                assert "DJ_USB" in t(f"error.shm_{reason}", drive=exc.drive)
    finally:
        set_language(before)


_HOLDER = r"""
import ctypes, sys, time
from ctypes import wintypes
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateFileW.restype = wintypes.HANDLE
h = k.CreateFileW(sys.argv[1], 0xC0000000, 0, None, 3, 0x80, None)   # aucun partage : -shm tenu
print("held" if h not in (None, ctypes.c_void_p(-1).value) else "fail", flush=True)
time.sleep(float(sys.argv[2]))
"""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows : -shm tenu par un autre processus")
def test_b105_windows_shm_held_by_another_process(shm_key, tmp_path):
    rb = shm_key / "PIONEER" / "rekordbox"
    script = tmp_path / "hold.py"
    script.write_text(_HOLDER)
    proc = subprocess.Popen([sys.executable, str(script), str(rb / "exportLibrary.db-shm"), "6"],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        lib = RekordboxUsbLibrary(drive_from_letter(str(shm_key)), busy_timeout_ms=500)
        try:
            lib.connect()
            outcome = "opened"
            lib.close()
        except ShmRepairError as exc:
            outcome = exc.reason
        import warnings

        warnings.warn(f"B105 Windows real test: outcome {outcome}")       # visible dans le journal de la CI
        assert outcome in ("opened", "still")
        wal = rb / "exportLibrary.db-wal"
        if outcome == "still":                       # réparée en mode exclusif : -wal fusionné, -shm gardé
            assert not wal.exists() or wal.stat().st_size == 0
    finally:
        proc.wait(timeout=30)
    assert (rb / "exportLibrary.db-shm").exists()
    with RekordboxUsbLibrary(drive_from_letter(str(shm_key))) as lib:      # -shm libéré : s'ouvre, rien perdu
        assert "FromWal" in [p.name for p in lib.list_playlists()]


# ------------------------------------------------------------------------------ A07 (avec C156)
from .test_v050 import _wav, local  # noqa: E402,F401 (fixture)


def _native_with_file(lib, path: Path):
    """Un son de Rekordbox (pas créé par DJSync) dont le fichier est `path`."""
    native = next(x for x in lib.list_tracks() if x.content_id not in {
        int(r[0]) for r in lib._read("SELECT ID, UUID FROM djmdContent") if r[1] in lib.owned.all()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _wav(path.parent, path.stem, seconds=2)
    with lib._write():
        lib._content(native.content_id).FolderPath = str(path)
    return lib.get_track(native.content_id)


def test_a07_foreign_file_goes_to_the_trash(local, tmp_path):  # noqa: F811
    from djsync.core import trash

    x = _native_with_file(local, tmp_path / "Rekordbox" / "native.wav")
    assert not local.is_owned(x.content_id)
    assert local.delete_tracks([x.content_id]) == (1, 0)
    assert not Path(x.path).exists() and trash.sent == [str(Path(x.path).resolve())]
    assert local.last_trashed == 1


def test_a07_protected_foreign_file_stays(local, tmp_path):  # noqa: F811
    from djsync.core import trash

    x = _native_with_file(local, tmp_path / "Rekordbox" / "native.wav")
    local.protect_foreign = True
    assert local.delete_tracks([x.content_id]) == (1, 0)
    assert Path(x.path).is_file() and trash.sent == []


def test_a07_file_used_by_another_track_is_kept(local, tmp_path):  # noqa: F811
    from djsync.core import trash

    x = _native_with_file(local, tmp_path / "Rekordbox" / "shared.wav")
    other = next(t for t in local.list_tracks() if t.content_id != x.content_id)
    with local._write():
        local._content(other.content_id).FolderPath = x.path.upper() if sys.platform == "win32" else x.path
    assert local.delete_tracks([x.content_id]) == (1, 0)
    assert Path(x.path).is_file() and trash.sent == []


def test_a07_guards_audio_only_and_trash_refused(local, tmp_path, monkeypatch):  # noqa: F811
    from djsync.core import trash

    note = tmp_path / "notes.txt"
    note.write_text("x")
    assert local._delete_audio(note, False) is False and note.exists()          # jamais autre chose que de l'audio

    def refuse(_p):
        raise OSError("no trash here")

    monkeypatch.setattr(trash, "_backend", refuse)
    x = _native_with_file(local, tmp_path / "Rekordbox" / "native.wav")
    assert local.delete_tracks([x.content_id]) == (1, 1)                     # pas effacé autrement : signalé
    assert Path(x.path).is_file()
    folder = local.default_download_dir("A", "B")                         # fichier de DJSync : effacé (comme avant)
    folder.mkdir(parents=True, exist_ok=True)
    mine = _wav(folder, "mine", seconds=2)
    t = local.add_track(mine, "Mine", "A", "B", "", [])
    assert local.delete_tracks([t.content_id]) == (1, 0) and not mine.exists()


@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="corbeille freedesktop (Linux)")
def test_a07_freedesktop_trash_with_restore_info(tmp_path, monkeypatch):
    from djsync.core import trash

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    f = tmp_path / "music" / "a b.wav"
    f.parent.mkdir()
    f.write_bytes(b"RIFF")
    trash._system(f)
    assert not f.exists()
    files = tmp_path / "share" / "Trash" / "files"
    assert (files / "a b.wav").read_bytes() == b"RIFF"
    info = (tmp_path / "share" / "Trash" / "info" / "a b.wav.trashinfo").read_text()
    assert "Path=" + str(f).replace(" ", "%20") in info and "DeletionDate=" in info
    f.write_bytes(b"RIFF2")                                                     # même nom : pas d'écrasement
    trash._system(f)
    assert (files / "a b 2.wav").read_bytes() == b"RIFF2"


@pytest.mark.skipif(sys.platform not in ("win32", "darwin") or not __import__("os").environ.get("CI"),
                    reason="vraie corbeille de Windows / macOS : seulement sur la CI")
def test_a07_system_trash_on_ci(tmp_path):
    from djsync.core import trash

    f = tmp_path / "djsync-trash-test.wav"
    f.write_bytes(b"RIFF")
    trash._system(f)
    assert not f.exists()


from .test_ui_v020 import demo  # noqa: E402,F401 (fixture)


def _goto_playlist(lib, name):
    p = next(p for p in lib.playlists if p.name == name)
    lib._goto(f"p{p.playlist_id}")
    return p


def test_a07_delete_confirmation_lists_tracks_without_link_in_red(demo):  # noqa: F811
    from djsync.ui.dialogs import ConfirmDialog
    from .qt_util import find, pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    umbrella = next(r.iid for r in lib.table.all_rows() if r.data.title == "Umbrella")
    lib.table.select([umbrella])
    lib._delete()
    dlg = find(demo, ConfirmDialog)
    assert dlg is not None and dlg.warning_lbl is not None
    assert "Umbrella" in dlg.warning_lbl.text() and dlg.warning_lbl.property("role") == "err"
    dlg.close()
    import dataclasses

    tracks = [dataclasses.replace(x, source_url="https://music.youtube.com/watch?v=abc")
              for x in lib.all_tracks if x.title == "Umbrella"]
    assert lib._no_source_warning(tracks) == "" and lib._no_source_warning(lib.all_tracks[:1], protect=True) == ""


def test_a07_delete_playlist_alone_or_with_its_tracks(demo):  # noqa: F811
    from djsync.ui.dialogs import ChoiceConfirmDialog
    from .qt_util import find, pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    _goto_playlist(lib, "Rap FR")
    lib._delete_playlist()
    assert pump(demo, 4, lambda: find(demo, ChoiceConfirmDialog) is not None)
    dlg = find(demo, ChoiceConfirmDialog)
    assert dlg.choice == 0 and not dlg.warning_lbl.isVisible()               # « La playlist seule » par défaut
    assert "3" in dlg.radios[1].text()
    dlg.radios[1].setChecked(True)
    assert dlg.warning_lbl.isVisible() and "Kalash" in dlg.warning_lbl.text()  # sans lien d'origine, en rouge
    assert "1" in dlg.detail_lbl.text()                                      # Kalash est aussi dans « Club »
    dlg._ok()
    assert pump(demo, 6, lambda: len(demo.ctrl.library.list_tracks()) == 7)
    assert "Rap FR" not in [p.name for p in demo.ctrl.library.list_playlists()]
    assert not list((demo.ctrl.drive.root / "Contents").rglob("*Vald*"))
    # la playlist seule : les sons restent
    _goto_playlist(lib, "Classiques") if pump(demo, 4, lambda: any(p.name == "Classiques" for p in lib.playlists)) \
        else None
    lib._delete_playlist()
    assert pump(demo, 4, lambda: find(demo, ChoiceConfirmDialog) is not None)
    find(demo, ChoiceConfirmDialog)._ok()
    assert pump(demo, 6, lambda: "Classiques" not in [p.name for p in demo.ctrl.library.list_playlists()])
    assert len(demo.ctrl.library.list_tracks()) == 7 and not demo.errors


# ------------------------------------------------------------------------------ C213 : grilles non vérifiées
def _tr(cid, analysed=True):
    return types.SimpleNamespace(content_id=cid, is_analysed=analysed)


def test_c213_unchecked_grids_line_does_not_change_the_verdict():
    from djsync.core.set_check import Check, check_grids, report, verdict

    c = check_grids([_tr(1), _tr(2), _tr(3, False)], {2})
    assert c.level == "note" and c.ids == [1] and c.action == "grids" and c.mark == "!"
    assert verdict([Check("files", "ok", ""), c]) == "ok"
    assert verdict([Check("files", "warn", ""), c]) == "warn"
    assert check_grids([_tr(1)], {1}).level == "ok"
    assert "1" in report([c], "DEMO", "all")


def test_c213_set_check_lists_grids_and_see_opens_the_library(demo, monkeypatch):  # noqa: F811
    from djsync.core import set_check
    from djsync.ui.set_check_dialog import SetCheckDialog
    from .qt_util import pump

    lib_view = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib_view.table.total == 10)
    ids = [x.content_id for x in lib_view.all_tracks[:3]]
    monkeypatch.setattr(set_check, "check_grids", lambda tracks, checked: set_check.Check(
        "grids", "note", "3 beat grids not checked yet.", action="grids", ids=ids))
    page = SetCheckDialog(demo, demo.ctrl)
    assert pump(demo, 10, lambda: "grids" in page.rows)
    keys = [c.key for c in page.checks]
    assert keys.index("grids") == keys.index("analysis") + 1
    row = page.rows["grids"]
    assert row["action"] is not None and row["text"].property("role") == "warn"
    row["action"].click()
    assert pump(demo, 4, lambda: demo.current == "library" and lib_view.table.count == 3)
    assert lib_view.focus_banner.isVisible() and "3" in lib_view.focus_lbl.text()
    assert "analysis" not in lib_view.table.user_hidden and lib_view._views.current == "prepare"
    lib_view.clear_focus()
    assert lib_view.table.count == 10 and not lib_view.focus_banner.isVisible()
    page.close()
    assert not demo.errors


# ------------------------------------------------------------------------------ C214 : vues de colonnes
OPT = ["pos", "key", "artist", "album", "bpm", "duration", "format", "source", "added", "genre", "bitrate", "real",
       "playlists", "cues", "analysis", "dup", "path", "size", "rate", "color", "rating", "mytags", "last_played"]


def test_c214_views_logic():
    from djsync.ui.column_views import DEFAULT, ColumnViews

    data: dict = {}
    v = ColumnViews(data, OPT)
    default_hidden = v.hidden(DEFAULT)
    assert v.first_use(default_hidden) == "discover" and not data["custom"]           # rien ne change à l'écran
    assert v.shown("all") == set(OPT) and "analysis" in v.shown("prepare") and "real" in v.shown("quality")
    assert not v.modified(default_hidden) and v.modified(default_hidden - {"genre"})
    v.save("discover", default_hidden - {"genre"})                                   # vue d'origine modifiée
    assert "genre" in v.shown("discover") and v.is_changed_builtin("discover")
    v.restore_builtin("discover")
    assert "genre" not in v.shown("discover")
    mine = v.create("  Préparation club ", {"path"})
    assert v.name(mine) == "Préparation club" and v.shown(mine) == set(OPT) - {"path"}
    v.select(mine, "E:|p3")
    assert v.for_list("E:|p3") == mine and v.current == mine
    v.rename(mine, "Club")
    assert v.name(mine) == "Club"
    v.delete(mine)
    assert v.for_list("E:|p3") == "" and v.current == DEFAULT and mine not in v.ids()
    other = ColumnViews({}, OPT)                                                     # colonnes à soi : gardées
    assert other.first_use({"pos"}) not in ("discover", "all") and other.name(other.current)
    assert other.shown(other.current) == set(OPT) - {"pos"}


def test_c214_library_view_menu_modified_save_revert_and_per_list(demo):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.dialogs import TextInputDialog
    from djsync.ui.views.library_view import ALL
    from .qt_util import find, pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    assert lib._views.current == "discover" and t("views.discover") in lib.view_btn.text()
    assert not lib.view_mod.isVisible()
    names = [e[0].strip("✓ ").strip() for e in lib._views_entries() if e]
    assert names[:5] == [t(f"views.{k}") for k in ("discover", "prepare", "mix", "quality", "all")]
    lib.select_view("quality")
    assert "bitrate" not in lib.table.user_hidden and "playlists" in lib.table.user_hidden
    lib.table.set_column_visible("genre", True)                                     # colonne changée
    assert lib.view_mod.isVisible() and lib.view_save.isVisible() and lib.view_revert.isVisible()
    lib._view_revert()
    assert "genre" in lib.table.user_hidden and not lib.view_mod.isVisible()
    lib.table.set_column_visible("genre", True)
    lib._view_save()
    assert not lib.view_mod.isVisible() and "genre" in demo.ctrl.settings.library_views["saved"]["quality"]
    # vue retenue par liste
    house = _goto_playlist(lib, "House")
    lib.select_view("prepare")
    lib._goto(ALL)
    assert lib._views.current == "quality"
    lib._goto(f"p{house.playlist_id}")
    assert lib._views.current == "prepare" and "analysis" not in lib.table.user_hidden
    # nouvelle vue nommée
    lib._view_new()
    dlg = find(demo, TextInputDialog)
    dlg._entry.setText("Mes sets")
    dlg._ok()
    custom = demo.ctrl.settings.library_views["custom"]
    assert [c["name"] for c in custom.values()] == ["Mes sets"] and "Mes sets" in lib.view_btn.text()
    assert any(t("views.rename") in (e[0] if e else "") for e in lib._views_entries())
    assert not demo.errors


def test_c214_texts_in_both_languages():
    from djsync.i18n import en, fr

    for k in ("discover", "prepare", "mix", "quality", "all", "label", "modified", "save", "revert", "new", "mine"):
        assert f"views.{k}" in en.STRINGS and f"views.{k}" in fr.STRINGS
    assert fr.STRINGS["views.label"] == "Vue : {name}" and fr.STRINGS["views.modified"] == "(modifiée)"


def test_a07_protection_setting_off_by_default_and_saved(demo, monkeypatch):  # noqa: F811
    from djsync.settings import Settings
    from .qt_util import pump

    assert Settings().protect_foreign is False
    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    demo.show_view("settings")
    view = demo.views["settings"]
    assert not view.protect_var.isChecked()
    view.protect_var.setChecked(True)
    assert pump(demo, 3, lambda: demo.ctrl.settings.protect_foreign is True)
    assert view.unsaved() == []
    for box, name in ((view.tags_var, "write_tags"), (view.gain_var, "auto_gain")):   # S05, C109 : aussi tout de suite
        want = not box.isChecked()
        box.setChecked(want)
        assert pump(demo, 3, lambda n=name, w=want: getattr(demo.ctrl.settings, n) == w)
