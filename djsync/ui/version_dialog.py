"""1.3.2 (C96) : choisir la version de DJSync à installer, plus ancienne comprise.

Paramètres ▸ DJSync ▸ « Choisir une version… » : liste des versions publiées installables sur ce système
(fichier et empreinte SHA-256 publiés), la plus récente en haut, avec ou sans les versions de test (rc).
L'installation est celle de la mise à jour (téléchargement, empreinte vérifiée, remplacement au
redémarrage) ; vers une version plus ancienne, un avertissement d'abord. Exemple d'usage : depuis la rc.9,
tester la 1.3.0 avant de passer à la 1.3.1.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QListWidget, QListWidgetItem

from .. import full_version
from ..core import updates
from ..i18n import t
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import button, hbox, label


class VersionDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any, on_channel: Any = None) -> None:
        super().__init__(parent, t("update.pick_title"), 520, 480)
        self.ctrl = controller
        self._on_channel = on_channel
        self.current = full_version()
        self.versions: List[updates.Update] = []
        self.heading(t("update.pick_title"), t("update.pick_sub", version=self.current))
        self.show_rc = QCheckBox(t("update.show_rc"))
        self.show_rc.setChecked(show_test_versions(controller.settings.update_channel, self.current))
        self.show_rc.toggled.connect(self._channel_changed)
        self.body.addWidget(self.show_rc)
        self.status = label(t("update.pick_loading"), "dim", wrap=True)
        self.body.addWidget(self.status)
        self.list = QListWidget()
        self.list.setMinimumHeight(theme.px(220))
        self.list.currentRowChanged.connect(lambda _i: self._refresh())
        self.list.itemDoubleClicked.connect(lambda _it: self._install())
        self.body.addWidget(self.list, 1)
        row = hbox(spacing=theme.px(6))
        self.notes_btn = button(t("update.pick_notes"), self._notes, kind="flat", icon="go")
        row.addWidget(self.notes_btn)
        row.addStretch(1)
        row.addWidget(button(t("action.close"), self.close))
        self.install_btn = button(t("update.pick_install"), self._install, kind="primary", icon="download")
        row.addWidget(self.install_btn)
        self.body.addLayout(row)
        self._refresh()
        self.show_dialog()
        self._load()

    # ------------------------------------------------------------------ liste
    def _load(self) -> None:
        self.list.clear()
        self.versions = []
        self.status.setText(t("update.pick_loading"))
        self._refresh()
        self.ctrl.app_versions(self.show_rc.isChecked(), self._loaded, self._failed)

    def _loaded(self, versions: List[updates.Update]) -> None:
        if not self.winfo_exists():
            return
        self.versions = list(versions)
        self.list.clear()
        current_row = -1
        for k, up in enumerate(self.versions):
            text = up.version + (f"  ·  {up.date}" if up.date else "")
            if up.prerelease:
                text += "  ·  " + t("update.pick_test")
            if up.version == self.current:
                text += "  ·  " + t("update.pick_installed")
                current_row = k
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, up.version)
            self.list.addItem(item)
        self.status.setText(t("update.pick_count", n=len(self.versions)) if self.versions else t("update.pick_none"))
        self.list.setCurrentRow(0 if current_row != 0 or len(self.versions) < 2 else 1)
        self._refresh()

    def _failed(self, exc: BaseException) -> None:
        if not self.winfo_exists():
            return
        from .controller import is_offline_error

        self.status.setText(t("error.offline") if is_offline_error(exc) else t("update.pick_failed"))
        self._refresh()

    def _channel_changed(self, on: bool) -> None:
        s = self.ctrl.settings
        s.update_channel = "test" if on else "stable"
        try:
            s.save()
        except OSError:
            pass
        if self._on_channel is not None:
            self._on_channel(on)
        self._load()

    # ------------------------------------------------------------------ choix
    def selected(self) -> Optional[updates.Update]:
        i = self.list.currentRow()
        return self.versions[i] if 0 <= i < len(self.versions) else None

    def _refresh(self) -> None:
        up = self.selected()
        busy = self.ctrl.update_progress is not None
        self.notes_btn.setEnabled(up is not None)
        self.install_btn.setEnabled(up is not None and up.version != self.current and not busy)
        if up is not None and not self.ctrl.can_self_update():
            self.install_btn.setText(t("update.pick_open_page"))
        elif up is not None and updates.is_older(up.version, self.current):
            self.install_btn.setText(t("update.pick_install_older", version=up.version))
        elif up is not None:
            self.install_btn.setText(t("update.install_to", version=up.version))
        else:
            self.install_btn.setText(t("update.pick_install"))

    def _notes(self) -> None:
        up = self.selected()
        if up is not None:
            self.ctrl._emit("open_url", up.url)

    def _install(self) -> None:
        up = self.selected()
        if up is None or up.version == self.current or self.ctrl.update_progress is not None:
            return

        def go() -> None:
            self.ctrl.app_update_install(up)
            self.close()

        if updates.is_older(up.version, self.current) and self.ctrl.can_self_update():
            ConfirmDialog(self, t("update.older_title"), t("update.older_msg", version=up.version,
                                                           current=self.current),
                          go, confirm_text=t("update.pick_install_older", version=up.version),
                          detail=t("update.older_detail"))
            return
        go()


def show_test_versions(channel: str, current: str) -> bool:
    """Case « Afficher les versions de test » : canal « test », ou « auto » sur une version de test."""
    if channel == "test":
        return True
    if channel == "stable":
        return False
    v = updates.parse_version(current.split("-dev")[0])
    return v is not None and v[3] == 0
