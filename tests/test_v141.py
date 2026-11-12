"""1.4.1 : B95 (dossier surveillé : rattrapage à l'activation), C177 (mesures comptées à partir de 0)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import pump  # noqa: E402,F401
from .test_v122 import demo, usb  # noqa: E402,F401
from .test_v140 import _wav  # noqa: E402


# ------------------------------------------------------------------ C177
def test_c177_bars_are_counted_from_zero():
    from djsync.ui import grid_editor

    assert grid_editor.FIRST_BAR == 0
    assert grid_editor.bar_label(1) == "0"                  # la première mesure affiche 0
    assert grid_editor.bar_label(9) == "8"                  # la neuvième affiche 8 : phrases aux multiples de 8


# ------------------------------------------------------------------ B95
def _watch_setup(demo, tmp_path):  # noqa: F811
    from djsync.core.importer import import_files
    from djsync.core.watcher import DONE_DIR

    ctrl = demo.ctrl
    lib = ctrl.library
    folder = tmp_path.parent / (tmp_path.name + "_watch")          # hors de la clé
    done = folder / DONE_DIR
    (done / "Album").mkdir(parents=True)
    a = _wav(done / "Artist A - Song A.wav")
    b = _wav(done / "Album" / "Artist B - Song B.wav", seconds=3.5)      # dans un sous-dossier
    c = _wav(done / "Artist C - Never imported.wav", seconds=4.0)        # rangé, mais pas dans la bibliothèque
    rep = import_files(lib, [a, b])
    assert len(rep.added) == 2
    ctrl.service.refresh_library()
    ctrl.settings.watch_folder = str(folder)
    ctrl.settings.watch_playlist = True
    ctrl.settings.watch_scanned = ""
    return ctrl, lib, folder, (a, b, c), {x.content_id for x in rep.added}


def _watch_pl(lib):
    from djsync.ui.ctrl.imports import watch_playlist_names

    return next((p for p in lib.list_playlists() if p.name in watch_playlist_names()), None)


def _tick(demo, ctrl):  # noqa: F811
    ctrl.watch_tick()
    assert pump(demo, 5, lambda: not getattr(ctrl, "_watch_busy", False) and not getattr(ctrl, "_watch_catching", False)
                and not getattr(ctrl, "_importing", False))


def test_b95_catch_up_puts_known_tracks_back_and_touches_no_file(demo, tmp_path):  # noqa: F811
    ctrl, lib, folder, files, ids = _watch_setup(demo, tmp_path)
    before_files = sorted(str(p) for p in folder.rglob("*") if p.is_file())
    n_tracks = len(lib.list_tracks())
    assert _watch_pl(lib) is None
    _tick(demo, ctrl)
    pl = _watch_pl(lib)
    assert pl is not None
    got = {x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)}
    assert ids <= got and len(got) == len(ids) + 1                                      # sous-dossier compris
    assert len(lib.list_tracks()) == n_tracks + 1                     # le fichier rangé mais absent est importé
    assert any(x.title == "Never imported" for x in lib.get_playlist_tracks(pl.playlist_id))
    assert sorted(str(p) for p in folder.rglob("*") if p.is_file()) == before_files     # rien de déplacé
    assert ctrl.settings.watch_scanned
    _tick(demo, ctrl)                                                                   # une seule fois
    assert len(lib.list_tracks()) == n_tracks + 1


def test_b95_only_on_activation_then_again_after_off_and_on(demo, tmp_path):  # noqa: F811
    ctrl, lib, _folder, _files, ids = _watch_setup(demo, tmp_path)
    _tick(demo, ctrl)
    lib.delete_playlist(_watch_pl(lib).playlist_id)
    _tick(demo, ctrl)                                       # dossier inchangé : la playlist supprimée le reste
    assert _watch_pl(lib) is None
    folder = ctrl.settings.watch_folder
    ctrl.settings.watch_folder = ""                         # désactivé…
    ctrl.watch_tick()
    assert ctrl.settings.watch_scanned == ""
    ctrl.settings.watch_folder = folder                     # … puis réactivé : tout revient, sans doublon
    _tick(demo, ctrl)
    pl = _watch_pl(lib)
    assert pl is not None
    got = [x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)]
    assert ids <= set(got) and len(got) == len(set(got)) == len(ids) + 1               # aucun doublon


def test_b95_old_imported_playlist_renamed_and_completed(demo, tmp_path):  # noqa: F811
    from djsync.i18n import t

    ctrl, lib, _folder, _files, ids = _watch_setup(demo, tmp_path)
    old = lib.create_playlist("Imported")
    lib.add_to_playlist(old.playlist_id, [sorted(ids)[0]])
    _tick(demo, ctrl)
    pl = _watch_pl(lib)
    assert pl is not None and pl.playlist_id == old.playlist_id and pl.name == t("watch.playlist")
    assert not any(p.name == "Imported" for p in lib.list_playlists())
    got = [x.content_id for x in lib.get_playlist_tracks(pl.playlist_id)]
    assert ids <= set(got) and len(got) == len(set(got)) == len(ids) + 1


def test_b95_no_empty_playlist_and_none_when_the_option_is_off(demo, tmp_path):  # noqa: F811
    ctrl, lib, folder, _files, _ids = _watch_setup(demo, tmp_path)
    ctrl.settings.watch_playlist = False
    n = len(lib.list_tracks())
    _tick(demo, ctrl)
    assert _watch_pl(lib) is None and ctrl.settings.watch_scanned
    assert len(lib.list_tracks()) == n + 1                  # importé quand même, sans playlist
    ctrl.settings.watch_playlist = True
    ctrl.settings.watch_scanned = ""
    ctrl.settings.watch_folder = str(folder.parent / "empty_watch")       # dossier sans rien de rangé
    (folder.parent / "empty_watch").mkdir(exist_ok=True)
    _tick(demo, ctrl)
    assert _watch_pl(lib) is None
