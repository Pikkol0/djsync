"""1.3.2 (C54) : accueil du tout premier lancement (pas après une mise à jour).

1.4.2 (A2-11) : deux écrans au lieu de quatre fenêtres.
Écran 1 : bienvenue et langue ensemble (un clic change la langue et retraduit l'écran), les trois points,
raccourci dans le menu Démarrer / Applications (C70), étoile GitHub en lien discret, remerciements (gardés),
« Premiers pas » (C68), « Suivant ».
Écran 2 : qualité des téléchargements YouTube (C146, C187) et la visite guidée proposée par une case (plus
de fenêtre à part), « Commencer ». « Passer » sur le premier écran ; rien n'est bloquant. La fenêtre prend
la hauteur de son contenu. Revu depuis Paramètres ▸ DJSync.

1.4.4 (C227) : un seul écran « Bienvenue dans DJSync » : langue, thème (tuiles de C226), zoom, qualité YouTube
(2 choix recommandés, le reste replié) ; « Passer » bordé, de la taille de « Commencer », en bas à gauche.
`_step` et `_to_quality` restent pour la compatibilité (tout est sur le même écran).
"""
from __future__ import annotations

import logging

from typing import Any

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QWidget

from ..i18n import get_language, set_language, t
from . import theme
from .dialogs import BaseDialog
from .widgets import WrapCheckBox, button, hbox, icon_label, label, vbox

log = logging.getLogger(__name__)

MP3_KEYS = ("mp3_320", "mp3_256", "mp3_192", "mp3_128")
QUALITY_OF = {"m4a": "original", "best": "yt_best", **{k: k for k in MP3_KEYS}}   # tuile → réglage

REPO = "https://github.com/Pikkol0/djsync"


def system_language() -> str:
    try:
        return "fr" if QLocale.system().name().lower().startswith("fr") else "en"
    except Exception:  # noqa: BLE001
        log.debug("Handled error in system_language", exc_info=True)  # 1.4.3 (A3-4)
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
        self.body.setSpacing(theme.px(10))
        self._build_welcome()                      # 1.4.4 (C227) : un seul écran
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
        # 1.4.4 (C227) : tout ce qui se personnalise, sur le même écran
        self.body.addWidget(label(t("welcome.custom_title").upper(), "section"))
        from .views.settings_view import theme_tiles
        from .widgets import FlowLayout

        row = hbox(spacing=theme.px(8))
        row.addWidget(label(t("settings.themes"), "dim"))
        tiles = FlowLayout(spacing=theme.px(6))
        from .palettes import THEMES

        self.theme_tiles = theme_tiles(tiles, self._pick_theme, list(THEMES)[:6])
        row.addLayout(tiles, 1)
        self.body.addLayout(row)
        from .widgets import icon_button

        row = hbox(spacing=theme.px(8))
        row.addWidget(label(t("settings.zoom"), "dim"))
        row.addWidget(icon_button("minus", lambda: self._zoom(-1), t("settings.zoom_out")))
        self.zoom_lbl = label(f"{self.ctrl.settings.zoom} %", "accent")
        row.addWidget(self.zoom_lbl)
        row.addWidget(icon_button("plus", lambda: self._zoom(1), t("settings.zoom_in")))
        row.addStretch(1)
        self.body.addLayout(row)
        self._build_quality()
        self.shortcut = WrapCheckBox(t("welcome.shortcut"))        # A2-3 : texte à la ligne, plus coupé
        from ..core import shortcut

        self.shortcut.setEnabled(shortcut.target() is not None)
        self.shortcut.setChecked(shortcut.target() is not None if self._shortcut_pref is None
                                 else self._shortcut_pref)
        self.shortcut.toggled.connect(lambda v: setattr(self, "_shortcut_pref", v))
        self.body.addWidget(self.shortcut)
        # 1.4.2 (A2-11) : la visite guidée proposée ici, au lieu d'une quatrième fenêtre
        from . import tour

        self.tour_box = None
        if tour.should_offer(self.ctrl.settings):
            self.tour_box = WrapCheckBox(t("welcome.tour"))
            self.tour_box.setChecked(True)
            self.body.addWidget(self.tour_box)
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
        # 1.4.4 (C227) : « Passer » bien visible : bordé, de la taille de « Commencer », en bas à gauche
        self.skip_btn = button(t("welcome.skip"), self._skip, icon="next")
        foot.addWidget(self.skip_btn)
        foot.addWidget(button(t("welcome.first_steps"), self._first_steps, kind="flat", icon="help"))
        foot.addStretch(1)
        self.start_btn = button(t("welcome.start"), self._finish, kind="primary", icon="go")
        self.start_btn.setDefault(True)
        self.validate_btn = self.start_btn            # compatibilité (ancien « Suivant »)
        foot.addWidget(self.start_btn)
        h = max(self.skip_btn.sizeHint().height(), self.start_btn.sizeHint().height())
        w = max(self.skip_btn.sizeHint().width(), self.start_btn.sizeHint().width())
        for b in (self.skip_btn, self.start_btn):
            b.setMinimumSize(w, h)
        self.body.addLayout(foot)

    def _pick_theme(self, key: str) -> None:
        """1.4.4 (C227) : thème appliqué tout de suite, écran redessiné dans ses couleurs (choix gardés)."""
        from .palettes import THEMES

        bg, light, accent = THEMES[key]                    # 1.4.4 (C238) : avec la luminosité
        s = self.ctrl.settings
        s.background, s.brightness, s.theme = bg, light, accent
        s.save()
        self._remember()
        self.ctrl._emit("restyle")
        self._build()

    def _zoom(self, delta: int) -> None:
        from ..settings import ZOOM_STEP
        from .zoom import clamp

        s = self.ctrl.settings
        z = clamp(s.zoom + delta * ZOOM_STEP)
        if z != s.zoom:
            s.zoom = z
            s.save()
            self._remember()
            self.ctrl._emit("restyle")
            self._build()

    def _remember(self) -> None:
        """Choix de l'écran gardés quand il est redessiné (thème, zoom)."""
        box = getattr(self, "shortcut", None)
        try:
            if box is not None:
                self._shortcut_pref = box.isChecked()
        except RuntimeError:
            pass

    def _skip(self) -> None:
        """« Passer » : ferme l'accueil d'un coup, réglages par défaut (qualité, pas de visite guidée)."""
        self._yt = None
        if self.tour_box is not None:
            self.tour_box.setChecked(False)
        self._finish()

    def _to_quality(self) -> None:
        """Compatibilité : la qualité est sur le même écran depuis la 1.4.4 (C227)."""
        self._step = 2

    def _build_quality(self) -> None:
        """1.4.0-rc.4 (C146) : qualité des téléchargements YouTube, M4A recommandé ; le meilleur flux
        affiche son compromis (poids, conversion)."""
        self.body.addWidget(label(t("welcome.yt_title"), "dim"))
        self.yt_buttons = {}
        for key, title, sub in (("m4a", t("welcome.yt_m4a"), t("welcome.yt_m4a_sub")),
                                ("best", t("welcome.yt_best"), t("welcome.yt_best_sub"))):
            b = button(f"{title}\n{sub}", lambda k=key: self._pick_yt(k), kind="tile")
            b.setCheckable(True)
            b.setMinimumHeight(theme.px(64))
            self.body.addWidget(b)
            self.yt_buttons[key] = b
        # 1.4.2 (B106) : les 6 qualités sur l'écran : les 2 recommandées en tête, les 4 MP3 repliées dessous
        from PySide6.QtWidgets import QToolButton

        from .views.settings_view import QUALITY_KBPS
        from ..i18n import num

        self.more_toggle = QToolButton()
        self.more_toggle.setText(t("welcome.more_qualities"))
        self.more_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.more_toggle.setAutoRaise(True)
        self.more_toggle.setCheckable(True)
        self.more_toggle.setCursor(Qt.PointingHandCursor)
        self.body.addWidget(self.more_toggle)
        self.more_box = QWidget()
        more_lay = vbox(self.more_box, spacing=theme.px(6))
        for key in MP3_KEYS:
            per_min = t("settings.quality_per_min", mb=num(QUALITY_KBPS[key] * 60 / 8 / 1000, ".1f"))
            b = button(f"{t('settings.quality_' + key)}\n{per_min}", lambda k=key: self._pick_yt(k), kind="tile")
            b.setCheckable(True)
            b.setMinimumHeight(theme.px(52))
            more_lay.addWidget(b)
            self.yt_buttons[key] = b
        self.body.addWidget(self.more_box)
        self.more_toggle.toggled.connect(self._fold_more)
        self.yt_warn = label(t("yt.settings_best_hint"), "dim", wrap=True)
        self.yt_warn.setStyleSheet(f"color: {theme.WARN};")
        self.body.addWidget(self.yt_warn)
        self.mp3_warn = label(t("quality.mp3_warning"), "dim", wrap=True)
        self.mp3_warn.setStyleSheet(f"color: {theme.WARN};")
        self.body.addWidget(self.mp3_warn)
        current = getattr(self, "_yt", None) or {v: k for k, v in QUALITY_OF.items()}.get(
            self.ctrl.settings.download_quality, "m4a")
        self.more_toggle.setChecked(current in MP3_KEYS)
        self._fold_more(current in MP3_KEYS)
        self._pick_yt(current)

    def _fold_more(self, shown: bool) -> None:
        self.more_toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)
        self.more_box.setVisible(shown)
        if hasattr(self, "_step"):
            self._fit()

    def _pick_yt(self, key: str) -> None:
        self._yt = key
        for k, b in self.yt_buttons.items():
            b.setChecked(k == key)
            b.setProperty("kind", "primary" if k == key else "tile")
            b.style().unpolish(b)
            b.style().polish(b)
        self.yt_warn.setVisible(key == "best")
        warn = getattr(self, "mp3_warn", None)
        if warn is not None:
            warn.setVisible(key in MP3_KEYS)
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
            # 1.4.2 (B106) : les 6 qualités sont sur l'écran (un MP3 déjà choisi y est présélectionné)
            s.download_quality = QUALITY_OF.get(self._yt, "original")
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
