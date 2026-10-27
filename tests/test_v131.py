"""1.3.1 : confort (C29 couleurs, C34 lecteur centré, C33 filtres, C37 colonnes, C28 réglages, C27 espace,
C30 suggestions, C38 genre dans export.pdb, C41/C43 Diagnostic, C42 qualité des doublons)."""
import pytest

pytest.importorskip("PySide6")

from .test_v130rc3 import _demo_app  # noqa: E402
from .test_usb_library import lib, usb  # noqa: E402,F401  (fixtures)


# ------------------------------------------------------------------ C29 / C42 : échelle de qualité
def test_quality_scale_thresholds():
    from djsync.ui import levels as L

    assert [L.similarity(p) for p in (95, 80, 60, 30)] == ["good", "fair", "warn", "bad"]
    assert [L.audio_quality(k) for k in (320, 256, 160, 96)] == ["good", "fair", "warn", "bad"]
    assert L.audio_quality(0, lossless=True) == "good" and L.audio_quality(0) == "neutral"
    assert [L.bpm_gap(p) for p in (1, -3, 5, 9)] == ["good", "fair", "warn", "bad"]
    assert L.quality_rank(0, True) > L.quality_rank(320) > L.quality_rank(128)


def test_audio_text_always_says_format_bitrate_and_rate():
    from djsync.core.quality import AudioInfo
    from djsync.ui import levels as L

    assert L.audio_text(AudioInfo("aac", 256, 44100), 4) == ("AAC · 256 kbps · 44.1 kHz", "fair")
    assert L.audio_text(AudioInfo("flac", 900, 48000), 5)[0] == "FLAC · lossless · 48 kHz"
    assert L.audio_text(None, 1) == ("MP3", "neutral")
    assert L.audio_text(AudioInfo("aac", 128, 44100), 4, missing=True) == ("?", "neutral")
    assert "320" in L.expected_download("ytmusic", "mp3")[0]


# ------------------------------------------------------------------ C34 : lecteur centré
@pytest.mark.parametrize("width", [1100, 1600, 2200])
def test_player_controls_are_centred_in_the_window(tmp_path, monkeypatch, width):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.resize(width, 800)
        pump(app, 0.3)
        bar = app.player_bar
        btn = bar.play_btn
        centre = btn.mapTo(bar, btn.rect().center()).x()
        assert abs(centre - bar.width() / 2) <= max(6, bar.width() * 0.01)
    finally:
        close_window(app)


# ------------------------------------------------------------------ C33 : un seul bouton de filtres
def test_search_has_one_filters_button_showing_active_filters(tmp_path, monkeypatch):
    from djsync.i18n import t
    from djsync.ui.dialogs import FiltersPopup

    from .qt_util import close_window

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        view = app.views["search"]
        assert not hasattr(view, "field_menu")
        assert view.filter_btn.text() == t("search.filters_short")
        got = {}
        monkeypatch.setattr(FiltersPopup, "show_dialog", lambda self: got.setdefault("dlg", self))
        view._open_filters()
        dlg = got["dlg"]
        dlg._field.setCurrentText(view._field_labels["artist"])
        dlg._minutes.setCurrentIndex(3)                      # ≤ 10 min
        dlg._apply()
        s = app.ctrl.settings
        assert s.search_field == "artist" and s.search_max_minutes == 10
        assert view.filter_btn.text() == f"{view._field_labels['artist']} · ≤ 10 min"
    finally:
        close_window(app)


# ------------------------------------------------------------------ C37 : toutes les colonnes, retenues
def test_usb_tracks_carry_genre_label_bitrate_and_more(lib):
    from .test_usb_library import make_wav

    with lib._write() as conn:
        conn.execute("CREATE TABLE genre(genre_id integer primary key, name varchar)")
        conn.execute("CREATE TABLE label(label_id integer primary key, name varchar)")
    lib._tables |= {"genre", "label"}
    t = lib.add_track(make_wav(lib, "Daft Punk", "a"), "One More Time", "Daft Punk", "Discovery",
                      meta={"genre": "Dance", "label": "Parlophone", "year": 2001})
    with lib._write() as conn:
        conn.execute("UPDATE content SET rating = 4, color_id = 5, djPlayCount = 7 WHERE content_id = ?",
                     (t.content_id,))
    x = lib.get_track(t.content_id)
    assert (x.genre, x.label, x.year, x.rating, x.color, x.play_count) == ("Dance", "Parlophone", 2001, 4, 5, 7)
    assert x.sample_rate > 0 and x.file_size > 0
    assert [y.genre for y in lib.list_tracks()] == ["Dance"]


def test_library_columns_button_order_and_no_auto_hiding(tmp_path, monkeypatch):
    from djsync.ui.views.library_view import EXTRA_COLUMNS

    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.show_view("library")
        lib = app.views["library"]
        assert pump(app, 5, lambda: lib.table.total > 0)
        table = lib.table
        assert set(EXTRA_COLUMNS) <= table._user_hidden                     # masquées par défaut
        keys = {c.key for c in table.optional_columns()}
        assert {"genre", "label", "year", "bitrate", "rate", "rating", "color", "plays", "path"} <= keys
        menu = lib.table.columns_menu(lib.cols_btn.mapToGlobal(lib.cols_btn.rect().bottomLeft()))
        assert lib.cols_btn.isVisible() and len(menu.actions()) > 12
        menu.close()
        for k in ("genre", "year", "label", "bitrate", "rate", "comment", "path", "size", "album"):
            table.set_column_visible(k, True)
        app.resize(900, 700)
        pump(app, 0.3)
        # colonne cochée = affichée, même à l'étroit : défilement horizontal au lieu de la masquer
        assert not table.hidden_columns
        for k in ("genre", "path", "artist"):
            assert not table.isColumnHidden(table.column_index(k))
        head = table.horizontalHeader()
        assert head.sectionsMovable()
        head.moveSection(head.visualIndex(table.column_index("genre")), 0)
        saved = ctrl.settings.table_layouts["library"]
        assert saved["order"][0] == "genre" and "genre" not in saved["hidden"]
        # tri sur une nouvelle colonne
        table._heading_clicked(table.column_index("bitrate"))
        assert table._sort_key == "bitrate"
        # retenu à la réouverture du tableau
        table.enable_layout("library", lambda: ctrl.settings.table_layouts, lambda: None,
                            ("album", "format") + EXTRA_COLUMNS, EXTRA_COLUMNS)
        assert table.column_order()[0] == "genre" and "path" not in table._user_hidden
        assert not app.errors
    finally:
        close_window(app)


def test_old_saved_layout_does_not_show_new_columns():
    from PySide6.QtWidgets import QApplication

    from djsync.ui.table import Column, TrackTable

    QApplication.instance() or QApplication([])
    cols = [Column("title", "T", 200, stretch=True), Column("album", "A"), Column("genre", "G")]
    store = {"library": {"hidden": [], "widths": {}}}                    # réglage 1.3.0 : album affiché
    table = TrackTable(None, cols)
    table.enable_layout("library", lambda: store, lambda: None, ("album", "genre"), ("genre",))
    assert table._user_hidden == {"genre"}


def test_extra_values_text():
    from djsync.models import LibraryTrack
    from djsync.ui.views.library_view import extra_values

    x = LibraryTrack(1, "t", "a", None, 200, "/Contents/a.m4a", 120.0, 4, None, "2026-01-01", True,
                     genre="House", year=2020, bitrate=256, sample_rate=44100, rating=3, color=2, play_count=4,
                     file_size=8_400_000)
    v = extra_values(x)
    assert v["rating"] == "★★★☆☆" and v["color__dot"] and "256" in v["bitrate"] and "44.1" in v["rate"]
    assert "8.4" in v["size"] and v["year"] == "2020" and v["path"] == "/Contents/a.m4a"
