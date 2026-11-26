"""1.4.4-rc.1 (lot 2) : C225 (Paramètres : une page par section, lignes lisibles, interrupteurs, Accessibilité)
et C219 (aide derrière un ⓘ, réglage « Afficher les infobulles »)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from djsync.i18n import t  # noqa: E402

from .qt_util import pump  # noqa: E402
from .test_v122 import demo, usb  # noqa: E402,F401  (fixtures)


def _c225_shown(view):
    return [box for _s, box in view._cards if box.isVisibleTo(view)]


# ------------------------------------------------------------------ C225 : une page par section
def test_c225_nine_sections_one_page_each(demo):  # noqa: F811
    from djsync.ui.views.settings_view import SECTIONS

    view = demo.views["settings"]
    demo.show_view("settings")
    assert [k for k, _i in SECTIONS] == ["general", "libraries", "download", "analysis", "accessibility", "storage",
                                         "privacy", "djsync", "advanced"]
    assert view.sections.count() == 9
    for key, _icon in SECTIONS:
        view.show_section(key)
        pump(demo, 0.05)
        shown = _c225_shown(view)
        assert shown and set(shown) == set(view.section_cards(key)), key
        assert view._heads[key].isVisibleTo(view) and view._current_section == key
        assert not any(h.isVisibleTo(view) for k, h in view._heads.items() if k != key)
    # un clic dans le volet ouvre la page
    view.sections.setCurrentRow(4)
    assert view._current_section == "accessibility" and view.ctrl.settings.settings_section == "accessibility"
    assert set(_c225_shown(view)) == set(view.section_cards("accessibility"))


def test_c225_cards_follow_the_plan(demo):  # noqa: F811
    view = demo.views["settings"]
    names = {key: [b.objectName() for b in view.section_cards(key)] for key in
             ("general", "accessibility", "storage", "advanced", "analysis")}
    assert names["general"] == ["card_interface", "card_performance", "card_playback"]
    assert names["accessibility"] == ["card_colors", "card_size", "card_help"]
    assert names["storage"] == ["card_backups", "card_space"]
    assert names["analysis"] == ["card_after", "card_grid", "card_volume", "card_display"]
    assert {"card_ffmpeg", "card_pdb_options", "card_engine", "card_tech", "card_analysis_adv"} <= set(names["advanced"])
    assert view.section_of(view.latency_box) == "general" and view.section_of(view.diag_auto_var) == "advanced"
    assert view.section_of(view.zoom_val) == "accessibility" and view.section_of(view.keep) == "storage"


def test_c225_search_covers_every_section_and_keeps_the_highlight(demo):  # noqa: F811
    view = demo.views["settings"]
    demo.show_view("settings")
    view.show_section("general")
    view.search.setText("soulseek")
    pump(demo, 1.0)
    shown = _c225_shown(view)
    assert shown and all(view.section_of(b) != "general" for b in shown)          # trouvé hors de la page
    assert view.slsk_var.isVisibleTo(view) and view._heads["download"].isVisibleTo(view)
    assert not any(b.property("flashed") for b in shown)                              # 1.4.4 (B132) : plus en recherche
    view.search.setText("ffmpeg")                                                       # carte repliée : ouverte
    assert view.ffmpeg.isVisibleTo(view)
    view.search.setText("zzzz-nothing")
    assert not _c225_shown(view) and view.no_match.isVisibleTo(view)
    view.search.clear()
    assert set(_c225_shown(view)) == set(view.section_cards("general"))                # retour à la page


def test_c225_links_open_the_right_page(demo):  # noqa: F811
    view = demo.views["settings"]
    demo._open_settings_section("diag_auto")
    pump(demo, 0.2)
    assert demo.current == "settings" and view._current_section == "advanced"
    assert view.diag_auto_var.isVisibleTo(view)
    card = view._card_of(view.diag_auto_var)
    assert card.property("flashed") is True
    demo.open_space()
    pump(demo, 0.3)
    assert view._current_section == "storage" and view.space_box.isVisibleTo(view)
    demo.views["home"].open_settings("pdb")
    pump(demo, 0.2)
    assert view._current_section == "libraries" and view.pdb_card.isVisibleTo(view)
    demo._open_settings_section("download")
    assert view._current_section == "download" and view.views_var.isVisibleTo(view)
    view.show_section("not-a-section")                                                  # sans effet
    assert view._current_section == "download"


def test_c225_switches_for_yes_no_settings(demo):  # noqa: F811
    from PySide6.QtWidgets import QCheckBox

    from djsync.ui.widgets import InfoDot, Switch

    view = demo.views["settings"]
    for name in ("analyze_usb_var", "analyze_local_var", "cue_var", "tags_var", "gain_var", "diag_auto_var",
                 "views_var", "meta_var", "pdb_var", "pdb_growth_var", "sc_original_var", "slsk_var",
                 "slsk_share_var", "watch_playlist_var", "protect_var", "update_var", "show_rc_var",
                 "shortcut_var", "tooltips_var"):
        sw = getattr(view, name)
        assert isinstance(sw, Switch) and isinstance(sw, QCheckBox), name
        assert sw.accessibleName() and not sw.text(), name
    # même clé interne, enregistrée tout de suite (A2-18)
    s = view.ctrl.settings
    before = s.write_tags
    view.tags_var.click()
    assert pump(demo, 2, lambda: s.write_tags != before)
    view.tags_var.click()
    assert pump(demo, 2, lambda: s.write_tags == before)
    # libellé à gauche, ⓘ à côté, contrôle aligné à droite
    view.show_section("analysis")
    demo.resize(1280, 800)
    pump(demo, 0.3)
    card = view._card_of(view.tags_var)
    dots = [d for d in card.findChildren(InfoDot) if d.isVisibleTo(view)]
    assert dots and any(d.help_text == t("settings.write_tags_hint") for d in dots)
    right = card.mapFromGlobal(view.tags_var.mapToGlobal(view.tags_var.rect().topRight())).x()
    assert right > card.width() - 40


@pytest.mark.parametrize("size", [(860, 560)])
def test_c225_every_page_fits_at_860(demo, size):  # noqa: F811
    from PySide6.QtWidgets import QWidget

    from djsync.ui.views.settings_view import SECTIONS

    demo.resize(*size)
    demo.show_view("settings")
    view = demo.views["settings"]
    for key, _icon in SECTIONS:
        view.show_section(key)
        pump(demo, 0.2)
        page = view.area.widget()
        room = view.area.viewport().width() + 1
        wide = [(type(w).__name__, w.minimumSizeHint().width()) for w in page.findChildren(QWidget)
                if w.isVisibleTo(page) and not w.layout() and w.minimumSizeHint().width() > room]
        assert page.minimumSizeHint().width() <= room and not wide, (key, wide)


# ------------------------------------------------------------------ C219 : ⓘ et réglage des infobulles
def test_c219_info_dot_hover_and_click_keeps_the_bubble(demo):  # noqa: F811
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QPushButton

    from djsync.ui.widgets import InfoDot, tooltip_filter

    view = demo.views["settings"]
    demo.show_view("settings")
    view.show_section("analysis")
    pump(demo, 0.2)
    dot = next(d for d in view.findChildren(InfoDot) if d.isVisibleTo(view))
    assert dot.toolTip() == dot.help_text and dot.accessibleName()                       # survol : le texte
    dot.click()
    assert dot.is_open() and dot.bubble.text.text() == dot.help_text
    pump(demo, 0.3)
    assert dot.is_open()                                                                  # reste affichée
    dot.click()                                                                           # clic suivant : fermée
    assert not dot.is_open()
    dot.click()
    assert dot.is_open() and tooltip_filter().installed                                   # posé le temps de la bulle
    other = next(b for b in view.findChildren(QPushButton) if b.isVisibleTo(view))
    press = QMouseEvent(QEvent.MouseButtonPress, QPoint(2, 2), other.mapToGlobal(QPoint(2, 2)), Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(other, press)                                                  # clic ailleurs : fermée
    assert not dot.is_open() and not tooltip_filter().installed
    dot.click()
    view.show_section("general")                                                          # page quittée : fermée
    pump(demo, 0.1)
    assert not dot.is_open()


def test_c219_tooltips_off_blocks_ordinary_tooltips_not_info_dots(demo):  # noqa: F811
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent

    from djsync.settings import Settings
    from djsync.ui.widgets import InfoDot, button, tooltip_filter, tooltips_enabled

    view = demo.views["settings"]
    s = view.ctrl.settings
    assert s.show_tooltips is True and tooltips_enabled()
    f = tooltip_filter()
    plain = button("x", tooltip="Plain tip")
    dot = InfoDot("Help text")

    def tip(w):
        return QHelpEvent(QEvent.ToolTip, QPoint(1, 1), w.mapToGlobal(QPoint(1, 1)))

    assert not f.eventFilter(plain, tip(plain))
    assert not f.installed                                     # rien posé sur l'app tant qu'il ne sert pas
    view.tooltips_var.click()                                                             # non : tout de suite
    assert s.show_tooltips is False and not tooltips_enabled() and f.installed
    assert f.eventFilter(plain, tip(plain))                                               # infobulle bloquée
    assert not f.eventFilter(dot, tip(dot))                                               # ⓘ toujours actif
    assert Settings.load().show_tooltips is False                                         # réglage enregistré
    demo.rebuild_ui()                                                                     # repris à la reconstruction
    assert not tooltips_enabled() and demo.views["settings"].tooltips_var.isChecked() is False
    demo.views["settings"].tooltips_var.click()
    assert s.show_tooltips is True and tooltips_enabled() and not f.eventFilter(plain, tip(plain))
    assert not f.installed
    plain.deleteLater()
    dot.deleteLater()


def test_c219_setting_normalized_and_reset():
    from djsync.settings import Settings

    s = Settings()
    assert s.show_tooltips is True
    s.show_tooltips = 0
    s.normalize()
    assert s.show_tooltips is False
    s.reset_to_defaults()
    assert s.show_tooltips is True


def test_c219_strings_translated():
    from djsync.i18n import en, fr

    for key in ("settings.show_tooltips", "settings.show_tooltips_tip", "settings.page_accessibility",
                "settings.card_help", "settings.page_storage"):
        assert key in en.STRINGS and key in fr.STRINGS and en.STRINGS[key] != fr.STRINGS[key]


def test_c219_grid_waveform_help_behind_an_info_dot(demo):  # noqa: F811
    from djsync.ui.grid_editor import GridEditor

    track = demo.ctrl.library.list_tracks()[0]
    ed = GridEditor(demo, demo.ctrl, track)
    try:
        ed.setGeometry(0, 0, 1200, 900)
        ed.show()
        pump(demo, 0.3)
        assert not ed.canvas.toolTip()                         # plus de bulle à chaque survol de la forme d'onde
        assert ed.canvas_help.help_text == t("grid.hint") and ed.canvas_help.isVisibleTo(ed)
        assert ed.canvas_help.parentWidget() is ed.style_bar
    finally:
        ed.close()
        ed.deleteLater()
