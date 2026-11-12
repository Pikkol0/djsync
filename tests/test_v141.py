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


# ------------------------------------------------------------------ C92 : aimant ; A02 : × 3/2 et × 2/3
BEATS = [((i % 4) + 1, 12000, 1000 + 500 * i) for i in range(16)]      # 120 BPM, un temps toutes les 500 ms


def test_c92_nearest_grid_ms_beat_and_quarter():
    from djsync.analysis.cues import nearest_grid_ms

    assert nearest_grid_ms(BEATS, 1240) == 1000                 # au temps
    assert nearest_grid_ms(BEATS, 1260) == 1500
    assert nearest_grid_ms(BEATS, 1240, 4) == 1250              # au quart de temps (125 ms)
    assert nearest_grid_ms(BEATS, 1180, 4) == 1125
    assert nearest_grid_ms(BEATS, 200, 4) == 250                # avant le premier temps : au même pas
    assert nearest_grid_ms(BEATS, 9000, 4) == 9000              # après le dernier : prolongé
    assert nearest_grid_ms([], 1234.4, 4) == 1234


def _snap(magnet, ms, **kw):
    from types import SimpleNamespace

    from djsync.ui.grid_editor import GridEditor

    return GridEditor.snap_ms(SimpleNamespace(beats=BEATS, magnet=magnet), ms, **kw)


def test_c92_snap_cursor_only_with_the_magnet_and_cues_as_before_without_it(qapp=None):
    from djsync.ui.app import qt_app

    qt_app()
    assert _snap(0, 1240.0, cursor=True) == 1240.0             # aimant coupé : curseur libre
    assert _snap(0, 1240.0) == 1000.0                           # … et les cues calés au temps, comme avant
    assert _snap(1, 1240.0, cursor=True) == 1000.0              # aimant au temps
    assert _snap(4, 1240.0, cursor=True) == 1250.0              # aimant au quart
    assert _snap(4, 1240.0) == 1250.0
    assert _snap(4, 1240.0, exact=True) == 1240.0               # Maj / Alt : libre


def test_a02_three_halves_and_two_thirds_keep_the_selected_beat():
    from djsync.analysis import grid as G

    beats = [((i % 4) + 1, 9000, 1000 + int(round(i * 60000 / 90))) for i in range(40)]   # 90 BPM
    up = G.scale_tempo(beats, 1.5, 4, 40000)
    assert abs(sorted(b[1] for b in up)[len(up) // 2] / 100 - 135) < 0.01
    assert any(abs(b[2] - beats[4][2]) <= 1 for b in up)          # le temps sélectionné ne bouge pas
    down = G.scale_tempo(up, 2.0 / 3.0, G.nearest(up, beats[4][2]), 40000)
    assert abs(sorted(b[1] for b in down)[len(down) // 2] / 100 - 90) < 0.01


def test_c92_a02_controls_translated():
    from djsync.i18n import en, fr

    for k in ("grid.magnet", "grid.magnet_tip", "grid.magnet_beat", "grid.magnet_quarter", "grid.two_thirds",
              "grid.three_halves", "grid.two_thirds_tip", "grid.three_halves_tip", "watch.caught_up_one",
              "watch.caught_up_many"):
        assert en.STRINGS.get(k) and fr.STRINGS.get(k), k


# ------------------------------------------------------------------ B84 : DJSync.exe dans Program Files
def test_b84_moved_contents_dir_holds_settings_tools_and_is_uninstalled(tmp_path, monkeypatch):
    from djsync import portable, uninstall

    exe_dir = tmp_path / "Program Files" / "djsync"
    moved = tmp_path / "LocalAppData" / "DJSync"
    (moved / "app" / "tools").mkdir(parents=True)
    exe_dir.mkdir(parents=True)
    monkeypatch.setenv("DJSYNC_APP_DIR", str(exe_dir))
    monkeypatch.delenv("DJSYNC_CONTENTS_DIR", raising=False)
    assert portable.contents_dir() is None
    assert portable.portable_data_dir() == exe_dir / ".djsync" / "data"           # cas habituel inchangé
    monkeypatch.setenv("DJSYNC_CONTENTS_DIR", str(moved))
    assert portable.portable_data_dir() == moved / "data"
    assert portable.tool_dirs()[0] == moved / "app" / "tools"
    monkeypatch.delenv("DJSYNC_HOME", raising=False)
    from djsync.settings import settings_dir

    assert settings_dir() == moved / "data"
    assert moved in uninstall.targets(frozen=False)


def test_b84_no_in_app_update_when_the_exe_folder_is_read_only(tmp_path, monkeypatch):
    from djsync.core import selfupdate

    exe = tmp_path / "DJSync.exe"
    exe.write_bytes(b"MZ")
    assert selfupdate.plan(frozen=True, platform="win32", launcher=str(exe)).kind == "windows"
    monkeypatch.setattr(selfupdate, "_writable", lambda folder: False)
    assert selfupdate.plan(frozen=True, platform="win32", launcher=str(exe)) is None   # page de la release


def test_b84_launcher_falls_back_to_local_app_data():
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "packaging" / "launcher" / "launcher.c").read_text("utf-8")
    assert "LOCALAPPDATA" in src and "DJSYNC_CONTENTS_DIR" in src and "writable(" in src
