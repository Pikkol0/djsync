"""1.3.2 (C54) : accueil du tout premier lancement (pas après une mise à jour).

Étape 1 : la langue (English / Français, celle du système présélectionnée), appliquée tout de suite.
Étape 2 : bienvenue, remerciements, étoile sur GitHub, raccourci dans le menu Démarrer / Applications
(C70), « Premiers pas » (C68). « Passer » partout ; rien n'est bloquant. Revu depuis Paramètres ▸ DJSync.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QCheckBox

from ..i18n import get_language, set_language, t
from . import theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label

REPO = "https://github.com/Pikkol0/djsync"


def system_language() -> str:
    try:
        return "fr" if QLocale.system().name().lower().startswith("fr") else "en"
    except Exception:  # noqa: BLE001
        return "en"


class WelcomeDialog(BaseDialog):
    modal = True

    def __init__(self, parent: Any, controller: Any, step: int = 1) -> None:
        super().__init__(parent, "DJSync", 520)
        self.ctrl = controller
        self._step = step
        self._build()
        self.show_dialog()

    # ------------------------------------------------------------------ étapes
    def _clear(self) -> None:
        from .duplicates_dialog import _drop_layout

        while self.body.count():
            item = self.body.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout() is not None:
                _drop_layout(item.layout())

    def _build(self) -> None:
        self._clear()
        if self._step == 1:
            self.heading(t("welcome.lang_title"), t("welcome.lang_sub"))
            row = hbox(spacing=theme.px(8))
            pre = get_language() if self.ctrl.settings.language != "en" else system_language()
            for code, name in (("en", "English"), ("fr", "Français")):
                b = button(name, lambda c=code: self._choose(c), kind="primary" if code == pre else "flat")
                b.setMinimumHeight(theme.px(44))
                row.addWidget(b, 1)
            self.body.addLayout(row)
            self.body.addStretch(1)
            foot = hbox()
            foot.addStretch(1)
            foot.addWidget(button(t("welcome.skip"), self._finish, kind="flat"))
            self.body.addLayout(foot)
            return
        from ..credits import thanks_text

        self.heading(t("welcome.title"))
        self.body.addWidget(label(t("welcome.text"), wrap=True))
        self.body.addWidget(label("🙏 " + thanks_text(get_language()), "dim", wrap=True))
        self.body.addWidget(button("⭐ " + t("welcome.star"), lambda: self.ctrl._emit("open_url", REPO), kind="flat"))
        self.shortcut = QCheckBox(t("welcome.shortcut"))
        from ..core import shortcut

        self.shortcut.setEnabled(shortcut.target() is not None)
        self.shortcut.setChecked(shortcut.target() is not None)
        self.body.addWidget(self.shortcut)
        self.body.addStretch(1)
        foot = hbox()
        foot.addWidget(button(t("welcome.first_steps"), self._first_steps, kind="flat", icon="help"))
        foot.addStretch(1)
        foot.addWidget(button(t("welcome.start"), self._finish, kind="primary", icon="check"))
        self.body.addLayout(foot)

    def _choose(self, code: str) -> None:
        s = self.ctrl.settings
        if code != s.language:
            s.language = code
            set_language(code)
            s.save()
            self.ctrl._emit("rebuild_ui")
        self._step = 2
        self._build()

    def _first_steps(self) -> None:
        self._finish()
        from .help_dialog import HelpDialog

        HelpDialog(self.parent(), start=True)

    def _finish(self) -> None:
        s = self.ctrl.settings
        s.welcome_done = True
        box = getattr(self, "shortcut", None)
        if box is not None and box.isChecked() and box.isEnabled():
            s.start_menu_shortcut = True
            self.ctrl.refresh_shortcut()
        s.save()
        self.close()
