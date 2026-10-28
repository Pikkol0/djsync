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
        assert app.ctrl.settings.settings_section == "advanced"            # 1.3.1 (C89) : dernière section
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


def test_home_pdb_chip_opens_the_advanced_section(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        app.views["home"].open_settings("advanced")                  # 1.3.1 (C89) : export.pdb dans Avancé
        pump(app, 0.2)
        assert app._current == "settings" and app.views["settings"]._current_section == "advanced"
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


# ------------------------------------------------------------------ C41 / C43 : Diagnostic en onglets
def test_missing_files_tab_replace_relink_remove(tmp_path, monkeypatch):
    import shutil

    from djsync.ui.diag_tabs import DiagTabs
    from djsync.ui.missing_dialog import DOWNLOAD, RELINK, REMOVE, REPLACE, MissingFilesDialog

    from .qt_util import close_window, find, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        lib = ctrl.library
        by_title = {x.title: x for x in lib.list_tracks()}
        clip, umbrella, vald = by_title["One More Time (Clip Officiel)"], by_title["Umbrella"], by_title["Désaccordé"]
        lib.absolute_path(clip).unlink()                                     # supprimé
        moved = usb / "Contents" / "Rangé" / lib.absolute_path(umbrella).name
        moved.parent.mkdir(parents=True)
        shutil.move(str(lib.absolute_path(umbrella)), str(moved))            # dossier déplacé
        lib.absolute_path(vald).unlink()
        pls_umbrella = set(lib.playlists_of([umbrella.content_id])[umbrella.content_id])

        app.open_diagnostic("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        dlg = find(app, MissingFilesDialog)
        assert pump(app, 8, lambda: len(dlg.items) == 3)
        assert ctrl.diag_counts["missing"] == 3
        tabs = dlg.findChild(DiagTabs)
        assert "(3)" in tabs.buttons["missing"].text()
        items = {i.track.title: i for i in dlg.items}
        assert [c.title for c in items[clip.title].candidates] == ["One More Time"]
        assert items[umbrella.title].found == moved and not items[vald.title].candidates

        # remplacer le clip par la version présente
        dlg._select(dlg.items.index(items[clip.title]))
        assert dlg._choice.checkedId() == REPLACE * 1000
        dlg._apply()
        assert pump(app, 6, lambda: len(dlg.items) == 2)
        ids = {x.content_id for x in lib.list_tracks()}
        assert clip.content_id not in ids and by_title["One More Time"].content_id in ids

        # relier Umbrella à son fichier déplacé : même son, mêmes playlists
        dlg._select(dlg.items.index(items[umbrella.title]))
        assert dlg._choice.checkedId() == RELINK * 1000
        dlg._apply()
        assert pump(app, 6, lambda: len(dlg.items) == 1)
        x = lib.get_track(umbrella.content_id)
        assert lib.absolute_path(x) == moved and set(lib.playlists_of([x.content_id])[x.content_id]) == pls_umbrella
        if x.analysis_path:
            from djsync.analysis.anlz import read_path

            assert read_path(lib.absolute_path(x.analysis_path).read_bytes()) == x.path

        # retirer l'entrée (pas d'autre choix proposé par défaut que retélécharger / retirer)
        assert dlg._choice.button(DOWNLOAD * 1000) is not None
        dlg._choice.button(REMOVE * 1000).setChecked(True)
        dlg._apply()
        assert pump(app, 6, lambda: not dlg.items)
        assert vald.content_id not in {x.content_id for x in lib.list_tracks()}
        assert ctrl.diag_counts["missing"] == 0 and "(0)" in tabs.buttons["missing"].text()
        assert not app.errors
    finally:
        close_window(app)


def test_diagnostic_tabs_switch_between_tools(tmp_path, monkeypatch):
    from djsync.ui.diag_tabs import DiagTabs
    from djsync.ui.diagnostic_dialog import DiagnosticDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    from .qt_util import close_window, find, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.show_view("library")
        app.views["library"]._duplicates()                            # Outils ▸ Doublons : onglet Doublons
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None)
        dup = find(app, DuplicatesDialog)
        tabs = dup.findChild(DiagTabs)
        assert tabs.buttons["dup"].isChecked() and not tabs.buttons["missing"].isChecked()
        assert pump(app, 6, lambda: ctrl.diag_counts.get("uniformize") is not None)   # comptes rapides
        tabs._go("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None and find(app, DuplicatesDialog) is None)
        page = find(app, MissingFilesDialog)
        page.findChild(DiagTabs)._go("quality")
        assert pump(app, 2, lambda: find(app, DiagnosticDialog) is not None and find(app, MissingFilesDialog) is None)
        q = find(app, DiagnosticDialog)
        q.close()                                                       # Retour : vue d'origine
        assert pump(app, 2, lambda: app._current == "library" and app.stack.currentWidget() is app.views["library"])
        # Uniformiser : choix de la portée, puis page avec la même barre d'onglets
        app.open_diagnostic("dup")
        dup = find(app, DuplicatesDialog)
        app.open_uniformize(ctrl.library.list_tracks()[:2], "test")
        assert find(app, DuplicatesDialog) is None
        uni = app.uniformize_page
        assert uni.findChild(DiagTabs).buttons["uniformize"].isChecked()
        uni.findChild(DiagTabs)._go("dup")
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None and app.uniformize_page is None)
        assert not app.errors
    finally:
        close_window(app)


def test_relink_updates_export_pdb_and_playlists(tmp_path):
    import shutil

    from .test_pdb_sync import make_usb, open_lib, pdb_of
    from .test_usb_library import make_wav

    usb = make_usb(tmp_path)
    with open_lib(usb) as lib:
        a = lib.add_track(make_wav(lib, "A", "a"), "a", "A", None, None, [1, 2])
        new = usb / "Contents" / "Moved" / "a.wav"
        new.parent.mkdir(parents=True)
        shutil.move(str(lib.absolute_path(a)), str(new))
        x = lib.relink_track(a.content_id, new)
        assert x.path == "/Contents/Moved/a.wav" and lib.pdb_state == "ok", lib.pdb_problem
    pdb = pdb_of(usb)
    assert pdb.has_track("/Contents/Moved/a.wav") and not pdb.has_track(a.path)
    assert [p.rsplit("/", 1)[-1] for p in pdb.playlist_tracks(("Rap",))] == ["a.wav"]


def test_missing_file_message_links_to_the_diagnostic(tmp_path, monkeypatch):
    from djsync.ui.missing_dialog import MissingFilesDialog

    from .qt_util import close_window, find, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.show()
        ctrl._player_event("missing", str(usb / "Contents" / "x.m4a"))
        assert app.toast_action.isVisibleTo(app) and app.toast_action.text() == "See in the Diagnostic"
        app.toast_action.click()
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        ctrl.message("info", "other")
        assert not app.toast_action.isVisibleTo(app)
    finally:
        close_window(app)


# ------------------------------------------------------------------ C30 : suggestions
def _lt(cid, key, bpm, title="t", genre=""):
    from djsync.models import LibraryTrack

    return LibraryTrack(cid, title or f"t{cid}", "a", None, 200, f"/Contents/{cid}.m4a", bpm, 4, None, "", True,
                        key=key, genre=genre)


def test_suggestion_scores_key_bpm_half_double():
    from djsync.core.suggest import bpm_gap, key_relation, suggestions

    assert key_relation("8A", "8A") == "same" and key_relation("8A", "9A") == "near"
    assert key_relation("8A", "8B") == "relative" and key_relation("8A", "10A") == "none"
    assert key_relation("8A", "10A", energy=True) == "far"
    assert bpm_gap(140, 70) == (0.0, 2.0) and bpm_gap(124, 126)[0] == 1.6
    ref = _lt(1, "Am", 124.0, genre="House")                       # 8A
    pool = [ref, _lt(2, "Am", 124.0, "same"), _lt(3, "Em", 126.0, "near"), _lt(4, "C", 62.0, "relative half"),
            _lt(5, "Am", 140.0, "too fast"), _lt(6, "F#m", 124.0, "clash"), _lt(7, "Am", 0.0, "no bpm"),
            _lt(8, "Am", 124.0, "same genre", genre="house")]
    got = suggestions(ref, pool)
    assert [s.track.title for s in got] == ["same genre", "same", "relative half", "near"]
    assert got[2].ratio == 2.0 and got[3].key_reason == "near"
    assert "near" not in [s.track.title for s in suggestions(ref, pool, tolerance=1.0)]


def test_suggestions_panel_follows_selection_and_adds_to_playlist(tmp_path, monkeypatch):
    from .qt_util import close_window, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        app.resize(1500, 900)
        app.show_view("library")
        lib = app.views["library"]
        assert pump(app, 5, lambda: lib.table.total > 0)
        lib.sug_btn.click()
        assert lib.suggestions.isVisible() and ctrl.settings.suggestions_open
        ref = next(x for x in lib.all_tracks if x.title == "One More Time")
        lib.table.select([str(ref.content_id)])
        pump(app, 0.2)
        panel = lib.suggestions
        assert panel.ref.content_id == ref.content_id
        titles = [s.track.title for s in panel.items]
        assert titles and "One More Time" not in titles
        assert all(abs(s.bpm_gap) <= 6 for s in panel.items)
        assert panel.list.count() == len(panel.items)
        panel.tol.setValue(1)
        assert all(abs(s.bpm_gap) <= 1 for s in panel.items)
        assert ctrl.settings.suggest_tolerance == 1
        # playlist ouverte : « + » ajoute à la fin, « ✓ » si déjà dedans
        club = next(k for k, p in lib._by_iid.items() if p.name == "Club")
        lib._goto(club)
        assert pump(app, 4, lambda: lib.in_playlist and lib.table.total == 3)
        panel.tol.setValue(10)
        new = next(s.track for s in panel.items if lib.table.row(str(s.track.content_id)) is None)
        panel._add(new.content_id)
        assert pump(app, 6, lambda: lib.table.row(str(new.content_id)) is not None)
        # harmonic filter : BPM ± x %
        lib.set_harmonic(ref)
        n_all = lib.table.count
        lib.harm_bpm.setCurrentIndex(1)
        assert lib.table.count <= n_all
        lib._clear_harmonic()
        lib.show_suggestions(False)
        assert not lib.suggestions.isVisible() and not ctrl.settings.suggestions_open
        assert not app.errors
    finally:
        close_window(app)


def test_duplicates_tab_shows_quality_best_and_clean_versions(tmp_path, monkeypatch):
    from djsync.core.quality import AudioInfo
    from djsync.models import Candidate, TrackResult
    from djsync.ui.dialogs import ConfirmDialog
    from djsync.ui.duplicates_dialog import ALT, DuplicatesDialog

    from .qt_util import close_window, find, pump

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        infos = {}

        def quality(tracks, ok):
            for i, x in enumerate(tracks):
                infos[x.content_id] = AudioInfo("aac", 256 if i == 0 else 128, 44100)
            ok({x.content_id: infos[x.content_id] for x in tracks})

        monkeypatch.setattr(ctrl, "track_quality", quality)
        clean = TrackResult(video_id="C" * 11, title="One More Time", artist="Daft Punk", duration_seconds=320,
                            result_type="song")
        monkeypatch.setattr(ctrl, "find_alternatives", lambda track, ok: ok([Candidate(clean, 95.0)]))
        app.open_diagnostic("dup")
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None)
        dlg = find(app, DuplicatesDialog)
        assert pump(app, 10, lambda: dlg.groups and dlg.current_group)
        group = dlg.current_group
        texts = [dlg._info_labels[x.content_id].text() for x in group]
        assert any("256 kbps" in s for s in texts) and any("128 kbps" in s for s in texts)
        best = dlg._best(group)
        assert best is not None and dlg.keep_index() == group.index(best)          # meilleure qualité proposée
        title_before = dlg.title_entry.text()
        assert title_before                                                          # titre propre gardé
        dlg._find_alternatives()
        assert dlg._keep.button(ALT) is not None
        dlg._keep.button(ALT).setChecked(True)
        assert dlg.download_choice().track is clean
        dlg._apply()
        assert pump(app, 2, lambda: find(app, ConfirmDialog) is not None)
        calls = []
        monkeypatch.setattr(ctrl, "replace_with_download", lambda tr, old: calls.append((tr, list(old))) or object())
        find(app, ConfirmDialog)._ok()
        assert calls and calls[0][0] is clean and len(calls[0][1]) == len(group)
        assert not app.errors
    finally:
        close_window(app)
