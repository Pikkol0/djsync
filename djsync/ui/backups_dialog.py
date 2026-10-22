"""Sauvegardes de la clé (V1.2.0) : revenir à un état enregistré en un clic, ou en créer un.

Liste des points de restauration (origine, manuels, année / mois / semaine, récents), du plus récent
au plus ancien. « Restaurer » remet la bibliothèque de la clé (sons connus, playlists) dans l'état
choisi ; l'état actuel est d'abord mis de côté, la restauration peut donc être annulée.
« Retirer DJSync de cette clé » : voir UninstallDialog.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QListWidget, QListWidgetItem

from ..i18n import t
from . import theme
from .dialogs import BaseDialog, ConfirmDialog, TextInputDialog
from .widgets import button, hbox, label


def _size(n: int) -> str:
    if n >= 100_000:
        return t("backups.size_mb", n=f"{n / 1_000_000:.1f}")
    return t("backups.size_kb", n=max(1, n // 1000))


def point_title(p: Any) -> str:
    when = p.created.strftime("%d/%m/%Y %H:%M")
    if p.kind == "origin":
        name = t("backups.kind_origin_approx" if p.approx else "backups.kind_origin")
    elif p.kind == "manual":
        name = p.label or t("backups.kind_manual")
    elif p.kind == "restore":
        name = t("backups.kind_restore")
    else:
        tags = [t(f"backups.tag_{tag}") for tag in ("year", "month", "week") if tag in p.tags]
        name = t("backups.kind_auto") + (f" ({', '.join(tags)})" if tags else "")
    return f"{when} — {name}"


def point_detail(p: Any) -> str:
    parts = []
    if p.tracks is not None:
        parts.append(t("backups.counts", tracks=p.tracks, playlists=p.playlists or 0))
    try:
        parts.append(_size(p.size))
    except OSError:
        pass
    if not p.has_pdb:
        parts.append(t("backups.no_pdb"))
    return " · ".join(parts)


class BackupsDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("backups.title"), 620, 520)
        self.ctrl = controller
        self.points: List[Any] = []
        self.heading(t("backups.title"), t("backups.sub"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(lambda _r: self._update_buttons())
        self.list.itemDoubleClicked.connect(lambda _i: self._restore())
        self.body.addWidget(self.list, 1)
        self.empty = label(t("backups.loading"), "dim", wrap=True)
        self.body.addWidget(self.empty)
        row = hbox(spacing=theme.px(6))
        row.addWidget(button(t("backups.create"), self._create, icon="plus"))
        self.delete_btn = button(t("backups.delete"), self._delete, kind="flat", icon="trash")
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        row.addWidget(button(t("action.close"), self.close))
        self.restore_btn = button(t("backups.restore"), self._restore, kind="primary", icon="back")
        row.addWidget(self.restore_btn)
        self.body.addLayout(row)
        self._update_buttons()
        self.reload()
        self.show_dialog()

    def reload(self) -> None:
        self.ctrl.backup_points(self._show)

    def _show(self, points: List[Any]) -> None:
        if not self.winfo_exists():
            return
        self.points = list(points)
        self.list.clear()
        for p in self.points:
            item = QListWidgetItem(point_title(p) + "\n" + point_detail(p))
            item.setData(Qt.UserRole, p.id)
            self.list.addItem(item)
        self.empty.setText("" if self.points else t("backups.none"))
        self.empty.setVisible(not self.points)
        if self.points:
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _current(self) -> Optional[Any]:
        row = self.list.currentRow()
        return self.points[row] if 0 <= row < len(self.points) else None

    def _update_buttons(self) -> None:
        p = self._current()
        self.restore_btn.setEnabled(p is not None)
        self.delete_btn.setEnabled(p is not None and p.kind != "origin")

    def _create(self) -> None:
        TextInputDialog(self, t("backups.create"), t("backups.create_prompt"),
                        lambda name: self.ctrl.create_backup(name, lambda _p: self.reload()), allow_empty=True)

    def _delete(self) -> None:
        p = self._current()
        if p is None or p.kind == "origin":
            return
        ConfirmDialog(self, t("backups.delete"), t("backups.delete_msg", name=point_title(p)),
                      lambda: self.ctrl.delete_backup(p, self.reload), confirm_text=t("backups.delete"), danger=True)

    def _restore(self) -> None:
        p = self._current()
        if p is None:
            return
        if self.ctrl.backups_busy():
            self.ctrl.message("warn", t("backups.busy"))
            return

        def go() -> None:
            self.close()
            self.ctrl.restore_backup(p, lambda: None)

        ConfirmDialog(self, t("backups.restore"), t("backups.restore_msg", name=point_title(p)), go,
                      confirm_text=t("backups.restore"), detail=t("backups.restore_detail"))


class UninstallDialog(BaseDialog):
    """Retirer DJSync de la clé qui le porte (programme, réglages, journal), musique conservée."""

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("uninstall.title"), 520)
        self.ctrl = controller
        self.heading(t("uninstall.title"), t("uninstall.sub"))
        self.restore_var = QCheckBox(t("uninstall.restore_origin"))
        self.body.addWidget(self.restore_var)
        self.body.addWidget(label(t("uninstall.restore_origin_hint"), "faint", wrap=True))
        self.backups_var = QCheckBox(t("uninstall.delete_backups"))
        self.body.addWidget(self.backups_var)
        self.body.addWidget(label(t("uninstall.keeps"), "dim", wrap=True))
        self.footer(t("uninstall.ok"), self._go, danger=True)
        self.show_dialog()

    def _go(self) -> None:
        restore, delete = self.restore_var.isChecked(), self.backups_var.isChecked()
        self.close()
        self.ctrl.uninstall(restore, delete)
