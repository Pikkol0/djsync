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
