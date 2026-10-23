"""Réglage « Playlists par genre » (1.2.2, C07 / S08) d'une bibliothèque.

Désactivé par défaut. Une ligne par playlist : cochée ou non, nom, genres qu'elle regroupe (modifiable :
« Rap » = « Rap/Hip Hop » + « Rap français »), nombre de sons. « Tenir à jour automatiquement » : chaque
son téléchargé ou modifié rejoint sa playlist. Les playlists peuvent ensuite être déplacées ou
renommées dans la bibliothèque. Décocher une playlist la supprime ; désactiver supprime toutes celles
que DJSync a créées (jamais les autres).
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from PySide6.QtWidgets import QCheckBox, QLineEdit, QScrollArea, QWidget

from ..core import genre_playlists as gp
from ..i18n import t
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import button, hbox, icon_button, label, vbox


class GenrePlaylistsDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("genre.title"), 620, 560)
        self.ctrl = controller
        self.original = controller.genre_config()
        self.config = copy.deepcopy(self.original)
        self.genres: Dict[int, str] = {}
        self.rows: List[Dict[str, Any]] = []
        self.heading(t("genre.title"), t("genre.sub"))
        self.enabled = QCheckBox(t("genre.enable"))
        self.enabled.setChecked(bool(self.config.get("enabled")))
        self.enabled.toggled.connect(lambda _on: self._refresh_enabled())
        self.body.addWidget(self.enabled)
        self.auto = QCheckBox(t("genre.auto"))
        self.auto.setChecked(bool(self.config.get("auto", True)))
        self.body.addWidget(self.auto)
        self.body.addWidget(label(t("genre.hint"), "faint", wrap=True))
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        self.list = vbox(inner, spacing=theme.px(6))
        area.setWidget(inner)
        self.body.addWidget(area, 1)
        self.unassigned = label("", "faint", wrap=True)
        self.body.addWidget(self.unassigned)
        row = hbox(spacing=theme.px(6))
        self.add_btn = button(t("genre.add"), self._add_group, icon="plus")
        row.addWidget(self.add_btn)
        self.reset_btn = button(t("genre.reset"), self._reset_groups, kind="flat", icon="refresh")
        row.addWidget(self.reset_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.footer(t("action.apply"), self._apply, stretch=False)
        self.show_dialog()
        controller.track_genres(self._loaded)

    # ------------------------------------------------------------------ données
    def _loaded(self, genres: Dict[int, str]) -> None:
        if not self.winfo_exists():
            return
        self.genres = genres
        if not self.config.get("groups"):
            self.config["groups"] = gp.default_groups(genres, others_name=t("genre.others"))
        self._build_rows()

    def _count(self, names: List[str]) -> int:
        wanted = {n.casefold() for n in names}
        return sum(1 for g in self.genres.values() if g and g.casefold() in wanted)

    def _build_rows(self) -> None:
        while self.list.count():
            item = self.list.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows = []
        if not self.genres:
            self.list.addWidget(label(t("genre.none"), "faint", wrap=True))
        for grp in self.config.get("groups", []):
            self._add_row(grp)
        self.list.addStretch(1)
        self._refresh_enabled()

    def _add_row(self, grp: Dict[str, Any]) -> None:
        w = QWidget()
        lay = hbox(w, spacing=theme.px(6))
        cb = QCheckBox()
        cb.setChecked(bool(grp.get("enabled", True)))
        lay.addWidget(cb)
        name = QLineEdit(grp.get("name", ""))
        name.setPlaceholderText(t("genre.name"))
        name.setMaximumWidth(theme.px(160))
        lay.addWidget(name)
        genres = QLineEdit(", ".join(grp.get("genres", [])))
        genres.setPlaceholderText(t("genre.genres_hint"))
        genres.setToolTip(t("genre.genres_tip"))
        lay.addWidget(genres, 1)
        count = label("", "dim")
        count.setMinimumWidth(theme.px(60))
        lay.addWidget(count)
        rm = icon_button("trash", lambda: self._remove_row(entry), t("genre.remove"))
        lay.addWidget(rm)
        entry = {"group": grp, "widget": w, "check": cb, "name": name, "genres": genres, "count": count}

        def recount() -> None:
            n = self._count(self._split(genres.text()))
            count.setText(t("genre.n_tracks", n=n))
            self._refresh_unassigned()

        genres.textChanged.connect(lambda _t: recount())
        recount()
        self.rows.append(entry)
        self.list.insertWidget(max(0, self.list.count() - 1), w)

    @staticmethod
    def _split(text: str) -> List[str]:
        return [g.strip() for g in text.split(",") if g.strip()]

    def _refresh_unassigned(self) -> None:
        used = {g.casefold() for r in self.rows for g in self._split(r["genres"].text())}
        rest = sorted({g for g in self.genres.values() if g and g.casefold() not in used}, key=str.lower)
        self.unassigned.setText(t("genre.unassigned", names=", ".join(rest)) if rest else "")

    def _remove_row(self, entry: Dict[str, Any]) -> None:
        self.rows.remove(entry)
        entry["widget"].deleteLater()
        self._refresh_unassigned()

    def _add_group(self) -> None:
        self._add_row({"name": "", "genres": [], "enabled": True, "playlist_id": 0, "members": []})

    def _reset_groups(self) -> None:
        old = {g.get("name"): g for g in self.config.get("groups", [])}
        groups = gp.default_groups(self.genres, others_name=t("genre.others"))
        for g in groups:                       # garde les playlists déjà créées pour le même nom
            if g["name"] in old:
                g["playlist_id"], g["members"] = old[g["name"]].get("playlist_id", 0), old[g["name"]].get("members", [])
        self.config["groups"] = groups
        self._build_rows()

    def _refresh_enabled(self) -> None:
        on = self.enabled.isChecked()
        self.auto.setEnabled(on)
        self.add_btn.setEnabled(on)
        self.reset_btn.setEnabled(on)
        for r in self.rows:
            r["widget"].setEnabled(on)

    # ------------------------------------------------------------------ appliquer
    def _collect(self) -> List[Dict[str, Any]]:
        groups = []
        for r in self.rows:
            grp = dict(r["group"])
            grp["enabled"] = r["check"].isChecked()
            grp["name"] = r["name"].text().strip() or (self._split(r["genres"].text()) or ["?"])[0]
            grp["genres"] = self._split(r["genres"].text())
            groups.append(grp)
        return groups

    def _apply(self) -> None:
        groups = self._collect()
        new = copy.deepcopy(self.config)
        new["groups"] = groups
        new["auto"] = self.auto.isChecked()
        was_on = bool(self.original.get("enabled"))
        if not self.enabled.isChecked():
            if was_on:
                ConfirmDialog(self, t("genre.off_title"), t("genre.off_msg"),
                              lambda: self._go(new, turn_off=True), confirm_text=t("genre.off_ok"), danger=True)
            else:
                self.ctrl.settings.genre_playlists[self.ctrl.library_key()] = new
                self.ctrl.save_settings_quiet()
                self.close()
            return
        new["enabled"] = True
        kept = {int(g.get("playlist_id") or 0) for g in groups if g["enabled"]}
        before = {int(g.get("playlist_id") or 0): g.get("name", "") for g in self.original.get("groups", [])
                  if g.get("playlist_id")}
        removed_ids = [pid for pid in before if pid not in kept]
        if removed_ids:
            names = ", ".join(before[pid] for pid in removed_ids)
            ConfirmDialog(self, t("genre.remove_title"), t("genre.remove_msg", names=names),
                          lambda: self._go(new, removed=removed_ids), confirm_text=t("action.apply"), danger=True)
            return
        self._go(new)

    def _go(self, config: Dict[str, Any], removed: Any = (), turn_off: bool = False) -> None:
        self.close()
        self.ctrl.genre_apply(config, removed=removed, turn_off=turn_off)
