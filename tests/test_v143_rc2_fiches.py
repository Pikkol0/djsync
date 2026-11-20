"""1.4.3-rc.2 (publiée en rc.2) : tests ciblés des fiches B114 à B124, C206, C207, C212, C217, C218, C224, C228."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .test_v122 import demo, usb  # noqa: F401  (fixtures)


# ------------------------------------------------------------------ B123 : débit MP3 lu sur la trame d'en-tête
def _mp3_without_xing_bytes(tmp_path: Path) -> Path:
    """MP3 VBR dont l'en-tête Xing n'a pas le nombre d'octets : mutagen donne le débit de la trame d'en-tête."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg absent")
    src = tmp_path / "vbr.mp3"
    subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=12:a=0.3",
                    "-c:a", "libmp3lame", "-q:a", "2", str(src)], check=True)
    data = bytearray(src.read_bytes())
    i = data.find(b"Xing")
    flags = int.from_bytes(data[i + 4:i + 8], "big")
    assert flags & 3 == 3
    del data[i + 12:i + 16]                                   # champ « octets » retiré
    data[i + 4:i + 8] = (flags & ~2).to_bytes(4, "big")
    data[i + 300:i + 300] = b"\0" * 4                         # taille de la trame d'en-tête gardée
    out = tmp_path / "Obito.mp3"
    out.write_bytes(bytes(data))
    return out


def test_b123_header_bitrate_replaced_by_mean(tmp_path):
    from mutagen.mp3 import MP3

    from djsync.analysis.encoder import mean_mp3_kbps, read_mp3
    from djsync.core.quality import _probe_header

    f = _mp3_without_xing_bytes(tmp_path)
    header = MP3(str(f)).info.bitrate // 1000
    mean = mean_mp3_kbps(f)
    assert mean > 0 and abs(header - mean) > 0.25 * mean          # le cas du bug
    assert _probe_header(f).bitrate == mean
    assert read_mp3(f).mean == mean


def test_b123_trusted_kbps_keeps_a_close_header():
    from djsync.analysis.encoder import trusted_kbps

    assert trusted_kbps(320, 318) == 320
    assert trusted_kbps(32, 124) == 124
    assert trusted_kbps(0, 124) == 124
    assert trusted_kbps(128, 0) == 128


def test_b123_encoder_register_reads_old_entries():
    from djsync.analysis.encoder import EncoderInfo

    old = EncoderInfo.from_list(["mp3", "LAME 3.100", "CBR", 320, 20500, ""])
    assert old.mean == 0 and EncoderInfo.from_list(old.to_list()) == old


def test_b123_library_shows_the_mean_and_colours_from_it(tmp_path, monkeypatch):
    from djsync.analysis import encoder
    from djsync.models import LibraryTrack
    from djsync.ui.views import library_view

    encoder.use_store(tmp_path / "encoder.json")
    try:
        f = tmp_path / "Obito.mp3"
        f.write_bytes(b"\0" * 2_100_000)
        encoder.remember(f, encoder.EncoderInfo(codec="mp3", name="x", mode="VBR", mean=117))
        x = LibraryTrack(content_id=1, title="Obito", artist="", album=None, duration_seconds=144,
                         path=str(f), bpm=0.0, file_type=1, source_url=None, date_added="", is_analysed=True,
                         bitrate=32, file_size=2_100_000)
        out = library_view.extra_values(x)
        assert "117" in out["bitrate"]
    finally:
        encoder.use_store(None)


# ------------------------------------------------------------------ C212 (GRI-7 KO) : défile aussi en largeur
def test_c212_grid_editor_scrolls_horizontally_when_narrow(demo):  # noqa: F811
    from djsync.ui.grid_editor import GridEditor

    from .qt_util import pump

    track = demo.ctrl.library.list_tracks()[0]
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        bar = ed.page_area.horizontalScrollBar()
        ed.setGeometry(0, 0, 1400, 900)
        ed.show()
        pump(demo, 0.3)
        assert bar.maximum() == 0                                         # assez large : pas de barre
        ed.setGeometry(0, 0, 420, 900)
        pump(demo, 0.3)
        inner = ed.page_area.widget()
        assert bar.maximum() > 0 and inner.width() >= inner.minimumSizeHint().width()   # rien n'est écrasé
    finally:
        ed.close()


# ------------------------------------------------------------------ B120 : une sauvegarde par rafale, corbeille à part
@pytest.fixture
def local_lib(tmp_path, monkeypatch):
    pytest.importorskip("pyrekordbox")
    from djsync.db import local_library as L

    from .test_local_library import DATA

    db_dir = tmp_path / "Pioneer" / "rekordbox"
    db_dir.mkdir(parents=True)
    for f in DATA.glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    monkeypatch.setattr(L, "rekordbox_running", lambda: False)
    lib = L.LocalRekordboxLibrary(L.LocalRekordbox(db_dir, tmp_path / "Music" / "DJSync"),
                                  backup_root=tmp_path / "bk", owned_path=tmp_path / "owned.json",
                                  analyze=False).connect()
    yield lib
    lib.close()


def test_b120_one_backup_per_burst_unless_another_writer(local_lib, monkeypatch, tmp_path):
    from djsync.db import local_library as L

    monkeypatch.setattr(L, "BACKUP_BURST_S", 60.0)
    copies = lambda: sorted((tmp_path / "bk").glob("master-*"))          # noqa: E731
    local_lib.create_playlist("A")
    local_lib.create_playlist("B")
    local_lib.create_playlist("C")
    assert len(copies()) == 1                                              # une rafale : une copie
    # une autre session (Rekordbox) écrit : la prochaine écriture refait une copie
    import os
    import time

    db = local_lib.drive.db_dir / "master.db"
    later = time.time() + 5
    os.utime(db, (later, later))
    local_lib.create_playlist("D")
    assert len(copies()) == 2
    # rafale finie (plus de 60 s) : nouvelle copie
    local_lib._burst = (local_lib._burst[0] - 61, local_lib._burst[1])
    local_lib.create_playlist("E")
    assert len(copies()) == 3


def test_b120_files_later_go_to_the_trash_in_one_batch(local_lib):
    from djsync.core import trash

    from .test_local_library import make_wav

    music = local_lib.default_download_dir("A", "")
    a = local_lib.add_track(make_wav(music, "a", 2), "Alpha", "A")
    b = local_lib.add_track(make_wav(music, "b", 2), "Beta", "A")
    files = [Path(a.path), Path(b.path)]
    removed, failures = local_lib.delete_tracks([a.content_id, b.content_id], True, files_later=True)
    assert (removed, failures) == (2, 0) and all(f.exists() for f in files)   # base d'abord, fichiers ensuite
    assert local_lib.trash_pending() == (2, 0)
    assert not any(f.exists() for f in files) and local_lib.last_trashed == 2
    assert {Path(p).name for p in trash.sent} >= {"a.wav", "b.wav"}
    assert local_lib.trash_pending() == (0, 0)


def test_b120_file_still_used_is_kept(local_lib):
    from .test_local_library import make_wav

    music = local_lib.default_download_dir("A", "")
    a = local_lib.add_track(make_wav(music, "a", 2), "Alpha", "A")
    assert local_lib._files_used([a.path, "/nowhere/x.mp3"]) == {__import__("os").path.normcase(a.path).lower()}


def test_b121_removed_rows_leave_without_reloading_the_playlist(demo, monkeypatch):  # noqa: F811
    from .qt_util import pump
    from .test_v143_lot4 import _goto_playlist

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    house = _goto_playlist(lib, "House")
    assert pump(demo, 4, lambda: lib.table.total > 1)
    n = lib.table.total
    first = lib.table.displayed_iids()[0]
    fills = []
    monkeypatch.setattr(lib, "_fill_table", lambda: fills.append(1))
    demo.ctrl.remove_from_playlist(house.playlist_id, [int(first)])
    assert pump(demo, 4, lambda: lib.table.total == n - 1)
    pump(demo, 0.5)
    assert not fills and first not in lib.table.displayed_iids()           # pas de rechargement de la playlist
    assert sorted(r.values["pos"] for r in lib.table.all_rows()) == list(range(1, n))
    assert not demo.errors


# ------------------------------------------------------------------ C218 : 4 vues, ordre des colonnes
OPT = ["pos", "key", "artist", "album", "bpm", "duration", "format", "source", "added", "genre", "bitrate", "real",
       "playlists", "cues", "analysis", "dup", "path", "size", "rate", "color", "rating", "mytags", "last_played"]


def test_c218_four_views_and_their_order():
    from djsync.ui.column_views import BUILTIN, ORDER, ColumnViews

    assert BUILTIN == ("essential", "prepare", "quality", "all")
    for view in ("essential", "prepare", "quality"):
        assert ORDER[view][:3] == ("pos", "title", "artist")               # #, titre puis artiste
    assert ORDER["quality"][-2:] == ("size", "path")                       # techniques à la fin
    v = ColumnViews({}, OPT)
    assert v.order("all")[:8] == list(ORDER["essential"])
    hidden = v.hidden("essential")
    order = ["pos", "key", "title", "artist", "bpm", "duration", "playlists", "added"]
    v.data["current"] = "essential"
    assert v.modified(hidden, order)                                        # tonalité avant le titre : modifiée
    assert not v.modified(hidden, list(ORDER["essential"]) + ["genre"])
    v.save("essential", hidden, order)
    assert v.order("essential") == order and not v.modified(hidden, order)
    v.restore_builtin("essential")
    assert v.order("essential") == list(ORDER["essential"])


def test_c218_retired_views_kept_when_changed_else_mapped():
    from djsync.i18n import t
    from djsync.ui.column_views import ColumnViews

    data = {"current": "mix", "saved": {"discover": ["artist", "genre"]},
            "by_list": {"E:|p1": "discover", "E:|p2": "mix"}}
    v = ColumnViews(data, OPT)
    assert v.migrated and v.current == "prepare"                           # « Mixer » -> « Préparer un set »
    mine = data["by_list"]["E:|p1"]
    assert v.is_custom(mine) and v.name(mine) == t("views.discover") and v.shown(mine) == {"artist", "genre"}
    assert data["by_list"]["E:|p2"] == "prepare" and "discover" not in data["saved"]
    assert "discover" not in v.ids() and "mix" not in v.ids()


def test_c218_legacy_default_columns_become_essential():
    from djsync.ui.column_views import LEGACY_DEFAULT, ColumnViews

    v = ColumnViews({}, OPT)
    assert v.first_use(set(OPT) - set(LEGACY_DEFAULT)) == "essential" and v.migrated


def test_c218_c224_library_bar(demo):  # noqa: F811
    from djsync.i18n import t

    from .qt_util import pump

    demo.resize(1600, 900)
    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    items = [w for w, *_r in lib.bar._items]
    assert items.index(lib.view_btn) == items.index(lib.cols_btn) + 1    # la vue juste à côté de « Colonnes »
    assert lib.view_btn.text().startswith(t("views.essential")) and ":" not in lib.view_btn.text()
    assert lib.harm_btn not in items and lib.import_btn.text() in (t("import_files.short"), "")
    order = lib.table.column_order()
    assert order.index("title") < order.index("artist") < order.index("bpm") < order.index("key")
    lib.select_view("quality")
    order = lib.table.column_order()
    assert order.index("real") < order.index("format") < order.index("path")
    # colonne déplacée à la main : vue « modifiée », Revenir remet l'ordre
    head = lib.table.horizontalHeader()
    path = [c.key for c in lib.table.columns].index("path")
    head.moveSection(head.visualIndex(path), 1)
    assert lib.view_mod.isVisibleTo(lib)
    lib._view_revert()
    assert not lib.view_mod.isVisibleTo(lib)
    # « Harmonique » dans le menu ☰
    captured = []
    import djsync.ui.views.library_view as LV

    orig = LV.popup_menu
    LV.popup_menu = lambda _w, entries, _pos: captured.append(entries)
    try:
        lib._tools_menu()
    finally:
        LV.popup_menu = orig
    assert any(e and t("lib.harmonic") in e[0] for e in captured[0])
    assert not demo.errors


def test_c217_no_transfer_button_on_the_cards(demo):  # noqa: F811
    from PySide6.QtWidgets import QPushButton

    home = demo.views["home"]
    demo.show_view("home")
    assert "transfer" in home.actions                                      # la tuile reste
    assert not home.findChildren(QPushButton, "transfer_sync")


def test_c224_texts():
    from djsync.i18n import en, fr

    assert fr.STRINGS["import_files.short"] == "Importer" and en.STRINGS["import_files.short"] == "Import"
    assert fr.STRINGS["views.essential"] == "Essentiel" and fr.STRINGS["views.quality"] == "Qualité et fichiers"


# ------------------------------------------------------------------ C206 : message Spotify sur sa propre ligne
def test_c206_spotify_note_on_its_own_line(demo):  # noqa: F811
    from djsync.models import SpotifyPlaylist, SpotifyTrack
    from djsync.i18n import t

    view = demo.views["import"]
    demo.show_view("import")
    pl = SpotifyPlaylist("Big", [SpotifyTrack(f"T{i}", ("A",), None, 200) for i in range(100)],
                         source_url="https://open.spotify.com/playlist/x", truncated=True, total=534)
    demo.ctrl.match_spotify = lambda tracks, on_item, on_done: None
    view._load_spotify(pl)
    assert view.note_lbl.isVisibleTo(view) and "534" in view.note_lbl.text()
    assert t("import.paste_list").rstrip("…") in view.note_lbl.text() and "534" not in view.info.text()
    assert view.note_lbl.wordWrap()


# ------------------------------------------------------------------ B119 : choix de la suppression lisibles
def test_b119_choice_dialog_wraps_and_widens(demo):  # noqa: F811
    from djsync.ui.dialogs import ChoiceConfirmDialog
    from djsync.ui.widgets import WrapRadioButton

    long = "La playlist et ses 42 sons (fichiers à la corbeille, sons retirés de toutes les autres playlists)"
    dlg = ChoiceConfirmDialog(demo, "Supprimer", "Supprimer la playlist « X » ?", ["La playlist seule", long],
                              lambda _i: None)
    try:
        assert all(isinstance(r, WrapRadioButton) for r in dlg.radios)
        assert dlg.minimumWidth() > 460 and dlg.radios[1].hasHeightForWidth()
        r = dlg.radios[1]
        assert r.heightForWidth(200) > r.heightForWidth(2000)               # le texte passe à la ligne
    finally:
        dlg.close()


# ------------------------------------------------------------------ B124 : aperçu de la fusion lisible
def test_b124_kept_lines_in_text_colour_and_long_lines_cut():
    from djsync.core import merge_preview as M

    lines = [M.Line("=", "tracks", "Kept: Art — Song"), M.Line("+", "playlists", "x" * 200)]
    html = M.to_html(lines, "#0f0", "#f00", "#777", "#eeeeee")
    assert "color:#eeeeee" in html and "inherit" not in html
    assert "…" in html and "x" * 120 not in html
    assert "x" * 200 in M.to_plain(lines)


# ------------------------------------------------------------------ B122 : liste des groupes stable
def test_b122_counter_has_a_fixed_width():
    import inspect

    from djsync.ui import duplicates_dialog as D

    src = inspect.getsource(D)
    assert "setRetainSizeWhenHidden(True)" in src and "doItemsLayout()" in src
    assert "ScrollBarAlwaysOn" in src


# ------------------------------------------------------------------ B114 : surlignage d'un seul tenant
def test_b114_row_highlight_square_and_tree_branch_filled():
    from djsync.ui import theme
    from djsync.ui.views.library_view import NavTree
    from djsync.ui.widgets import RowTree

    css = theme.stylesheet() if hasattr(theme, "stylesheet") else ""
    if css:
        assert "QTreeWidget::item, QListWidget::item {" in css and "border-radius: 0;" in css
    assert issubclass(NavTree, RowTree) and "drawBranches" in RowTree.__dict__


# ------------------------------------------------------------------ B117 : formes d'onde Bleu et RGB lisses
def test_b117_detail_image_is_continuous_when_zoomed(demo):  # noqa: F811
    import numpy as np

    from djsync.ui.grid_editor import COLS_PER_S, detail_image

    detail = [(0.2, "#1f6fe5"), (0.9, "#1f6fe5")] * 200
    px_per_ms = 8 * COLS_PER_S / 1000.0                               # 8 pixels par colonne ANLZ
    img = detail_image(detail, 0.0, px_per_ms, 400, 100, 50, 42, "#888888")
    heights = []
    for x in range(8, 120):
        col = [img.pixelColor(x, y).alpha() for y in range(100)]
        heights.append(sum(a / 255 for a in col))
    steps = np.abs(np.diff(heights))
    assert steps.max() < 0.25 * (max(heights) - min(heights))             # plus d'escalier d'une colonne à l'autre
    edge = [img.pixelColor(20, y).alpha() for y in range(100)]
    assert any(0 < a < 255 for a in edge)                                  # bords antialiasés
    zoomed_out = detail_image(detail, 0.0, 0.01, 400, 100, 50, 42, "#888888")
    assert zoomed_out is not None and zoomed_out.width() == 400


# ------------------------------------------------------------------ C228 : sons téléchargés à part
def test_c228_downloaded_tracks_counted_apart(tmp_path, demo):  # noqa: F811
    from djsync.core import space

    data, music = tmp_path / "data", tmp_path / "music"
    data.mkdir()
    music.mkdir()
    (music / "t.mp3").write_bytes(b"x" * 50_000)
    fp = space.djsync_footprint(data, music)
    assert "music" not in space.FOOTPRINT_PARTS and fp["music"] >= 50_000
    assert fp["total"] == sum(fp[k] for k in space.FOOTPRINT_PARTS) and fp["total"] < fp["total"] + fp["music"]
    from djsync.ui.space_card import SpaceCard
    from djsync.ui.widgets import vbox
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    card = SpaceCard(vbox(host), demo.ctrl)
    card._show_footprint(fp)
    assert card.footprint_music.isVisibleTo(host) and card.footprint_music.text()
    from djsync.i18n import t

    assert t("space.fp_music", size="").strip() not in card.footprint_detail.text()
