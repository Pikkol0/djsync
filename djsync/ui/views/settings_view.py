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
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QLineEdit, QScrollArea, QSlider, QToolButton, QWidget,
)

from ...db import UsbDrive
from ...i18n import LANGUAGES, t
from ...settings import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP
from .. import theme
from ..logo import logo_pixmap
from ..palettes import PALETTES
from ..widgets import button, hbox, icon_button, icon_label, label, panel, vbox
from .common import View

BACKUP_CHOICES = ["5", "10", "20", "50"]
KEY_NOTATIONS = ("auto", "camelot", "musical")
SIDEBAR_MODES = ("auto", "on", "off")


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
        area = QScrollArea()
        area.setWidgetResizable(True)
        page = QWidget()
        self.page = vbox(page, spacing=theme.px(10))
        area.setWidget(page)
        self.root.addWidget(area, 1)

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

        # ---- clé USB
        card = self._card(t("settings.drive"), "usb", t("settings.drive_hint"))
        row = hbox()
        self.drive_menu = QComboBox()
        self.drive_menu.setMinimumWidth(theme.px(280))
        row.addWidget(self.drive_menu)
        row.addWidget(icon_button("refresh", self.ctrl.refresh_drives, t("action.refresh")))
        self.connect_btn = button(t("action.connect"), self._connect, kind="primary", icon="usb")
        row.addWidget(self.connect_btn)
        row.addWidget(button(t("action.disconnect"), lambda: self.ctrl.disconnect(True), icon="close"))
        row.addStretch(1)
        card.addLayout(row)
        self.drive_state = label("", "dim")
        card.addWidget(self.drive_state)
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.forced_drive_short"))))
        self.forced = QLineEdit(s.forced_drive)
        self.forced.setPlaceholderText(t("settings.forced_placeholder"))
        self.forced.setToolTip(t("settings.forced_drive"))
        self.forced.setMaximumWidth(theme.px(120))
        row.addWidget(self.forced)
        row.addStretch(1)
        card.addLayout(row)

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

        # ---- FFmpeg
        card = self._card("FFmpeg", "wave", t("settings.ffmpeg_hint"))
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
        card = self._card(t("settings.analysis"), "key", t("settings.analysis_hint"))
        self.analyze_var = QCheckBox(t("settings.analyze_on_add"))
        self.analyze_var.setChecked(s.analyze_on_add)
        card.addWidget(self.analyze_var)
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

        # ---- anciennes platines : export.pdb
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
        card = self._card(t("settings.downloads"), "download")
        self.views_var = QCheckBox(t("settings.fetch_views"))
        self.views_var.setChecked(s.fetch_views)
        self.meta_var = QCheckBox(t("settings.fetch_metadata"))
        self.meta_var.setChecked(s.fetch_metadata)
        card.addWidget(self.views_var)
        card.addWidget(self.meta_var)

        # ---- sauvegardes
        card = self._card(t("settings.backups"), "folder", t("settings.backups_hint"))
        row = hbox()
        row.addWidget(self._fixed(label(t("settings.backups_keep"))))
        self.keep = QComboBox()
        self.keep.addItems(BACKUP_CHOICES)
        self.keep.setCurrentText(str(s.backup_keep) if str(s.backup_keep) in BACKUP_CHOICES else "10")
        row.addWidget(self.keep)
        row.addStretch(1)
        card.addLayout(row)
        self.page.addStretch(1)

        controller.on("drive", lambda: QTimer.singleShot(300, self._pdb_refresh))
        controller.on("drives", self._refresh_drives)
        controller.on("drive", self._refresh_drives)
        self._refresh_drives()
        self._ffmpeg_status()

    def _card(self, title: str, icon: str = "", hint: str = "") -> Any:
        """Carte de réglages : icône + titre ; l'explication éventuelle est une info-bulle (ⓘ)."""
        box = panel()
        lay = vbox(box, margins=theme.px(14), spacing=theme.px(8))
        head = hbox(spacing=theme.px(8))
        if icon:
            head.addWidget(icon_label(icon, 18, theme.ACCENT))
        head.addWidget(label(title, "h2"))
        if hint:
            info = icon_label("info", 14, theme.FAINT)
            info.setToolTip(hint)
            head.addWidget(info)
        head.addStretch(1)
        lay.addLayout(head)
        self.page.addWidget(box)
        return lay

    @staticmethod
    def _fixed(w: Any) -> Any:
        w.setFixedWidth(theme.px(150))
        return w

    def on_show(self) -> None:
        self.ctrl.refresh_drives()

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
        self.ffmpeg_state.setProperty("role", "dim" if found else "warn")
        self.ffmpeg_state.style().unpolish(self.ffmpeg_state)
        self.ffmpeg_state.style().polish(self.ffmpeg_state)

    # --------------------------------------------------------------- enregistrer
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
        s.analyze_on_add = self.analyze_var.isChecked()
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
