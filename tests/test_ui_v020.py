"""V0.2.0 : interface (fenêtre réelle, fausse clé de démonstration, aucun réseau).

Onglets, Accueil, « Tous les titres », statistiques, filtre harmonique, glisser vers une playlist,
file d'écoute (suivant / précédent), zoom à chaud, petite fenêtre, changement de langue sans
redémarrage, fenêtres Aide / Analyse / Doublons / Métadonnées.
    xvfb-run -a python -m pytest -q tests/test_ui_v020.py
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")

from djsync.db import UsbDrive  # noqa: E402
from djsync.settings import Settings  # noqa: E402

from .demo_fixture import make_demo_usb  # noqa: E402
from .test_ui_smoke import FakeService, pump  # noqa: E402


@pytest.fixture
def demo(tmp_path, monkeypatch):
    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    from djsync.ui.app import DJSyncApp

    try:
        window = DJSyncApp(Settings())
    except tk.TclError as exc:
        pytest.skip(f"pas d'écran disponible : {exc}")
    errors = []
    window.report_callback_exception = lambda *a: errors.append(a[1])
    window.errors = errors
    window.maxsize(4000, 4000)        # Xvfb (640 x 480 par défaut) : Tk borne sinon la fenêtre à l'écran
    window.geometry("1280x800+0+0")
    assert pump(window, 6, lambda: window.ctrl.has_library)
    # V0.2.2 : la fenêtre s'ouvre à la taille de l'écran ; Xvfb vaut 640 x 480 par défaut -> on
    # attend que la fenêtre agrandie ci-dessus soit prise en compte (barre latérale complète)
    pump(window, 3, lambda: window._compact is False)
    yield window
    window.ctrl.shutdown()
    window.destroy()


def _find(root, cls):
    for w in root.winfo_children():
        if isinstance(w, cls):
            return w
        hit = _find(w, cls)
        if hit:
            return hit
    return None


def test_tabs_home_and_english_default(demo):
    assert list(demo.views) == ["home", "search", "library", "downloads", "import", "settings"]
    assert demo._nav["home"].cget("text") == "Home" and demo.current == "home", (demo._compact, demo.winfo_width(), demo._logical_width(), demo.ctrl.settings.sidebar_compact)
    home = demo.views["home"]
    assert pump(demo, 8, lambda: home._summaries and home._summaries[0].tracks == 10)
    s = home._summaries[0]
    assert s.connected and s.playlists == 4 and s.unanalysed == 10 and s.total > 0
    # omnibar : texte -> Recherche ; lien -> Import
    home.omnibar.insert(0, "daft punk")
    home._go()
    assert demo.current == "search" and pump(demo, 8, lambda: demo.views["search"].table.count == 3)
    assert demo.ctrl.is_url("https://open.spotify.com/playlist/37i9dQZF1DX") and not demo.ctrl.is_url("daft punk")
    assert not demo.errors


def test_library_all_tracks_stats_harmonic_and_drag(demo):
    demo.show("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    assert lib.nav.item("all", "text").strip().startswith("All tracks")
    assert "10 tracks" in lib.sub_lbl.cget("text") and "min" in lib.sub_lbl.cget("text")
    # pastille Camelot dans la colonne #0 + tri par clé
    rows = {r.data.title: r for r in lib.table.all_rows()}
    assert rows["One More Time"].badge[0] == "11A" and rows["Sans analyse"].badge[0] == ""
    lib.table._heading_clicked(lib.table._tree_col)
    first = lib.table.displayed_rows()[0].data
    assert first.camelot == "1A"
    # filtre harmonique (11A : 11A, 10A, 12A, 11B)
    lib.set_harmonic(rows["One More Time"].data)
    shown = {r.data.camelot for r in lib.table.displayed_rows()}
    assert shown <= {"11A", "10A", "12A", "11B"} and len(lib.table.displayed_rows()) == 3
    lib._clear_harmonic()
    assert lib.table.count == 10
    # glisser vers la playlist « House » (3 sons) : + « Umbrella »
    house = next(p for p in lib.playlists if p.name == "House")
    iid = f"p{house.playlist_id}"
    lib.nav.see(iid)
    demo.update()
    x, y, _w, h = lib.nav.bbox(iid)
    umbrella = str(rows["Umbrella"].data.content_id)
    xr, yr = lib.nav.winfo_rootx() + x + 10, lib.nav.winfo_rooty() + y + h // 2
    assert lib._drag_over([umbrella], xr, yr)
    lib._drop_outside([umbrella], xr, yr)
    assert pump(demo, 4, lambda: any(p.name == "House" and p.track_count == 4 for p in lib.playlists))
    assert not demo.errors


def test_queue_next_previous_and_shortcut(demo):
    demo.show("library")
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
    assert demo.player_bar.next_btn.cget("state") == "normal"
    assert not demo.errors


def test_zoom_small_window_and_language_rebuild(demo):
    from djsync.ui import theme

    demo.ctrl.settings.zoom = 150
    demo.ctrl._emit("zoom")
    pump(demo, 0.5)
    assert abs(theme.ui_factor() - 1.5 * theme._AUTO) < 1e-6
    demo.ctrl.settings.zoom = 100
    demo.ctrl._emit("zoom")
    demo.geometry("780x520")
    assert pump(demo, 3, lambda: demo._compact is True)
    demo.show("library")
    lib = demo.views["library"]
    assert pump(demo, 3, lambda: lib.table.total == 10)
    pump(demo, 0.6)
    assert lib.table.hidden_columns                              # colonnes secondaires masquées
    demo.geometry("1280x800")
    assert pump(demo, 3, lambda: demo._compact is False)
    # langue : reconstruction sans redémarrage, la clé reste connectée
    demo.ctrl.settings.language = "fr"
    demo.ctrl._emit("rebuild_ui")
    pump(demo, 1.0)
    assert demo._nav["home"].cget("text") == "Accueil" and demo.ctrl.has_library
    assert pump(demo, 3, lambda: demo.views["library"].table.total == 10 or demo.current != "library")
    demo.ctrl.settings.language = "en"
    demo.ctrl._emit("rebuild_ui")
    pump(demo, 0.5)
    assert demo._nav["home"].cget("text") == "Home"
    assert not demo.errors


def test_dialogs_open(demo):
    from djsync.ui.analysis_dialog import AnalysisDialog
    from djsync.ui.dialogs import MetadataDialog
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.help_dialog import HelpDialog

    demo.open_help()
    assert pump(demo, 2, lambda: _find(demo, HelpDialog) is not None)
    _find(demo, HelpDialog).close()

    demo.views["home"]._duplicates()
    assert pump(demo, 2, lambda: _find(demo, DuplicatesDialog) is not None)
    dup = _find(demo, DuplicatesDialog)
    assert pump(demo, 4, lambda: len(dup.groups) == 1)
    assert {x.title for x in dup.current_group} == {"One More Time", "One More Time (Clip Officiel)"}
    assert dup.title_entry.get() == "One More Time" and dup.artist_entry.get() == "Daft Punk"
    dup.close()

    demo.show("library")
    lib = demo.views["library"]
    assert pump(demo, 4, lambda: lib.table.total == 10)
    lib.table.select(lib.table.displayed_iids()[:2])
    lib._analyse(lib._selected_tracks())
    assert pump(demo, 2, lambda: _find(demo, AnalysisDialog) is not None)
    an = _find(demo, AnalysisDialog)
    assert "2 tracks to analyse" in an.what.cget("text")
    an.close()
    lib.table.select(lib.table.displayed_iids()[:1])
    lib._edit_metadata()
    assert pump(demo, 2, lambda: _find(demo, MetadataDialog) is not None)
    md = _find(demo, MetadataDialog)
    md._title.delete(0, "end")
    md._title.insert(0, "Nouveau titre")
    md._ok()
    assert pump(demo, 4, lambda: any(x.title == "Nouveau titre" for x in lib.all_tracks))
    assert not demo.errors


def test_window_always_fits_the_screen_and_splash(tmp_path, monkeypatch):
    """V0.2.2 : la fenêtre ne dépasse jamais de l'écran (géométrie enregistrée trop grande ou sur
    un autre écran) ; l'écran de démarrage se ferme quand la fenêtre est prête."""
    import tkinter

    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    import djsync.ui.controller as controller

    monkeypatch.setattr(controller, "find_usb_drives", lambda: [])
    from djsync.ui import splash
    from djsync.ui.app import DJSyncApp

    screen = splash.show()
    if screen is None:
        pytest.skip("pas d'écran disponible")
    assert tkinter._default_root is None                  # la vraie fenêtre deviendra la racine
    s = Settings()
    s.geometry = "9000x6000+12000+40"
    app = DJSyncApp(s, splash=screen)
    try:
        pump(app, 0.6)
        sw, sh, _k = app._screen_logical()
        w, h = app.winfo_width(), app.winfo_height()
        assert w <= sw and h <= sh and 0 <= app.winfo_x() <= sw - 100
        assert screen.root is None
        assert tkinter._default_root is app
    finally:
        app.ctrl.shutdown()
        app.destroy()
