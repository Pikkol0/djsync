"""1.4.1 (C140, D19) : entrée « Diagnostic » du volet, onglet « Un son », socle du volet (zone des entrées qui
défile, cartes en une ligne quand la hauteur manque, Aide et Réduire sur une ligne)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from djsync.i18n import t  # noqa: E402

from .qt_util import pump  # noqa: E402
from .test_ui_v024 import _app  # noqa: E402


@pytest.fixture
def demo(tmp_path, monkeypatch):
    from .qt_util import close_window

    window = _app(tmp_path, monkeypatch)
    yield window
    close_window(window)


def _tasks(win, n=2):
    reg = win.ctrl.tasks
    a = reg.start("analysis", "nav.analysing", icon="wave", order=0, linger=0, total=40, can_pause=True,
                  pause=lambda: None, resume=lambda: None, can_stop=True, stop=lambda: None)
    a.progress(12, 40, detail="Daft Punk - One More Time")
    if n > 1:
        d = reg.start("downloads", "nav.downloading", icon="download", order=1, linger=0, total=2,
                      can_pause=True, pause=lambda: None, resume=lambda: None, can_stop=True, stop=lambda: None,
                      show_title="always")
        d.progress(1, 2)
    return reg


def _crushed(win):
    """Libellés ou boutons du volet plus petits que ce qu'il leur faut (texte coupé, carte écrasée)."""
    from PySide6.QtWidgets import QAbstractButton, QLabel

    bar, out = win.sidebar, []
    for kind in (QLabel, QAbstractButton):
        for w in bar.findChildren(kind):
            if not w.isVisibleTo(bar) or w.width() <= 0:
                continue
            need = w.heightForWidth(w.width()) if w.hasHeightForWidth() else w.minimumSizeHint().height()
            if w.height() + 1 < need:
                out.append((type(w).__name__, w.text()[:20], w.height(), need))
            bottom = w.mapTo(bar, w.rect().bottomLeft()).y()
            if bottom > bar.height() and not win.nav_inner.isAncestorOf(w):
                out.append(("out", w.text()[:20]))
    return out


# ------------------------------------------------------------------ entrée du volet
def test_c140_diagnostic_entry_opens_one_track_and_stays_checked(demo):
    from djsync.ui.one_track_page import OneTrackPage

    nav = demo._nav
    keys = list(nav)
    assert keys.index("diagnostic") == keys.index("downloads") + 1          # place prévue par D10
    demo.ctrl.settings.diag_tab = "one"
    nav["diagnostic"].click()
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage))
    assert nav["diagnostic"].isChecked() and not nav["home"].isChecked()
    assert pump(demo, 5, lambda: demo.diag_total() is not None)             # compteurs connus à l'ouverture
    assert f"({demo.diag_total()})" in nav["diagnostic"].text()
    demo.open_diagnostic("dup")                                              # autre onglet : entrée toujours cochée
    assert pump(demo, 3, lambda: type(demo.stack.currentWidget()).__name__ == "DuplicatesDialog")
    assert nav["diagnostic"].isChecked()
    demo.show_view("library")
    assert not nav["diagnostic"].isChecked() and nav["library"].isChecked()
    assert not demo.errors


def test_c140_no_number_before_anything_is_counted(demo):
    demo.ctrl.diag_counts.clear()
    demo._badge()
    assert demo._nav["diagnostic"].text() == t("nav.diagnostic")


def test_c140_shortcuts_unchanged(demo):
    # 1.4.2 (C182) : raccourcis attachés aux pages (plus à leur position) ; volet court de 6 entrées
    from djsync.ui.app import NAV, SHORTCUT_KEYS, TABS

    assert [k for k, *_ in NAV] == ["home", "search", "library", "downloads", "diagnostic", "settings"]
    assert SHORTCUT_KEYS["library"] == 3 and SHORTCUT_KEYS["diagnostic"] == 5
    assert set(SHORTCUT_KEYS) == {k for k, *_ in TABS} | {"diagnostic"}
    assert sorted(SHORTCUT_KEYS.values()) == list(range(1, 10))


def test_c140_collapsed_one_icon_no_menu(demo):
    demo.ctrl.settings.sidebar_compact = "on"
    demo._compact = None
    demo._update_compact()
    pump(demo, 0.2)
    b = demo._nav["diagnostic"]
    assert b.text() == "" and b.toolTip().startswith(t("nav.diagnostic")) and b.menu() is None
    b.click()
    assert pump(demo, 3, lambda: type(demo.stack.currentWidget()).__name__ in
                ("OneTrackPage", "MissingFilesDialog", "DuplicatesDialog", "QualityPage"))
    demo.ctrl.settings.sidebar_compact = "auto"


# ------------------------------------------------------------------ onglet « Un son »
def test_c140_one_track_search_card_and_four_actions(demo):
    from djsync.ui.diag_tabs import TABS, DiagTabs
    from djsync.ui.one_track_page import OneTrackPage

    assert TABS[0] == "one"
    demo.open_diagnostic("one")
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage))
    page = demo.stack.currentWidget()
    tabs = page.findChild(DiagTabs)
    assert tabs is not None and tabs.buttons["one"].isChecked()
    assert pump(demo, 5, lambda: len(page.tracks) == 10)
    page.entry.setText("daft one")
    assert pump(demo, 2, lambda: len(page.shown) == 2)
    page.list.setCurrentRow(0)
    pump(demo, 0.3)
    assert page.track is not None and page.track.artist == "Daft Punk"
    buttons = [page.edit_btn, page.dup_btn, page.quality_btn, page.reveal_btn]
    assert all(b.isVisibleTo(page) for b in buttons)
    # sous les infos : le premier bouton est plus bas que la ligne « Fichier »
    assert page.edit_btn.mapTo(page, page.edit_btn.rect().topLeft()).y() > \
        page.file_lbl.mapTo(page, page.file_lbl.rect().topLeft()).y()
    assert pump(demo, 3, lambda: page.pl_lbl.text() not in ("", t("one.loading_short")))
    assert "House" in page.pl_lbl.text()
    # pas de cartes d'outils sur la page (D19) : les onglets les remplacent ; seuls boutons : onglets, Retour, 4 actions
    from PySide6.QtWidgets import QPushButton

    others = [b for b in page.findChildren(QPushButton) if b not in buttons and b not in tabs.buttons.values()]
    assert [b.text() for b in others] == [t("grid.back")]
    assert not demo.errors


def test_c140_one_track_comes_back_on_the_same_track(demo):
    from djsync.ui.one_track_page import OneTrackPage

    demo.open_diagnostic("one")
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage))
    page = demo.stack.currentWidget()
    assert pump(demo, 5, lambda: page.tracks)
    page.entry.setText("umbrella")
    assert pump(demo, 2, lambda: len(page.shown) == 1)
    page.list.setCurrentRow(0)
    cid = page.track.content_id
    demo.open_diagnostic("missing", from_page=page)                         # changement d'onglet
    assert pump(demo, 3, lambda: type(demo.stack.currentWidget()).__name__ == "MissingFilesDialog")
    demo.open_diagnostic("one", from_page=demo.stack.currentWidget())
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage))
    again = demo.stack.currentWidget()
    assert pump(demo, 5, lambda: again.track is not None and again.track.content_id == cid)


def test_c140_duplicates_action_opens_the_group_or_says_none(demo, monkeypatch):
    from djsync.ui.one_track_page import OneTrackPage

    demo.open_diagnostic("one")
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage))
    page = demo.stack.currentWidget()
    assert pump(demo, 5, lambda: page.tracks)
    page.entry.setText("umbrella")
    assert pump(demo, 2, lambda: len(page.shown) == 1)
    page.list.setCurrentRow(0)
    page._duplicates()
    assert pump(demo, 5, lambda: page.note.text() == t("one.no_duplicates"))
    page.entry.setText("one more time")
    assert pump(demo, 2, lambda: len(page.shown) == 2)
    page.list.setCurrentRow(0)
    seen = []
    import djsync.ui.duplicates_dialog as dd

    monkeypatch.setattr(dd, "DuplicatesDialog", lambda *a, **k: seen.append(k.get("focus_ids")))
    page._duplicates()
    assert pump(demo, 5, lambda: seen)
    assert page.track.content_id in seen[0] and len(seen[0]) == 2


def test_c140_quality_measures_this_track_only(demo, monkeypatch):
    from djsync.ui.one_track_page import OneTrackPage

    calls = []
    monkeypatch.setattr(demo.ctrl, "measure_quality",
                        lambda tracks, ok, progress=None, force=False: (calls.append((tracks, force)), ok(0), True)[-1])
    demo.open_diagnostic("one")
    assert pump(demo, 3, lambda: isinstance(demo.stack.currentWidget(), OneTrackPage))
    page = demo.stack.currentWidget()
    assert pump(demo, 5, lambda: page.tracks)
    page.list.setCurrentRow(0)
    page._quality()
    assert calls and len(calls[0][0]) == 1 and calls[0][1] is True
    assert page.note.text() == t("one.quality_ok")


def test_c140_search_helper():
    from djsync.models import LibraryTrack
    from djsync.ui.one_track_page import breakable, search

    def tr(i, title, artist, album=None):
        return LibraryTrack(i, title, artist, album, 180, f"/x/{i}.wav", 0, 1, None, "", False)

    tracks = [tr(1, "Umbrella", "Rihanna", "Good Girl Gone Bad"), tr(2, "One More Time", "Daft Punk"),
              tr(3, "Désaccordé", "Vald", "Agartha")]
    assert [x.content_id for x in search(tracks, "DAFT time")] == [2]
    assert [x.content_id for x in search(tracks, "girl")] == [1]                 # album
    assert [x.content_id for x in search(tracks, "désaccordé")] == [3]
    assert len(search(tracks, "")) == 3
    assert breakable("/a/b").replace("​", "") == "/a/b"


# ------------------------------------------------------------------ socle du volet (TAC-5)
@pytest.mark.parametrize("size, zoom, compact", [((1366, 697), 100, "off"), ((1366, 697), 125, "off"),
                                                 ((1366, 697), 125, "on"), ((1920, 1009), 200, "off"),
                                                 ((1920, 1009), 200, "on")])
def test_c140_sidebar_never_crushed(demo, size, zoom, compact):
    try:
        demo.ctrl.settings.zoom = zoom
        demo.ctrl.settings.sidebar_compact = compact
        demo.restyle()
        demo.resize(*size)
        _tasks(demo, 2)
        demo.open_diagnostic("one")
        pump(demo, 0.6)
        assert _crushed(demo) == [], (size, zoom, compact)
        if compact == "off" and zoom >= 125:
            assert demo.card_lines                                            # cartes en une ligne
            assert demo.an_box.cards["analysis"].line.isVisible()
            assert "12 / 40" in demo.an_box.cards["analysis"].line.full_text
            assert "Daft Punk" in demo.an_box.cards["analysis"].toolTip()     # détail dans la bulle
            assert demo.an_box.cards["analysis"].pause.isVisible()            # ⏸ ⏹ gardés
        # l'entrée cochée reste visible dans la zone qui défile
        b = demo._nav["diagnostic"]
        top = b.mapTo(demo.nav_area.viewport(), b.rect().topLeft()).y()
        assert 0 <= top and top + b.height() <= demo.nav_area.viewport().height() + 1
    finally:
        demo.ctrl.settings.zoom = 100
        demo.ctrl.settings.sidebar_compact = "auto"
        demo.restyle()


def test_c140_whole_cards_when_there_is_room(demo):
    demo.resize(1280, 800)
    _tasks(demo, 2)
    pump(demo, 0.6)
    assert not demo.card_lines
    assert demo.an_label.isVisible() and demo.an_bar.isVisible() and demo.usb_bar.isVisible()
    demo.resize(1366, 520)                    # fenêtre basse (1.4.2, C182 : volet court, le seuil a baissé)
    pump(demo, 0.6)
    assert demo.card_lines and not demo.an_bar.isVisible() and demo.usb_line.isVisible()
    demo.resize(1280, 800)
    pump(demo, 0.6)
    assert not demo.card_lines and demo.an_bar.isVisible()


def test_c140_help_and_collapse_on_one_line(demo):
    demo.ctrl.settings.sidebar_compact = "off"
    demo._compact = None
    demo._update_compact()
    pump(demo, 0.2)
    h, f = demo.help_btn, demo.fold_btn
    assert abs(h.mapTo(demo.sidebar, h.rect().center()).y() - f.mapTo(demo.sidebar, f.rect().center()).y()) <= 2
    assert f.text() == "" and f.toolTip() == t("nav.collapse")
    demo.ctrl.settings.sidebar_compact = "auto"
