"""1.4.4-rc.1 (lot 2) : C138, volet « Infos » d'un son dans la Bibliothèque."""
from __future__ import annotations

from .test_v122 import demo, usb  # noqa: F401  (fixtures)


def _c138_library(demo):  # noqa: F811
    from tests.qt_util import pump

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 5, lambda: lib.table.total == 10)
    return lib


def _c138_select(demo, lib, title):  # noqa: F811
    from tests.qt_util import pump

    row = next(r for r in lib.table.all_rows() if r.data is not None and r.data.title == title)
    lib.table.select([row.iid])
    panel = lib.info_panel
    if panel.isVisible() and not panel.dirty:
        assert pump(demo, 3, lambda: panel.track is not None and panel.track.title == title and panel.info is not None)
    return row.data


def _c138_dialog(demo):  # noqa: F811
    from djsync.ui.track_info_panel import UnsavedInfoDialog
    from tests.qt_util import find, pump

    assert pump(demo, 3, lambda: find(demo, UnsavedInfoDialog) is not None)
    return find(demo, UnsavedInfoDialog)


def test_c138_menu_opens_panel_instead_of_edit_dialog(demo):  # noqa: F811
    from djsync.i18n import t
    from tests.qt_util import pump

    lib = _c138_library(demo)
    assert not lib.info_panel.isVisible()
    x = _c138_select(demo, lib, "Mon Survet")
    entries = [e for e in lib._menu([str(x.content_id)]) if e]
    labels = [e[0] for e in entries]
    assert t("info.panel_menu") in labels and t("action.edit_metadata") not in labels
    # ailleurs (lecteur), la fenêtre « Modifier les infos » reste
    from djsync.ui.track_menu import track_entries

    assert t("action.edit_metadata") in [e[0] for e in track_entries(lib, demo.ctrl, [x], where="player") if e]
    next(e for e in entries if e[0] == t("info.panel_menu"))[1]()
    panel = lib.info_panel
    assert pump(demo, 3, lambda: panel.isVisible() and panel.track is not None and panel.info is not None)
    assert panel.track.content_id == x.content_id
    assert panel.fields["title"].text() == "Mon Survet"
    assert demo.ctrl.settings.track_info_open is True
    # la table garde de la place (séparateur, largeur bornée)
    assert lib.table.width() > panel.width()
    assert not demo.errors


def test_c138_key_i_toggles_and_state_is_kept(demo):  # noqa: F811
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from djsync.settings import Settings
    from tests.qt_util import pump

    lib = _c138_library(demo)
    _c138_select(demo, lib, "Mon Survet")
    lib.table.setFocus()
    assert pump(demo, 1, lambda: lib.table.hasFocus())
    QTest.keyClick(lib.table, Qt.Key_I)
    assert pump(demo, 3, lambda: lib.info_panel.isVisible() and lib.info_panel.track is not None)
    demo.ctrl.settings.save()
    assert Settings.load().track_info_open is True
    QTest.keyClick(lib.table, Qt.Key_I)
    assert pump(demo, 2, lambda: not lib.info_panel.isVisible())
    assert demo.ctrl.settings.track_info_open is False
    assert Settings.load().track_info_open is False
    assert not demo.errors


def test_c138_follows_selection_one_load_per_track(demo):  # noqa: F811
    from tests.qt_util import pump

    lib = _c138_library(demo)
    lib.show_info(True)
    panel = lib.info_panel
    _c138_select(demo, lib, "Mon Survet")
    n = panel.loads
    other = _c138_select(demo, lib, "Umbrella")
    assert panel.track.content_id == other.content_id and panel.fields["title"].text() == "Umbrella"
    assert panel.loads == n + 1
    pump(demo, 0.3)
    assert panel.loads == n + 1                     # pas de rechargement sans changement
    assert not demo.errors


def test_c138_edit_shows_buttons_cancel_changes_nothing(demo):  # noqa: F811
    from tests.qt_util import pump

    lib = _c138_library(demo)
    lib.show_info(True)
    panel = lib.info_panel
    x = _c138_select(demo, lib, "Mon Survet")
    assert panel.edit_bar.isHidden()
    album = panel.fields["album"]
    assert album.isReadOnly()                        # affiché comme un texte
    album.start_edit()
    assert not album.isReadOnly()
    album.setText("Album C138")
    album.textEdited.emit("Album C138")
    assert not panel.edit_bar.isHidden() and panel.values() == {"album": "Album C138"}
    panel.cancel()
    assert panel.edit_bar.isHidden() and album.text() == (x.album or "") and not panel.dirty
    pump(demo, 0.5)
    assert next(t for t in lib.all_tracks if t.content_id == x.content_id).album == x.album
    assert not demo.errors


def test_c138_save_updates_library(demo):  # noqa: F811
    from tests.qt_util import pump

    lib = _c138_library(demo)
    lib.show_info(True)
    panel = lib.info_panel
    x = _c138_select(demo, lib, "Mon Survet")
    for key, value in (("title", "Mon Survet C138"), ("year", "2019"), ("genre", "Rap FR")):
        panel.fields[key].start_edit()
        panel.fields[key].setText(value)
        panel.fields[key].textEdited.emit(value)
    assert panel.values() == {"title": "Mon Survet C138", "year": 2019, "genre": "Rap FR"}
    panel.save_btn.click()
    assert pump(demo, 5, lambda: any(t.title == "Mon Survet C138" for t in lib.all_tracks))
    saved = next(t for t in lib.all_tracks if t.content_id == x.content_id)
    assert saved.year == 2019 and saved.genre == "Rap FR"
    assert pump(demo, 3, lambda: panel.edit_bar.isHidden() and not panel.dirty)
    assert panel.track.title == "Mon Survet C138"
    assert not demo.errors


def test_c138_changing_track_with_changes_asks(demo):  # noqa: F811
    from tests.qt_util import pump

    lib = _c138_library(demo)
    lib.show_info(True)
    panel = lib.info_panel
    x = _c138_select(demo, lib, "Mon Survet")
    e = panel.fields["artist"]
    e.start_edit()
    e.setText("Artiste C138")
    e.textEdited.emit("Artiste C138")
    # Rester : la sélection revient, les modifications restent
    _c138_select(demo, lib, "Umbrella")
    dlg = _c138_dialog(demo)
    dlg.stay_btn.click()
    assert pump(demo, 2, lambda: [r.data.content_id for r in lib.table.selected_rows()] == [x.content_id])
    assert panel.track.content_id == x.content_id and panel.dirty
    # Abandonner : l'autre son s'affiche, rien n'est écrit
    other = _c138_select(demo, lib, "Umbrella")
    _c138_dialog(demo).discard_btn.click()
    assert pump(demo, 3, lambda: panel.track is not None and panel.track.content_id == other.content_id)
    assert not panel.dirty
    assert next(t for t in lib.all_tracks if t.content_id == x.content_id).artist != "Artiste C138"
    # Enregistrer : écrit puis passe au son choisi
    e = panel.fields["artist"]
    e.start_edit()
    e.setText("Rihanna C138")
    e.textEdited.emit("Rihanna C138")
    _c138_select(demo, lib, "Mon Survet")
    _c138_dialog(demo).save_btn.click()
    assert pump(demo, 5, lambda: any(t.artist == "Rihanna C138" for t in lib.all_tracks))
    assert pump(demo, 3, lambda: panel.track is not None and panel.track.content_id == x.content_id)
    assert not demo.errors


def test_c138_computed_fields_are_read_only(demo):  # noqa: F811
    from PySide6.QtWidgets import QLineEdit

    lib = _c138_library(demo)
    lib.show_info(True)
    panel = lib.info_panel
    _c138_select(demo, lib, "Mon Survet")
    edits = panel.card.findChildren(QLineEdit)
    assert set(panel.fields) == {"title", "artist", "album", "year", "genre"}
    assert len(edits) == len(panel.fields)          # BPM, tonalité, format, chemin… : textes seulement
    # pas de modification possible du label, du BPM ou du chemin : aucune valeur hors des champs modifiables
    assert set(panel.values()) == set()
    assert panel.cues_lbl.text() and panel.gain_lbl.text() and panel.grid_lbl.text() != "…"
    assert not demo.errors


def test_c138_playlist_link_opens_playlist(demo):  # noqa: F811
    from tests.qt_util import pump

    lib = _c138_library(demo)
    lib.show_info(True)
    panel = lib.info_panel
    x = None
    for r in lib.table.all_rows():
        if lib._playlist_paths(r.data.content_id):
            x = r.data
            break
    assert x is not None
    _c138_select(demo, lib, x.title)
    assert pump(demo, 3, lambda: bool(getattr(panel, "pl_buttons", [])))
    pid = lib._playlist_paths(x.content_id)[0][0]
    panel.pl_buttons[0].click()
    assert pump(demo, 3, lambda: lib.current == f"p{pid}")
    assert panel.isVisible() and panel.track.content_id == x.content_id
    assert not demo.errors


def test_c138_width_is_bounded_at_860(demo):  # noqa: F811
    from djsync.ui import theme
    from djsync.ui.track_info_panel import MAX_SHARE, MIN_WIDTH, panel_width
    from tests.qt_util import pump

    demo.resize(860, 560)
    lib = _c138_library(demo)
    lib.show_info(True)
    pump(demo, 0.5)
    # plancher réel du volet : MIN_WIDTH, ou son contenu quand le zoom est réduit (Windows CI : 280 px)
    floor = max(theme.px(MIN_WIDTH), lib.info_panel.minimumSizeHint().width())
    pump(demo, 3, lambda: lib.info_panel.width() <= max(floor, int(lib.info_split.width() * MAX_SHARE)) + 2)
    total = lib.info_split.width() - lib.info_split.handleWidth()     # poignée du séparateur comprise
    panel = lib.info_panel
    assert panel.width() <= max(floor, int(total * MAX_SHARE)) + 2, (
        total, lib.info_split.sizes(), floor, lib.table.minimumSizeHint().width(), demo.width())
    # la table garde 300 px, ou tout ce qui reste quand le volet est à sa largeur minimale (Windows)
    assert lib.table.width() >= min(theme.px(300), total - floor) - 2
    _c138_select(demo, lib, "Mon Survet")
    pump(demo, 0.3)
    assert panel.card.minimumSizeHint().width() <= panel.scroll.viewport().width()   # rien de coupé (A2-1)
    assert panel_width(5000, 1000) == int(1000 * MAX_SHARE)
    assert panel_width(5000, 600) == max(theme.px(MIN_WIDTH), min(int(600 * MAX_SHARE), 600 - theme.px(300)))
    assert panel_width(5000, 450) == theme.px(MIN_WIDTH)
    assert not demo.errors
