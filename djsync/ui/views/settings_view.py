"""Vue Paramètres : apparence (langue, couleur, zoom, barre latérale), clé, destination, FFmpeg,
analyse, export.pdb, recherche, sauvegardes.

Apparence : appliquée immédiatement. La couleur et le zoom changent la feuille de style (Qt
redessine, rien n'est reconstruit) ; la langue reconstruit les pages (rapide). Le reste : bouton
« Enregistrer ».
"""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QFileDialog, QGridLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QProgressBar, QScrollArea, QSlider, QSpinBox, QToolButton, QWidget,
)

from ...db import UsbDrive
from ...i18n import LANGUAGES, t
from ...settings import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP
from .. import theme
from ..logo import logo_pixmap
from ..palettes import PALETTES
from ..icons import qicon
from ..widgets import button, hbox, icon_button, icon_label, label, line_edit, panel, vbox
from .common import View

BACKUP_CHOICES = ["5", "10", "20", "50"]
KEY_NOTATIONS = ("auto", "camelot", "musical")
SIDEBAR_MODES = ("auto", "on", "off")
# 1.3.1 (C28) : volet des sections (clé, icône)
SECTIONS = (("general", "settings"), ("libraries", "library"), ("download", "download"), ("analysis", "key"),
            ("privacy", "info"), ("djsync", "refresh"), ("advanced", "menu"))     # 1.3.1 (C89) : Avancé
NARROW_PX = 760          # en dessous (à 100 %), le volet devient une liste déroulante


class SettingsView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self._drives: Dict[str, UsbDrive] = {}
        self._swatches: Dict[str, QToolButton] = {}
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(250)
        self._zoom_timer.timeout.connect(self._apply_zoom)
        s = controller.settings

        head = self.header(t("tab.settings"))
        self.saved = label("", "accent")
        head.addWidget(self.saved)
        head.addWidget(button(t("action.save"), self._save, kind="primary", icon="check"))
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
        self.sections.setStyleSheet(f"#settingsSections::item {{ padding: {theme.px(7)}px {theme.px(6)}px; "
                                    f"border-radius: {theme.px(6)}px; }}")
        for key, icon in SECTIONS:
            item = QListWidgetItem(qicon(icon, 16, theme.FAINT if key == "advanced" else theme.ACCENT),
                                   t(f"settings.section_{key}"))
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
        self.section_menu = QComboBox()          # fenêtre étroite : le volet devient une liste déroulante
        for key, icon in SECTIONS:
            self.section_menu.addItem(qicon(icon, 16, theme.ACCENT), t(f"settings.section_{key}"), key)
        self.section_menu.currentIndexChanged.connect(
            lambda i: self.show_section(self.section_menu.itemData(i)) if i >= 0 else None)
        self.section_menu.hide()
        top.addWidget(self.section_menu)
        top.addStretch(1)
        self.check_all_btn = button(t("checkall.button"), self.check_all, icon="refresh",
                                    tooltip=t("checkall.tip"))           # 1.3.1 (C89) : tout vérifier
        top.addWidget(self.check_all_btn)
        right.addLayout(top)
        self.check_panel = panel()
        self.check_lay = vbox(self.check_panel, margins=theme.px(10), spacing=theme.px(4))
        self.check_panel.hide()
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

        # ---- apparence
        card = self._card(t("settings.appearance"), "settings")
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.language"))))
        self.lang_menu = QComboBox()
        self.lang_menu.addItems(list(LANGUAGES.values()))
        self.lang_menu.setCurrentText(LANGUAGES.get(s.language, "English"))
        self.lang_menu.currentTextChanged.connect(self._language_changed)
        row.addWidget(self.lang_menu)
        row.addStretch(1)
        card.addLayout(row)

        row = hbox()
        row.addWidget(self._fixed(label(t("settings.theme"))), 0, Qt.AlignTop)
        grid = QGridLayout()
        grid.setSpacing(theme.px(3))
        for i, (name, accent) in enumerate(PALETTES.items()):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(logo_pixmap(theme.px(22), accent))
            b.setIconSize(QSize(theme.px(22), theme.px(22)))
            b.setToolTip(t(f"theme.{name}"))
            b.setChecked(name == theme.CURRENT_THEME)
            b.clicked.connect(lambda _=False, n=name: self._theme_changed(n))
            grid.addWidget(b, i // 10, i % 10)
            self._swatches[name] = b
        row.addLayout(grid)
        row.addStretch(1)
        card.addLayout(row)
        self.theme_name = label(t(f"theme.{theme.CURRENT_THEME}"), "dim")
        self.theme_name.hide()

        row = hbox()
        row.addWidget(self._fixed(label(t("settings.zoom"))))
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(ZOOM_MIN // ZOOM_STEP, ZOOM_MAX // ZOOM_STEP)
        self.zoom.setValue(s.zoom // ZOOM_STEP)
        self.zoom.setFixedWidth(theme.px(220))
        self.zoom.valueChanged.connect(self._zoom_moved)
        row.addWidget(self.zoom)
        self.zoom_val = label(f"{s.zoom} %", "accent")
        row.addWidget(self.zoom_val)
        row.addWidget(button(t("settings.zoom_reset"), lambda: self.zoom.setValue(100 // ZOOM_STEP), kind="flat",
                             icon="refresh"))
        row.addStretch(1)
        card.addLayout(row)

        row = hbox()
        row.addWidget(self._fixed(label(t("settings.sidebar"))))
        self._sidebar_labels = {m: t(f"settings.sidebar_{m}") for m in SIDEBAR_MODES}
        self.sidebar_menu = QComboBox()
        self.sidebar_menu.addItems(list(self._sidebar_labels.values()))
        self.sidebar_menu.setCurrentText(self._sidebar_labels.get(s.sidebar_compact, self._sidebar_labels["auto"]))
        self.sidebar_menu.currentTextChanged.connect(self._sidebar_changed)
        row.addWidget(self.sidebar_menu)
        row.addStretch(1)
        card.addLayout(row)
        self.scroll_wave_var = QCheckBox(t("settings.scrolling_wave"))       # 1.2.3
        self.scroll_wave_var.setToolTip(t("settings.scrolling_wave_tip"))
        self.scroll_wave_var.setChecked(s.scrolling_wave)
        card.addWidget(self.scroll_wave_var)

        # ---- clé USB
        self._section = "libraries"
        card = self._card(t("settings.drive"), "usb", t("settings.drive_hint"))
        row = hbox()
        self.drive_menu = QComboBox()
        self.drive_menu.setMinimumWidth(theme.px(280))
        row.addWidget(self.drive_menu)
        row.addWidget(icon_button("refresh", self.ctrl.refresh_drives, t("action.refresh")))
        self.connect_btn = button(t("action.connect"), self._connect, kind="primary", icon="usb")
        row.addWidget(self.connect_btn)
        row.addWidget(button(t("action.disconnect"), lambda: self.ctrl.disconnect(True), icon="close"))
        self.eject_btn = button(t("action.eject"), self.ctrl.eject, icon="eject")
        self.eject_btn.setToolTip(t("eject.hint"))
        row.addWidget(self.eject_btn)
        row.addStretch(1)
        card.addLayout(row)
        self.drive_state = label("", "dim")
        card.addWidget(self.drive_state)

        # ---- dossier de destination
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.destination"))))
        self.contents = QLineEdit(s.contents_dir)
        self.contents.setToolTip(t("settings.destination_hint"))
        self.contents.setMaximumWidth(theme.px(260))
        row.addWidget(self.contents)
        row.addStretch(1)
        card.addLayout(row)

        # ---- Rekordbox de cet ordinateur (V0.4.0)
        from ...db.local_library import default_music_dir

        card = self._card(t("settings.local"), "computer", t("settings.local_hint"))
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.local_db"))))
        self.local_db = QLineEdit(s.local_db_dir)
        self.local_db.setPlaceholderText(t("settings.local_auto"))
        row.addWidget(self.local_db, 1)
        row.addWidget(button(t("action.browse"), lambda: self._browse_into(self.local_db), icon="folder"))
        card.addLayout(row)
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.local_music"))))
        self.local_music = QLineEdit(s.local_music_dir)
        self.local_music.setPlaceholderText(str(default_music_dir()))
        row.addWidget(self.local_music, 1)
        row.addWidget(button(t("action.browse"), lambda: self._browse_into(self.local_music), icon="folder"))
        card.addLayout(row)
        row = hbox()
        self.local_state = label("", "dim", wrap=True)
        row.addWidget(self.local_state, 1)
        self.local_btn = button(t("action.connect"), self.ctrl.connect_local, kind="primary", icon="computer")
        row.addWidget(self.local_btn)
        card.addLayout(row)

        # ---- FFmpeg (1.3.1, C89 : Avancé, repliée quand tout va bien)
        self._section = "advanced"
        card = self._card("FFmpeg", "wave", t("settings.ffmpeg_hint"), fold=True)
        self.ffmpeg_card = self._cards[-1][1]
        row = hbox()
        self.ffmpeg = QLineEdit(s.ffmpeg_location)
        self.ffmpeg.setPlaceholderText(t("settings.ffmpeg_placeholder"))
        self.ffmpeg.textEdited.connect(lambda _t: self._ffmpeg_status())
        row.addWidget(self.ffmpeg, 1)
        row.addWidget(button(t("action.browse"), self._browse_ffmpeg, icon="folder"))
        card.addLayout(row)
        self.ffmpeg_state = label("", "dim")
        card.addWidget(self.ffmpeg_state)

        # ---- analyse
        self._section = "analysis"
        card = self._card(t("settings.analysis"), "key", t("settings.analysis_hint"))
        self.analyze_usb_var = QCheckBox(t("settings.analyze_after_usb"))       # 1.3.0-rc.3 (C32)
        self.analyze_usb_var.setChecked(s.analyze_after_download_usb)
        card.addWidget(self.analyze_usb_var)
        self.analyze_local_var = QCheckBox(t("settings.analyze_after_local"))
        self.analyze_local_var.setChecked(s.analyze_after_download_local)
        card.addWidget(self.analyze_local_var)
        self.cue_var = QCheckBox(t("settings.auto_cue"))
        self.cue_var.setChecked(s.auto_cue)
        self.cue_var.setToolTip(t("settings.auto_cue_hint"))
        card.addWidget(self.cue_var)
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.key_notation"))))
        self._notation_labels = {k: t(f"settings.notation_{k}") for k in KEY_NOTATIONS}
        self.notation = QComboBox()
        self.notation.addItems(list(self._notation_labels.values()))
        self.notation.setCurrentText(self._notation_labels.get(s.key_notation, self._notation_labels["auto"]))
        row.addWidget(self.notation)
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()
        row.addWidget(button(t("settings.analyse_now"), lambda: self.ctrl._emit("show_unanalysed"), icon="wave"))
        row.addStretch(1)
        card.addLayout(row)

        # ---- anciennes platines : export.pdb (1.3.1, C89 : Avancé)
        self._section = "advanced"
        card = self._card(t("settings.pdb"), "library", t("settings.pdb_hint"))
        self.pdb_var = QCheckBox(t("settings.pdb_sync"))
        self.pdb_var.setChecked(s.pdb_sync == "auto")
        card.addWidget(self.pdb_var)
        self.pdb_growth_var = QCheckBox(t("settings.pdb_growth"))
        self.pdb_growth_var.setChecked(s.pdb_allow_growth)
        card.addWidget(self.pdb_growth_var)
        row = hbox()
        row.addWidget(button(t("settings.check"), self._pdb_refresh, icon="check"))
        self.pdb_sync_btn = button(t("settings.sync_now"), self.ctrl.pdb_sync_now, kind="primary", icon="refresh")
        row.addWidget(self.pdb_sync_btn)
        row.addStretch(1)
        card.addLayout(row)
        self.pdb_state = label("", "dim", wrap=True)
        card.addWidget(self.pdb_state)

        # ---- recherche
        self._section = "download"
        card = self._card(t("settings.downloads"), "download")
        self.views_var = QCheckBox(t("settings.fetch_views"))
        self.views_var.setChecked(s.fetch_views)
        self.meta_var = QCheckBox(t("settings.fetch_metadata"))
        self.meta_var.setChecked(s.fetch_metadata)
        card.addWidget(self.views_var)
        card.addWidget(self.meta_var)
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.format"))))
        self._format_labels = {"m4a": t("settings.format_m4a"), "mp3": t("settings.format_mp3")}
        self.format_menu = QComboBox()
        self.format_menu.addItems(list(self._format_labels.values()))
        self.format_menu.setCurrentText(self._format_labels.get(s.audio_format, self._format_labels["m4a"]))
        row.addWidget(self.format_menu)
        row.addStretch(1)
        card.addLayout(row)
        self.normalize_var = QCheckBox(t("settings.normalize"))
        self.normalize_var.setChecked(s.normalize_volume)
        self.normalize_var.setToolTip(t("settings.normalize_hint"))
        card.addWidget(self.normalize_var)

        # ---- moteur de téléchargement (yt-dlp) : mises à jour à la demande seulement (C89 : Avancé, repliée)
        self._section = "advanced"
        card = self._card(t("engine.title"), "refresh", t("engine.hint"), fold=True)
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

        # ---- sauvegardes
        self._section = "libraries"
        card = self._card(t("settings.backups"), "folder", t("settings.backups_hint"))
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.backups_keep"))))
        self.keep = QComboBox()
        self.keep.addItems(BACKUP_CHOICES)
        self.keep.setCurrentText(str(s.backup_keep) if str(s.backup_keep) in BACKUP_CHOICES else "10")
        row.addWidget(self.keep)
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()                                       # V1.2.0 : points de restauration, journal, retrait
        self.points_btn = button(t("backups.open"), self._open_backups, kind="primary", icon="back")
        row.addWidget(self.points_btn)
        row.addStretch(1)
        self.uninstall_btn = button(t("uninstall.open"), self._open_uninstall, kind="flat", icon="trash")
        self.uninstall_btn.setVisible(self.ctrl.can_uninstall())
        row.addWidget(self.uninstall_btn)
        card.addLayout(row)
        self.points_hint = label("", "faint", wrap=True)
        card.addWidget(self.points_hint)
        # 1.3.1 (C27) : espace occupé (calculé à l'ouverture de la section)
        from ..space_card import SpaceCard

        self._space_box_layout = self._card(t("settings.space"), "usb", t("settings.space_hint"))
        self.space = SpaceCard(self._space_box_layout, controller)
        self.space_box = self._cards[-1][1]
        self._build_about(s)
        # ---- 1.3.1 (C89) : réglages techniques peu utilisés (Avancé)
        self._section = "advanced"
        card = self._card(t("settings.tech"), "menu", t("settings.tech_hint"))
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.forced_drive_short"))))
        self.forced = QLineEdit(s.forced_drive)
        self.forced.setPlaceholderText(t("settings.forced_placeholder"))
        self.forced.setToolTip(t("settings.forced_drive"))
        self.forced.setMaximumWidth(theme.px(120))
        row.addWidget(self.forced)
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()                                                         # 1.3.0-rc.3 (C39)
        row.addWidget(label(t("settings.audio_latency")))
        self.latency_box = QSpinBox()
        self.latency_box.setRange(-200, 2000)                                # 1.3.0-rc.4 : Bluetooth ~1 s
        self.latency_box.setSingleStep(10)
        self.latency_box.setSuffix(" ms")
        self.latency_box.setValue(s.audio_latency_ms)
        self.latency_box.setToolTip(t("settings.audio_latency_tip"))
        row.addWidget(self.latency_box)
        row.addWidget(button(t("latency.test"), self._latency_test, icon="wave"))     # 1.3.0-rc.4 (C39)
        row.addStretch(1)
        card.addLayout(row)
        self.page.addStretch(1)
        start = s.settings_section if s.settings_section in dict(SECTIONS) else "general"
        self.show_section(start, remember=False)

        controller.on("drive", lambda: QTimer.singleShot(300, self._pdb_refresh))
        controller.on("drive", self._backups_state)
        controller.on("drive", lambda: QTimer.singleShot(400, self._space_if_shown))   # 1.3.1 (C27)
        controller.on("drives", self._refresh_drives)
        controller.on("diag_counts", self._check_counts)                              # 1.3.1 (C89)
        controller.on("drive", self._refresh_drives)
        self._refresh_drives()
        self._ffmpeg_status()
        self._engine_show()
        self._backups_state()

    # ------------------------------------------------ DJSync : version, mises à jour, à propos
    def _build_about(self, s: Any) -> None:
        """1.2.0-rc.4 : mise à jour en un clic (C20) et « À propos » (C19)."""
        from ... import full_version

        self._section = "djsync"
        card = self._card(t("about.title"), "refresh", t("about.hint"))
        row = hbox()
        self.version_lbl = label(t("about.version", version=full_version()), "accent")
        row.addWidget(self.version_lbl)
        self.update_state = label("", "dim", wrap=True)
        row.addWidget(self.update_state, 1)
        card.addLayout(row)
        self.update_bar = QProgressBar()
        self.update_bar.setRange(0, 1000)
        self.update_bar.setTextVisible(False)
        self.update_bar.hide()
        card.addWidget(self.update_bar)
        row = hbox()
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
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()
        self.update_var = QCheckBox(t("update.auto"))
        self.update_var.setChecked(s.check_updates)
        row.addWidget(self.update_var)
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()
        row.addWidget(self._fixed(label(t("update.channel"))))
        self._channel_labels = {"auto": t("update.channel_auto"), "stable": t("update.channel_stable"),
                                "test": t("update.channel_test")}
        self.channel_menu = QComboBox()
        self.channel_menu.addItems(list(self._channel_labels.values()))
        self.channel_menu.setCurrentText(self._channel_labels.get(s.update_channel, self._channel_labels["auto"]))
        row.addWidget(self.channel_menu)
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()                                    # 1.3.1 (C88) : désinstaller, toujours visible
        self.app_uninstall_btn = button(t("uninstall.app_open"), self._open_app_uninstall, kind="flat", icon="trash")
        mode = self.ctrl.uninstall_mode()
        self.app_uninstall_btn.setEnabled(mode != "source")
        self.app_uninstall_btn.setToolTip(t("uninstall.app_source") if mode == "source"
                                          else t("uninstall.app_tip_drive") if mode == "drive"
                                          else t("uninstall.app_tip_computer"))
        row.addWidget(self.app_uninstall_btn)
        row.addStretch(1)
        card.addLayout(row)
        card.addWidget(label(t("about.credits"), "dim", wrap=True))
        # 1.3.1 (C55) : remerciements
        from ...credits import thanks_text
        from ...i18n import get_language

        thanks = label("🙏 " + thanks_text(get_language()), wrap=True)
        thanks.setObjectName("about_thanks")
        card.addWidget(thanks)
        # 1.3.1 (C28) : rapports d'erreur et journal dans « Retours et confidentialité »
        self._section = "privacy"
        card = self._card(t("settings.section_privacy"), "info")
        row = hbox()                                   # 1.2.3 : rapports d'erreur
        row.addWidget(self._fixed(label(t("err_report.setting"))))
        self._report_labels = {"ask": t("err_report.mode_ask"), "always": t("err_report.mode_always"),
                               "never": t("err_report.mode_never")}
        self.report_menu = QComboBox()
        self.report_menu.addItems(list(self._report_labels.values()))
        self.report_menu.setCurrentText(self._report_labels.get(s.error_reports, self._report_labels["ask"]))
        self.report_menu.setToolTip(t("err_report.what"))
        row.addWidget(self.report_menu)
        row.addStretch(1)
        card.addLayout(row)
        row = hbox()
        row.addWidget(button(t("settings.open_log"), self._open_log, kind="flat", icon="folder"))
        row.addStretch(1)
        card.addLayout(row)
        self._section = "djsync"
        row = hbox()
        row.addWidget(button(t("about.github"), lambda: self.ctrl._emit("open_url", "https://github.com/Pikkol0/djsync"),
                             kind="flat", icon="go"))
        row.addWidget(button(t("about.license"), lambda: self._show_text("LICENSE", t("about.license")), kind="flat",
                             icon="info"))
        row.addWidget(button(t("about.third_party"),
                             lambda: self._show_text("THIRD_PARTY_NOTICES.md", t("about.third_party")), kind="flat",
                             icon="info"))
        row.addStretch(1)
        card.addLayout(row)
        self.ctrl.on("app_update_state", self._update_state)
        self._update_state()

    def _install_update(self) -> None:
        if self.ctrl.available_update is not None:
            self.ctrl.app_update_install(self.ctrl.available_update)

    def _update_state(self) -> None:
        from .common import alive

        if not alive(self.update_state):
            return
        upd, prog, ready = self.ctrl.available_update, self.ctrl.update_progress, self.ctrl.update_ready
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

    def _show_text(self, name: str, title: str) -> None:
        """Licence ou composants tiers : fichiers livrés avec DJSync (ou à la racine du dépôt)."""
        import sys
        from pathlib import Path

        from ..help_dialog import TextDialog

        roots = [Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parents[3]]
        path = next((r / name for r in roots if str(r) and (r / name).is_file()), None)
        text = path.read_text(encoding="utf-8", errors="replace") if path else t("about.missing", name=name)
        TextDialog(self, title, text)

    def _card(self, title: str, icon: str = "", hint: str = "", fold: bool = False) -> Any:
        """Carte de réglages : icône + titre ; l'explication éventuelle est une info-bulle (ⓘ).
        1.3.1 (C89) : `fold` = repliable (flèche + une ligne d'état), repliée tant que tout va bien."""
        box = panel()
        lay = vbox(box, margins=theme.px(14), spacing=theme.px(8))
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
        head.addWidget(label(title, "h2"))
        if hint:
            info = icon_label("info", 14, theme.FAINT)
            info.setToolTip(hint)
            head.addWidget(info)
        summary = None
        if fold:
            summary = label("", "dim")
            head.addWidget(summary, 1)
        head.addStretch(1)
        lay.addLayout(head)
        self.page.addWidget(box)
        self._cards.append((self._section, box))
        if not fold:
            return lay
        inner = QWidget()
        inner_lay = vbox(inner, spacing=theme.px(8))
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
    def show_section(self, key: str, remember: bool = True) -> None:
        """Affiche les cartes d'une section (aussi appelé depuis l'app : lien « export.pdb pas à jour »)."""
        if key not in dict(SECTIONS):
            return
        self._current_section = key
        keys = [k for k, _i in SECTIONS]
        for w, idx in ((self.sections, keys.index(key)), (self.section_menu, keys.index(key))):
            w.blockSignals(True)
            w.setCurrentRow(idx) if w is self.sections else w.setCurrentIndex(idx)
            w.blockSignals(False)
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self._apply_filter()
        self.area.verticalScrollBar().setValue(0)
        self._space_if_shown()
        if remember and self.ctrl.settings.settings_section != key:
            self.ctrl.settings.settings_section = key
            try:
                self.ctrl.settings.save()
            except OSError:
                pass

    @staticmethod
    def _card_text(box: QWidget) -> str:
        parts = []
        for w in box.findChildren(QWidget):
            if isinstance(w, (QLabel, QAbstractButton)):
                parts += [w.text(), w.toolTip()]
            elif isinstance(w, QComboBox):
                parts += [w.itemText(i) for i in range(w.count())] + [w.toolTip()]
            elif isinstance(w, QLineEdit):
                parts.append(w.placeholderText())
        return " ".join(p for p in parts if p).casefold()

    def _apply_filter(self) -> None:
        """Sans recherche : cartes de la section choisie. Avec : cartes de toutes les sections qui
        contiennent tous les mots cherchés (titre, libellés, cases, choix, info-bulles)."""
        words = self.search.text().casefold().split()
        shown = 0
        for sec, box in self._cards:
            visible = all(w in self._card_text(box) for w in words) if words else sec == self._current_section
            box.setVisible(visible)
            shown += visible
            if box in self._folds:                     # C89 : une recherche montre aussi le contenu replié
                self._folds[box][0].setVisible(self._folds[box][3] or bool(words))
        self.sections.setEnabled(not words)
        self.sections.blockSignals(True)
        if words:
            self.sections.clearSelection()                      # la recherche couvre toutes les sections
        else:
            self.sections.setCurrentRow([k for k, _i in SECTIONS].index(self._current_section))
        self.sections.blockSignals(False)
        self.no_match.setText(t("settings.search_none", text=self.search.text()))
        self.no_match.setVisible(bool(words) and not shown)

    def _space_if_shown(self) -> None:
        """C27 : mesure lancée seulement quand la carte « Espace » est affichée."""
        space = getattr(self, "space", None)
        if space is not None and self.isVisible() and not self.space_box.isHidden():
            space.compute()

    def show_space(self) -> None:
        """Lien « espace » de l'Accueil : section Bibliothèques, défilée jusqu'à la carte."""
        self.show_section("libraries")
        QTimer.singleShot(120, lambda: self.area.verticalScrollBar().setValue(
            self.area.verticalScrollBar().maximum()))         # dernière carte de la section

    def visible_cards(self) -> list:
        return [box for _s, box in self._cards if not box.isHidden()]

    def resizeEvent(self, e: Any) -> None:       # noqa: N802
        super().resizeEvent(e)
        narrow = self.width() < theme.px(NARROW_PX)
        self.side.setVisible(not narrow)
        self.section_menu.setVisible(narrow)

    @staticmethod
    def _fixed(w: Any) -> Any:
        w.setFixedWidth(theme.px(150))
        return w

    def on_show(self) -> None:
        self.ctrl.refresh_drives()
        QTimer.singleShot(0, self._space_if_shown)

    # --------------------------------------------------------------- apparence
    def _language_changed(self, text: str) -> None:
        code = next((c for c, n in LANGUAGES.items() if n == text), "en")
        if code != self.ctrl.settings.language:
            self.ctrl.settings.language = code
            self.ctrl.settings.save()
            QTimer.singleShot(0, lambda: self.ctrl._emit("rebuild_ui"))

    def _theme_changed(self, name: str) -> None:
        for n, b in self._swatches.items():
            b.setChecked(n == name)
        self.theme_name.setText(t(f"theme.{name}"))
        if name != self.ctrl.settings.theme:
            self.ctrl.settings.theme = name
            self.ctrl.settings.save()
            self.ctrl._emit("restyle")

    def _zoom_moved(self, value: int) -> None:
        self.zoom_val.setText(f"{value * ZOOM_STEP} %")
        self._zoom_timer.start()

    def _apply_zoom(self) -> None:
        z = self.zoom.value() * ZOOM_STEP
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
            self.drive_state.setText(t("settings.connected", drive=str(self.ctrl.drive)))
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
        self.ffmpeg_state.setText(text)
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
        self.engine_back_btn.setEnabled(bool(engine.engine_dir().exists()))

    def _engine_check(self) -> None:
        self.engine_check_btn.setEnabled(False)
        self._engine_show(t("engine.checking"))

        def done(release: Any, current: str, error: Any) -> None:
            if not self.winfo_exists():
                return
            self.engine_check_btn.setEnabled(True)
            if error:
                self._engine_show(t("engine.check_failed", error=str(error)[:160]))
            elif release is not None and release.newer_than(current):
                self._engine_release = release
                self.engine_install_btn.setText(t("engine.install_version", version=release.version))
                self.engine_install_btn.show()
                self._engine_show(t("engine.available", version=release.version))
            else:
                self.engine_install_btn.hide()
                self._engine_show(t("engine.up_to_date"))

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
    CHECKS = ("app", "engine", "ffmpeg", "drives", "pdb", "diag")

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
                                    go="advanced" if stale else "")
                    self._pdb_refresh()

            def status(st: Any) -> None:
                if not ok():
                    return
                if st.state == "stale":
                    self._check_row("pdb", "busy", t("checkall.pdb_syncing"))
                    self.ctrl.pdb_sync_now(synced, lambda *_a: ok() and self._check_row(
                        "pdb", "warn", t("checkall.pdb_left"), go="advanced"))
                elif st.state in ("ok", "off", "absent"):
                    self._check_row("pdb", "ok" if st.state == "ok" else "skip",
                                    t("checkall.pdb_ok") if st.state == "ok" else t(f"checkall.pdb_{st.state}"))
                else:
                    self._check_row("pdb", "warn", t("checkall.pdb_problem"), go="advanced")
                self._pdb_show(st)

            self.ctrl.pdb_status(status)
        if lib is None:
            self._check_row("diag", "skip", t("checkall.pdb_none"))
        else:
            self.ctrl.diag_quick_counts()           # réponse : évènement « diag_counts » (_check_counts)
        self._space_if_shown()

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

    def _save(self) -> None:
        s = self.ctrl.settings
        forced = self.forced.text().strip()
        changed_forced = forced != s.forced_drive
        s.forced_drive = forced
        s.contents_dir = self.contents.text().strip().strip("/\\") or "Contents"
        s.ffmpeg_location = self.ffmpeg.text().strip()
        s.fetch_views = self.views_var.isChecked()
        s.fetch_metadata = self.meta_var.isChecked()
        s.backup_keep = int(self.keep.currentText())
        s.pdb_sync = "auto" if self.pdb_var.isChecked() else "off"
        s.pdb_allow_growth = self.pdb_growth_var.isChecked()
        s.analyze_after_download_usb = self.analyze_usb_var.isChecked()
        s.analyze_after_download_local = self.analyze_local_var.isChecked()
        s.auto_cue = self.cue_var.isChecked()
        s.audio_format = next((k for k, v in self._format_labels.items() if v == self.format_menu.currentText()), "m4a")
        s.normalize_volume = self.normalize_var.isChecked()
        s.scrolling_wave = self.scroll_wave_var.isChecked()
        s.audio_latency_ms = int(self.latency_box.value())
        s.check_updates = self.update_var.isChecked()
        s.update_channel = next((k for k, v in self._channel_labels.items() if v == self.channel_menu.currentText()),
                                "auto")
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
