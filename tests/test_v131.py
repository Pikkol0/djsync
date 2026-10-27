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


# ------------------------------------------------------------------ C38 : genre et label dans export.pdb
def _usb_with_genres(tmp_path):
    from sqlcipher3 import dbapi2 as sqlcipher

    from djsync.db._key import get_default_key

    from .test_pdb_sync import make_usb

    usb = make_usb(tmp_path)
    conn = sqlcipher.connect(str(usb / "PIONEER" / "rekordbox" / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("CREATE TABLE genre(genre_id integer primary key, name varchar)")
    conn.execute("CREATE TABLE label(label_id integer primary key, name varchar)")
    conn.commit()
    conn.close()
    return usb


def test_genre_and_label_are_written_to_export_pdb(tmp_path):
    from djsync.db.pdb import check
    from djsync.db.pdb.format import T

    from .test_pdb_sync import open_lib, pdb_of
    from .test_usb_library import make_wav

    usb = _usb_with_genres(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1], meta={"genre": "House", "label": "Defected"})
        b = lib.add_track(make_wav(lib, "B", "b"), "b", "B", None, None, [1], meta={"genre": "house"})
        assert lib.pdb_state == "ok"
    pdb = pdb_of(usb)
    ia, ib = pdb.track_info(a.path), pdb.track_info(b.path)
    assert (ia["genre"], ia["label"]) == ("House", "Defected") and ib["genre"] == "House"   # genre réutilisé
    assert sum(1 for _ in pdb.file.iter_rows(T.GENRES)) == 1
    lines = "\n".join(check.report(usb / "PIONEER" / "rekordbox" / "export.pdb"))
    assert "Layout recognised" in lines and "PROBLEM" not in lines and "INDEX:" not in lines, lines
    assert "genres" in lines and "rows 1" in lines.split("genres", 1)[1].splitlines()[0]


def test_genre_edit_and_missing_genre_are_caught_up(tmp_path):
    from sqlcipher3 import dbapi2 as sqlcipher

    from djsync.db._key import get_default_key

    from .test_pdb_sync import open_lib, pdb_of
    from .test_usb_library import make_wav

    usb = _usb_with_genres(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1])
        assert pdb_of(usb).track_info(a.path)["genre"] == ""
        lib.edit_track_metadata(a.content_id, genre="Techno")
        assert lib.pdb_state == "ok"
        assert pdb_of(usb).track_info(a.path)["genre"] == "Techno"
    # clé écrite avant la 1.3.1 : genre présent dans exportLibrary.db mais pas dans export.pdb
    db = usb / "PIONEER" / "rekordbox" / "exportLibrary.db"
    with open_lib(usb) as lib:
        lib.edit_track_metadata(a.content_id, genre="")
    conn = sqlcipher.connect(str(db))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("INSERT INTO genre (name) VALUES ('Disco')")
    conn.execute("UPDATE content SET genre_id = (SELECT genre_id FROM genre WHERE name = 'Disco')")
    conn.commit()
    conn.close()
    with open_lib(usb) as lib:
        st = lib.pdb_status()
        assert st.state == "stale" and st.changed_tracks == 1
        lib.pdb_catch_up()
        assert lib.pdb_status().state == "ok"
    assert pdb_of(usb).track_info(a.path)["genre"] == "Disco"


# ------------------------------------------------------------------ C28 : volet des réglages
def test_settings_sections_search_and_remembered_section(tmp_path, monkeypatch):
    from djsync.i18n import t
    from djsync.ui.views.settings_view import SECTIONS

    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.resize(1400, 900)
        app.show_view("settings")
        view = app.views["settings"]
        pump(app, 0.3)
        assert view.sections.count() == len(SECTIONS)
        seen = set()
        for key, _icon in SECTIONS:
            view.show_section(key)
            cards = view.visible_cards()
            assert cards, key                                    # chaque section a au moins une carte
            seen.update(id(c) for c in cards)
        assert len(seen) == len(view._cards)                     # chaque carte est dans une section
        assert app.ctrl.settings.settings_section == "djsync"
        view.show_section("analysis")
        assert view.analyze_usb_var.isVisibleTo(view)
        assert not view.update_var.isVisibleTo(view)
        # recherche dans toutes les sections
        view.search.setText("export.pdb")
        assert view.pdb_var.isVisibleTo(view) and not view.no_match.isVisibleTo(view)
        view.search.setText("zzzz introuvable")
        assert not view.visible_cards() and view.no_match.isVisibleTo(view)
        view.search.setText("")
        assert view.analyze_usb_var.isVisibleTo(view)
        # rapports d'erreur : section « Retours et confidentialité »
        view.show_section("privacy")
        assert view.report_menu.isVisibleTo(view)
        # fenêtre étroite : liste déroulante au lieu du volet
        app.resize(700, 700)
        pump(app, 0.3)
        assert view.section_menu.isVisibleTo(view) and not view.side.isVisibleTo(view)
        view.section_menu.setCurrentIndex(0)
        assert view._current_section == "general"
        assert t("settings.section_privacy")
        assert not app.errors
    finally:
        close_window(app)


def test_home_pdb_chip_opens_the_libraries_section(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.views["home"].open_settings("libraries")
        pump(app, 0.2)
        assert app._current == "settings" and app.views["settings"]._current_section == "libraries"
        assert app.views["settings"].pdb_var.isVisibleTo(app.views["settings"])
    finally:
        close_window(app)


# ------------------------------------------------------------------ C27 : espace occupé
def test_usb_usage_parts_and_safe_actions(tmp_path):
    from datetime import datetime, timedelta

    from djsync.core import space
    from djsync.db import backups

    root = tmp_path / "key"
    (root / "Contents" / "A").mkdir(parents=True)
    (root / "Contents" / "A" / "a.m4a").write_bytes(b"x" * 5000)
    (root / "PIONEER" / "rekordbox").mkdir(parents=True)
    (root / "PIONEER" / "rekordbox" / "exportLibrary.db").write_bytes(b"x" * 700)
    (root / "PIONEER" / "USBANLZ" / "P001").mkdir(parents=True)
    (root / "PIONEER" / "USBANLZ" / "P001" / "ANLZ0000.DAT").write_bytes(b"x" * 300)
    data = root / ".djsync" / "data"
    (data / "cache" / "grid").mkdir(parents=True)
    (data / "cache" / "grid" / "g.npz").write_bytes(b"x" * 900)
    (data / "settings.json").write_bytes(b"x" * 100)
    (root / "DJSync.exe").write_bytes(b"x" * 2000)
    bdir = root / "DJSync_Backups"
    pts = backups.points_dir(bdir)
    now = datetime(2026, 10, 27, 12, 0)
    for i, kind in enumerate(["origin", "manual"] + ["auto"] * 7):
        folder = pts / f"p{i:02d}-{kind}"
        folder.mkdir(parents=True)
        (folder / "exportLibrary.db").write_bytes(b"x" * 100)
        backups._write_meta(folder, kind, now - timedelta(days=10 - i), "", [], (1, 1))
    u = space.usb_usage(root, "Contents", data)
    p = u.parts
    assert list(p) == list(space.USB_PARTS)
    assert p["music"] == 5000 and p["databases"] == 700 and p["analysis"] == 300
    assert p["caches"] == 900 and p["app"] == 2100                     # cache compté à part
    assert p["backups"] >= 900 and p["free"] == u.free
    assert space.clear_caches(data) == 900 and not any((data / "cache").iterdir())
    kinds = lambda: sorted(x.kind for x in backups.list_points(bdir))    # noqa: E731
    assert kinds().count("auto") == 7
    removed, freed = space.trim_points(bdir, 5)
    assert removed == 2 and freed > 0
    assert kinds() == ["auto"] * 5 + ["manual", "origin"]               # origine et manuel gardés


def test_space_warnings_and_cache():
    from djsync.core import space

    u = space.Usage({"music": 50, "backups": 40, "free": 5}, total=100, free=5)
    assert u.warnings() == ["low_free", "heavy_backups"]
    c = space.UsageCache(seconds=60)
    u.at = __import__("time").time()
    c.put("k", u)
    assert c.get("k") is u
    c.drop("k")
    assert c.get("k") is None


def test_space_card_measures_when_shown_and_home_link(tmp_path, monkeypatch):
    from djsync.core import space

    from .qt_util import close_window, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        calls = []
        real = space.usb_usage
        monkeypatch.setattr(space, "usb_usage", lambda *a, **k: calls.append(a) or real(*a, **k))
        app.resize(1300, 900)
        app.show_view("settings")
        view = app.views["settings"]
        view.show_section("general")
        pump(app, 0.3)
        assert not calls                                         # pas mesuré tant que la carte est cachée
        app.show_view("home")
        app.views["home"].open_space()
        assert pump(app, 8, lambda: view.space.usage is not None)
        assert view._current_section == "libraries" and len(calls) == 1
        assert view.space.usage.parts["music"] > 0
        assert "music" in view.space.usage.folders
        view.show_section("general")
        view.show_section("libraries")
        pump(app, 0.3)
        assert len(calls) == 1                                   # résultat gardé quelques minutes
        view.space.compute(force=True)
        assert pump(app, 8, lambda: len(calls) == 2 and view.space.refresh_btn.isEnabled())
        assert not app.errors
    finally:
        close_window(app)
