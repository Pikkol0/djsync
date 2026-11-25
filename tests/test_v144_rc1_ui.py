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
