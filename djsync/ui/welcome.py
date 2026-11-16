"""1.3.2 (C54) : accueil du tout premier lancement (pas après une mise à jour).

1.4.2 (A2-11) : deux écrans au lieu de quatre fenêtres.
Écran 1 : bienvenue et langue ensemble (un clic change la langue et retraduit l'écran), les trois points,
raccourci dans le menu Démarrer / Applications (C70), étoile GitHub en lien discret, remerciements (gardés),
« Premiers pas » (C68), « Suivant ».
Écran 2 : qualité des téléchargements YouTube (C146, C187) et la visite guidée proposée par une case (plus
de fenêtre à part), « Commencer ». « Passer » sur le premier écran ; rien n'est bloquant. La fenêtre prend
la hauteur de son contenu. Revu depuis Paramètres ▸ DJSync.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLocale, Qt

from ..i18n import get_language, set_language, t
from . import theme
from .dialogs import BaseDialog
from .widgets import WrapCheckBox, button, hbox, icon_label, label

REPO = "https://github.com/Pikkol0/djsync"


def system_language() -> str:
    try:
        return "fr" if QLocale.system().name().lower().startswith("fr") else "en"
    except Exception:  # noqa: BLE001
        return "en"


class WelcomeDialog(BaseDialog):
    modal = True

    def __init__(self, parent: Any, controller: Any, step: int = 1) -> None:
        # 1.4.2 (A2-11) : largeur fixe, hauteur du contenu (plus de fenêtre à moitié vide)
        super().__init__(parent, "DJSync", 600)
        self.ctrl = controller
        self._step = step
        pre = get_language() if self.ctrl.settings.language != "en" else system_language()
        self._lang = pre
        self._shortcut_pref = None
        if pre != self.ctrl.settings.language:           # 1.4.2 (A2-11) : langue du système appliquée d'office
            self._apply_language(pre)
        self._build()
        self.show_dialog()

    # ------------------------------------------------------------------ étapes
    def _clear(self) -> None:
        def drop(lay: Any) -> None:
            while lay.count():
                item = lay.takeAt(0)
                if item.widget() is not None:
                    w = item.widget()                        # 1.4.2 (A2-11) : rien ne reste visible
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                elif item.layout() is not None:
                    drop(item.layout())

        drop(self.body)

    def _logo_row(self, title: str, role: str = "h2") -> None:
        from PySide6.QtWidgets import QLabel

        from .logo import logo_pixmap

        row = hbox(spacing=theme.px(12))
        logo = QLabel()
        logo.setPixmap(logo_pixmap(theme.px(40), theme.ACCENT))
        row.addWidget(logo)
        row.addWidget(label(title, role), 1)
        self.body.addLayout(row)

    def _build(self) -> None:
        self._clear()
        self.body.setSpacing(theme.px(12))
        if self._step >= 2:
            self._build_quality()
        else:
            self._build_welcome()
        self._fit()

    def _fit(self) -> None:
        """Hauteur du contenu (A2-11), recalculée à chaque écran et changement de langue."""
        from PySide6.QtCore import QTimer

        def go() -> None:
            try:
                self.body.activate()
                w = max(self.width(), self.minimumWidth())
                h = self.body.totalHeightForWidth(w) if self.body.hasHeightForWidth() else self.sizeHint().height()
                self.resize(w, max(h, self.minimumSizeHint().height()))
            except RuntimeError:
                pass

        go()
        QTimer.singleShot(0, go)

    def _build_welcome(self) -> None:
        from ..credits import thanks_text

        # 1.3.2-rc.3 (C128) : hiérarchie de tailles (titre, accroche, trois points avec une icône chacun,
        # remerciements en petit et centrés) ; 1.4.2 (A2-11) : la langue sur le même écran
        self._logo_row(t("welcome.lang_title"), role="title")
        lang = hbox(spacing=theme.px(8))
        lang.addWidget(label(t("welcome.lang_label"), "dim"))
        self.lang_buttons = {}
        for code, name in (("en", "English"), ("fr", "Français")):
            b = button(name, lambda c=code: self._pick(c), kind="tile")
            b.setCheckable(True)
            lang.addWidget(b)
            self.lang_buttons[code] = b
        lang.addStretch(1)
        self.body.addLayout(lang)
        self._show_pick()
        self.body.addWidget(label(t("welcome.lead"), "h2", wrap=True))
        for icon, key in (("search", "welcome.point_find"), ("wave", "welcome.point_analyse"),
                          ("usb", "welcome.point_free")):
            line = hbox(spacing=theme.px(10))
            line.addWidget(icon_label(icon, 18, theme.ACCENT), 0, Qt.AlignTop)
            line.addWidget(label(t(key), wrap=True), 1)
            self.body.addLayout(line)
        self.shortcut = WrapCheckBox(t("welcome.shortcut"))        # A2-3 : texte à la ligne, plus coupé
        from ..core import shortcut

        self.shortcut.setEnabled(shortcut.target() is not None)
        self.shortcut.setChecked(shortcut.target() is not None if self._shortcut_pref is None
                                 else self._shortcut_pref)
        self.shortcut.toggled.connect(lambda v: setattr(self, "_shortcut_pref", v))
        self.body.addWidget(self.shortcut)
        # A2-11 : l'étoile devient un lien discret, avec sa raison en bulle
        star = button("⭐  " + t("welcome.star"), lambda: self.ctrl._emit("open_url", REPO), kind="flat",
                      tooltip=t("welcome.star_why"))
        self.star_btn = star
        thanks = label("🙏 " + thanks_text(get_language()), "faint", wrap=True)
        thanks.setAlignment(Qt.AlignCenter)                   # 1.3.2-rc.3 (C128, DEM-12) : centré
        self.thanks_lbl = thanks
        self.body.addWidget(thanks)
        self.body.addWidget(star, 0, Qt.AlignHCenter)
        foot = hbox(spacing=theme.px(8))
        foot.addWidget(button(t("welcome.skip"), self._finish, kind="flat"))
        foot.addWidget(button(t("welcome.first_steps"), self._first_steps, kind="flat", icon="help"))
        foot.addStretch(1)
        self.validate_btn = button(t("welcome.next"), lambda: self._choose(self._lang), kind="primary", icon="go")
        self.validate_btn.setDefault(True)
        foot.addWidget(self.validate_btn)
        self.body.addLayout(foot)

    def _to_quality(self) -> None:
        if self._step < 2:
            box = getattr(self, "shortcut", None)
            try:
                self._shortcut_wanted = bool(box is not None and box.isChecked() and box.isEnabled())
            except RuntimeError:                              # case déjà détruite
                pass
        self._step = 2
        self._build()

    def _build_quality(self) -> None:
        """1.4.0-rc.4 (C146) : qualité des téléchargements YouTube, M4A recommandé ; le meilleur flux
        affiche son compromis (poids, conversion)."""
        self._logo_row(t("welcome.yt_title"))
        self.body.addWidget(label(t("welcome.yt_sub"), "dim", wrap=True))
        self.yt_buttons = {}
        for key, title, sub in (("m4a", t("welcome.yt_m4a"), t("welcome.yt_m4a_sub")),
                                ("best", t("welcome.yt_best"), t("welcome.yt_best_sub"))):
            b = button(f"{title}\n{sub}", lambda k=key: self._pick_yt(k), kind="tile")
            b.setCheckable(True)
            b.setMinimumHeight(theme.px(64))
            self.body.addWidget(b)
            self.yt_buttons[key] = b
        self.yt_warn = label(t("yt.settings_best_hint"), "dim", wrap=True)
        self.yt_warn.setStyleSheet(f"color: {theme.WARN};")
        self.body.addWidget(self.yt_warn)
        # 1.4.2 (C187) : deux choix pour débuter ; « Plus de choix… » ouvre les 6 qualités des réglages
        more = hbox(spacing=theme.px(8))
        more.addWidget(label(t("welcome.yt_later"), "faint", wrap=True), 1)
        more.addWidget(button(t("welcome.more_choices"), self._more_choices, kind="flat", icon="settings",
                              tooltip=t("welcome.more_choices_tip")))
        self.body.addLayout(more)
        self._pick_yt("best" if self.ctrl.settings.download_quality == "yt_best" else "m4a")
        # 1.4.2 (A2-11) : la visite guidée proposée ici, au lieu d'une quatrième fenêtre
        from . import tour

        self.tour_box = None
        if tour.should_offer(self.ctrl.settings):
            self.tour_box = WrapCheckBox(t("welcome.tour"))
            self.tour_box.setChecked(True)
            self.body.addWidget(self.tour_box)
        foot = hbox(spacing=theme.px(8))
        foot.addStretch(1)
        self.start_btn = button(t("welcome.start"), self._finish, kind="primary", icon="go")
        self.start_btn.setDefault(True)
        foot.addWidget(self.start_btn)
        self.body.addLayout(foot)

    def _more_choices(self) -> None:
        """1.4.2 (C187) : termine l'accueil (choix en cours gardé) et ouvre Paramètres ▸ Téléchargement."""
        self._finish()
        self.ctrl._emit("open_settings_section", "download")

    def _pick_yt(self, key: str) -> None:
        self._yt = key
        for k, b in self.yt_buttons.items():
            b.setChecked(k == key)
            b.setProperty("kind", "primary" if k == key else "tile")
            b.style().unpolish(b)
            b.style().polish(b)
        self.yt_warn.setVisible(key == "best")
        if hasattr(self, "_step"):
            self._fit()

    def _pick(self, code: str) -> None:
        """1.3.2-rc.2 (B44) : un clic choisit la langue, « Suivant » passe à la suite. 1.4.2 (A2-11) : la langue
        s'applique tout de suite (l'écran de bienvenue est retraduit)."""
        changed = code != self._lang or code != self.ctrl.settings.language
        self._lang = code
        if changed and code != self.ctrl.settings.language:
            self._apply_language(code)
            self._build()
            return
        self._show_pick()

    def _apply_language(self, code: str) -> None:
        s = self.ctrl.settings
        s.language = code
        set_language(code)
        s.save()
        self.ctrl._emit("rebuild_ui")

    def _show_pick(self) -> None:
        for c, b in self.lang_buttons.items():
            b.setChecked(c == self._lang)
            b.setProperty("kind", "primary" if c == self._lang else "tile")
            b.style().unpolish(b)
            b.style().polish(b)

    def _choose(self, code: str) -> None:
        if code != self.ctrl.settings.language:
            self._apply_language(code)
        self._to_quality()

    def _first_steps(self) -> None:
        self._finish()
        from .help_dialog import HelpDialog

        HelpDialog(self.parent(), start=True)

    def _finish(self) -> None:
        s = self.ctrl.settings
        s.welcome_done = True
        box = getattr(self, "shortcut", None)
        wanted = getattr(self, "_shortcut_wanted", None)
        if wanted is None:
            try:
                wanted = bool(box is not None and box.isChecked() and box.isEnabled())
            except RuntimeError:
                wanted = False
        if wanted:
            s.start_menu_shortcut = True
            self.ctrl.refresh_shortcut()
        if getattr(self, "_yt", None):                      # 1.4.0-rc.4 (C146)
            # 1.4.1 (C143) : un MP3 déjà choisi est gardé ; sinon flux standard ou meilleur flux
            if not s.download_quality.startswith("mp3"):
                s.download_quality = "yt_best" if self._yt == "best" else "original"
            s.youtube_best = s.download_quality == "yt_best"
        tour_box = getattr(self, "tour_box", None)
        go_tour = False
        if tour_box is not None:                            # 1.4.2 (A2-11) : la case remplace la fenêtre
            go_tour = tour_box.isChecked()
            s.tour_state = "done" if go_tour else "later"
            win = self.parent().window() if self.parent() is not None else None
            if win is not None:
                win._tour_asked = True                       # pas de seconde proposition ce lancement-ci
        s.save()
        self.close()
        if go_tour and self.parent() is not None:
            from PySide6.QtCore import QTimer

            from . import tour

            win = self.parent().window()
            QTimer.singleShot(300, lambda: tour.start(win))
