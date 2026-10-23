"""Interface (fenêtre Qt réelle hors écran, fausse clé de démonstration, aucun réseau).

Onglets, Accueil, « Tous les titres », statistiques, filtre harmonique, glisser vers une playlist,
file d'écoute (suivant / précédent), zoom à chaud, petite fenêtre, changement de langue sans
redémarrage, fenêtres Aide / Analyse / Doublons / Métadonnées.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from djsync.db import UsbDrive  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .demo_fixture import make_demo_usb  # noqa: E402
from .qt_util import close_window, find, make_window, pump  # noqa: E402
from .test_ui_smoke import FakeService  # noqa: E402


@pytest.fixture
def demo(tmp_path, monkeypatch):
    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    window = make_window(Settings(), monkeypatch)
    assert pump(window, 6, lambda: window.ctrl.has_library)
    pump(window, 1, lambda: window._compact is False)
    yield window
    close_window(window)


def test_tabs_home_and_english_default(demo):
    assert list(demo.views) == ["home", "search", "library", "downloads", "import", "settings", "feedback"]
    assert demo._nav["home"].text() == "Home" and demo.current == "home"
    home = demo.views["home"]
    assert pump(demo, 8, lambda: home._summaries and home._summaries[0].tracks == 10)
    s = home._summaries[0]
    assert s.connected and s.playlists == 4 and s.unanalysed == 10 and s.total > 0
    # omnibar : texte -> Recherche ; lien -> Import
    home.omnibar.setText("daft punk")
    home._go()
    assert demo.current == "search" and pump(demo, 8, lambda: demo.views["search"].table.count == 3)
    assert demo.ctrl.is_url("https://open.spotify.com/playlist/37i9dQZF1DX") and not demo.ctrl.is_url("daft punk")
    assert not demo.errors


def test_library_all_tracks_stats_harmonic_and_drag(demo):
    from djsync.ui.views.library_view import ALL

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    assert lib._items[ALL].text(0).startswith("All tracks")
    assert "10 tracks" in lib.sub_lbl.text() and "min" in lib.sub_lbl.text()
    # colonne « Key » + tri par clé
    rows = {r.data.title: r for r in lib.table.all_rows()}
    assert rows["One More Time"].values["key"] == "11A" and rows["Sans analyse"].values["key"] == ""
    lib.table._heading_clicked(lib.table.column_index("key"))
    assert lib.table.displayed_rows()[0].data.camelot == "1A"
    # filtre harmonique (11A : 11A, 10A, 12A, 11B)
    lib.set_harmonic(rows["One More Time"].data)
    shown = {r.data.camelot for r in lib.table.displayed_rows()}
    assert shown <= {"11A", "10A", "12A", "11B"} and len(lib.table.displayed_rows()) == 3
    assert lib.banner.isVisible()
    lib._clear_harmonic()
    assert lib.table.count == 10
    # glisser vers la playlist « House » (3 sons) : + « Umbrella »
    house = next(p for p in lib.playlists if p.name == "House")
    lib._drop_on(house, [rows["Umbrella"].data.content_id])
    assert pump(demo, 4, lambda: any(p.name == "House" and p.track_count == 4 for p in lib.playlists))
    assert not demo.errors


def test_queue_next_previous(demo):
    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    ids = lib.table.displayed_iids()
    lib._play(ids[2])
    ctrl = demo.ctrl
    assert ctrl.queue_index == 2 and len(ctrl.queue) == 10
    ctrl.play_next()
    assert ctrl.queue_index == 3 and ctrl.current_item.item.content_id == int(ids[3])
    ctrl.play_previous()
    assert ctrl.queue_index == 2
    pump(demo, 1.0)
    assert demo.player_bar.next_btn.isEnabled()
    assert not demo.errors


def test_zoom_is_live_and_window_size_does_not_change_it(demo):
    from djsync.ui import theme

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total == 10)
    views_before = dict(demo.views)
    demo.ctrl.settings.zoom = 150
    demo.ctrl._emit("restyle")
    pump(demo, 0.3)
    assert theme.zoom() == 1.5 and demo.views == views_before          # pas de reconstruction
    assert lib.table.total == 10
    demo.ctrl.settings.zoom = 100
    demo.ctrl._emit("restyle")
    # petite fenêtre : barre latérale en icônes, le zoom ne bouge pas
    demo.resize(780, 520)
    assert pump(demo, 2, lambda: demo._compact is True)
    assert theme.zoom() == 1.0
    demo.resize(1280, 800)
    assert pump(demo, 2, lambda: demo._compact is False)
    # couleur : à chaud aussi
    demo.ctrl.settings.theme = "green"
    demo.ctrl._emit("restyle")
    assert demo.views == views_before
    assert not demo.errors


def test_language_rebuild(demo):
    demo.ctrl.settings.language = "fr"
    demo.ctrl._emit("rebuild_ui")
    pump(demo, 0.5)
    assert demo._nav["home"].text() == "Accueil" and demo.ctrl.has_library
    demo.show_view("library")
    assert pump(demo, 3, lambda: demo.views["library"].table.total == 10)
    demo.ctrl.settings.language = "en"
    demo.ctrl._emit("rebuild_ui")
    pump(demo, 0.3)
    assert demo._nav["home"].text() == "Home"
    assert not demo.errors


def test_dialogs_open(demo):
    from djsync.ui.analysis_dialog import AnalysisDialog
    from djsync.ui.track_info_dialog import TrackInfoDialog as MetadataDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.help_dialog import HelpDialog

    demo.open_help()
    assert pump(demo, 2, lambda: find(demo, HelpDialog) is not None)
    find(demo, HelpDialog).close()

    demo.views["home"]._duplicates()
    assert pump(demo, 2, lambda: find(demo, DuplicatesDialog) is not None)
    dup = find(demo, DuplicatesDialog)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    assert {x.title for x in dup.current_group} == {"One More Time", "One More Time (Clip Officiel)"}
    assert dup.title_entry.text() == "One More Time" and dup.artist_entry.text() == "Daft Punk"
    dup.close()

    demo.show_view("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    lib.table.select(lib.table.displayed_iids()[:2])
    an = AnalysisDialog(lib, demo.ctrl, lib._selected_tracks())     # lancement seulement
    assert "2 tracks to analyse" in an.what.text()
    an.close()
    lib.table.select(lib.table.displayed_iids()[:1])
    lib._edit_metadata()
    assert pump(demo, 2, lambda: find(demo, MetadataDialog) is not None)
    md = find(demo, MetadataDialog)
    md.title_e.setText("Nouveau titre")
    md._ok()
    assert pump(demo, 4, lambda: any(x.title == "Nouveau titre" for x in lib.all_tracks))
    assert not demo.errors


def test_window_always_fits_the_screen_and_splash(tmp_path, monkeypatch):
    """La fenêtre ne dépasse jamais de l'écran (géométrie enregistrée invalide ou sur un autre
    écran) ; l'écran de démarrage se ferme quand la fenêtre est prête."""
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [])
    from djsync.ui import splash
    from djsync.ui.app import DJSyncApp, qt_app

    qapp = qt_app()
    screen = splash.show(qapp)
    assert screen is not None and screen.widget.isVisible()
    s = Settings()
    s.geometry = "9000x6000+12000+40"                     # ancienne valeur (Tk) : ignorée
    app = DJSyncApp(s, splash=screen)
    try:
        app.reveal()
        pump(app, 0.2)
        area = qapp.primaryScreen().availableGeometry()
        assert app.width() <= area.width() and app.height() <= area.height()
        assert area.contains(app.geometry().topLeft())
        assert screen.widget is None
    finally:
        app.close()
