"""1.3.2 : fenêtre devant l'Explorateur sous Windows (B36), groupe affiché bien visible dans Doublons (C98),
sources acceptées dans l'onglet Import (C101)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from .test_v122 import demo, usb  # noqa: E402,F401


# ------------------------------------------------------------------ B36
class _User32:
    def __init__(self, allowed: bool, front: int = 7):
        self.allowed, self.front, self.calls = allowed, front, []

    def GetForegroundWindow(self):  # noqa: N802
        return self.front

    def SetWindowPos(self, hwnd, after, *a):  # noqa: N802
        self.calls.append(("pos", after))

    def SetForegroundWindow(self, hwnd):  # noqa: N802
        self.calls.append(("fg", hwnd))
        if self.allowed:
            self.front = hwnd

    def FlashWindowEx(self, info):  # noqa: N802
        self.calls.append(("flash",))


def test_window_brought_in_front_or_flashing(monkeypatch):
    from djsync.ui import foreground as F

    u = _User32(allowed=True)
    assert F.bring_to_front(42, u) == "raised"
    assert u.calls[:2] == [("pos", F.HWND_TOPMOST), ("pos", F.HWND_NOTOPMOST)]   # « toujours au-dessus » relâché
    assert F.bring_to_front(42, u) == "already"
    u = _User32(allowed=False)
    monkeypatch.setattr(F, "_flash", lambda hwnd, user32: user32.FlashWindowEx(None))
    assert F.bring_to_front(42, u) == "flashed" and ("flash",) in u.calls
    assert F.bring_to_front(1, None) in ("skip", "already", "raised", "flashed", "error")


def test_launcher_gives_the_foreground_right():
    src = (Path(__file__).parents[1] / "packaging" / "launcher" / "launcher.c").read_text(encoding="utf-8")
    start = src.index("CreateProcessW(exe, cmd")
    assert "AllowSetForegroundWindow(pi.dwProcessId)" in src[start:start + 600]


# ------------------------------------------------------------------ C98
def test_duplicates_selected_group_kept_and_highlighted(demo):  # noqa: F811
    from djsync.ui import theme
    from djsync.ui.duplicates_dialog import DuplicatesDialog

    from .qt_util import pump

    dup = DuplicatesDialog(demo.views["home"], demo.ctrl)
    try:
        assert pump(demo, 6, lambda: len(dup.groups) >= 1)
        css = dup.list.styleSheet()
        assert "item:selected:!active" in css and theme.ACCENT in css            # visible même sans le focus
        i = len(dup.groups) - 1
        dup._select(i)
        dup._fill_list()                                                          # liste redessinée
        assert dup.list.currentRow() == i
    finally:
        dup.close()


# ------------------------------------------------------------------ C101
def test_import_tab_lists_every_accepted_source(demo):  # noqa: F811
    from djsync.core.urlimport import SOURCES, classify_url, source_names
    from djsync.i18n import set_language, t
    from djsync.models import UrlKind

    # la liste affichée est celle que le code reconnaît
    examples = {"spotify": "https://open.spotify.com/playlist/abc", "youtube": "https://youtu.be/xyz",
                "ytmusic": "https://music.youtube.com/playlist?list=PL1", "soundcloud": "https://soundcloud.com/a/sets/b"}
    assert {s.key for s in SOURCES} == set(examples)
    assert all(classify_url(u) != UrlKind.UNKNOWN for u in examples.values())
    view = demo.views["import"]
    assert [c.text().split("</span> ")[-1] for c in view.source_chips] == [s.name for s in SOURCES]
    assert all("100" in c.toolTip() or "200" in c.toolTip() for c in view.source_chips)
    assert all(s.name in view.url.placeholderText() for s in SOURCES)
    for lang in ("fr", "en"):
        set_language(lang)
        try:
            msg = t("error.url_unknown", names=source_names())
            assert all(s.name in msg for s in SOURCES)
            for s in SOURCES:
                assert "{" not in t(f"import.src_{s.key}", n=s.limit)
        finally:
            set_language("en")
    got = []
    demo.ctrl.import_url("https://example.com/x", lambda *a: None, got.append)
    assert got and "SoundCloud" in str(got[0])
