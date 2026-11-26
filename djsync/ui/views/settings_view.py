"""Vue Paramètres : apparence (langue, couleur, zoom, barre latérale), clé, destination, FFmpeg,
analyse, export.pdb, recherche, sauvegardes.

Apparence : appliquée immédiatement. La couleur et le zoom changent la feuille de style (Qt
redessine, rien n'est reconstruit) ; la langue reconstruit les pages (rapide). Le reste : bouton
« Enregistrer ».
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QFileDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QProgressBar, QScrollArea, QSizePolicy, QSpinBox, QToolButton, QWidget,
)

from ...db import UsbDrive
from ...i18n import LANGUAGES, num, t
from ...settings import ZOOM_STEP
from .. import theme
from ..logo import logo_pixmap
from ..palettes import PALETTES
from ..icons import qicon
from ..widgets import (
    InfoDot, ShrinkCombo, ShrinkLabel, Switch, button, flow_row, hbox, icon_button, icon_label, label, line_edit, panel,
    set_tooltips_enabled, vbox,
)
from .common import View

log = logging.getLogger(__name__)

KEY_NOTATIONS = ("auto", "camelot", "musical")
SIDEBAR_MODES = ("auto", "on", "off")
# 1.3.1 (C28) : volet des sections (clé, icône) ; 1.4.4 (C225) : 9 sections, une page chacune
SECTIONS = (("general", "settings"), ("libraries", "library"), ("download", "download"), ("analysis", "key"),
            ("accessibility", "help"), ("storage", "folder"), ("privacy", "info"), ("djsync", "refresh"),
            ("advanced", "menu"))     # 1.3.1 (C89) : Avancé
# 1.4.0-rc.5 (C165) : ordre des cartes dans leur section ; 1.4.4 (C225) : celui de l'écran « Plan » de la maquette
CARD_ORDER = ("card_interface", "card_performance", "card_playback",
              "card_drive", "card_local", "card_watch", "card_pdb",
              "card_format", "card_search", "card_youtube", "card_soundcloud", "card_soulseek",
              "card_after", "card_grid", "card_volume", "card_display",
              "card_colors", "card_size", "card_help",
              "card_backups", "card_space", "card_reports",
              "card_updates", "card_install", "card_about",
              "card_ffmpeg", "card_pdb_options", "card_engine", "card_tech", "card_analysis_adv")
# 1.4.4 (C225) : liens vers un réglage précis (Accueil, Diagnostic…) : section ouverte et élément mis en valeur
LINKS = {"space": ("storage", "space_box"), "backups": ("storage", "points_btn"),
         "diag_auto": ("advanced", "diag_auto_var"), "light": ("general", "light_menu"),
         "pdb": ("libraries", "pdb_card"), "watch": ("libraries", "watch_folder"),
         "soulseek": ("download", "slsk_var"), "youtube": ("download", "yt_browser"),
         "tooltips": ("accessibility", "tooltips_var")}
FIELD_PX = 360           # 1.4.0-rc.5 (C165) : largeur des champs de texte courts (nom, mot de passe, jeton)
NARROW_PX = 760          # en dessous (à 100 %), le volet devient une liste déroulante


# 1.4.1 (C143) : débit annoncé de chaque choix, pour la taille approximative par minute
QUALITY_KBPS = {"original": 128, "yt_best": 256, "mp3_320": 320, "mp3_256": 256, "mp3_192": 192, "mp3_128": 128}


def quality_label(q: str) -> str:
    """« M4A · AAC ≈ 128 kbps, sans conversion  —  ≈ 1 Mo/min » : vrai format, puis taille par minute."""
    mb = QUALITY_KBPS.get(q, 128) * 60 / 8 / 1000
    return t(f"settings.quality_{q}") + "  —  " + t("settings.quality_per_min", mb=num(mb, ".1f"))


def quality_grid(rows_text: str) -> QWidget:
    """Tableau « Quelle qualité j'obtiens vraiment ? » : lignes séparées par des retours, cases par « | »."""
    from PySide6.QtWidgets import QFrame, QGridLayout, QLabel

    box = QFrame()
    box.setObjectName("qualityGrid")
    box.setStyleSheet(f"#qualityGrid {{ border: 1px solid {theme.BORDER}; border-radius: 6px; }}"
                      f"#qualityGrid QLabel {{ border-right: 1px solid {theme.BORDER}; "
                      f"border-bottom: 1px solid {theme.BORDER}; padding: 4px 8px; }}")
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(0)
    box.cells = []                                   # type: ignore[attr-defined]
    for r, line in enumerate(x for x in rows_text.split("\n") if x.strip()):
        for c, cell in enumerate(line.split("|")):
            lab = QLabel(cell.strip())
            lab.setWordWrap(False)
            if r == 0:
                lab.setStyleSheet("font-weight: 600;")
            grid.addWidget(lab, r, c)
            box.cells.append(lab)                    # type: ignore[attr-defined]
    box.setFixedHeight(box.sizeHint().height())
    return box



def theme_tiles(layout: Any, on_pick: Any, keys: Any = None) -> Dict[str, Any]:
    """1.4.4 (C226, C227) : une tuile par thème prêt (pastille de la couleur sur le fond du thème + nom) ; la
    tuile du thème en cours est cochée. Renvoie {clé: bouton}."""
    from ..palettes import THEMES

    out = {}
    cur = (getattr(theme, "CURRENT_BACKGROUND", "default"), theme.CURRENT_THEME)
    for key in (keys or THEMES):
        bg, accent = THEMES[key]
        b = QToolButton()
        b.setIcon(logo_pixmap(theme.px(22), PALETTES[accent], theme.BACKGROUNDS[bg][1]))
        b.setIconSize(QSize(theme.px(22), theme.px(22)))
        b.setText(t(f"themes.{key}"))
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setCheckable(True)
        b.setChecked((bg, accent) == cur)
        b.setProperty("kind", "tile")
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(t("themes.tip", bg=t(f"settings.background_{bg}"), color=t(f"theme.{accent}")))
        b.clicked.connect(lambda _c=False, k=key: on_pick(k))
        layout.addWidget(b)
        out[key] = b
    return out

class _RowLabel(QLabel):
    """1.4.2 (A2-1) : libellé de début de ligne des Paramètres, qui peut descendre à 100 px (texte à la ligne)
    quand la page est étroite, au lieu d'imposer sa largeur à la page. 1.4.4 (C225) : largeur naturelle = son
    texte sur une ligne (plus de colonne de 170 px : le contrôle est aligné à droite)."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        from PySide6.QtWidgets import QSizePolicy

        self.setWordWrap(True)
        pol = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        pol.setHeightForWidth(True)
        self.setSizePolicy(pol)

    def sizeHint(self) -> Any:  # noqa: N802
        from PySide6.QtCore import QSize

        one = self.fontMetrics().horizontalAdvance(self.text()) + theme.px(6)
        return QSize(min(one, theme.px(420)), super().heightForWidth(min(one, theme.px(420))))

    def minimumSizeHint(self) -> Any:  # noqa: N802
        from PySide6.QtCore import QSize

        return QSize(theme.px(100), super().minimumSizeHint().height())


class SettingsView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._drives: Dict[str, UsbDrive] = {}
        self._swatches: Dict[str, QToolButton] = {}
        s = controller.settings

        head = self.header(t("tab.settings"))
        self.saved = label("", "accent")
        head.addWidget(self.saved)
        head.addWidget(button(t("settings.reset"), self._reset_defaults, kind="flat", icon="back",
                              tooltip=t("settings.reset_tip")))           # 1.3.2 (C57)
        # 1.4.3 (A2-18, option A) : plus de bouton « Enregistrer » : chaque réglage est enregistré dès qu'il change
        self.root.addLayout(head)
        # 1.3.1 (C28) : volet à gauche (sections + recherche), cartes de la section choisie à droite
        self._cards: list = []                 # [(section, carte)]
        self._folds: Dict[Any, Any] = {}       # 1.3.1 (C89) : carte repliable -> [contenu, flèche, résumé, ouverte]
        self._section = "general"
        body = hbox(spacing=theme.px(12))
        self.side = QWidget()
        side = vbox(self.side, spacing=theme.px(6))
        self._current_section = "general"
        self.sections = QListWidget()
        self.sections.setObjectName("settingsSections")
        self.sections.setIconSize(QSize(theme.px(16), theme.px(16)))
        self.sections.setSpacing(theme.px(2))
        self._sections_css = (f"#settingsSections::item {{ padding: {theme.px(7)}px {theme.px(6)}px; "
                              f"border-radius: {theme.px(6)}px; }}")
        self.sections.setStyleSheet(self._sections_css)
        for key, icon in SECTIONS:
            item = QListWidgetItem(qicon(icon, 16, theme.FAINT if key == "advanced" else theme.ACCENT),
                                   t(f"settings.page_{key}"))
            item.setData(Qt.UserRole, key)
            if key == "advanced":                   # C89 : réglages techniques, en dernier et en gris
                from PySide6.QtGui import QBrush, QColor

                item.setForeground(QBrush(QColor(theme.DIM)))
                item.setToolTip(t("settings.section_advanced_tip"))
            self.sections.addItem(item)
        self.sections.currentItemChanged.connect(lambda cur, _old: cur and self.show_section(cur.data(Qt.UserRole)))
        side.addWidget(self.sections, 1)
        self.side.setFixedWidth(theme.px(230))
        body.addWidget(self.side)
        right = vbox(spacing=theme.px(6))
        top = hbox(spacing=theme.px(8))
        self.search = line_edit(t("settings.search"), "search")
        self.search.setMaximumWidth(theme.px(320))
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        top.addWidget(self.search)
        self.section_menu = ShrinkCombo()          # fenêtre étroite : le volet devient une liste déroulante
        for key, icon in SECTIONS:
            self.section_menu.addItem(qicon(icon, 16, theme.ACCENT), t(f"settings.page_{key}"), key)
        self.section_menu.currentIndexChanged.connect(
            lambda i: self.show_section(self.section_menu.itemData(i)) if i >= 0 else None)
        self.section_menu.hide()
        top.addWidget(self.section_menu)
        top.addStretch(1)
        self.check_all_btn = button(t("checkall.button"), self.check_all, icon="refresh",
                                    tooltip=t("checkall.tip_short"))     # 1.3.1 (C89) ; 1.4.4 (C219) : bulle courte
        top.addWidget(self.check_all_btn)
        top.addWidget(InfoDot(t("checkall.tip")), 0, Qt.AlignVCenter)       # 1.4.4 (C219) : le détail
        right.addLayout(top)
        self.check_panel = panel()
        self.check_panel.setObjectName("checkPanel")
        self.check_panel.setStyleSheet("#checkPanel QWidget { background: transparent; }")   # C90 : sans rayures
        outer = hbox(self.check_panel, margins=theme.px(10), spacing=theme.px(6))
        self.check_lay = vbox(spacing=theme.px(4))
        outer.addLayout(self.check_lay, 1)
        self.check_close = icon_button("close", self.check_panel.hide, t("checkall.close"))   # C90 : ✕
        outer.addWidget(self.check_close, 0, Qt.AlignTop)
        self.check_panel.hide()
        self._check_timer = QTimer(self)                     # C90 : repliée seule quand tout est ✓
        self._check_timer.setSingleShot(True)
        self._check_timer.setInterval(6000)
        self._check_timer.timeout.connect(self._check_autohide)
        self._check_rows: Dict[str, Any] = {}
        right.addWidget(self.check_panel)
        area = QScrollArea()
        area.setWidgetResizable(True)
        self.area = area
        page = QWidget()
        self.page = vbox(page, spacing=theme.px(10))
        area.setWidget(page)
        right.addWidget(area, 1)
        self.no_match = label("", "dim", wrap=True)
        self.no_match.hide()
        self.page.addWidget(self.no_match)
        body.addLayout(right, 1)
        self.root.addLayout(body, 1)

        # 1.4.3 (A3-8) : cartes construites section par section ; 1.4.4 (C225) : rangées ensuite (CARD_ORDER)
        self._build_general(s)
        self._build_accessibility(s)
        self._build_usb(s)
        self._build_local(s)
        self._build_ffmpeg(s)
        self._build_analysis(s)
        self._build_pdb(s)
        self._build_search(s)
        self._build_soundcloud(s)
        self._build_soulseek(s)
        self._build_watch(s)
        self._build_engine(s)
        self._build_backups(s)
        self._build_advanced(s)
        self._arrange_sections()                                             # 1.3.2-rc.2 (C121)
        from ..wheel_guard import guard_children

        guard_children(self.area)              # 1.3.2-rc.3 (B51) : la molette fait défiler, pas les réglages
        self.page.addStretch(1)
        self.area.verticalScrollBar().valueChanged.connect(lambda _v: self._on_scroll())
        start =s.settings_section if s.settings_section in dict(SECTIONS) else "general"
        self._start_section: Optional[str] = None        # 1.4.0-rc.2 (B57) : section à montrer à l'affichage
        self.show_section(start, remember=False)

        controller.on("drive", lambda: QTimer.singleShot(300, self._pdb_refresh))
        controller.on("drive", self._backups_state)
        controller.on("drive", lambda: (setattr(self, "_space_done", False),
                                        QTimer.singleShot(400, self._space_if_shown)))   # 1.3.1 (C27), B71
        controller.on("drives", self._refresh_drives)
        controller.on("waveform_style", self._wave_style_follow)                     # 1.4.4 (C234)
        controller.on("diag_counts", self._check_counts)                              # 1.3.1 (C89)
        controller.on("drive", self._refresh_drives)
        self._refresh_drives()
        self._ffmpeg_status()
        self._engine_show()
        self._backups_state()
        self._wire_autosave()

    # ------------------------------------------------ 1.4.4 (C225) : lignes des Paramètres
    def _row(self, card: Any, text: str, *controls: Any, info: str = "", grow: bool = False, wide: bool = False) -> Any:
        """1.4.4 (C225) : une ligne = libellé (+ ⓘ) à gauche, contrôle(s) alignés à droite. `grow` : le premier
        contrôle prend la largeur libre (champ de chemin, tuiles) ; `wide` : il s'élargit jusqu'à sa largeur
        maximale, toujours aligné à droite (champ court). Un contrôle peut être une mise en page."""
        from PySide6.QtWidgets import QLayout

        row = hbox(spacing=theme.px(10))
        row.addWidget(_RowLabel(text))
        if info:
            row.addWidget(InfoDot(info), 0, Qt.AlignVCenter)
        if not grow:
            row.addStretch(1)
        for i, c in enumerate(controls):
            stretch = 1 if (grow or wide) and i == 0 else 0
            if isinstance(c, QLayout):
                row.addLayout(c, stretch)
            elif stretch:
                row.addWidget(c, stretch)
            else:
                row.addWidget(c, 0, Qt.AlignVCenter)
        card.addLayout(row)
        return row

    def _switch(self, card: Any, text: str, checked: Any, info: str = "") -> Switch:
        """1.4.4 (C225) : réglage oui / non : interrupteur à droite de son libellé."""
        sw = Switch(text)
        sw.setChecked(bool(checked))
        self._row(card, text, sw, info=info)
        return sw

    # ------------------------------------------------ 1.4.3 (A3-8) : cartes des Paramètres
    def _build_general(self, s: Any) -> None:
        """1.4.4 (C225) : Général : langue et barre latérale, mode léger, retard audio."""
        self._section = "general"
        card = self._card(t("settings.card_interface"), "settings", key="interface")
        self.lang_menu = ShrinkCombo()
        self.lang_menu.addItems(list(LANGUAGES.values()))
        self.lang_menu.setCurrentText(LANGUAGES.get(s.language, "English"))
        self.lang_menu.currentTextChanged.connect(self._language_changed)
        self._row(card, t("settings.language"), self.lang_menu)
        self._sidebar_labels = {m: t(f"settings.sidebar_{m}") for m in SIDEBAR_MODES}
        self.sidebar_menu = ShrinkCombo()
        self.sidebar_menu.addItems(list(self._sidebar_labels.values()))
        self.sidebar_menu.setCurrentText(self._sidebar_labels.get(s.sidebar_compact, self._sidebar_labels["auto"]))
        self.sidebar_menu.currentTextChanged.connect(self._sidebar_changed)
        self._row(card, t("settings.sidebar"), self.sidebar_menu)
        # 1.4.0 (C65) : mode léger pour les PC modestes ; 1.4.0-rc.5 (C165) : sa propre carte
        from ...core.machine import MODES, light_active, machine_info

        card = self._card(t("settings.performance"), "wave", key="performance")
        self._light_labels = {m: t(f"settings.light_{m}") for m in MODES}
        self.light_menu = ShrinkCombo()
        self.light_menu.addItems(list(self._light_labels.values()))
        self.light_menu.setCurrentText(self._light_labels.get(s.light_mode, self._light_labels["auto"]))
        self._row(card, t("settings.light"), self.light_menu, info=t("settings.light_tip"))
        info = machine_info()
        self.light_state = label(t("settings.light_state_on" if light_active(s, info) else "settings.light_state_off",
                                   machine=info.describe_ui()), "dim", wrap=True)
        card.addWidget(self.light_state)
        # 1.4.0-rc.5 (C165) : le décalage audio (carte Lecture) ; 1.4.4 (C225) : dans Général
        card = self._card(t("settings.playback"), "play", key="playback")
        self.latency_box = QSpinBox()                                        # 1.3.0-rc.3 (C39)
        self.latency_box.setRange(-200, 2000)                                # 1.3.0-rc.4 : Bluetooth ~1 s
        self.latency_box.setSingleStep(10)
        self.latency_box.setSuffix(" ms")
        self.latency_box.setValue(s.audio_latency_ms)
        self._row(card, t("settings.audio_latency"), self.latency_box,
                  button(t("latency.test"), self._latency_test, icon="wave"), info=t("settings.audio_latency_tip"))

    def _build_accessibility(self, s: Any) -> None:
        """1.4.4 (C225) : Accessibilité : Couleurs (thèmes, couleur, fond), Taille (zoom), Aide à l'écran."""
        from ..palettes import FEATURED
        from ..widgets import FlowLayout

        self._section = "accessibility"
        card = self._card(t("settings.card_colors"), "settings", key="colors")
        # 1.4.4 (C226) : thèmes prêts à choisir (fond + couleur), en tuiles
        tiles = FlowLayout(spacing=theme.px(6))
        self.theme_tiles = theme_tiles(tiles, self._apply_theme_preset)
        self._row(card, t("settings.themes"), tiles, grow=True)
        # 1.4.4 (C226) : 7 couleurs à portée de clic ; la pastille de la couleur actuelle ouvre « Toutes… »
        self._featured = {}
        colors = FlowLayout(spacing=theme.px(2))           # à la ligne si la fenêtre est étroite (A2-1)
        for name in FEATURED:
            b = QToolButton()
            b.setIcon(logo_pixmap(theme.px(20), PALETTES[name]))
            b.setIconSize(QSize(theme.px(20), theme.px(20)))
            b.setAutoRaise(True)
            b.setCheckable(True)
            b.setChecked(name == theme.CURRENT_THEME)
            b.setToolTip(t(f"theme.{name}"))
            b.setAccessibleName(t(f"theme.{name}"))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, n=name: self._theme_changed(n))
            colors.addWidget(b)
            self._featured[name] = b
        # 1.4.0 (C50) : une pastille (la couleur actuelle) ; un clic ouvre un petit menu avec les couleurs
        from PySide6.QtWidgets import QMenu

        self.theme_btn = QToolButton()
        self.theme_btn.setIcon(logo_pixmap(theme.px(22), PALETTES[theme.CURRENT_THEME]))
        self.theme_btn.setIconSize(QSize(theme.px(22), theme.px(22)))
        self.theme_btn.setText(t(f"theme.{theme.CURRENT_THEME}"))
        self.theme_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.theme_btn.setPopupMode(QToolButton.InstantPopup)
        self.theme_btn.setToolTip(t("settings.colors_all"))
        menu = QMenu(self.theme_btn)
        self.theme_btn.setMenu(menu)
        self._theme_families(menu)
        colors.addWidget(self.theme_btn)
        self._row(card, t("settings.theme"), colors, grow=True)
        self.theme_name = label(t(f"theme.{theme.CURRENT_THEME}"), "dim")
        self.theme_name.hide()
        self._bg_labels = {k: t(f"settings.background_{k}") for k in theme.BACKGROUNDS}     # 1.4.3 (C53) : fond
        self.bg_menu = ShrinkCombo()
        self.bg_menu.addItems(list(self._bg_labels.values()))
        self.bg_menu.setCurrentText(self._bg_labels.get(getattr(s, "background", "default"), self._bg_labels["default"]))
        self.bg_menu.currentTextChanged.connect(self._background_changed)
        self._row(card, t("settings.background"), self.bg_menu)

        # 1.4.0 (C102) : plus de curseur : − / + / 100 % et les raccourcis (Ctrl/Cmd +, −, 0, molette)
        card = self._card(t("settings.card_size"), "plus", key="size")
        self.zoom_val = label(f"{s.zoom} %", "accent")
        self.zoom_val.setMinimumWidth(theme.px(52))
        self.zoom_val.setAlignment(Qt.AlignCenter)
        self._row(card, t("settings.zoom"), icon_button("minus", lambda: self._zoom_step(-1), t("settings.zoom_out")),
                  self.zoom_val, icon_button("plus", lambda: self._zoom_step(1), t("settings.zoom_in")),
                  button(t("settings.zoom_reset"), lambda: self._zoom_step(0), icon="refresh"),
                  info=t("settings.zoom_keys", mod="⌘" if sys.platform == "darwin" else "Ctrl"))
        self.ctrl.on("zoom_preview", lambda z: self.zoom_val.setText(f"{z} %"))

        # 1.4.4 (C219) : infobulles affichées ou non (les ⓘ restent) ; (C54) revoir l'accueil
        card = self._card(t("settings.card_help"), "help", key="help")
        self.tooltips_var = self._switch(card, t("settings.show_tooltips"), getattr(s, "show_tooltips", True),
                                         info=t("settings.show_tooltips_tip"))
        self.tooltips_var.toggled.connect(self._tooltips_toggled)
        self._row(card, t("settings.welcome_label"), button(t("settings.welcome_again"), self._welcome_again,
                                                             icon="info"))

    def _tooltips_toggled(self, on: bool) -> None:
        """1.4.4 (C219) : appliqué tout de suite, dans toute l'app, sans redémarrer."""
        s = self.ctrl.settings
        s.show_tooltips = bool(on)
        try:
            s.save()
        except OSError:
            log.debug("Ignored error in _tooltips_toggled", exc_info=True)
        set_tooltips_enabled(on)

    def _build_usb(self, s: Any) -> None:
        """1.4.3 (A3-8) : Clé USB et dossier de destination (découpé de __init__, même ordre)."""
        # ---- clé USB
        self._section = "libraries"
        card = self._card(t("settings.drive"), "usb", t("settings.drive_hint"), key="drive")
        # 1.4.2 (A2-1) : la liste et les boutons passent à la ligne quand la page est étroite
        self.drive_menu = ShrinkCombo()
        self.drive_menu.setMinimumWidth(theme.px(200))
        self.connect_btn = button(t("action.connect"), self._connect, kind="primary", icon="usb")
        self.eject_btn = button(t("action.eject"), self.ctrl.eject, icon="eject")
        self.eject_btn.setToolTip(t("eject.hint"))
        card.addLayout(flow_row(self.drive_menu, icon_button("refresh", self.ctrl.refresh_drives, t("action.refresh")),
                                self.connect_btn,
                                button(t("action.disconnect"), lambda: self.ctrl.disconnect(True), icon="close"),
                                self.eject_btn))
        self.drive_state = label("", "dim", wrap=True)
        card.addWidget(self.drive_state)

        # ---- dossier de destination
        self.contents = QLineEdit(s.contents_dir)
        self.contents.setMaximumWidth(theme.px(260))
        self._row(card, t("settings.destination"), self.contents, info=t("settings.destination_hint"), wide=True)

    def _build_local(self, s: Any) -> None:
        """1.4.3 (A3-8) : Rekordbox de cet ordinateur (découpé de __init__, même ordre)."""
        # ---- Rekordbox de cet ordinateur (V0.4.0)
        from ...db.local_library import default_music_dir

        card = self._card(t("settings.local"), "computer", t("settings.local_hint"), key="local")
        self.local_db = QLineEdit(s.local_db_dir)
        self.local_db.setPlaceholderText(t("settings.local_auto"))
        self._row(card, t("settings.local_db"), self.local_db,
                  button(t("action.browse"), lambda: self._browse_into(self.local_db), icon="folder"), grow=True)
        self.local_music = QLineEdit(s.local_music_dir)
        self.local_music.setPlaceholderText(str(default_music_dir()))
        self._row(card, t("settings.local_music"), self.local_music,
                  button(t("action.browse"), lambda: self._browse_into(self.local_music), icon="folder"), grow=True)
        row = hbox()
        self.local_state = label("", "dim", wrap=True)
        row.addWidget(self.local_state, 1)
        self.local_btn = button(t("action.connect"), self.ctrl.connect_local, kind="primary", icon="computer")
        row.addWidget(self.local_btn)
        card.addLayout(row)
        self.protect_var = self._switch(card, t("settings.protect_foreign"), s.protect_foreign,       # A07, C156
                                        info=t("settings.protect_foreign_hint"))

    def _build_ffmpeg(self, s: Any) -> None:
        """1.4.3 (A3-8) : FFmpeg (Avancé, repliée quand tout va bien) (découpé de __init__, même ordre)."""
        # ---- FFmpeg (1.3.1, C89 : Avancé, repliée quand tout va bien)
        self._section = "advanced"
        card = self._card("FFmpeg", "wave", t("settings.ffmpeg_hint"), fold=True, key="ffmpeg")
        self.ffmpeg_card = self._cards[-1][1]
        row = hbox()
        self.ffmpeg = QLineEdit(s.ffmpeg_location)
        self.ffmpeg.setPlaceholderText(t("settings.ffmpeg_placeholder"))
        self.ffmpeg.textEdited.connect(lambda _t: self._ffmpeg_status())
        row.addWidget(self.ffmpeg, 1)
        row.addWidget(button(t("action.browse"), self._browse_ffmpeg, icon="folder"))
        card.addLayout(row)
        self.ffmpeg_state = label("", "dim", wrap=True)     # 1.4.2 (A2-1) : long chemin (Windows) à la ligne
        card.addWidget(self.ffmpeg_state)

    def _build_analysis(self, s: Any) -> None:
        """1.4.4 (C225) : Analyse en quatre cartes (Après un téléchargement, Grille et repères, Volume et fichiers,
        Affichage des résultats) ; réanalyse des sons de Rekordbox et Diagnostic à l'ouverture dans Avancé."""
        self._section = "analysis"
        card = self._card(t("settings.card_after"), "download", t("settings.analysis_hint"), key="after")
        self.analyze_usb_var = self._switch(card, t("settings.analyze_after_usb"),            # 1.3.0-rc.3 (C32)
                                            s.analyze_after_download_usb)
        self.analyze_local_var = self._switch(card, t("settings.analyze_after_local"), s.analyze_after_download_local)
        row = hbox()
        row.addWidget(button(t("settings.analyse_now"), lambda: self.ctrl._emit("show_unanalysed"), icon="wave"))
        row.addStretch(1)
        card.addLayout(row)

        card = self._card(t("settings.card_grid"), "grid", key="grid")
        self.tempo_grid = ShrinkCombo()                                             # 1.4.3 (C16)
        for key in ("auto", "never"):
            self.tempo_grid.addItem(t(f"settings.tempo_grid_{key}"), key)
        self.tempo_grid.setCurrentIndex(max(0, self.tempo_grid.findData(getattr(s, "tempo_grid", "auto"))))
        self._row(card, t("settings.tempo_grid"), self.tempo_grid, info=t("settings.tempo_grid_hint"))
        self.cue_var = self._switch(card, t("settings.auto_cue"), s.auto_cue, info=t("settings.auto_cue_hint"))

        card = self._card(t("settings.card_volume"), "volume", key="volume")
        self.gain_var = self._switch(card, t("settings.auto_gain"), s.auto_gain,              # 1.4.3 (C109)
                                     info=t("settings.auto_gain_hint"))
        self.tags_var = self._switch(card, t("settings.write_tags"), s.write_tags,            # 1.4.3 (S05)
                                     info=t("settings.write_tags_hint"))

        card = self._card(t("settings.card_display"), "wave", key="display")
        self.wave_style = ShrinkCombo()                                             # 1.4.1 (C77)
        for key in ("blue", "rgb", "3band"):
            self.wave_style.addItem(t(f"settings.waveform_{key}"), key)
        self.wave_style.setCurrentIndex(max(0, self.wave_style.findData(s.waveform_style)))
        self._row(card, t("settings.waveform_style"), self.wave_style, info=t("settings.waveform_style_hint"))
        self._notation_labels = {k: t(f"settings.notation_{k}") for k in KEY_NOTATIONS}
        self.notation = ShrinkCombo()
        self.notation.addItems(list(self._notation_labels.values()))
        self.notation.setCurrentText(self._notation_labels.get(s.key_notation, self._notation_labels["auto"]))
        self._row(card, t("settings.key_notation"), self.notation)

        # ---- Avancé : réglages d'analyse rarement changés
        self._section = "advanced"
        card = self._card(t("settings.card_analysis_adv"), "key", key="analysis_adv")
        self._row(card, t("settings.reanalyse_rekordbox"), info=t("settings.reanalyse_rekordbox_hint"))   # C131, D20
        row = flow_row(spacing=12)                                                  # 1.4.2 (A2-1)
        self.reanalyse_vars = {}
        for part in ("grid", "key", "waves"):
            box = QCheckBox(t(f"reanalyse.part_{part}"))
            box.setChecked(part in s.reanalyze_rekordbox)
            box.setToolTip(t(f"reanalyse.hint_{part}"))
            row.addWidget(box)
            self.reanalyse_vars[part] = box
        card.addLayout(row)
        self.diag_auto_var = self._switch(card, t("settings.diag_auto"), getattr(s, "diag_auto", False),  # B103
                                          info=t("settings.diag_auto_tip"))

    def _build_pdb(self, s: Any) -> None:
        """1.4.3 (A3-8) : Anciennes platines (export.pdb) (découpé de __init__, même ordre)."""
        # ---- anciennes platines : export.pdb (1.3.1, C90 : état et synchronisation dans Bibliothèques,
        # les deux options techniques dans Avancé)
        self._section = "libraries"
        card = self._card(t("settings.pdb"), "library", t("settings.pdb_hint"), key="pdb")
        self.pdb_card = self._cards[-1][1]
        self.pdb_sync_btn = button(t("settings.sync_now"), self.ctrl.pdb_sync_now, kind="primary", icon="refresh")
        card.addLayout(flow_row(button(t("settings.check"), self._pdb_refresh, icon="check"),
                                self.pdb_sync_btn))                     # 1.4.2 (A2-1) : à la ligne si étroit
        self.pdb_state = label("", "dim", wrap=True)
        card.addWidget(self.pdb_state)
        self._player_formats = {"": t("players.keep"), "wav": t("players.wav"), "aiff": t("players.aiff")}
        self.player_format = ShrinkCombo()                    # 1.4.0 (C26 sens C)
        self.player_format.addItems(list(self._player_formats.values()))
        self.player_format.setCurrentText(self._player_formats.get(s.player_format, self._player_formats[""]))
        self._row(card, t("players.settings_flac"), self.player_format, info=t("players.settings_tip"))
        self._section = "advanced"
        card = self._card(t("settings.pdb_options"), "library", t("settings.pdb_hint"), key="pdb_options")
        self.pdb_var = self._switch(card, t("settings.pdb_sync"), s.pdb_sync == "auto")
        self.pdb_growth_var = self._switch(card, t("settings.pdb_growth"), s.pdb_allow_growth)

    def _build_search(self, s: Any) -> None:
        """1.4.3 (A3-8) : Recherche, format et qualité, YouTube (découpé de __init__, même ordre)."""
        # 1.4.0-rc.5 (C165) : l'ancienne carte « Téléchargements » (14 réglages mêlés) coupée en trois :
        # Recherche, Format et qualité, YouTube
        self._section = "download"
        card = self._card(t("settings.search_card"), "search", key="search")
        self.views_var = self._switch(card, t("settings.fetch_views"), s.fetch_views)
        self.meta_var = self._switch(card, t("settings.fetch_metadata"), s.fetch_metadata)
        card = self._card(t("settings.format_card"), "download", key="format")
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.format"))))
        # 1.4.1 (C143, D15) : une seule liste de six choix ; chaque ligne dit le vrai format obtenu, une seule
        # porte « (meilleur flux) » ; taille par minute à côté. « Même volume » retiré (décision du 05/11).
        from ...settings import DOWNLOAD_QUALITIES

        self._format_labels = {q: quality_label(q) for q in DOWNLOAD_QUALITIES}
        self.format_menu = ShrinkCombo()
        for i, q in enumerate(DOWNLOAD_QUALITIES):
            self.format_menu.addItem(self._format_labels[q], q)
            self.format_menu.setItemData(i, t(f"settings.quality_{q}_tip"), Qt.ToolTipRole)
        self.format_menu.setCurrentText(self._format_labels.get(s.download_quality, self._format_labels["original"]))
        row.addWidget(self.format_menu, 1)               # 1.4.2 (A2-1) : toute la largeur libre, texte entier
        card.addLayout(row)
        # 1.4.0-rc.2 (C137) : convertir en MP3 ne rend pas la qualité perdue ; on le dit au moment du choix
        self.format_warn = label(t("quality.mp3_warning"), "dim", wrap=True)
        self.format_warn.setStyleSheet(f"color: {theme.WARN};")
        card.addWidget(self.format_warn)
        # 1.4.0-rc.4 (C146) : fichiers plus lourds avec le meilleur flux (affiché seulement s'il est choisi)
        self.yt_best_warn = label(t("yt.settings_best_hint"), "dim", wrap=True)
        self.yt_best_warn.setStyleSheet(f"color: {theme.WARN};")
        card.addWidget(self.yt_best_warn)
        self.format_menu.currentIndexChanged.connect(lambda _i: self._format_hints())
        self._format_hints()
        # 1.4.0-rc.2 (C137) : ce que donne vraiment chaque source, en équivalent MP3 ; rc.5 (C165) : replié
        self.quality_toggle = QToolButton()
        self.quality_toggle.setText(t("quality.real_title"))
        self.quality_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.quality_toggle.setArrowType(Qt.RightArrow)
        self.quality_toggle.setAutoRaise(True)
        self.quality_toggle.setCheckable(True)
        self.quality_toggle.setCursor(Qt.PointingHandCursor)
        card.addWidget(self.quality_toggle)
        self.quality_box = QWidget()
        qlay = vbox(self.quality_box, spacing=theme.px(6))
        # 1.4.0-rc.3 (B69, C143) : vraie grille à cases tracées, hauteur fixe (le texte HTML tremblait au
        # défilement : sa hauteur était recalculée à chaque redessin)
        self.quality_table = quality_grid(t("quality.real_rows"))
        qlay.addWidget(self.quality_table)
        qlay.addWidget(label(t("quality.real_note"), "dim", wrap=True))
        self.quality_box.hide()
        card.addWidget(self.quality_box)
        self.quality_toggle.toggled.connect(lambda on: (self.quality_box.setVisible(on),
                                                        self.quality_toggle.setArrowType(
                                                            Qt.DownArrow if on else Qt.RightArrow)))
        card = self._card("YouTube", "download", key="youtube")     # 1.4.1 (C143) : meilleur flux dans la liste
        from ...core.soundcloud import BROWSERS as _YT_BROWSERS

        self._yt_browsers = {"": t("yt.settings_no_account")}
        self._yt_browsers.update({b: t("sc.settings_browser", name=b.capitalize()) for b in _YT_BROWSERS})
        self.yt_browser = ShrinkCombo()
        self.yt_browser.addItems(list(self._yt_browsers.values()))
        self.yt_browser.setCurrentText(self._yt_browsers.get(s.youtube_browser, self._yt_browsers[""]))
        self._row(card, t("yt.settings_account"), self.yt_browser, info=t("yt.settings_account_tip"))

    def _build_soundcloud(self, s: Any) -> None:
        """1.4.3 (A3-8) : SoundCloud, fichier d'origine (découpé de __init__, même ordre)."""
        # ---- 1.4.0 (C10.1) : SoundCloud, fichier d'origine
        card = self._card(t("sc.settings_title"), "download", t("sc.settings_hint"), key="soundcloud")
        self.sc_original_var = self._switch(card, t("sc.settings_original"), s.soundcloud_original,
                                            info=t("sc.settings_original_tip"))
        from ...core.soundcloud import BROWSERS

        self._sc_browsers = {"": t("sc.settings_no_account")}
        # 1.4.0-rc.4 (B82) : Chrome et Edge chiffrent leurs cookies sous Windows : lecture presque impossible
        self._sc_browsers.update({b: t("sc.settings_browser_unreliable" if sys.platform == "win32"
                                       and b in ("chrome", "edge", "brave", "opera", "vivaldi", "chromium")
                                       else "sc.settings_browser", name=b.capitalize()) for b in BROWSERS})
        self.sc_browser = ShrinkCombo()
        self.sc_browser.addItems(list(self._sc_browsers.values()))
        self.sc_browser.setCurrentText(self._sc_browsers.get(s.soundcloud_browser, self._sc_browsers[""]))
        self._row(card, t("sc.settings_account"), self.sc_browser, info=t("sc.settings_browser_tip"))
        self.sc_token = QLineEdit(s.soundcloud_token)
        self.sc_token.setEchoMode(QLineEdit.Password)
        self.sc_token.setPlaceholderText(t("sc.settings_token_ph"))
        self.sc_token.setMaximumWidth(theme.px(FIELD_PX))                # C165 : champs de même largeur
        self._row(card, t("sc.settings_token"), self.sc_token, info=t("sc.settings_token_tip"), wide=True)

    def _build_soulseek(self, s: Any) -> None:
        """1.4.3 (A3-8) : Soulseek (découpé de __init__, même ordre)."""
        # ---- 1.4.0 (C10.2) : Soulseek, désactivé par défaut, avertissement à la première activation
        card = self._card(t("slsk.settings_title"), "download", t("slsk.settings_hint"), key="soulseek")
        self.slsk_var = self._switch(card, t("slsk.settings_enable"), s.soulseek_enabled)
        self.slsk_var.toggled.connect(self._slsk_toggled)
        self.slsk_user = QLineEdit(s.soulseek_user)
        self.slsk_user.setPlaceholderText(t("slsk.settings_user_ph"))
        self.slsk_user.setMaximumWidth(theme.px(FIELD_PX))
        self._row(card, t("slsk.settings_user"), self.slsk_user, info=t("slsk.settings_account_hint"), wide=True)
        self.slsk_password = QLineEdit(s.soulseek_password)
        self.slsk_password.setEchoMode(QLineEdit.Password)
        self.slsk_password.setMaximumWidth(theme.px(FIELD_PX))
        self._row(card, t("slsk.settings_password"), self.slsk_password, wide=True)
        self.slsk_share_var = self._switch(card, t("slsk.settings_share"), s.soulseek_share,
                                           info=t("slsk.settings_share_tip"))
        card.addWidget(label(t("slsk.settings_warning_short"), "warn", wrap=True))

    def _build_watch(self, s: Any) -> None:
        """1.4.3 (A3-8) : Dossier surveillé (découpé de __init__, même ordre)."""
        # ---- 1.4.0 (C10.3) : dossier surveillé (achats, promos, téléchargements gratuits)
        self._section = "libraries"                  # 1.4.0-rc.5 (C165) : il alimente la bibliothèque
        card = self._card(t("watch.settings_title"), "watch", t("watch.settings_hint"), show_hint=True,
                          key="watch")                # C160 : à quoi il sert, écrit en clair
        row = hbox()
        self.watch_folder = QLineEdit(s.watch_folder)
        self.watch_folder.setPlaceholderText(t("watch.settings_off"))
        self.watch_folder.setReadOnly(True)
        row.addWidget(self.watch_folder, 1)
        row.addWidget(button(t("watch.settings_browse"), lambda: self._browse_into(self.watch_folder), icon="folder"))
        row.addWidget(button(t("watch.settings_clear"), lambda: self.watch_folder.setText(""), icon="close"))
        card.addLayout(row)
        # 1.4.2 (B102) : où ranger ce qui arrive (bibliothèque de l'ordinateur par défaut, ou clé ouverte)
        self.watch_target = ShrinkCombo()
        self.watch_target.addItem(t("watch.target_local"), "local")
        self.watch_target.addItem(t("watch.target_usb"), "usb")
        self.watch_target.setCurrentIndex(1 if s.watch_target == "usb" else 0)
        self._row(card, t("watch.settings_target"), self.watch_target, info=t("watch.settings_target_tip"))
        self.watch_playlist_var = self._switch(card, t("watch.settings_playlist", name=t("watch.playlist")),
                                               s.watch_playlist)

    def _build_engine(self, s: Any) -> None:
        """1.4.3 (A3-8) : Moteur de téléchargement (yt-dlp) (découpé de __init__, même ordre)."""
        # ---- moteur de téléchargement (yt-dlp) : mises à jour à la demande seulement (C89 : Avancé, repliée)
        self._section = "advanced"
        card = self._card(t("engine.title"), "refresh", t("engine.hint"), fold=True, key="engine")
        self.engine_card = self._cards[-1][1]
        self.engine_state = label("", "dim", wrap=True)
        card.addWidget(self.engine_state)
        row = hbox()
        self.engine_check_btn = button(t("engine.check"), self._engine_check, icon="search")
        row.addWidget(self.engine_check_btn)
        self.engine_install_btn = button(t("engine.install"), self._engine_install, kind="primary", icon="download")
        self.engine_install_btn.hide()
        row.addWidget(self.engine_install_btn)
        self.engine_back_btn = button(t("engine.rollback"), self._engine_rollback, kind="flat", icon="back")
        row.addWidget(self.engine_back_btn)
        row.addStretch(1)
        card.addLayout(row)
        self._engine_release = None

    def _build_backups(self, s: Any) -> None:
        """1.4.3 (A3-8) : Sauvegardes et espace occupé ; 1.4.4 (C225) : leur propre section."""
        # ---- sauvegardes
        self._section = "storage"
        card = self._card(t("settings.backups"), "folder", t("settings.backups_hint"), key="backups")
        # 1.4.4 (C235) : un seul réglage, Légères / Normales / Complètes (+ « Supprimer les anciennes »)
        self.keep = ShrinkCombo()
        for lvl in ("light", "normal", "full"):
            self.keep.addItem(t(f"settings.backup_level_{lvl}"), lvl)
        self.keep.setCurrentIndex(max(0, self.keep.findData(s.backup_level or "normal")))
        self._row(card, t("settings.backup_level"), self.keep, info=t("settings.backup_level_tip"))
        self.merge_undo = ShrinkCombo()                    # 1.3.2 (C82) : délai pour annuler une fusion
        for v in (5, 10, 30):
            self.merge_undo.addItem(t("settings.seconds", n=v), v)
        self.merge_undo.setCurrentIndex(max(0, self.merge_undo.findData(s.merge_undo_s)))
        self._row(card, t("settings.merge_undo"), self.merge_undo, info=t("settings.merge_undo_tip"))
        row = hbox()                                       # V1.2.0 : points de restauration, journal, retrait
        self.points_btn = button(t("backups.open"), self._open_backups, kind="primary", icon="back")
        row.addWidget(self.points_btn)
        row.addStretch(1)
        self.uninstall_btn = button(t("uninstall.open"), self._open_uninstall, kind="flat", icon="trash")
        self.uninstall_btn.setVisible(self.ctrl.can_uninstall())
        row.addWidget(self.uninstall_btn)
        card.addLayout(row)
        # 1.4.4 (C235) : sur sa propre ligne (A2-1 : aucune ligne plus large que la page)
        row = hbox()
        self.prune_btn = button(t("settings.backup_prune"), self._prune_backups, kind="flat", icon="trash",
                                tooltip=t("settings.backup_prune_tip"))
        row.addWidget(self.prune_btn)
        row.addStretch(1)
        card.addLayout(row)
        self.points_hint = label("", "faint", wrap=True)
        card.addWidget(self.points_hint)
        # 1.3.1 (C27) : espace occupé (calculé à l'ouverture de la section)
        from ..space_card import SpaceCard

        self._space_box_layout = self._card(t("settings.space"), "usb", t("settings.space_hint"), key="space")
        self.space = SpaceCard(self._space_box_layout, self.ctrl)
        self.space_box = self._cards[-1][1]
        self._build_about(s)

    def _build_advanced(self, s: Any) -> None:
        """1.4.3 (A3-8) : Avancé (clé forcée) (découpé de __init__, même ordre)."""
        # ---- 1.3.1 (C89) : réglages techniques peu utilisés (Avancé)
        self._section = "advanced"
        card = self._card(t("settings.tech"), "usb", t("settings.tech_hint"), key="tech")
        self.forced = QLineEdit(s.forced_drive)
        self.forced.setPlaceholderText(t("settings.forced_placeholder"))
        self.forced.setMaximumWidth(theme.px(120))
        self._row(card, t("settings.forced_drive_short"), self.forced, info=t("settings.forced_drive"))

    # ------------------------------------------------ DJSync : version, mises à jour, à propos
    def _build_about(self, s: Any) -> None:
        """1.2.0-rc.4 : mise à jour en un clic (C20) et « À propos » (C19)."""
        from ... import full_version

        self._section = "djsync"
        # 1.4.0-rc.5 (C165) : trois cartes au lieu d'une (Mises à jour, À propos, Cette installation) ;
        # la version et « Rechercher » sur la même ligne
        card = self._card(t("about.updates"), "refresh", key="updates")
        self.version_lbl = label(t("about.version", version=full_version()), "accent")
        self.version_lbl = self._fixed(self.version_lbl)          # 1.4.2 (A2-1) : nouveau libellé
        row = flow_row()                                          # 1.4.2 (A2-1) : boutons à la ligne si étroit
        row.addWidget(self.version_lbl)
        self.update_state = label("", "dim", wrap=True)
        self.update_bar = QProgressBar()
        self.update_bar.setRange(0, 1000)
        self.update_bar.setTextVisible(False)
        self.update_bar.hide()
        card.addWidget(self.update_bar)
        self.update_check_btn = button(t("update.check"), lambda: self.ctrl.app_update_check(manual=True),
                                       icon="search")
        row.addWidget(self.update_check_btn)
        self.update_install_btn = button("", self._install_update, kind="primary", icon="download")
        self.update_install_btn.hide()
        row.addWidget(self.update_install_btn)
        self.update_cancel_btn = button(t("action.cancel"), self.ctrl.app_update_cancel, kind="flat")
        self.update_cancel_btn.hide()
        row.addWidget(self.update_cancel_btn)
        self.update_restart_btn = button(t("update.restart"), self.ctrl.app_update_restart, kind="primary",
                                         icon="refresh")
        self.update_restart_btn.hide()
        row.addWidget(self.update_restart_btn)
        card.addLayout(row)
        card.addWidget(self.update_state)
        self.update_var = self._switch(card, t("update.auto"), s.check_updates)
        # 1.3.2 (C96) : une case au lieu du menu « Versions proposées » (auto / stables / stables et test),
        # et le choix de la version à installer, plus ancienne comprise
        from ..version_dialog import show_test_versions

        # 1.3.2-rc.2 (C96, test MAJ-1) : sur une ligne, la liste des versions, le bouton d'installation à droite
        pick_lbl = self._fixed(label(t("update.pick_label")))
        self.version_menu = ShrinkCombo()
        self.version_menu.setMinimumWidth(theme.px(180))
        self.version_menu.addItem(t("update.pick_loading"))
        self.version_menu.setEnabled(False)
        self.version_menu.currentIndexChanged.connect(lambda _i: self._version_refresh())
        self.version_install_btn = button(t("update.pick_install"), self._install_picked, kind="primary",
                                          icon="download")
        self.version_install_btn.setEnabled(False)
        card.addLayout(flow_row(pick_lbl, self.version_menu, self.version_install_btn))
        # 1.4.2 (A2-1) : la case sur sa propre ligne (la rangée imposait 880 px à la page)
        self.show_rc_var = self._switch(card, t("update.show_rc"), show_test_versions(s.update_channel, full_version()))
        self.show_rc_var.toggled.connect(self._show_rc_toggled)
        self._versions: list = []
        self._versions_loaded = False
        # 1.3.2 (C70) : lancer DJSync depuis la recherche du système ; 1.3.1 (C88) : désinstaller
        from ...core import shortcut as _sc

        card = self._card(t("about.install"), "computer", key="install")
        self.shortcut_var = self._switch(card, t("settings.shortcut"), s.start_menu_shortcut,
                                         info=t("settings.shortcut_tip") if _sc.target() is not None
                                         else t("settings.shortcut_source"))
        self.shortcut_var.setEnabled(_sc.target() is not None)
        self.shortcut_var.toggled.connect(self._shortcut_toggled)
        row = hbox()                                    # en dernier : l'action qui retire tout
        self.app_uninstall_btn = button(t("uninstall.app_open"), self._open_app_uninstall, kind="danger", icon="trash")
        mode = self.ctrl.uninstall_mode()
        self.app_uninstall_btn.setEnabled(mode != "source")
        self.app_uninstall_btn.setToolTip(t("uninstall.app_source") if mode == "source"
                                          else t("uninstall.app_tip_drive") if mode == "drive"
                                          else t("uninstall.app_tip_computer"))
        row.addWidget(self.app_uninstall_btn)
        row.addStretch(1)
        card.addLayout(row)
        card = self._card(t("about.card"), "info", key="about")
        card.addWidget(label(t("about.credits"), "dim", wrap=True))
        # 1.3.1 (C55) : remerciements
        from ...credits import thanks_text
        from ...i18n import get_language

        thanks = label("🙏 " + thanks_text(get_language()), wrap=True)
        thanks.setObjectName("about_thanks")
        card.addWidget(thanks)
        links = []                                       # 1.4.2 (A2-1) : passent à la ligne si besoin
        links.append(button(t("about.github"), lambda: self.ctrl._emit("open_url", "https://github.com/Pikkol0/djsync"),
                             icon="go"))
        links.append(button(t("about.license"), lambda: self._show_text("LICENSE", t("about.license")), icon="info"))
        links.append(button(t("about.third_party"),
                             lambda: self._show_text("THIRD_PARTY_NOTICES.md", t("about.third_party")), icon="info"))
        card.addLayout(flow_row(*links))
        # 1.3.1 (C28) : rapports d'erreur et journal dans « Confidentialité »
        self._section = "privacy"
        card = self._card(t("settings.reports_card"), "info", key="reports")   # C165 : pas le titre de la section
        self._report_labels = {"ask": t("err_report.mode_ask"), "always": t("err_report.mode_always"),
                               "never": t("err_report.mode_never")}
        self.report_menu = ShrinkCombo()                # 1.2.3 : rapports d'erreur
        self.report_menu.addItems(list(self._report_labels.values()))
        self.report_menu.setCurrentText(self._report_labels.get(s.error_reports, self._report_labels["ask"]))
        self._row(card, t("err_report.setting"), self.report_menu, info=t("err_report.what"))
        self._row(card, t("settings.log_label"), button(t("settings.open_log"), self._open_log, icon="folder"))
        self.ctrl.on("app_update_state", self._update_state)
        self._update_state()

    def _shortcut_toggled(self, on: bool) -> None:
        self.ctrl.settings.start_menu_shortcut = bool(on)
        self.ctrl.settings.save()
        self.ctrl.refresh_shortcut(announce=True)

    def _welcome_again(self) -> None:
        from ..welcome import WelcomeDialog

        WelcomeDialog(self, self.ctrl)


    # 1.3.2-rc.2 (C96) : liste des versions directement dans la carte DJSync
    def load_versions(self) -> None:
        from .common import alive

        self._versions_loaded = True
        self.version_menu.blockSignals(True)
        self.version_menu.clear()
        self.version_menu.addItem(t("update.pick_loading"))
        self.version_menu.setEnabled(False)
        self.version_menu.blockSignals(False)
        self._versions = []
        self._version_refresh()

        def ok(versions: list) -> None:
            if not alive(self.version_menu):
                return
            from ... import full_version
            from ..version_dialog import version_text

            current = full_version()
            self._versions = list(versions)
            self.version_menu.blockSignals(True)
            self.version_menu.clear()
            for up in self._versions:
                self.version_menu.addItem(version_text(up, current), up.version)
            if not self._versions:
                self.version_menu.addItem(t("update.pick_none"))
            self.version_menu.setEnabled(bool(self._versions))
            mine = next((k for k, up in enumerate(self._versions) if up.version == current), -1)
            self.version_menu.setCurrentIndex(0 if mine != 0 or len(self._versions) < 2 else 1)
            self.version_menu.blockSignals(False)
            self._version_refresh()

        def failed(exc: BaseException) -> None:
            if not alive(self.version_menu):
                return
            from ..controller import is_offline_error

            self.version_menu.clear()
            self.version_menu.addItem(t("error.offline") if is_offline_error(exc) else t("update.pick_failed"))
            self.version_menu.setEnabled(False)
            self._version_refresh()

        self.ctrl.app_versions(self.show_rc_var.isChecked(), ok, failed)

    def picked_version(self) -> Any:
        i = self.version_menu.currentIndex()
        return self._versions[i] if 0 <= i < len(self._versions) else None

    def _version_refresh(self) -> None:
        from ... import full_version
        from ..version_dialog import install_label

        up, current = self.picked_version(), full_version()
        self.version_install_btn.setText(install_label(self.ctrl, up, current))
        self.version_install_btn.setEnabled(up is not None and up.version != current
                                            and self.ctrl.update_progress is None)

    def _install_picked(self) -> None:
        from ... import full_version
        from ..version_dialog import install_version

        install_version(self, self.ctrl, self.picked_version(), full_version())

    def _show_rc_toggled(self, on: bool) -> None:
        s = self.ctrl.settings
        s.update_channel = "test" if on else "stable"
        try:
            s.save()
        except OSError:
            log.debug("Ignored error in _show_rc_toggled", exc_info=True)  # 1.4.3 (A3-4)
        self.load_versions()

    def _install_update(self) -> None:
        if self.ctrl.available_update is not None:
            self.ctrl.app_update_install(self.ctrl.available_update)

    def _update_state(self) -> None:
        from .common import alive

        if not alive(self.update_state):
            return
        upd, prog, ready = self.ctrl.available_update, self.ctrl.update_progress, self.ctrl.update_ready
        if hasattr(self, "version_install_btn"):
            self._version_refresh()                          # C96 : pas d'installation pendant une autre
        self.update_bar.setVisible(prog is not None)
        self.update_cancel_btn.setVisible(prog is not None)
        self.update_restart_btn.setVisible(ready is not None and prog is None)
        self.update_install_btn.setVisible(upd is not None and prog is None and ready is None)
        self.update_check_btn.setEnabled(prog is None)
        if upd is not None:
            self.update_install_btn.setText(t("update.install_to", version=upd.version) if self.ctrl.can_self_update()
                                            else t("update.ok"))
        if prog is not None:
            done, total = prog
            self.update_bar.setValue(int(1000 * done / total) if total else 0)
            self.update_state.setText(t("update.downloading", mb=f"{done / 1e6:.0f}",
                                        total=f"{total / 1e6:.0f}" if total else "?"))
        elif ready is not None:
            self.update_state.setText(t("update.ready_msg", version=ready[2]))
        elif upd is not None:
            self.update_state.setText(t("update.msg", version=upd.version))
        else:
            self.update_state.setText("")
        self.update_state.setVisible(bool(self.update_state.text()))      # 1.4.4 (C225) : pas de ligne vide

    def _show_text(self, name: str, title: str) -> None:
        """Licence ou composants tiers : fichiers livrés avec DJSync (ou à la racine du dépôt)."""
        import sys
        from pathlib import Path

        from ..help_dialog import TextDialog

        roots = [Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parents[3]]
        path = next((r / name for r in roots if str(r) and (r / name).is_file()), None)
        text = path.read_text(encoding="utf-8", errors="replace") if path else t("about.missing", name=name)
        TextDialog(self, title, text)

    def _card(self, title: str, icon: str = "", hint: str = "", fold: bool = False, show_hint: bool = False,
              key: str = "") -> Any:
        """Carte de réglages : icône + titre ; l'explication éventuelle derrière un ⓘ (1.4.4, C219 : bulle au
        survol, qui reste au clic). 1.3.1 (C89) : `fold` = repliable (flèche + une ligne d'état), repliée tant que
        tout va bien. 1.4.0-rc.5 (C165) : `show_hint` = l'explication écrite sous le titre (réglage dont l'utilité
        ne se devine pas) ; `key` = place de la carte dans sa section (CARD_ORDER)."""
        box = panel()
        box.setObjectName(f"card_{key}" if key else "")
        # 1.4.4 (C225) : lignes espacées
        lay = vbox(box, margins=theme.px(16), spacing=theme.px(12))
        head = hbox(spacing=theme.px(8))
        arrow = None
        if fold:
            arrow = QToolButton()
            arrow.setAutoRaise(True)
            arrow.setArrowType(Qt.RightArrow)
            arrow.setToolTip(t("settings.fold_tip"))
            arrow.clicked.connect(lambda: self.set_folded(box, not self._folds[box][3]))
            head.addWidget(arrow)
        if icon:
            head.addWidget(icon_label(icon, 18, theme.ACCENT))
        head.addWidget(ShrinkLabel(title, "h2"))             # 1.4.2 (A2-1) : titre à la ligne si étroit
        if hint and not show_hint:
            head.addWidget(InfoDot(hint), 0, Qt.AlignVCenter)
        summary = None
        if fold:
            summary = label("", "dim", wrap=True)                # 1.4.2 (A2-1)
            head.addWidget(summary, 1)
        head.addStretch(1)
        lay.addLayout(head)
        if hint and show_hint:
            lay.addWidget(label(hint, "dim", wrap=True))
        self.page.addWidget(box)
        self._cards.append((self._section, box))
        if not fold:
            return lay
        inner = QWidget()
        inner_lay = vbox(inner, spacing=theme.px(12))
        lay.addWidget(inner)
        self._folds[box] = [inner, arrow, summary, False]
        inner.hide()
        return inner_lay

    def set_folded(self, box: Any, opened: bool, summary: str = None) -> None:
        """C89 : ouvre ou replie une carte repliable ; `summary` = ligne d'état à côté du titre."""
        f = self._folds.get(box)
        if f is None:
            return
        f[3] = bool(opened)
        if summary is not None:
            f[2].setText(summary)
        f[0].setVisible(f[3] or bool(self.search.text().split()))
        f[1].setArrowType(Qt.DownArrow if f[3] else Qt.RightArrow)
        f[2].setVisible(not f[3])

    # ------------------------------------------------------- 1.3.1 (C28) : sections et recherche
    def _arrange_sections(self) -> None:
        """1.4.4 (C225) : une page par section : titre (et sous-titre) de section puis ses cartes, sur une seule
        colonne ; seule la section choisie est affichée (`_apply_filter`), la recherche couvre toutes les
        sections (1.3.2-rc.2, C121 : avant, toutes les sections l'une sous l'autre)."""
        for _sec, box in self._cards:
            self.page.removeWidget(box)
        # 1.4.0-rc.5 (C165) : cartes rangées par usage (CARD_ORDER) dans leur section, les autres dans l'ordre
        # de création ; la liste elle-même est rangée (sections, recherche et tests la lisent)
        rank = {key: i for i, (key, _icon) in enumerate(SECTIONS)}
        order = list(self._cards)
        self._cards.sort(key=lambda sb: (rank.get(sb[0], 99), CARD_ORDER.index(sb[1].objectName())
                                         if sb[1].objectName() in CARD_ORDER else 99, order.index(sb)))
        self._heads: Dict[str, QLabel] = {}
        self._subs: Dict[str, QLabel] = {}
        for key, _icon in SECTIONS:
            boxes = [box for sec, box in self._cards if sec == key]
            if not boxes:
                continue
            head = label(t(f"settings.page_{key}"), "h2")
            head.setObjectName("settingsSectionTitle")
            head.setContentsMargins(0, theme.px(6), 0, 0)
            self._heads[key] = head
            self.page.addWidget(head)
            sub = label(t(f"settings.page_{key}_sub"), "dim", wrap=True)
            self._subs[key] = sub
            self.page.addWidget(sub)
            for box in boxes:
                self.page.addWidget(box)

    def section_cards(self, key: str) -> list:
        return [box for sec, box in self._cards if sec == key]

    def section_of(self, box: Any) -> str:
        """1.4.4 (C225) : section d'une carte (ou de la carte qui contient un réglage)."""
        card = self._card_of(box)
        return next((sec for sec, b in self._cards if b is card), "")

    def _card_of(self, w: Any) -> Any:
        boxes = {id(b): b for _s, b in self._cards}
        while w is not None and id(w) not in boxes:
            w = w.parentWidget()
        return w

    def _set_nav(self, key: str) -> None:
        """Surligne la section dans le volet (et la liste déroulante) sans rien déclencher."""
        self._current_section = key
        # C90 : « Avancé » reste gris même sélectionné
        self.sections.setStyleSheet(self._sections_css + (f" #settingsSections::item:selected {{ color: {theme.DIM}; }}"
                                                          if key == "advanced" else ""))
        idx = [k for k, _i in SECTIONS].index(key)
        for w in (self.sections, self.section_menu):
            w.blockSignals(True)
            w.setCurrentRow(idx) if w is self.sections else w.setCurrentIndex(idx)
            w.blockSignals(False)

    def _format_hints(self) -> None:
        """C137 : avertissement des conversions MP3 ; C146 : poids du meilleur flux (1.4.1, C143 : une liste)."""
        q = self.format_menu.currentData() or "original"
        self.format_warn.setVisible(q.startswith("mp3"))
        self.yt_best_warn.setVisible(q == "yt_best")

    def show_section(self, key: str, remember: bool = True, highlight: Any = None) -> None:
        """Ouvre la page d'une section (aussi appelé depuis l'app : lien « export.pdb pas à jour »).
        1.4.4 (C225) : une page par section ; `key` peut aussi nommer un réglage précis (LINKS : « space »,
        « diag_auto »…) : sa section s'ouvre et sa carte est mise en valeur.
        1.4.4 (C220) : `highlight` (carte ou réglage visé, sinon le titre de la section) est mis en valeur à
        l'arrivée, pour les liens venus d'ailleurs dans l'app."""
        target = None
        if key in LINKS:
            key, attr = LINKS[key]
            target = self._card_of(getattr(self, attr, None))
            highlight = highlight or True
        if key not in dict(SECTIONS):
            return
        self._set_nav(key)
        self._start_section = key                        # 1.4.0-rc.2 (B57) : refait à l'affichage
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self._apply_filter()
        self._scroll_to(key)
        if highlight is not None:
            from ..widgets import flash

            if highlight is not True:
                target = self._card_of(highlight) or highlight
            target = target or getattr(self, "_heads", {}).get(key)

            def arrive(w: Any = target) -> None:
                try:
                    if target is not None and target is not getattr(self, "_heads", {}).get(key):
                        self.area.ensureWidgetVisible(w, 0, theme.px(20))
                except RuntimeError:
                    return
                flash(w)

            QTimer.singleShot(0, arrive)
        if remember and self.ctrl.settings.settings_section != key:
            self.ctrl.settings.settings_section = key
            try:
                self.ctrl.settings.save()
            except OSError:
                log.debug("Ignored error in show_section", exc_info=True)  # 1.4.3 (A3-4)

    def _scroll_to(self, key: str) -> None:
        """1.4.4 (C225) : haut de la page de la section."""
        head = getattr(self, "_heads", {}).get(key)
        if head is None:
            return
        self._scrolling_to = key
        page = self.area.widget()
        if page is not None and page.layout() is not None:
            page.layout().activate()                     # positions à jour même avant le premier affichage
        bar = self.area.verticalScrollBar()
        bar.setValue(min(bar.maximum(), head.y()))
        self._scrolling_to = None
        self._space_if_shown()

    def _on_scroll(self) -> None:
        """1.4.4 (C225) : une page par section : le volet ne suit plus le défilement ; la carte « Espace » est
        mesurée quand elle arrive à l'écran."""
        self._space_if_shown()

    @staticmethod
    def _card_text(box: QWidget) -> str:
        parts = []
        for w in box.findChildren(QWidget):
            if isinstance(w, (QLabel, QAbstractButton)):
                parts += [w.text(), w.toolTip(), w.accessibleName() if isinstance(w, Switch) else ""]
            elif isinstance(w, QComboBox):
                parts += [w.itemText(i) for i in range(w.count())] + [w.toolTip()]
            elif isinstance(w, QLineEdit):
                parts.append(w.placeholderText())
        return " ".join(p for p in parts if p).casefold()

    def _apply_filter(self) -> None:
        """1.4.4 (C225) : sans recherche : les cartes de la section choisie (une page par section). Avec : cartes
        de toutes les sections qui contiennent tous les mots cherchés (titre, libellés, choix, ⓘ, info-bulles),
        sous leur titre de section."""
        words = self.search.text().casefold().split()
        shown = 0
        per_section: Dict[str, int] = {}
        for sec, box in self._cards:
            visible = all(w in self._card_text(box) for w in words) if words else sec == self._current_section
            box.setVisible(visible)
            shown += visible
            per_section[sec] = per_section.get(sec, 0) + visible
            if box in self._folds:                     # C89 : une recherche montre aussi le contenu replié
                self._folds[box][0].setVisible(self._folds[box][3] or bool(words))
        for key, head in getattr(self, "_heads", {}).items():
            head.setVisible(per_section.get(key, 0) > 0)
        for key, sub in getattr(self, "_subs", {}).items():
            sub.setVisible(not words and key == self._current_section)
        self.sections.setEnabled(not words)
        self.sections.blockSignals(True)
        if words:
            self.sections.clearSelection()                      # la recherche couvre toutes les sections
        else:
            self.sections.setCurrentRow([k for k, _i in SECTIONS].index(self._current_section))
        self.sections.blockSignals(False)
        self.no_match.setText(t("settings.search_none", text=self.search.text()))
        self.no_match.setVisible(bool(words) and not shown)
        if not words:
            InfoDot.close_any()
        # 1.4.4 (C220) : recherche : la ou les cartes trouvées mises en valeur (après une courte pause de frappe)
        if words and shown:
            if not hasattr(self, "_flash_timer"):
                self._flash_timer = QTimer(self)
                self._flash_timer.setSingleShot(True)
                self._flash_timer.timeout.connect(self._flash_matches)
            self._flash_timer.start(600)

    def _flash_matches(self) -> None:
        from ..widgets import flash

        if not self.search.text().split():
            return
        for _sec, box in self._cards:
            if box.isVisibleTo(self):
                flash(box)

    def _space_if_shown(self) -> None:
        """C27 : mesure lancée seulement quand la carte « Espace » arrive à l'écran (C121 : en défilant)."""
        space = getattr(self, "space", None)
        if space is None or not self.isVisible() or self.space_box.isHidden():
            return
        bar = self.area.verticalScrollBar()
        top, bottom = bar.value(), bar.value() + self.area.viewport().height()
        y = self.space_box.y()
        if y < bottom and y + self.space_box.height() > top and not getattr(self, "_space_done", False):
            # 1.4.0-rc.3 (B71) : une seule fois par affichage de la page, plus à chaque pas de défilement
            # (les lignes étaient recréées pendant qu'on défilait : la carte clignotait et changeait de hauteur)
            self._space_done = True
            space.compute()

    def show_space(self) -> None:
        """Lien « espace » de l'Accueil : 1.4.4 (C225) : page Sauvegardes et espace, carte mise en valeur."""
        self.show_section("space")

        def go() -> None:
            try:
                self.area.ensureWidgetVisible(self.space_box, 0, theme.px(20))
            except RuntimeError:
                return
            self._space_if_shown()

        QTimer.singleShot(120, go)

    def visible_cards(self) -> list:
        return [box for _s, box in self._cards if not box.isHidden()]

    def resizeEvent(self, e: Any) -> None:       # noqa: N802
        super().resizeEvent(e)
        narrow = self.width() < theme.px(NARROW_PX)
        self.side.setVisible(not narrow)
        self.section_menu.setVisible(narrow)

    @staticmethod
    def _fixed(w: Any) -> Any:
        # 1.3.2-rc.2 (B45) : un libellé trop long passe à la ligne au lieu d'être coupé
        if isinstance(w, QLabel):
            # 1.4.2 (A2-1) : largeur naturelle quand la place le permet, jusqu'à 100 px (texte à la ligne) sinon
            lbl = _RowLabel(w.text())
            lbl.setProperty("role", w.property("role"))
            lbl.setToolTip(w.toolTip())
            w.deleteLater()
            return lbl
        w.setFixedWidth(theme.px(170))
        return w

    def on_show(self) -> None:
        from ..wheel_guard import guard_children

        guard_children(self.area)                           # B51 : champs ajoutés depuis la construction
        self.ctrl.refresh_drives()
        if not self._versions_loaded:                       # 1.3.2-rc.2 (C96) : une fois, à la première visite
            QTimer.singleShot(0, self.load_versions)
        self._space_done = False                         # B71 : remesurée à chaque ouverture de la page
        QTimer.singleShot(0, self._space_if_shown)
        QTimer.singleShot(0, self._sync_nav)

    def _sync_nav(self) -> None:
        """1.4.0-rc.2 (B57) : à la construction, la page n'a pas encore sa taille : au premier affichage, la
        page de la section retenue est remise en haut. 1.4.4 (C225) : le volet ne suit plus le défilement."""
        start, self._start_section = getattr(self, "_start_section", None), None
        if start and not self.search.text().split():
            self._set_nav(start)
            self._apply_filter()
            self._scroll_to(start)
        if not self._current_section:
            self._set_nav("general")

    # --------------------------------------------------------------- apparence
    def _language_changed(self, text: str) -> None:
        code = next((c for c, n in LANGUAGES.items() if n == text), "en")
        if code != self.ctrl.settings.language:
            self.ctrl.settings.language = code
            self.ctrl.settings.save()
            QTimer.singleShot(0, lambda: self.ctrl._emit("rebuild_ui"))

    def _theme_families(self, menu: Any) -> None:
        """1.4.2 (C144, C205) : les trois familles (Vives, Profondes, Douces) côte à côte, une colonne chacune ;
        empilées seulement si l'écran est trop étroit."""
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QBoxLayout, QWidgetAction

        from ..palettes import FAMILIES

        box = QWidget()
        cols = QBoxLayout(QBoxLayout.LeftToRight, box)
        cols.setContentsMargins(theme.px(8), theme.px(6), theme.px(8), theme.px(6))
        cols.setSpacing(theme.px(14))
        self._family_cols = []
        for family, names in FAMILIES.items():
            col = vbox(spacing=theme.px(1))
            col.addWidget(label(t(f"theme.family_{family}").upper(), "section"))
            for name in names:
                act = QAction(logo_pixmap(theme.px(18), PALETTES[name]), t(f"theme.{name}"), menu)
                act.setCheckable(True)
                act.setChecked(name == theme.CURRENT_THEME)
                act.triggered.connect(lambda _=False, n=name: (menu.close(), self._theme_changed(n)))
                b = QToolButton()
                b.setDefaultAction(act)
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                b.setIconSize(QSize(theme.px(18), theme.px(18)))
                b.setAutoRaise(True)
                b.setCursor(Qt.PointingHandCursor)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                col.addWidget(b)
                self._swatches[name] = act
            col.addStretch(1)
            cols.addLayout(col)
            self._family_cols.append(col)
        screen = self.screen() if hasattr(self, "screen") else None
        avail = screen.availableGeometry().width() if screen is not None else 1280
        if box.sizeHint().width() > avail * 0.9:                    # écran étroit : familles l'une sous l'autre
            cols.setDirection(QBoxLayout.TopToBottom)
        self._family_box = box
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(box)
        menu.addAction(wa)

    def _apply_theme_preset(self, key: str) -> None:
        """1.4.4 (C226) : thème prêt = fond + couleur, appliqués ensemble (un seul restyle)."""
        from ..palettes import THEMES

        bg, accent = THEMES[key]
        s = self.ctrl.settings
        if (s.background, s.theme) != (bg, accent):
            s.background, s.theme = bg, accent
            s.save()
            self.ctrl._emit("restyle")

    def _theme_changed(self, name: str) -> None:
        for n, b in self._swatches.items():
            b.setChecked(n == name)
        for n, b in getattr(self, "_featured", {}).items():
            b.setChecked(n == name)
        self.theme_name.setText(t(f"theme.{name}"))
        if name != self.ctrl.settings.theme:
            self.ctrl.settings.theme = name
            self.ctrl.settings.save()
            self.ctrl._emit("restyle")

    def _background_changed(self, text: str) -> None:
        name = next((k for k, v in self._bg_labels.items() if v == text), "default")
        if name != getattr(self.ctrl.settings, "background", "default"):
            self.ctrl.settings.background = name
            self.ctrl.settings.save()
            self.ctrl._emit("restyle")

    def _zoom_step(self, delta: int) -> None:
        keys = getattr(self.window(), "zoom_keys", None)
        if keys is not None:
            keys.step(delta)
            return
        from ..zoom import clamp                      # page seule (tests) : appliqué tout de suite

        z = 100 if delta == 0 else clamp(self.ctrl.settings.zoom + delta * ZOOM_STEP)
        self.zoom_val.setText(f"{z} %")
        if z != self.ctrl.settings.zoom:
            self.ctrl.settings.zoom = z
            self.ctrl.settings.save()
            self.ctrl._emit("restyle")

    def _sidebar_changed(self, text: str) -> None:
        mode = next((m for m, v in self._sidebar_labels.items() if v == text), "auto")
        self.ctrl.settings.sidebar_compact = mode
        self.ctrl.settings.save()
        self.ctrl._emit("restyle")

    # ------------------------------------------------------------------ clé
    def _prune_backups(self) -> None:
        """1.4.4 (C235) : sauvegardes en trop supprimées tout de suite (niveau choisi), place libérée annoncée."""
        lib = self.ctrl.library
        if lib is None:
            self.ctrl.message("warn", t("msg.no_drive"))
            return
        from ...db import backup_levels
        from .common import human_size

        backup_levels.set_level(self.keep.currentData() or "normal")
        self.prune_btn.setEnabled(False)

        def done(freed: int) -> None:
            self.prune_btn.setEnabled(True)
            self.ctrl.message("ok", t("settings.backup_pruned", size=human_size(freed)))
            self._space_done = False
            self._space_if_shown()

        def failed(exc: BaseException) -> None:
            self.prune_btn.setEnabled(True)
            self.ctrl._on_error(exc)

        self.ctrl.dispatcher.submit(lambda: backup_levels.prune_now(lib.backup_dir), done, failed, pool="tools")

    def _wave_style_follow(self, *_a: Any) -> None:
        """1.4.4 (C234) : type de forme d'onde changé depuis Grille et cues : la liste suit, sans signal."""
        box = getattr(self, "wave_style", None)
        if box is not None:
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(self.ctrl.settings.waveform_style)))
            box.blockSignals(False)

    def _refresh_drives(self) -> None:
        if not self.winfo_exists():
            return
        self._drives = {str(d): d for d in self.ctrl.drives}
        local = self.ctrl.local
        self.local_state.setText(t("settings.local_found", path=str(local.db_path)) if local
                                 else t("settings.local_none"))
        self.local_btn.setEnabled(local is not None and not self.ctrl.is_local)
        values = list(self._drives) or [t("nav.no_drive")]
        self.drive_menu.blockSignals(True)
        self.drive_menu.clear()
        self.drive_menu.addItems(values)
        current = str(self.ctrl.drive) if self.ctrl.drive else None
        if current in self._drives:
            self.drive_menu.setCurrentText(current)
        self.drive_menu.blockSignals(False)
        self.connect_btn.setEnabled(bool(self._drives))
        self.eject_btn.setEnabled(self.ctrl.drive is not None and not self.ctrl.is_local)
        if self.ctrl.drive:
            drive = str(self.ctrl.drive).replace("\\", "\\\u200b").replace("/", "/\u200b")   # 1.4.2 (A2-1)
            self.drive_state.setText(t("settings.connected", drive=drive))
        else:
            self.drive_state.setText(t("msg.no_drive_short"))

    def _connect(self) -> None:
        drive = self._drives.get(self.drive_menu.currentText())
        if drive is not None:
            self.ctrl.connect(drive)

    def _pdb_refresh(self) -> None:
        if not self.winfo_exists():
            return
        if self.ctrl.library is None:
            self.pdb_state.setText(t("msg.no_drive_short"))
            return
        self.ctrl.pdb_status(self._pdb_show)

    def _pdb_show(self, st: Any) -> None:
        if not self.winfo_exists():
            return
        text = {
            "off": t("pdb.off"),
            "absent": t("pdb.absent"),
            "ok": t("pdb.ok", n=st.pdb_tracks),
            "stale": t("pdb.stale", tracks=st.missing_tracks, playlists=st.missing_playlists)
            + (f"  [{st.detail}]" if st.detail else ""),
            "unsupported": t("pdb.unsupported", detail=st.detail),
        }.get(st.state, t("pdb.unknown"))
        self.pdb_state.setText(text)
        self.pdb_sync_btn.setEnabled(st.state == "stale")

    def _slsk_toggled(self, on: bool) -> None:
        """1.4.0 (C10.2) : première activation -> avertissement à accepter (VPN, droits, fiabilité)."""
        if not on or self.ctrl.settings.soulseek_accepted:
            return
        from ..dialogs import ConfirmDialog

        def accept() -> None:
            self.ctrl.settings.soulseek_accepted = True
            self.ctrl.settings.save()

        def refuse() -> None:
            self.slsk_var.blockSignals(True)
            self.slsk_var.setChecked(False)
            self.slsk_var.blockSignals(False)

        ConfirmDialog(self, t("slsk.warn_title"), t("slsk.warn_text"), accept, confirm_text=t("slsk.warn_accept"),
                      detail=t("slsk.warn_detail"), on_cancel=refuse)

    def _latency_test(self) -> None:
        from ..latency_dialog import LatencyDialog

        def done(ms: int) -> None:
            if self.winfo_exists():
                self.latency_box.setValue(ms)
            self.ctrl.settings.audio_latency_ms = ms
            self.ctrl.settings.save()

        LatencyDialog(self, self.ctrl, self.latency_box.value(), done)

    def _browse_into(self, entry: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "", entry.text() or "")
        if folder:
            entry.setText(folder)

    def _browse_ffmpeg(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("settings.ffmpeg_browse_title"))
        if folder:
            self.ffmpeg.setText(folder)
            self._ffmpeg_status()

    def _ffmpeg_status(self) -> None:
        found, text = self.ctrl.ffmpeg_status(self.ffmpeg.text().strip())
        # 1.4.2 (A2-1) : un chemin sans espace ne passe pas à la ligne : coupure possible après chaque séparateur
        self.ffmpeg_state.setText(text.replace("\\", "\\\u200b").replace("/", "/\u200b"))
        if not found or not self._folds[self.ffmpeg_card][3]:      # C89 : ouverte d'office en cas de problème
            self.set_folded(self.ffmpeg_card, not found or self._folds[self.ffmpeg_card][3],
                            t("settings.ffmpeg_ok_short") if found else t("settings.ffmpeg_missing_short"))
        self.ffmpeg_state.setProperty("role", "dim" if found else "warn")
        self.ffmpeg_state.style().unpolish(self.ffmpeg_state)
        self.ffmpeg_state.style().polish(self.ffmpeg_state)

    # ------------------------------------------------------- moteur de téléchargement
    def _engine_show(self, extra: str = "") -> None:
        from ...core import engine

        version = engine.current_version() or "?"
        updated = engine.override_version() and engine.parse_version(engine.override_version()) > engine.parse_version(
            engine.bundled_version())
        runtime = next(iter(engine.js_runtimes()), "deno")
        js_names = {"deno": t("engine.js_deno"), "node": t("engine.js_node"), "quickjs": t("engine.js_quickjs")}
        text = t("engine.state", version=version, origin=t("engine.updated") if updated else t("engine.bundled"),
                 js=js_names.get(runtime, runtime))
        self.engine_state.setText(text + (f"\n{extra}" if extra else ""))
        f = self._folds.get(getattr(self, "engine_card", None))
        if f is not None:                                            # C89 : ligne d'état de la carte repliée
            f[2].setText(t("engine.short", version=version))
        # 1.4.0-rc.5 (B88) : plus de bouton sans effet : « Version précédente » s'il y en a une, sinon
        # « Revenir à la version intégrée » après une mise à jour, sinon rien (déjà la version intégrée)
        target = engine.rollback_target()
        self.engine_back_btn.setVisible(bool(target))
        self.engine_back_btn.setText(t("engine.rollback") if target == "prev" else t("engine.back_to_bundled",
                                                                                      version=engine.bundled_version()))

    def _engine_check(self) -> None:
        # 1.4.0-rc.5 (B88) : le bouton n'est plus désactivé pendant la recherche : il avait le focus, Qt le
        # donnait au réglage suivant et la page défilait jusqu'à lui (saut vers le haut)
        if getattr(self, "_engine_busy", False):
            return
        self._engine_busy = True
        self.engine_check_btn.setText(t("engine.checking"))
        self._engine_show(t("engine.checking"))

        def done(release: Any, current: str, error: Any) -> None:
            self._engine_busy = False
            if not self.winfo_exists():
                return
            self.engine_check_btn.setText(t("engine.check"))
            if error:
                self._engine_show(t("engine.check_failed", error=str(error)[:160]))
            elif release is not None and release.newer_than(current):
                self._engine_release = release
                self.engine_install_btn.setText(t("engine.install_version", version=release.version))
                self.engine_install_btn.show()
                self.set_folded(self.engine_card, True)              # C89 : une mise à jour se voit
                self._engine_show(t("engine.available", version=release.version))
            else:
                self.engine_install_btn.hide()
                from datetime import datetime

                self._engine_show(t("engine.up_to_date_at", time=datetime.now().strftime(t("engine.time_format"))))

        self.ctrl.engine_check(done)

    def _engine_install(self) -> None:
        if self._engine_release is None:
            return
        self.engine_install_btn.setEnabled(False)

        def done(ok: bool, _info: str) -> None:
            if not self.winfo_exists():
                return
            self.engine_install_btn.setEnabled(True)
            if ok:
                self.engine_install_btn.hide()
            self._engine_show()

        self.ctrl.engine_install(self._engine_release, done)

    def _engine_rollback(self) -> None:
        self.ctrl.engine_rollback()
        self.engine_install_btn.hide()
        self._engine_show()

    # ------------------------------------------------- 1.3.1 (C89) : « Tout vérifier »
    CHECKS = ("app", "engine", "ffmpeg", "drives", "pdb", "local", "diag", "space")

    def _check_row(self, key: str, state: str, text: str, go: str = "") -> None:
        """Une ligne d'état : ✓ à jour, ↑ mise à jour disponible, ⚠ problème, … en cours, – sans objet."""
        mark = {"ok": "✓", "update": "↑", "warn": "⚠", "busy": "…", "skip": "–"}.get(state, "•")
        role = {"ok": "dim", "update": "accent", "warn": "warn", "busy": "faint", "skip": "faint"}.get(state, "dim")
        row = self._check_rows.get(key)
        if row is None:
            w = QWidget()
            lay = hbox(w, spacing=theme.px(8))
            name = label(t(f"checkall.{key}"))
            name.setFixedWidth(theme.px(170))
            lay.addWidget(name)
            val = label("", role, wrap=True)
            lay.addWidget(val, 1)
            link = button(t("checkall.open"), None, kind="flat")
            link.hide()
            lay.addWidget(link)
            self.check_lay.addWidget(w)
            row = self._check_rows[key] = {"val": val, "link": link, "state": state}
        row["state"] = state
        row["val"].setText(f"{mark}  {text}")
        row["val"].setProperty("role", role)
        row["val"].style().unpolish(row["val"])
        row["val"].style().polish(row["val"])
        try:
            row["link"].clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        if go:
            row["link"].clicked.connect(lambda: self.show_section(go))
        row["link"].setVisible(bool(go))
        self._check_settled()

    def _check_settled(self) -> None:
        """C90 : toutes les lignes ont répondu et tout est ✓ (ou sans objet) : repli après 6 s."""
        states = [r["state"] for r in self._check_rows.values()]
        if states and "busy" not in states and all(x in ("ok", "skip") for x in states):
            self._check_timer.start()
        else:
            self._check_timer.stop()

    def _check_autohide(self) -> None:
        if all(r["state"] in ("ok", "skip") for r in self._check_rows.values()):
            self.check_panel.hide()

    def _check_counts(self) -> None:
        row = self._check_rows.get("diag")
        if row is None or row["state"] != "busy":
            return
        c = self.ctrl.diag_counts
        missing, dup = c.get("missing") or 0, c.get("dup") or 0
        self._check_row("diag", "warn" if missing else "ok", t("checkall.diag_n", missing=missing, dup=dup))

    def check_states(self) -> Dict[str, str]:
        return {k: r["state"] for k, r in self._check_rows.items()}

    def check_all(self) -> None:
        """Vérifie d'un coup, en arrière-plan : DJSync, le moteur de téléchargement, FFmpeg, les clés
        branchées, export.pdb (rattrapé s'il n'est pas à jour, comme « Synchroniser maintenant »)
        et les compteurs du Diagnostic. Rien n'est installé sans clic."""
        from ... import full_version
        from .common import alive

        self.check_panel.show()
        for key in self.CHECKS:
            self._check_row(key, "busy", t("checkall.checking"))
        ok = lambda: alive(self.check_panel)       # noqa: E731
        current = full_version()

        def app_done(update: Any, error: Any) -> None:
            if not ok():
                return
            if error is not None:
                self._check_row("app", "warn", t("checkall.app_failed"))
            elif update is not None:
                self._check_row("app", "update", t("checkall.app_update", version=update.version), go="djsync")
            else:
                self._check_row("app", "ok", t("checkall.app_ok", version=current))

        self.ctrl.app_update_check(manual=False, force=True, result=app_done)

        def engine_done(release: Any, cur: str, error: Any) -> None:
            if not ok():
                return
            if error:
                self._check_row("engine", "warn", t("checkall.engine_failed"), go="advanced")
            elif release is not None and release.newer_than(cur):
                self._engine_release = release
                self.engine_install_btn.setText(t("engine.install_version", version=release.version))
                self.engine_install_btn.show()
                self.set_folded(self.engine_card, True)
                self._check_row("engine", "update", t("checkall.engine_update", version=release.version), go="advanced")
            else:
                self._check_row("engine", "ok", t("checkall.engine_ok", version=cur or "?"))

        self.ctrl.engine_check(engine_done)
        self._ffmpeg_status()
        found, _text = self.ctrl.ffmpeg_status(self.ffmpeg.text().strip())
        self._check_row("ffmpeg", "ok" if found else "warn",
                        t("settings.ffmpeg_ok_short") if found else t("settings.ffmpeg_missing_short"),
                        go="" if found else "advanced")

        def drives_done() -> None:
            if ok():
                n = len(self.ctrl.drives)
                self._check_row("drives", "ok" if n else "skip", t("checkall.drives_n", n=n) if n
                                else t("checkall.no_drive"))

        self.ctrl.refresh_drives(then=drives_done)
        lib = self.ctrl.library
        if lib is None or self.ctrl.is_local:
            self._check_row("pdb", "skip", t("checkall.pdb_none"))
        else:
            def synced(_s: Any = None) -> None:
                if ok():
                    stale = getattr(self.ctrl.library, "pdb_state", "ok") == "stale"
                    self._check_row("pdb", "warn" if stale else "ok",
                                    t("checkall.pdb_left") if stale else t("checkall.pdb_synced"),
                                    go="libraries" if stale else "")
                    self._pdb_refresh()

            def status(st: Any) -> None:
                if not ok():
                    return
                if st.state == "stale":
                    self._check_row("pdb", "busy", t("checkall.pdb_syncing"))
                    self.ctrl.pdb_sync_now(synced, lambda *_a: ok() and self._check_row(
                        "pdb", "warn", t("checkall.pdb_left"), go="libraries"))
                elif st.state in ("ok", "off", "absent"):
                    self._check_row("pdb", "ok" if st.state == "ok" else "skip",
                                    t("checkall.pdb_ok") if st.state == "ok" else t(f"checkall.pdb_{st.state}"))
                else:
                    self._check_row("pdb", "warn", t("checkall.pdb_problem"), go="libraries")
                self._pdb_show(st)

            self.ctrl.pdb_status(status)
        # C90 : bibliothèque de l'ordinateur relue (Rekordbox a pu la modifier)
        local = self.ctrl.library if self.ctrl.is_local else None
        if local is None or not hasattr(local, "refresh"):
            self._check_row("local", "skip", t("checkall.local_none"))
        else:
            def reread_done(_r: Any = None) -> None:
                if ok():
                    self._check_row("local", "ok", t("checkall.local_ok"))
                self.ctrl._emit("library")

            self.ctrl.dispatcher.submit(local.refresh, reread_done,
                                        lambda _e: ok() and self._check_row("local", "warn", t("checkall.local_failed")),
                                        pool="db")
        if lib is None:
            self._check_row("diag", "skip", t("checkall.pdb_none"))
        else:
            self.ctrl.diag_quick_counts()           # réponse : évènement « diag_counts » (_check_counts)

        def space_done(usage: Any) -> None:         # C90 : espace remesuré même si sa carte est cachée
            if not ok():
                return
            if usage is None:
                self._check_row("space", "skip", t("checkall.pdb_none"))
                return
            from .common import human_size

            low = usage.total and usage.free < usage.total * 0.1
            self._check_row("space", "warn" if low else "ok",
                            t("space.summary", free=human_size(usage.free), total=human_size(usage.total)),
                            go="space" if low else "")          # 1.4.4 (C225) : page Sauvegardes et espace

        self.space.compute(force=True, done=space_done)

    # --------------------------------------------------------------- enregistrer
    # ------------------------------------------------- sauvegardes de la clé (V1.2.0)
    def _backups_state(self) -> None:
        ok = self.ctrl.backups_available
        self.points_btn.setEnabled(ok)
        self.points_hint.setText("" if ok else t("backups.need_drive"))
        self.points_hint.setVisible(not ok)

    def _open_backups(self) -> None:
        from ..backups_dialog import BackupsDialog

        BackupsDialog(self, self.ctrl)

    def _open_uninstall(self) -> None:
        from ..backups_dialog import UninstallDialog

        UninstallDialog(self, self.ctrl)

    def _open_app_uninstall(self) -> None:
        """1.3.1 (C88) : Paramètres ▸ DJSync ▸ Désinstaller DJSync (clé ou ordinateur)."""
        from ..backups_dialog import UninstallDialog

        mode = self.ctrl.uninstall_mode()
        if mode != "source":
            UninstallDialog(self, self.ctrl, mode=mode)

    def _open_log(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        folder = self.ctrl.log_folder()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _reset_defaults(self) -> None:
        """1.3.2 (C57) : confirmation, copie du fichier, remise à zéro appliquée tout de suite, « Annuler »."""
        from PySide6.QtWidgets import QCheckBox

        from ..dialogs import ConfirmDialog

        keep = QCheckBox(t("settings.reset_keep"))
        keep.setChecked(True)

        def go() -> None:
            import shutil
            import time as _time

            s = self.ctrl.settings
            try:                                   # copie de l'ancien fichier, à côté
                path = s.path()
                if path.is_file():
                    shutil.copy2(path, path.with_name(f"settings-before-reset-{_time.strftime('%Y%m%d-%H%M%S')}.json"))
            except OSError:
                log.debug("Ignored error in go", exc_info=True)  # 1.4.3 (A3-4)
            old = s.reset_to_defaults(keep_choices=keep.isChecked())
            s.save()
            self.ctrl.apply_settings()
            ctrl = self.ctrl

            def undo() -> None:
                ctrl.settings.restore(old)
                ctrl.settings.save()
                ctrl.apply_settings()
                ctrl._emit("rebuild_ui")
                QTimer.singleShot(250, lambda: ctrl.message("ok", t("settings.reset_undone")))

            def announce() -> None:
                ctrl.message("ok", t("settings.reset_done"))
                ctrl._emit("message_action", t("action.undo"), undo)

            ctrl._emit("rebuild_ui")               # thème, zoom, langue, valeurs des Paramètres
            # 1.3.2-rc.2 (C57, test PAR-2 ; B42) : le message et son « Annuler » après la reconstruction de
            # la fenêtre (mise en page faite) : envoyés aussitôt, la bulle était mal placée ou perdue.
            QTimer.singleShot(250, announce)

        dlg = ConfirmDialog(self.window(), t("settings.reset"), t("settings.reset_msg"), go,
                            confirm_text=t("settings.reset_confirm"), detail=t("settings.reset_detail"))
        try:
            dlg.body.insertWidget(max(0, dlg.body.count() - 1), keep)
        except Exception:  # noqa: BLE001 - la case est un plus : sans elle, choix par défaut (gardés)
            log.debug("Ignored error in _reset_defaults", exc_info=True)  # 1.4.3 (A3-4)

    def unsaved(self) -> List[str]:
        """1.4.2 (A2-18) : réglages modifiés à l'écran mais pas encore enregistrés (ceux qui attendent
        « Enregistrer »). Même lecture que `_save`, sans rien écrire."""
        from ... import full_version
        from ..version_dialog import show_test_versions

        s = self.ctrl.settings

        def pick(mapping: Dict[str, str], text: str, default: str) -> str:
            return next((k for k, v in mapping.items() if v == text), default)

        try:
            _w = self.watch_folder.text().strip()
            form = {
                "forced_drive": self.forced.text().strip(),
                "contents_dir": self.contents.text().strip().strip("/\\") or "Contents",
                "ffmpeg_location": self.ffmpeg.text().strip(),
                "fetch_views": self.views_var.isChecked(),
                "fetch_metadata": self.meta_var.isChecked(),
                "backup_level": self.keep.currentData() or "normal",
                "merge_undo_s": int(self.merge_undo.currentData() or 10),
                "pdb_sync": "auto" if self.pdb_var.isChecked() else "off",
                "pdb_allow_growth": self.pdb_growth_var.isChecked(),
                "analyze_after_download_usb": self.analyze_usb_var.isChecked(),
                "analyze_after_download_local": self.analyze_local_var.isChecked(),
                "auto_cue": self.cue_var.isChecked(),
                "write_tags": self.tags_var.isChecked(),
                "protect_foreign": self.protect_var.isChecked(),
                "auto_gain": self.gain_var.isChecked(),
                "diag_auto": self.diag_auto_var.isChecked(),
                "waveform_style": self.wave_style.currentData() or "3band",
                "tempo_grid": self.tempo_grid.currentData() or "auto",
                "reanalyze_rekordbox": [p for p, box in self.reanalyse_vars.items() if box.isChecked()],
                "download_quality": self.format_menu.currentData() or "original",
                "soundcloud_original": self.sc_original_var.isChecked(),
                "soundcloud_browser": pick(self._sc_browsers, self.sc_browser.currentText(), ""),
                "soundcloud_token": self.sc_token.text().strip(),
                "youtube_browser": pick(self._yt_browsers, self.yt_browser.currentText(), ""),
                "watch_folder": str(Path(_w)) if _w else "",
                "soulseek_enabled": self.slsk_var.isChecked() and s.soulseek_accepted,
                "soulseek_user": self.slsk_user.text().strip(),
                "soulseek_password": self.slsk_password.text(),
                "soulseek_share": self.slsk_share_var.isChecked(),
                "player_format": pick(self._player_formats, self.player_format.currentText(), ""),
                "watch_playlist": self.watch_playlist_var.isChecked(),
                "watch_target": self.watch_target.currentData() or "local",
                "light_mode": pick(self._light_labels, self.light_menu.currentText(), "auto"),
                "audio_latency_ms": int(self.latency_box.value()),
                "check_updates": self.update_var.isChecked(),
                "update_channel": "test" if self.show_rc_var.isChecked() else "stable",
                "error_reports": pick(self._report_labels, self.report_menu.currentText(), "ask"),
                "key_notation": pick(self._notation_labels, self.notation.currentText(), "auto"),
                "local_db_dir": self.local_db.text().strip(),
                "local_music_dir": self.local_music.text().strip(),
            }
        except (RuntimeError, AttributeError, ValueError):     # page en cours de construction ou détruite
            return []
        out = []
        for key, value in form.items():
            cur = getattr(s, key, None)
            if key == "update_channel":
                cur = "test" if show_test_versions(s.update_channel, full_version()) else "stable"
            if key == "watch_folder" and cur:
                cur = str(Path(cur))
            if key == "reanalyze_rekordbox":
                cur = list(cur or [])
            if value != cur:
                out.append(key)
        return out

    def _autosave_widgets(self) -> List[Any]:
        """1.4.3 (A2-18) : champs lus par `_save` (même liste que `unsaved`)."""
        names = ("forced", "contents", "ffmpeg", "views_var", "meta_var", "keep", "merge_undo", "pdb_var",
                 "pdb_growth_var", "analyze_usb_var", "analyze_local_var", "cue_var", "diag_auto_var", "wave_style",
                 "format_menu", "sc_original_var", "sc_browser", "sc_token", "yt_browser", "watch_folder", "slsk_var",
                 "slsk_user", "slsk_password", "slsk_share_var", "player_format", "watch_playlist_var", "watch_target",
                 "light_menu", "latency_box", "update_var", "show_rc_var", "report_menu", "notation", "local_db",
                 "local_music", "tags_var", "gain_var", "protect_var",      # 1.4.3 : S05, C109 (oubliés), A07
                 "tempo_grid")                                               # 1.4.3 (C16)
        out = [getattr(self, n, None) for n in names]
        out += list(getattr(self, "reanalyse_vars", {}).values())
        return [w for w in out if w is not None]

    def _wire_autosave(self) -> None:
        """1.4.3 (A2-18, option A) : tout est enregistré tout de suite (cases, listes, nombres au changement ;
        champs de texte à la sortie du champ ou sur Entrée), « ✓ Enregistré » affiché brièvement."""
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(250)
        self._autosave_timer.timeout.connect(self._autosave_now)
        for w in self._autosave_widgets():
            if isinstance(w, QCheckBox):
                w.toggled.connect(lambda _v: self._autosave())
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda _i: self._autosave())
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(lambda _v: self._autosave())
            elif isinstance(w, QLineEdit):
                w.editingFinished.connect(self._autosave)

    def _autosave(self) -> None:
        timer = getattr(self, "_autosave_timer", None)
        if timer is not None:
            timer.start()

    def _autosave_now(self) -> None:
        if not self.winfo_exists():
            return
        try:
            pending = self.unsaved()
        except Exception:  # noqa: BLE001 - jamais d'erreur à l'écran pour un enregistrement automatique
            log.debug("Handled error in _autosave_now", exc_info=True)
            pending = ["?"]
        if pending:
            log.info("Settings saved: %s", ", ".join(pending))
            self._save()

    def save_now(self) -> None:
        """1.4.2 (A2-18) : « Enregistrer » depuis l'alerte en quittant la page."""
        self._save()

    def discard(self) -> None:
        """1.4.2 (A2-18) : « Ne pas enregistrer » : la page est remise sur les réglages enregistrés."""
        win = self.window()
        if hasattr(win, "rebuild_ui"):
            win.rebuild_ui()

    def _save(self) -> None:
        s = self.ctrl.settings
        forced = self.forced.text().strip()
        changed_forced = forced != s.forced_drive
        s.forced_drive = forced
        s.contents_dir = self.contents.text().strip().strip("/\\") or "Contents"
        s.ffmpeg_location = self.ffmpeg.text().strip()
        s.fetch_views = self.views_var.isChecked()
        s.fetch_metadata = self.meta_var.isChecked()
        from ...db import backup_levels                       # 1.4.4 (C235)

        s.backup_level = backup_levels.set_level(self.keep.currentData() or "normal")
        s.backup_keep = backup_levels.LEVELS[s.backup_level]["copies"]
        s.merge_undo_s = int(self.merge_undo.currentData() or 10)
        s.pdb_sync = "auto" if self.pdb_var.isChecked() else "off"
        s.pdb_allow_growth = self.pdb_growth_var.isChecked()
        s.analyze_after_download_usb = self.analyze_usb_var.isChecked()
        s.analyze_after_download_local = self.analyze_local_var.isChecked()
        s.auto_cue = self.cue_var.isChecked()
        s.write_tags = self.tags_var.isChecked()                  # 1.4.3 (S05)
        s.protect_foreign = self.protect_var.isChecked()          # 1.4.3 (A07, C156)
        s.auto_gain = self.gain_var.isChecked()                   # 1.4.3 (C109)
        s.diag_auto = self.diag_auto_var.isChecked()                              # 1.4.2 (B103)
        s.tempo_grid = self.tempo_grid.currentData() or "auto"                     # 1.4.3 (C16)
        style = self.wave_style.currentData() or "3band"                  # 1.4.1 (C77) : appliqué tout de suite
        if style != s.waveform_style:
            s.waveform_style = style
            self.ctrl._emit("waveform_style")
        parts = [p for p, box in self.reanalyse_vars.items() if box.isChecked()]
        if parts != s.reanalyze_rekordbox:                  # 1.4.1 (C131) : changer le choix, c'est l'avoir fait
            s.reanalyze_rekordbox, s.reanalyze_rekordbox_asked = parts, True
        s.download_quality = self.format_menu.currentData() or "original"            # 1.4.1 (C143)
        s.soundcloud_original = self.sc_original_var.isChecked()
        s.soundcloud_browser = next((k for k, v in self._sc_browsers.items() if v == self.sc_browser.currentText()), "")
        s.soundcloud_token = self.sc_token.text().strip()
        s.youtube_browser = next((k for k, v in self._yt_browsers.items() if v == self.yt_browser.currentText()), "")
        _w = self.watch_folder.text().strip()
        s.watch_folder = str(Path(_w)) if _w else ""            # 1.4.0-rc.4 (B77) : chemin normalisé
        s.soulseek_enabled = self.slsk_var.isChecked() and s.soulseek_accepted
        s.soulseek_user = self.slsk_user.text().strip()
        s.soulseek_password = self.slsk_password.text()
        s.soulseek_share = self.slsk_share_var.isChecked()
        s.player_format = next((k for k, v in self._player_formats.items() if v == self.player_format.currentText()), "")
        s.watch_playlist = self.watch_playlist_var.isChecked()
        s.watch_target = self.watch_target.currentData() or "local"             # 1.4.2 (B102)
        s.light_mode = next((k for k, v in self._light_labels.items() if v == self.light_menu.currentText()), "auto")
        s.audio_latency_ms = int(self.latency_box.value())
        s.check_updates = self.update_var.isChecked()
        s.update_channel = "test" if self.show_rc_var.isChecked() else "stable"      # C96
        s.error_reports = next((k for k, v in self._report_labels.items() if v == self.report_menu.currentText()), "ask")
        s.key_notation = next((k for k, v in self._notation_labels.items() if v == self.notation.currentText()), "auto")
        local_changed = (self.local_db.text().strip(), self.local_music.text().strip()) != (s.local_db_dir,
                                                                                            s.local_music_dir)
        s.local_db_dir, s.local_music_dir = self.local_db.text().strip(), self.local_music.text().strip()
        self.ctrl.apply_settings()
        if local_changed:                    # nouveau dossier : la bibliothèque de l'ordinateur est rouverte
            was_local = self.ctrl.is_local
            self.ctrl.refresh_drives(then=lambda: self.ctrl.connect_local() if was_local else None)
        if forced and changed_forced:
            self.ctrl.connect(forced, remember=False)
        self.saved.setText("✓ " + t("settings.saved"))
        QTimer.singleShot(2500, lambda: self.winfo_exists() and self.saved.setText(""))
