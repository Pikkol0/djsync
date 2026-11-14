"""1.4.1-rc.2 : retours des tests de la rc.1 (B99, B100, B101, C195, C196, C190, GRI-2)."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from .qt_util import close_window, find, pump  # noqa: E402
from .test_v130rc3 import _demo_app  # noqa: E402


# ------------------------------------------------------------------ B99 : Doublons garde sa tâche
def test_b99_switching_diagnostic_tab_keeps_duplicates_running(tmp_path, monkeypatch):
    from djsync.ui.diag_tabs import DiagTabs
    from djsync.ui.duplicates_dialog import DuplicatesDialog
    from djsync.ui.missing_dialog import MissingFilesDialog

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        assert pump(app, 6, lambda: app.ctrl.has_library)
        app.show_view("library")
        app.views["library"]._duplicates()
        assert pump(app, 2, lambda: find(app, DuplicatesDialog) is not None)
        dup = find(app, DuplicatesDialog)
        dup.findChild(DiagTabs)._go("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        assert app.stack.indexOf(dup) >= 0 and dup.winfo_exists()          # toujours ouverte derrière
        find(app, MissingFilesDialog).findChild(DiagTabs)._go("dup")
        assert pump(app, 2, lambda: app.stack.currentWidget() is dup)      # la même page, pas recréée
        pages = [app.stack.widget(i) for i in range(app.stack.count())]
        assert sum(isinstance(p, DuplicatesDialog) for p in pages) == 1
        dup.findChild(DiagTabs)._go("missing")
        miss = find(app, MissingFilesDialog)
        miss.close()                                                         # Retour : vue d'origine
        assert pump(app, 2, lambda: app.stack.currentWidget() is app.views["library"])
        assert not app.errors
    finally:
        close_window(app)


# ------------------------------------------------------------------ B100, B101, C195, C196 : introuvables
def test_b100_cards_for_every_identical_version_scroll_listen_and_orphans(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QScrollArea

    from djsync.i18n import t
    from djsync.ui.missing_dialog import MissingFilesDialog

    app, _usb = _demo_app(tmp_path, monkeypatch)
    try:
        ctrl = app.ctrl
        assert pump(app, 6, lambda: ctrl.has_library)
        lib = ctrl.library
        by_title = {x.title: x for x in lib.list_tracks()}
        clip, song, vald = by_title["One More Time (Clip Officiel)"], by_title["One More Time"], by_title["Désaccordé"]
        lib.absolute_path(clip).unlink()          # durée différente : pas une « version » C173, mais un doublon
        lib.absolute_path(vald).unlink()
        app.open_diagnostic("missing")
        assert pump(app, 2, lambda: find(app, MissingFilesDialog) is not None)
        dlg = find(app, MissingFilesDialog)
        assert pump(app, 8, lambda: len(dlg.items) == 2)
        assert isinstance(dlg.detail_scroll, QScrollArea) and dlg.detail_scroll.widget() is dlg.detail   # B101
        items = {i.track.title: i for i in dlg.items}
        it = items[clip.title]
        assert song.content_id in [v.content_id for v in it.versions]                # B100 : carte affichée
        dlg._select(dlg.items.index(it))
        assert song.content_id in dlg._version_rows
        texts = [b.text() for b in dlg.detail.findChildren(type(dlg.apply_btn))]
        assert t("action.listen") in texts and t("missing.merge_with") in texts        # C196
        assert not any(t("missing.replace_by", title="", artist="", duration="")[:8] in x for x in texts)
        # C195 : le bouton compte les introuvables dans aucune playlist
        orphans = dlg.orphans()
        assert dlg.remove_orphans_btn.isEnabled() == bool(orphans)
        assert dlg.remove_orphans_btn.text() == t("missing.remove_orphans", n=len(orphans))
        assert not app.errors
    finally:
        close_window(app)


def test_c195_remove_orphans_leaves_offline_and_listed_ones():
    from types import SimpleNamespace as NS

    from djsync.ui.missing_dialog import MissingFilesDialog

    a = NS(playlists=[], offline=False, track=NS(content_id=1))
    b = NS(playlists=["House"], offline=False, track=NS(content_id=2))
    c = NS(playlists=[], offline=True, track=NS(content_id=3))
    fake = NS(items=[a, b, c])
    assert MissingFilesDialog.orphans(fake) == [a]


# ------------------------------------------------------------------ 141-GRI-2 : aimant et curseur fixe
def test_gri2_magnet_greyed_with_fixed_cursor_and_cursor_not_snapped():
    from types import SimpleNamespace as NS

    from djsync.ui.grid_editor import GridEditor

    beats = [((i % 4) + 1, 12000, 1000 + 500 * i) for i in range(16)]
    ed = NS(beats=beats, magnet=1, fixed_cursor=True)
    assert GridEditor.snap_ms(ed, 1230.0, cursor=True) == 1230.0          # curseur fixe : pas d'aimant
    ed.fixed_cursor = False
    assert GridEditor.snap_ms(ed, 1230.0, cursor=True) != 1230.0          # sinon : calé sur la grille


def test_c190_silver_is_a_steel_blue_distinct_from_grey_and_white():
    from PySide6.QtGui import QColor

    from djsync.ui import shine, theme

    c = QColor(theme.SILVER)
    assert c.blue() - c.red() > 60                                          # bleuté, plus un gris
    assert theme.SILVER.upper() not in {theme.TEXT.upper(), theme.DIM.upper(), "#FFFFFF"}
    assert shine.kind_of(theme.SILVER) == "silver"
