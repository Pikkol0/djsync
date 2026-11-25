"""1.4.4-rc.1 : tests ciblés des fiches d'interface (C216, C227, C226, C219, C220, C225, C215, C223, C138, A08…)."""
from __future__ import annotations

import pytest

from .test_v122 import demo, usb  # noqa: F401  (fixtures)


# ------------------------------------------------------------------ C216 : sons tapés ou collés, un par ligne
def test_c216_link_field_accepts_a_list(demo):  # noqa: F811
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from djsync.i18n import t

    view = demo.views["import"]
    demo.show_view("import")
    seen = []
    view._load_spotify = lambda pl: seen.append([x.title for x in pl.tracks])
    view.ctrl.import_url = lambda *a, **k: seen.append("url")
    h1 = view.url.height()
    view.url.setText("Rihanna - Umbrella")
    assert not view.url.is_link()
    # Entrée sur une liste : nouvelle ligne, pas de recherche
    view.url.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    view.url.insertPlainText("Daft Punk - One More Time\nAround the World")
    assert view.url.height() > h1 and not seen
    assert view.go.text() == t("import.search_many", n=3)
    # Ctrl+Entrée : recherche comme une playlist
    view.url.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier))
    assert seen and seen[0][0] == "Umbrella" and len(seen[0]) == 3


def test_c216_single_link_reads_on_enter_and_paste_is_an_icon(demo):  # noqa: F811
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from djsync.i18n import t

    view = demo.views["import"]
    seen = []
    view.ctrl.import_url = lambda url, ok, err: seen.append(url)
    view.url.setText("https://open.spotify.com/playlist/abc")
    assert view.url.is_link() and view.go.text() == t("import.read_link")
    view.url.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert seen == ["https://open.spotify.com/playlist/abc"]
    assert not hasattr(view, "paste_list")
    from PySide6.QtWidgets import QPushButton

    pastes = [b for b in view.findChildren(QPushButton) if b.toolTip() == t("action.paste")]
    assert pastes and all(not b.text() for b in pastes)


# ------------------------------------------------------------------ C231, C232 : cartes de l'Accueil allégées
def test_c231_c232_home_cards(demo):  # noqa: F811
    from PySide6.QtWidgets import QLabel, QPushButton

    from djsync.db import UsbDrive
    from djsync.i18n import t
    from djsync.ui.ctrl.library_ops import DriveSummary

    home = demo.views["home"]
    drive = UsbDrive(root=demo.ctrl.drive.root, label="DEMO")
    closed = home._card(DriveSummary(drive=drive, connected=False, tracks=-1, playlists=0, has_pdb=True))
    texts = [b.text() for b in closed.findChildren(QPushButton)]
    assert t("action.connect") in texts and t("diag.button") not in texts            # C231
    ok = home._card(DriveSummary(drive=drive, connected=True, tracks=3, playlists=1, has_pdb=True, pdb_state="ok"))
    labels = [x for x in ok.findChildren(QLabel)]
    assert not [x for x in labels if x.text() == t("home.pdb_short_yes")]            # C232 : plus de pastille
    assert any(x.text() == t("home.connected") and x.toolTip() == t("home.pdb_yes") for x in labels)
    assert t("diag.button") in [b.text() for b in ok.findChildren(QPushButton)]
    stale = home._card(DriveSummary(drive=drive, connected=True, tracks=3, playlists=1, has_pdb=True,
                                    pdb_state="stale", pdb_problem="x"))
    assert any(x.text() == t("home.pdb_stale") for x in stale.findChildren(QLabel))


# ------------------------------------------------------------------ C233, C234 : Grille et cues
def test_c233_c234_wave_height_and_style(demo):  # noqa: F811
    from djsync.ui import theme
    from djsync.ui.grid_editor import GridEditor

    from .qt_util import pump

    track = demo.ctrl.library.list_tracks()[0]
    seen = []
    demo.ctrl.on("waveform_style", lambda *a: seen.append(demo.ctrl.settings.waveform_style))
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        ed.setGeometry(0, 0, 1200, 900)
        ed.show()
        pump(demo, 0.3)
        assert ed.style_bar.buttons["3band"].isChecked()
        ed.style_bar.buttons["blue"].click()
        assert demo.ctrl.settings.waveform_style == "blue" and seen == ["blue"]
        assert ed.style_bar.buttons["blue"].isChecked() and not ed.style_bar.buttons["3band"].isChecked()
        sv = demo.views.get("settings")
        if sv is not None and hasattr(sv, "wave_style"):
            assert sv.wave_style.currentData() == "blue"                              # Paramètres suit
        ed.set_wave_height(150)
        pump(demo, 0.1)
        assert ed.canvas.height() == theme.px(150) and demo.ctrl.settings.grid_wave_height == 150
        ed.set_wave_height(5000)
        assert ed._wave_height == GridEditor.WAVE_MAX
        ed.height_grip.mouseDoubleClickEvent(None)
        assert demo.ctrl.settings.grid_wave_height == 0 and ed.canvas.maximumHeight() > 10000
    finally:
        ed.close()
        ed.deleteLater()


# ------------------------------------------------------------------ C226 : couleurs, fonds teintés, thèmes
def test_c226_palettes_backgrounds_and_themes(demo):  # noqa: F811
    import colorsys

    from djsync.i18n import t
    from djsync.ui import theme
    from djsync.ui.palettes import FAMILIES, FEATURED, PALETTES, THEMES

    from .qt_util import pump

    assert all(len(v) == 16 for v in FAMILIES.values()) and len(PALETTES) == 48
    for names in FAMILIES.values():                        # rangées par teinte, pas deux couleurs identiques
        assert len({PALETTES[n].upper() for n in names}) == 16
    assert {"navy", "brown", "fir", "prune"} <= set(theme.BACKGROUNDS)
    assert all(bg in theme.BACKGROUNDS and acc in PALETTES for bg, acc in THEMES.values())
    assert set(FEATURED) <= set(PALETTES) and len(FEATURED) == 7
    for k in list(PALETTES) + list(theme.BACKGROUNDS) + list(THEMES):
        key = (f"theme.{k}" if k in PALETTES else f"settings.background_{k}" if k in theme.BACKGROUNDS
               else f"themes.{k}")
        assert t(key) != key
    demo.show_view("settings")
    view = demo.views["settings"]
    assert set(view.theme_tiles) == set(THEMES) and len(view._featured) == 7
    view.theme_tiles["night"].click()
    pump(demo, 0.3)
    s = demo.ctrl.settings
    assert (s.background, s.theme) == ("navy", "sky") and theme.CURRENT_BACKGROUND == "navy"
    s.background, s.theme = "default", "violet_light"
    demo.ctrl._emit("restyle")
    pump(demo, 0.2)


# ------------------------------------------------------------------ C227 : accueil en un seul écran
def test_c227_welcome_single_screen(demo, monkeypatch):  # noqa: F811
    from djsync.ui.welcome import WelcomeDialog

    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    w = WelcomeDialog(demo, demo.ctrl)
    assert w.lang_buttons and len(w.theme_tiles) == 6 and w.yt_buttons and w.zoom_lbl
    assert w.skip_btn.property("kind") in (None, "") and w.skip_btn.width() == w.start_btn.width()
    w._pick_yt("best")
    w.theme_tiles["forest"].click()                         # thème appliqué, écran redessiné, choix gardé
    assert demo.ctrl.settings.background == "fir" and w.yt_buttons["best"].isChecked()
    z = demo.ctrl.settings.zoom
    w._zoom(1)
    assert demo.ctrl.settings.zoom > z
    quality = demo.ctrl.settings.download_quality
    w.skip_btn.click()                                      # Passer : rien d'autre n'est changé
    assert demo.ctrl.settings.welcome_done and demo.ctrl.settings.download_quality == quality
    s = demo.ctrl.settings
    s.background, s.theme, s.zoom = "default", "violet_light", z
    demo.ctrl._emit("restyle")


# ------------------------------------------------------------------ C236 : Doublons, pause et groupes choisis
def test_c236_duplicates_pause_manual_and_selection(demo):  # noqa: F811
    from djsync.i18n import t
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    from .qt_util import pump

    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    try:
        assert pump(demo, 4, lambda: len(dup.groups) >= 1)
        g = dup.groups[0]
        asked = []
        demo.ctrl.refine_duplicate_group = lambda group, done: asked.append(group)
        dup._refining = None
        dup.groups = [list(g) for _ in range(5)]
        dup.verified = [False] * 5
        dup.apart = [[] for _ in range(5)]
        dup._priority = []
        dup._fill_list()
        dup.auto_box.setChecked(False)                         # seulement à la demande : rien ne part
        assert demo.ctrl.settings.dup_auto_verify is False and not asked
        dup.list.clearSelection()
        dup.list.item(1).setSelected(True)
        dup.list.item(3).setSelected(True)
        assert dup._selected_todo() == [1, 3] and dup.verify_sel_btn.isVisibleTo(dup)
        dup.verify_selected()
        assert asked and dup._refining is dup.groups[1]        # premier choisi vérifié d'abord
        dup._refining = None
        dup.auto_box.setChecked(True)
        assert dup.pause_btn.isVisibleTo(dup)
        dup._toggle_pause()
        assert dup._paused and dup.pause_btn.text() == t("dup.resume")
        n = len(asked)
        dup._refining = None
        dup._priority = []
        dup._refine_next()
        assert len(asked) == n                                 # en pause : pas de groupe suivant
        dup._toggle_pause()
        assert not dup._paused and len(asked) == n + 1         # reprise : le suivant part
    finally:
        demo.ctrl.settings.dup_auto_verify = True
        dup.close()


# ------------------------------------------------------------------ C220 : réglage visé mis en valeur
def test_c220_settings_target_flashes(demo):  # noqa: F811
    from .qt_util import pump

    view = demo.views["settings"]
    demo._open_settings_section("libraries")
    pump(demo, 0.2)
    head = view._heads["libraries"]
    assert head.property("flashed") is True
    assert pump(demo, 3, lambda: head.property("flashed") is False)       # s'efface seul
    view.search.setText("export.pdb")
    pump(demo, 1.0)
    shown = [box for _s, box in view._cards if box.isVisibleTo(view)]
    assert shown and all(box.property("flashed") for box in shown)
    view.search.clear()


# ------------------------------------------------------------------ C223 : sons supprimés, retélécharger
def test_c223_deleted_tracks_listed_and_redownloaded(demo):  # noqa: F811
    from djsync.core.deleted_log import DeletedLog
    from djsync.ui.deleted_dialog import DeletedTracksDialog

    from .qt_util import pump

    lib = demo.ctrl.library
    track = next(x for x in lib.list_tracks() if x.title == "Umbrella")
    demo.ctrl.delete_tracks([track.content_id], delete_files=False)
    assert pump(demo, 6, lambda: bool(DeletedLog(lib.backup_dir).entries()))
    entry = DeletedLog(lib.backup_dir).entries()[0]
    assert entry.title == "Umbrella"
    d = DeletedTracksDialog(demo.views["library"], demo.ctrl)
    assert d.list.count() == 1
    seen = []
    view = demo.views["import"]
    view.analyse = lambda: seen.append(view.url.text())
    view.open_url = lambda url: seen.append(url)
    d.list.item(0).setSelected(True)
    d.redownload()
    assert seen == [entry.url or entry.query]
    assert demo.current == "import"
