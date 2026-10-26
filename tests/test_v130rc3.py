"""1.3.0-rc.3 : version au démarrage (C31), analyse après téléchargement (C32)."""
import json
from types import SimpleNamespace

from djsync.settings import Settings
from djsync.ui.ctrl.downloads import DownloadsMixin


# ------------------------------------------------------------------ C32 : analyse après téléchargement
def test_after_download_analysis_is_on_by_default_and_migrated(tmp_path):
    assert Settings().analyze_after_download_usb and Settings().analyze_after_download_local
    old = tmp_path / "old.json"           # réglages d'une 1.3.0-rc.2 : ancienne case décochée
    old.write_text(json.dumps({"analyze_on_add": False, "settings_version": 1}), encoding="utf-8")
    s = Settings.load(old)
    assert s.analyze_after_download_usb and s.analyze_after_download_local and s.settings_version == 2
    chosen = tmp_path / "chosen.json"     # choix fait après la migration : respecté
    chosen.write_text(json.dumps({"analyze_after_download_usb": False, "settings_version": 2}), encoding="utf-8")
    s = Settings.load(chosen)
    assert not s.analyze_after_download_usb and s.analyze_after_download_local


class _Ctrl(DownloadsMixin):
    def __init__(self, local: bool, usb_on: bool = True, local_on: bool = True) -> None:
        self.library = object()
        self.is_local = local
        self.settings = SimpleNamespace(analyze_after_download_usb=usb_on, analyze_after_download_local=local_on)
        self.calls = []

    def analyze(self, ids, quiet=False):
        self.calls.append((list(ids), quiet))


def test_downloaded_track_goes_to_the_analysis_queue_per_library_setting():
    c = _Ctrl(local=False)
    c._analyse_after_download(SimpleNamespace(content_id=7, library=c.library))
    assert c.calls == [([7], True)]                      # en file, sans message par son
    c = _Ctrl(local=False, usb_on=False)
    c._analyse_after_download(SimpleNamespace(content_id=7, library=c.library))
    assert c.calls == []
    c = _Ctrl(local=True, usb_on=False, local_on=True)    # réglages séparés clé / PC
    c._analyse_after_download(SimpleNamespace(content_id=8, library=c.library))
    assert c.calls == [([8], True)]
    c = _Ctrl(local=True, local_on=False)
    c._analyse_after_download(SimpleNamespace(content_id=8, library=c.library))
    assert c.calls == []


def test_no_analysis_if_the_library_changed_meanwhile():
    c = _Ctrl(local=False)
    c._analyse_after_download(SimpleNamespace(content_id=7, library=object()))
    c._analyse_after_download(SimpleNamespace(content_id=0, library=c.library))
    assert c.calls == []


# ------------------------------------------------------------------ C31 : version au démarrage
def test_native_splash_image_carries_the_version(tmp_path):
    from PIL import Image, ImageChops

    from djsync.ui.palettes import DEFAULT_THEME, PALETTES
    from tools.export_logos import make_splash

    plain, versioned = tmp_path / "a.png", tmp_path / "b.png"
    make_splash(plain, PALETTES[DEFAULT_THEME])
    make_splash(versioned, PALETTES[DEFAULT_THEME], "1.3.0-rc.3")
    diff = ImageChops.difference(Image.open(plain).convert("RGB"), Image.open(versioned).convert("RGB")).getbbox()
    assert diff is not None and diff[1] >= 165                # seule la ligne de version, sous « Loading… »


def test_qt_splash_shows_the_version_and_a_normal_size_logo():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from djsync import full_version
    from djsync.ui import splash

    app = QApplication.instance() or QApplication([])
    s = splash.Splash(app)
    try:
        img: QImage = s.widget.pixmap().toImage()
        # le logo (56 px, centré à partir de y=30) ne déborde plus sur le nom « DJSync » (y >= 96)
        bg = img.pixelColor(img.width() // 2 + 40, 92)
        assert bg == img.pixelColor(10, 92)
        assert full_version()
    finally:
        s.close()


# ------------------------------------------------------------------ B14 : messages d'export.pdb en anglais
def test_pdb_error_messages_are_english():
    """L'app est en anglais par défaut : aucun message d'erreur technique d'export.pdb en français."""
    import re
    from pathlib import Path

    import djsync.db.pdb as pdb_pkg

    french = re.compile(r"\b(de la|des|du|une|est|pas|inconnus?|drapeaux|clé|fichier)\b", re.I)
    for f in Path(pdb_pkg.__file__).parent.glob("*.py"):
        for m in re.finditer(r'raise \w*Error\(f?"([^"]*)"', f.read_text(encoding="utf-8")):
            assert not french.search(m.group(1)), (f.name, m.group(1))


# ------------------------------------------------------------------ C36 : bouton « Mettre à jour export.pdb »
def _demo_app(tmp_path, monkeypatch):
    from djsync.db import UsbDrive
    from djsync.settings import Settings
    from tests.demo_fixture import make_demo_usb

    from .qt_util import make_window
    from .test_ui_smoke import FakeService
    import djsync.ui.controller as controller

    usb = make_demo_usb(tmp_path)
    monkeypatch.setenv("DJSYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(controller, "find_usb_drives", lambda: [UsbDrive(root=usb, label="DEMO")])
    monkeypatch.setattr(controller, "MusicService", FakeService)
    return make_window(Settings(), monkeypatch), usb


def test_home_offers_to_update_a_stale_export_pdb(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLabel, QPushButton

    from djsync.db import UsbDrive
    from djsync.i18n import t
    from djsync.ui.ctrl.library_ops import DriveSummary

    from .qt_util import close_window, pump

    app, usb = _demo_app(tmp_path, monkeypatch)
    try:
        home = app.views["home"]
        calls = []
        monkeypatch.setattr(home.ctrl, "pdb_sync_now", lambda ok=None, failed=None: calls.append((ok, failed)))
        drive = UsbDrive(root=usb, label="DEMO")
        stale = home._card(DriveSummary(drive=drive, connected=True, tracks=3, playlists=1, has_pdb=True,
                                        pdb_state="stale", pdb_problem="1 playlist(s) missing"))
        buttons = [b for b in stale.findChildren(QPushButton) if b.text() == t("home.pdb_update")]
        assert len(buttons) == 1
        assert any("1 playlist(s) missing" in l.text() for l in stale.findChildren(QLabel))
        buttons[0].click()
        pump(app, 0.1)
        assert len(calls) == 1 and buttons[0].text() == t("home.pdb_updating") and not buttons[0].isEnabled()
        calls[0][0](None)                                     # réconciliation finie : bouton rétabli
        assert buttons[0].isEnabled() and buttons[0].text() == t("home.pdb_update")
        ok = home._card(DriveSummary(drive=drive, connected=True, tracks=3, playlists=1, has_pdb=True, pdb_state="ok"))
        assert not [b for b in ok.findChildren(QPushButton) if b.text() == t("home.pdb_update")]
    finally:
        close_window(app)


def test_sync_now_always_refreshes_home_and_reports_what_is_left(tmp_path, monkeypatch):
    from djsync.ui.ctrl.library_ops import LibraryOpsMixin

    class Lib:
        pdb_state, pdb_problem = "stale", "1 track(s) missing"

        def pdb_catch_up(self):
            return object()

    class Ctrl(LibraryOpsMixin):
        def __init__(self):
            self.library, self.events, self.msgs = Lib(), [], []
            self.dispatcher = SimpleNamespace(submit=self._run)

        def _run(self, fn, ok, err, pool=None):
            try:
                ok(fn())
            except Exception as exc:  # noqa: BLE001
                err(exc)

        def message(self, kind, text):
            self.msgs.append(kind)

        def _emit(self, name, *a):
            self.events.append(name)

        def _on_error(self, exc):
            self.msgs.append("error")

    c = Ctrl()
    c.pdb_sync_now()
    assert c.msgs == ["warn"] and c.events == ["library"]           # écart restant : dit, Accueil redessiné
    c.library.pdb_state = "ok"
    c.msgs, c.events = [], []
    c.pdb_sync_now()
    assert c.msgs == ["ok"] and c.events == ["library"]

    def locked():
        raise OSError("cannot write export.pdb (file used by another program?)")
    c.library.pdb_catch_up = locked
    c.msgs, c.events = [], []
    failed = []
    c.pdb_sync_now(failed=failed.append)
    assert c.msgs == ["warn"] and c.events == ["library"] and failed


# ------------------------------------------------------------------ B16 / B17 : page Grille et cues
from .test_ui_v024 import demo_grid  # noqa: E402,F401


def _open_grid(app):
    from .qt_util import pump

    app.show_view("library")
    lib = app.views["library"]
    assert pump(app, 4, lambda: lib.table.total == 11)
    target = next(r.data for r in lib.table.all_rows() if r.data.title == "Grid Test")
    app.open_grid_editor(target)
    ed = app.grid_editor
    assert pump(app, 4, lambda: bool(ed.beats))
    return ed


def test_grid_page_player_overview_and_cursor_modes(demo_grid):  # noqa: F811
    from .qt_util import pump

    app = demo_grid
    ed = _open_grid(app)
    bar = app.player_bar
    # B17 : le lecteur montre la vue d'ensemble 3 bandes (pas la forme d'onde défilante)
    assert bar._grid_editor is ed and not bar.grid_overview.isHidden() and bar.scroll_wave.isHidden()
    bar.grid_overview.resize(400, 40)
    bar.grid_overview._go(200)                                     # milieu de la vue d'ensemble
    assert abs(ed.cursor_ms - ed.duration_ms / 2) < ed.duration_ms * 0.01
    bar.grid_overview.grab()
    # curseur volant par défaut ; case « fixe au centre » gardée dans les réglages
    assert not ed.fixed_cursor and not ed.fixed_box.isChecked()
    ed.fixed_box.setChecked(True)
    assert ed.fixed_cursor and app.ctrl.settings.grid_fixed_cursor
    ed.canvas.resize(800, 200)
    ed.go_to(ed.beats[20][2])
    ed.grab()
    assert abs(ed._x(ed.cursor_ms) - ed.canvas.width() / 2) < 2          # curseur au milieu
    before = ed.cursor_ms
    ed.begin_scrub(400)
    ed.scrub_to(300)                                                     # le son glisse vers la gauche
    ed.end_scrub(300)
    assert ed.cursor_ms > before and abs(ed._x(ed.cursor_ms) - ed.canvas.width() / 2) < 2
    ed.pan(0.15)                                                         # molette : avance sous le curseur
    assert ed.cursor_ms > before
    ed.fixed_box.setChecked(False)
    assert not app.ctrl.settings.grid_fixed_cursor
    ed.close()
    pump(app, 0.2)
    assert bar._grid_editor is None and bar.grid_overview.isHidden()


def test_grid_page_top_strip_and_pads_fit(demo_grid):  # noqa: F811
    from PySide6.QtGui import QFont, QFontMetrics

    app = demo_grid
    ed = _open_grid(app)
    ed.canvas.resize(900, 220)
    ed.grab()
    fm = QFontMetrics(ed.canvas.font())
    assert ed._label_top >= fm.height() * 0.8 and ed._label_bottom > ed._label_top   # deux niveaux
    pad = ed.cue_panel.pads[0]
    f = QFont(pad.font())
    f.setBold(True)
    assert pad.minimumHeight() >= 2 * QFontMetrics(f).lineSpacing()                # deux lignes tiennent
    ed.close()
