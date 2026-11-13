"""1.3.2-rc.2 : correctifs des tests de la rc.1 (auteur, 02/11) et signalements de testeurs."""
from __future__ import annotations

from .test_v122 import demo, usb  # noqa: F401
from .qt_util import pump


# ------------------------------------------------------------------ C58 : boutons visibles
def test_action_button_is_really_painted():
    """Le bouton (fond + icône) est dessiné : avant, l'icône était perdue et la cellule restait vide."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

    from djsync.ui.table import Row, TrackTable, _ButtonDelegate
    from djsync.ui.views.common import result_columns

    app = QApplication.instance() or QApplication([])
    table = TrackTable(None, result_columns(), click_columns=("dl",))
    table.resize(900, 300)
    table.set_rows([Row("1", {"title": "T", "artist": "A", "dl": "1"})])
    app.processEvents()
    col = table.column_index("dl")
    delegate = table.itemDelegateForColumn(col)
    assert isinstance(delegate, _ButtonDelegate)
    img = QImage(60, 40, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    painter = QPainter(img)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 60, 40)
    opt.widget = table
    delegate.paint(painter, opt, table.model().index(0, col))
    painter.end()
    colours = {img.pixel(x, y) for x in range(0, 60) for y in range(0, 40)}
    assert len(colours) > 5, "bouton non dessiné"
    table.close()


# ------------------------------------------------------------------ B39 : pas de vide à droite
def test_button_column_never_fills_the_rest():
    from PySide6.QtWidgets import QApplication

    from djsync.ui.table import Row, TrackTable
    from djsync.ui.views.common import result_columns

    app = QApplication.instance() or QApplication([])
    store = {"search": {"hidden": [], "widths": {"title": 60}}}          # titre réduit (cas de la capture)
    table = TrackTable(None, result_columns(), show_covers=True, click_columns=("dl",))
    table.enable_layout("search", lambda: store, lambda: None)
    table.resize(1600, 700)
    table.show()
    table.set_rows([Row(str(i), {"title": f"T{i}", "artist": "A", "type": "Song", "views": "1", "duration": "3:00",
                                 "lib": "", "source": "YouTube", "dl": "1"}) for i in range(4)])
    for _ in range(10):
        app.processEvents()
    head = table.horizontalHeader()
    dl, title = table.column_index("dl"), table.column_index("title")
    assert head.sectionSize(dl) <= table._width(table.columns[dl]) + 8
    assert head.sectionSize(title) > 600
    table.close()


# ------------------------------------------------------------------ B46 : ronds à tout zoom
def test_round_shapes_stay_round_at_any_zoom():
    import re

    from djsync.ui import theme

    for zoom in (80, 100, 150, 180, 200):
        theme.set_zoom(zoom)
        css = theme.stylesheet()
        handle = re.search(r"QSlider::handle:horizontal \{ width: (\d+)px; margin: -(\d+)px 0;[^}]*border-radius: (\d+)px", css)
        w, m, r = (int(x) for x in handle.groups())
        groove = theme.px(4)
        assert 2 * r <= min(w, groove + 2 * m)
        play_r = int(re.search(r'QToolButton\[kind="primary"\][^}]*border-radius: (\d+)px', css).group(1))
        assert 2 * play_r <= theme.px(34)
    theme.set_zoom(100)


# ------------------------------------------------------------------ C56 : glisser depuis « Hors playlist »
def test_drag_from_not_in_playlist_onto_a_playlist(demo):  # noqa: F811
    from PySide6.QtCore import QByteArray, QMimeData, QPointF, Qt
    from PySide6.QtGui import QDragMoveEvent, QDropEvent

    from djsync.ui.table import MIME_IDS
    from djsync.ui.views.library_view import ALL, ORPH

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > 0)
    assert pump(demo, 4, lambda: getattr(lib, "_orphans", None))
    lib._goto(ALL)
    assert "hors playlist" in lib.sub_lbl.text().lower() or "not in a playlist" in lib.sub_lbl.text().lower()
    lib._goto(ORPH)
    pump(demo, 0.3)
    ids = lib.table.displayed_iids()
    house = next(p for p in lib.playlists if p.name == "House")
    rect = lib.nav.visualItemRect(lib._items[f"p{house.playlist_id}"])
    mime = QMimeData()
    mime.setData(MIME_IDS, QByteArray(ids[0].encode()))
    lib.nav.dragMoveEvent(QDragMoveEvent(rect.center(), Qt.CopyAction | Qt.MoveAction, mime, Qt.LeftButton,
                                         Qt.NoModifier))
    assert lib.current == ORPH                         # survoler une playlist ne l'ouvre plus
    lib.nav.dropEvent(QDropEvent(QPointF(rect.center()), Qt.CopyAction | Qt.MoveAction, mime, Qt.LeftButton,
                                 Qt.NoModifier))
    assert pump(demo, 4, lambda: any(p.name == "House" and p.track_count == house.track_count + 1
                                     for p in lib.playlists))
    assert pump(demo, 6, lambda: int(ids[0]) not in (lib._orphans or set()))
    assert not demo.errors


# ------------------------------------------------------------------ B36 : premier plan refusé
class _StrictUser32:
    """Windows qui refuse SetForegroundWindow tant que le fil n'est pas attaché au premier plan."""

    def __init__(self, attach_works: bool):
        self.front, self.attached, self.attach_works, self.calls = 7, False, attach_works, []

    def GetForegroundWindow(self):  # noqa: N802
        return self.front

    def SetWindowPos(self, *a):  # noqa: N802
        pass

    def GetWindowThreadProcessId(self, hwnd, _pid):  # noqa: N802
        return 100

    def AttachThreadInput(self, ours, theirs, on):  # noqa: N802
        self.calls.append(("attach", on))
        self.attached = on and self.attach_works
        return 1

    def BringWindowToTop(self, hwnd):  # noqa: N802
        pass

    def SetForegroundWindow(self, hwnd):  # noqa: N802
        if self.attached:
            self.front = hwnd

    def keybd_event(self, *a):  # noqa: N802
        self.calls.append(("alt",) + a[:3])
        self.attached = True                          # l'entrée clavier rend le premier plan possible

    def FlashWindowEx(self, info):  # noqa: N802
        self.calls.append(("flash",))


class _Kernel32:
    def GetCurrentThreadId(self):  # noqa: N802
        return 200


def test_foreground_refused_then_obtained_by_attaching(monkeypatch):
    from djsync.ui import foreground as F

    u = _StrictUser32(attach_works=True)
    assert F.bring_to_front(42, u, _Kernel32()) == "raised"
    assert ("attach", True) in u.calls and u.calls[-1] == ("attach", False)       # toujours détaché ensuite
    u = _StrictUser32(attach_works=False)
    assert F.bring_to_front(42, u, _Kernel32()) == "raised"                        # puis la touche Alt
    assert ("alt", F.VK_MENU, 0, F.KEYEVENTF_KEYUP) in u.calls


def test_foreground_retried_after_the_splash_closes(monkeypatch):
    import sys

    from djsync.ui import foreground as F

    monkeypatch.setattr(sys, "platform", "win32")
    tries, delays = [], []
    monkeypatch.setattr(F, "bring_to_front", lambda hwnd: tries.append(hwnd))

    class W:
        def winId(self):  # noqa: N802
            return 5

    F.ensure_front(W(), lambda ms, fn: (delays.append(ms), fn()))
    assert delays == [300, 1000] and tries == [5, 5, 5]


# ------------------------------------------------------------------ B44 : accueil
def test_welcome_language_needs_confirm_and_star_is_primary(demo, monkeypatch):  # noqa: F811
    from djsync.ui.welcome import WelcomeDialog

    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    w = WelcomeDialog(demo, demo.ctrl)
    w._pick("fr" if demo.ctrl.settings.language == "en" else "en")
    assert w._step == 1                                   # un clic choisit, ne passe pas à la suite
    w._pick(demo.ctrl.settings.language)
    w.validate_btn.click()
    assert w._step == 2
    assert w.star_btn.property("kind") == "primary"
    assert w.width() >= w.minimumWidth() > 0
    w._finish()
    assert not demo.errors


# ------------------------------------------------------------------ C119, C68
def test_thanks_and_first_steps_without_faq():
    from djsync.credits import THANKS
    from djsync.i18n import en, fr

    assert THANKS == ["Tazyh"]
    assert not any(k.startswith(("start.faq", "start.q")) for k in list(en.STRINGS) + list(fr.STRINGS))


# ------------------------------------------------------------------ C70, C121 : Paramètres
def test_settings_one_page_with_anchors(demo):  # noqa: F811
    from djsync.ui.views.settings_view import SECTIONS

    demo.resize(1300, 800)
    demo.show_view("settings")
    view = demo.views["settings"]
    pump(demo, 0.3)
    assert all(not box.isHidden() for _s, box in view._cards)            # tout sur une page
    bar = view.area.verticalScrollBar()
    for key, _icon in SECTIONS:
        view.show_section(key)
        pump(demo, 0.05)
        assert bar.value() == min(bar.maximum(), view._heads[key].y()), key
    view.show_section("general")
    bar.setValue(view._heads["download"].y() + 5)                         # défilement à la main
    pump(demo, 0.05)
    assert view._current_section == "download"
    djsync_cards = view.section_cards("djsync")
    assert any(view.shortcut_var in box.findChildren(type(view.shortcut_var)) for box in djsync_cards)
    assert not any(view.shortcut_var in box.findChildren(type(view.shortcut_var))
                   for box in view.section_cards("privacy"))
    assert not demo.errors


# ------------------------------------------------------------------ C96 : liste des versions dans la carte
def test_versions_dropdown_in_settings(demo, monkeypatch):  # noqa: F811
    from djsync.core.updates import Update
    from djsync.ui import version_dialog

    ctrl = demo.ctrl
    vs = [Update("9.9.0", "u", False, "a", "c", "2026-11-01"), Update("1.0.0", "u", False, "a", "c")]
    asked = []
    monkeypatch.setattr(ctrl, "app_versions", lambda pre, ok, failed=None: (asked.append(pre), ok(vs)))
    monkeypatch.setattr(ctrl, "can_self_update", lambda: True)
    installed = []
    monkeypatch.setattr(ctrl, "app_update_install", installed.append)
    demo.show_view("settings")
    view = demo.views["settings"]
    view.load_versions()
    assert view.version_menu.count() == 2 and view.version_menu.isEnabled()
    view.version_menu.setCurrentIndex(0)
    assert view.version_install_btn.isEnabled() and "9.9.0" in view.version_install_btn.text()
    view.version_install_btn.click()
    assert [u.version for u in installed] == ["9.9.0"]
    view.show_rc_var.setChecked(not view.show_rc_var.isChecked())        # liste relue
    assert len(asked) == 2
    assert version_dialog.version_text(vs[0], "9.9.0").endswith(version_dialog.t("update.pick_installed"))
    assert not demo.errors


# ------------------------------------------------------------------ C57 : « Annuler » après la remise à zéro
def test_reset_message_and_undo_after_rebuild(demo, monkeypatch):  # noqa: F811
    from djsync.ui.dialogs import ConfirmDialog

    monkeypatch.setattr(demo.ctrl.settings, "save", lambda *a, **k: None)
    made = []
    real_init = ConfirmDialog.__init__

    def spy(self, *a, **k):
        real_init(self, *a, **k)
        made.append(self)

    monkeypatch.setattr(ConfirmDialog, "__init__", spy)
    demo.show_view("settings")
    demo.views["settings"]._reset_defaults()
    made[-1]._ok()
    assert pump(demo, 3, lambda: demo.toast_action.isVisibleTo(demo))
    assert demo.toast.isVisibleTo(demo) and demo.toast.geometry().intersects(demo.stack.rect())
    assert not demo.errors


# ------------------------------------------------------------------ B47 : Retour ne ferme pas Doublons
def test_back_keeps_the_duplicates_page(demo):  # noqa: F811
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    demo.show_view("library")
    page = DuplicatesDialog(demo, demo.ctrl)
    assert demo.stack.currentWidget() is page
    page.go_back()
    assert demo.stack.currentWidget() is demo.views["library"]
    assert page.winfo_exists() and demo.stack.indexOf(page) >= 0        # toujours ouverte, en arrière-plan
    assert demo.reopen_dialog_page(DuplicatesDialog) is page
    page.close()                                                          # « Fermer » la ferme vraiment
    assert not page.winfo_exists()
    assert not demo.errors


# ------------------------------------------------------------------ C85 : pas de forme d'onde défilante
def test_no_scrolling_waveform_above_the_player(demo):  # noqa: F811
    bar = demo.player_bar
    bar._use_scroll(None)
    bar._grid_page(None)
    assert bar.scroll_wave.isHidden()
    assert not hasattr(demo.views["settings"], "scroll_wave_var")
    from djsync.i18n import en

    assert "settings.scrolling_wave" not in en.STRINGS


# ------------------------------------------------------------------ C76 : fichiers introuvables écartés
def test_analysis_page_leaves_out_missing_files(demo, monkeypatch):  # noqa: F811
    from djsync.ui.analysis_dialog import AnalysisDialog

    lib = demo.views["library"]
    demo.show_view("library")
    assert pump(demo, 4, lambda: lib.table.total > 2)
    tracks = [r.data for r in lib.table.all_rows() if r.data is not None][:3]
    gone = demo.ctrl.library.absolute_path(tracks[0])
    gone.unlink()
    started = []
    monkeypatch.setattr(demo.ctrl, "analyze", lambda ids, force=False: started.append(list(ids)))
    d = AnalysisDialog(demo, demo.ctrl, tracks)
    d.force.setChecked(True)
    assert pump(demo, 4, lambda: tracks[0].content_id in d._missing)
    assert tracks[0].content_id not in [x.content_id for x in d._todo()]
    assert "introuvable" in d.what.text() or "not found" in d.what.text()
    d._start()                                             # 1.4.1 (C131) : lancement après native_ids (asynchrone)
    assert pump(demo, 4, lambda: bool(started))
    assert tracks[0].content_id not in started[0]
    assert d._eta(0)                                       # temps restant affiché pendant l'analyse
    d.close()
    assert not demo.errors


# ------------------------------------------------------------------ B40, B41 : messages clairs
def test_absent_drive_and_unreadable_file_messages():
    from pathlib import PureWindowsPath

    from djsync.i18n import set_language, t
    from djsync.ui.ctrl.diagnostic import volume_label
    from djsync.ui.player_bar import play_error_text

    assert volume_label(PureWindowsPath("E:\\")) == "E:"
    set_language("fr")
    try:
        assert "E:" in t("missing.offline", drive="E:") and "clé" in t("missing.offline", drive="E:")
        text = play_error_text("Cannot play: ('failed to init decoder', -1)", type("M", (), {"path": "/x/a.m4a"})())
        assert text.startswith("Impossible de lire « a.m4a »") and "failed to init decoder" in text
    finally:
        set_language("en")
