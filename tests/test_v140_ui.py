"""1.4.0 : tests d'interface sur la clé de démonstration (fixtures de test_v122)."""
from .test_v122 import demo, usb  # noqa: F401


# ------------------------------------------------------------------ C50 : choix de couleur discret
def test_color_choice_is_one_button_with_a_menu(demo):  # noqa: F811
    from PySide6.QtWidgets import QToolButton

    from djsync.ui import theme
    from djsync.ui.palettes import PALETTES, RETIRED

    from .qt_util import pump

    assert all(v in PALETTES for v in RETIRED.values())
    demo.show_view("settings")
    view = demo.views["settings"]
    btn = view.theme_btn
    assert isinstance(btn, QToolButton) and len(btn.menu().actions()) == 12
    assert btn.height() <= theme.px(48)                       # une ligne, plus une grille de 2 × 10
    next(a for a in btn.menu().actions() if a.text() == view._swatches["red"].text()).trigger()
    pump(demo, 0.3)
    assert demo.ctrl.settings.theme == "red" and theme.ACCENT.upper() == PALETTES["red"].upper()
    assert demo.views["settings"].theme_btn.text() == view._swatches["red"].text()   # vue reconstruite (B23)
