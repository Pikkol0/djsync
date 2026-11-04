"""1.3.2 (C54) : accueil du tout premier lancement (pas après une mise à jour).

Étape 1 : la langue (English / Français, celle du système présélectionnée), puis « Valider » (1.3.2-rc.2, B44).
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
        # 1.3.2-rc.2 (B44) : fenêtre plus grande (aucun texte coupé), plus aérée
        super().__init__(parent, "DJSync", 640, 500)
        self.ctrl = controller
        self._step = step
        pre = get_language() if self.ctrl.settings.language != "en" else system_language()
        self._lang = pre
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

    def _logo_row(self, title: str) -> None:
        from PySide6.QtWidgets import QLabel

        from .logo import logo_pixmap

        row = hbox(spacing=theme.px(12))
        logo = QLabel()
        logo.setPixmap(logo_pixmap(theme.px(40), theme.ACCENT))
        row.addWidget(logo)
        row.addWidget(label(title, "h2"), 1)
        self.body.addLayout(row)

    def _build(self) -> None:
        self._clear()
        self.body.setSpacing(theme.px(12))
        if self._step == 1:
            self._logo_row(t("welcome.lang_title"))
            self.body.addWidget(label(t("welcome.lang_sub"), "dim", wrap=True))
            row = hbox(spacing=theme.px(12))
            self.lang_buttons = {}
            for code, name in (("en", "English"), ("fr", "Français")):
                b = button(name, lambda c=code: self._pick(c), kind="tile")
                b.setCheckable(True)
                b.setMinimumHeight(theme.px(72))
                row.addWidget(b, 1)
                self.lang_buttons[code] = b
            self.body.addLayout(row)
            self._pick(self._lang)
            self.body.addStretch(1)
            foot = hbox(spacing=theme.px(8))
            foot.addWidget(button(t("welcome.skip"), self._finish, kind="flat"))
            foot.addStretch(1)
            self.validate_btn = button(t("welcome.validate"), lambda: self._choose(self._lang), kind="primary",
                                       icon="check")
            foot.addWidget(self.validate_btn)
            self.body.addLayout(foot)
            return
        from ..credits import thanks_text

        self._logo_row(t("welcome.title"))
        for line in t("welcome.text").split("\n"):
            self.body.addWidget(label(line, wrap=True))
        star = button("⭐  " + t("welcome.star"), lambda: self.ctrl._emit("open_url", REPO), kind="primary")
        star.setMinimumHeight(theme.px(48))
        self.star_btn = star
        self.body.addWidget(star)
        self.body.addWidget(label(t("welcome.star_why"), "faint", wrap=True))
        self.shortcut = QCheckBox(t("welcome.shortcut"))
        from ..core import shortcut

        self.shortcut.setEnabled(shortcut.target() is not None)
        self.shortcut.setChecked(shortcut.target() is not None)
        self.body.addWidget(self.shortcut)
        self.body.addStretch(1)
        self.body.addWidget(label("🙏 " + thanks_text(get_language()), "faint", wrap=True))
        foot = hbox(spacing=theme.px(8))
        foot.addWidget(button(t("welcome.first_steps"), self._first_steps, kind="flat", icon="help"))
        foot.addStretch(1)
        foot.addWidget(button(t("welcome.start"), self._finish, icon="go"))
        self.body.addLayout(foot)

    def _pick(self, code: str) -> None:
        """1.3.2-rc.2 (B44) : un clic choisit la langue ; « Valider » passe à la suite."""
        self._lang = code
        for c, b in self.lang_buttons.items():
            b.setChecked(c == code)
            b.setProperty("kind", "primary" if c == code else "tile")
            b.style().unpolish(b)
            b.style().polish(b)

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
