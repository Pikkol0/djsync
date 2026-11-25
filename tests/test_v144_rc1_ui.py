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
