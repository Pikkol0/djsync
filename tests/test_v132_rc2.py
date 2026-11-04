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
    assert head.sectionSize(dl) <= table._width(table.columns[dl]) + 2
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
