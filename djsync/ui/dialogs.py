"""Fenêtres modales Qt : confirmation, saisie de texte, choix de playlists (avec création), filtres
de recherche, titre / artiste. Toutes s'ouvrent sans bloquer la boucle (`open()`), centrées sur la
fenêtre principale ; Qt les garde dans l'écran et les dimensionne d'après leur contenu."""
from __future__ import annotations

import sys
from typing import Any, Callable, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QLineEdit, QScrollArea, QWidget,
)

from ..i18n import t
from ..models import SEARCH_MODE_LABELS, PlaylistInfo, SearchMode
from . import theme
from .widgets import button, hbox, label, vbox


class BaseDialog(QDialog):
    modal = True

    def __init__(self, parent: Any, title: str, width: int = 440, height: int = 0) -> None:
        super().__init__(parent.window() if parent is not None else None)
        if sys.platform == "darwin":
            # 1.2.0-rc.4 (B05) : sur macOS, une fenêtre ordinaire s'ouvrait derrière DJSync, ou dans un
            # autre espace quand DJSync est en plein écran. Une fenêtre « outil » reste au-dessus de
            # la fenêtre principale, dans le même espace, et se déplace et se redimensionne librement.
            self.setWindowFlag(Qt.Tool, True)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setModal(self.modal)
        self.body = vbox(self, margins=theme.px(16), spacing=theme.px(8))
        self.setMinimumWidth(theme.px(width))
        if height:
            self.resize(theme.px(width), theme.px(height))
        self._closed = False

    def heading(self, text: str, sub: str = "") -> None:
        self.body.addWidget(label(text, "h2"))
        if sub:
            self.body.addWidget(label(sub, "dim", wrap=True))

    def footer(self, ok_text: str, on_ok: Callable[[], None], danger: bool = False, cancel_text: str = "",
               show_cancel: bool = True, stretch: bool = True) -> Any:
        """`stretch=False` : le contenu (déjà extensible) prend toute la hauteur libre."""
        if stretch:
            self.body.addStretch(1)
        row = hbox(spacing=theme.px(6))
        row.addStretch(1)
        if show_cancel:
            row.addWidget(button(cancel_text or t("action.cancel"), self.close))
        ok = button(ok_text, on_ok, kind="danger" if danger else "primary")
        ok.setDefault(True)
        row.addWidget(ok)
        self.body.addLayout(row)
        return ok

    def show_dialog(self) -> "BaseDialog":
        if self.modal:
            self.open()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        return self

    def close(self) -> bool:                      # noqa: D401 - même nom que Tk : compatibilité des vues
        self._closed = True
        return super().close()

    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return not self._closed and isValid(self)


class ConfirmDialog(BaseDialog):
    def __init__(self, parent: Any, title: str, message: str, on_confirm: Callable[[], None],
                 confirm_text: str = "", danger: bool = False, detail: str = "",
                 on_cancel: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent, title, 440)
        self._on_confirm, self._on_cancel = on_confirm, on_cancel
        self.heading(title)
        self.body.addWidget(label(message, wrap=True))
        if detail:
            self.body.addWidget(label(detail, "dim", wrap=True))
        self.footer(confirm_text or t("action.confirm"), self._ok, danger=danger)
        self.show_dialog()

    def _ok(self) -> None:
        self._on_cancel = None
        self.close()
        self._on_confirm()

    def closeEvent(self, e: Any) -> None:         # noqa: N802
        cancel, self._on_cancel = self._on_cancel, None
        super().closeEvent(e)
        if cancel:
            cancel()


class TextInputDialog(BaseDialog):
    def __init__(self, parent: Any, title: str, prompt: str, on_ok: Callable[[str], None], initial: str = "",
                 confirm_text: str = "", allow_empty: bool = False) -> None:
        super().__init__(parent, title, 400)
        self._on_ok, self._allow_empty = on_ok, allow_empty
        self.body.addWidget(label(prompt, "dim"))
        self._entry = QLineEdit(initial)
        self._entry.selectAll()
        self._entry.returnPressed.connect(self._ok)
        self.body.addWidget(self._entry)
        self.footer(confirm_text or t("action.ok"), self._ok)
        self.show_dialog()
        self._entry.setFocus()

    def _ok(self) -> None:
        text = self._entry.text().strip()
        if text or self._allow_empty:
            self.close()
            self._on_ok(text)


class _CheckItem:
    """Vue « case à cocher » d'une ligne de l'arbre (mêmes méthodes que QCheckBox, pour les vues et
    les tests : isChecked / setChecked / text / isVisible)."""

    def __init__(self, item: Any) -> None:
        self.item = item

    def isChecked(self) -> bool:                  # noqa: N802
        return self.item.checkState(0) == Qt.Checked

    def setChecked(self, on: bool) -> None:       # noqa: N802
        self.item.setCheckState(0, Qt.Checked if on else Qt.Unchecked)

    def text(self) -> str:
        return self.item.text(0)

    def isVisible(self) -> bool:                  # noqa: N802
        it = self.item
        while it is not None:
            if it.isHidden():
                return False
            it = it.parent()
        return True


class PlaylistPicker(BaseDialog):
    """Cocher une ou plusieurs playlists, ou en créer une. `on_ok(liste d'identifiants)`.
    1.2.1 (C02) : arborescence avec les dossiers comme dans Rekordbox, recherche qui garde les
    dossiers parents visibles, création dans le dossier sélectionné."""

    def __init__(self, parent: Any, controller: Any, title: str, confirm_text: str,
                 on_ok: Callable[[List[int]], None], multi: bool = True, preselect: Sequence[int] = (),
                 new_name: str = "", exclude: Sequence[int] = (), allow_empty: bool = False,
                 subtitle: str = "") -> None:
        from PySide6.QtWidgets import QTreeWidget

        super().__init__(parent, title, 460, 560)
        self.ctrl = controller
        self._on_ok, self._multi, self._allow_empty = on_ok, multi, allow_empty
        self._exclude = set(exclude)
        self._checked: set = set(preselect)
        self._vars: Dict[int, _CheckItem] = {}
        self._folders: Dict[int, Any] = {}
        self._filling = False
        self.heading(title, subtitle)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(t("picker.search"))
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        self.body.addWidget(self._filter)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.itemChanged.connect(self._item_changed)
        self._tree.itemDoubleClicked.connect(self._item_double)
        self.body.addWidget(self._tree, 1)
        self._empty = label(t("picker.none"), "faint")
        self._empty.hide()
        self.body.addWidget(self._empty)
        row = hbox()
        self._new = QLineEdit(new_name)
        self._new.setPlaceholderText(t("picker.new_name"))
        self._new.returnPressed.connect(self._create)
        row.addWidget(self._new, 1)
        row.addWidget(button(t("action.create"), self._create, icon="plus"))
        self.body.addLayout(row)
        self._where = label("", "faint")
        self.body.addWidget(self._where)
        self._tree.currentItemChanged.connect(lambda *_: self._show_where())
        self._ok_btn = self.footer(confirm_text, self._confirm, stretch=False)
        self.show_dialog()
        self._reload()

    # ------------------------------------------------------------------ arbre
    @staticmethod
    def _paths(playlists: List[PlaylistInfo], exclude: set) -> List[tuple]:
        """(chemin « Dossier / Playlist », playlist) des playlists où l'on peut ajouter, triés."""
        by_id = {p.playlist_id: p for p in playlists}

        def path(p: PlaylistInfo) -> str:
            parts, cur, guard = [p.name], p, 0
            while cur.parent_id and cur.parent_id in by_id and guard < 10:
                cur = by_id[cur.parent_id]
                parts.append(cur.name)
                guard += 1
            return " / ".join(reversed(parts))

        rows = [(path(p), p) for p in playlists if not p.is_folder and p.playlist_id not in exclude and p.is_editable]
        return sorted(rows, key=lambda r: r[0].lower())

    def _reload(self, tick: Optional[int] = None) -> None:
        from PySide6.QtWidgets import QTreeWidgetItem

        def show(playlists: List[PlaylistInfo]) -> None:
            if self._closed:
                return
            if tick is not None:
                self._checked = {tick} if not self._multi else self._checked | {tick}
            self._filling = True
            self._tree.clear()
            self._vars.clear()
            self._folders.clear()
            by_parent: Dict[int, List[PlaylistInfo]] = {}
            for p in playlists:
                by_parent.setdefault(p.parent_id, []).append(p)
            usable = {p.playlist_id for _path, p in self._paths(playlists, self._exclude)}

            def add(parent_item: Any, parent_id: int, depth: int = 0) -> bool:
                any_child = False
                kids = sorted(by_parent.get(parent_id, []), key=lambda p: (not p.is_folder, p.sequence, p.name.lower()))
                for p in kids:
                    if depth > 12:
                        break
                    if p.is_folder:
                        item = QTreeWidgetItem([p.name])
                        item.setData(0, Qt.UserRole, ("folder", p.playlist_id))
                        item.setFlags((item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsUserCheckable)
                        (parent_item.addChild if parent_item is not None else self._tree.addTopLevelItem)(item)
                        if add(item, p.playlist_id, depth + 1):
                            any_child = True
                        self._folders[p.playlist_id] = item
                    elif p.playlist_id in usable:
                        item = QTreeWidgetItem([f"{p.name}   ·   {p.track_count}"])
                        item.setData(0, Qt.UserRole, ("playlist", p.playlist_id))
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.Checked if p.playlist_id in self._checked else Qt.Unchecked)
                        (parent_item.addChild if parent_item is not None else self._tree.addTopLevelItem)(item)
                        self._vars[p.playlist_id] = _CheckItem(item)
                        any_child = True
                return any_child

            add(None, 0)
            self._tree.expandAll()
            self._filling = False
            self._empty.setVisible(not self._vars)
            self._apply_filter()
            if tick is not None and tick in self._vars:
                self._tree.scrollToItem(self._vars[tick].item)
            self._refresh_ok()

        self.ctrl.fetch_playlists(show)

    def _apply_filter(self, text: str = "") -> None:
        words = (text or self._filter.text()).lower().split()

        def visit(item: Any) -> bool:
            kind, _pid = item.data(0, Qt.UserRole) or ("", 0)
            if kind == "playlist":
                cb = _CheckItem(item)
                path = item.text(0).lower()
                parent = item.parent()
                while parent is not None:                     # le nom du dossier compte aussi
                    path = parent.text(0).lower() + " " + path
                    parent = parent.parent()
                show = cb.isChecked() or all(w in path for w in words)
            else:
                show = False
                for i in range(item.childCount()):
                    show = visit(item.child(i)) or show
                show = show or (not words and item.childCount() == 0)
            item.setHidden(not show)
            return show

        for i in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(i))

    def _item_changed(self, item: Any, _col: int) -> None:
        if self._filling:
            return
        kind, pid = item.data(0, Qt.UserRole) or ("", 0)
        if kind == "playlist":
            self._toggled(pid, item.checkState(0) == Qt.Checked)

    def _item_double(self, item: Any, _col: int) -> None:
        kind, _pid = item.data(0, Qt.UserRole) or ("", 0)
        if kind == "playlist":
            cb = _CheckItem(item)
            cb.setChecked(not cb.isChecked())

    def _target_folder(self) -> int:
        """Dossier où créer une playlist : le dossier sélectionné, ou celui de la playlist sélectionnée."""
        item = self._tree.currentItem()
        while item is not None:
            kind, pid = item.data(0, Qt.UserRole) or ("", 0)
            if kind == "folder":
                return int(pid)
            item = item.parent()
        return 0

    def _show_where(self) -> None:
        folder = self._target_folder()
        item = self._folders.get(folder)
        self._where.setText(t("picker.create_in", folder=item.text(0)) if item is not None else "")

    def _toggled(self, pid: int, on: bool) -> None:
        if on:
            if not self._multi:
                self._filling = True
                for other, cb in self._vars.items():
                    if other != pid and cb.isChecked():
                        cb.setChecked(False)
                self._filling = False
            self._checked = {pid} if not self._multi else self._checked | {pid}
        else:
            self._checked.discard(pid)
        self._refresh_ok()

    def _selected(self) -> List[int]:
        return [pid for pid, cb in self._vars.items() if cb.isChecked()]

    def _refresh_ok(self) -> None:
        self._ok_btn.setEnabled(self._allow_empty or bool(self._selected()))

    def _create(self) -> None:
        name = self._new.text().strip()
        if not name:
            return
        self._new.setEnabled(False)

        def done(pid: Any) -> None:
            if not self._closed:
                self._new.setEnabled(True)
                self._new.clear()
                self._reload(tick=getattr(pid, "playlist_id", pid))

        def fail(exc: BaseException) -> None:
            if not self._closed:
                self._new.setEnabled(True)
            self.ctrl._on_error(exc)

        self.ctrl.create_playlist(name, self._target_folder(), ok=done, err=fail)

    def _confirm(self) -> None:
        ids = self._selected()
        if not ids and not self._allow_empty:
            return
        self.close()
        self._on_ok(ids)


class FiltersPopup(BaseDialog):
    """Options de recherche avancées : mots à exclure, type de résultat ; 1.2.1 (C08) : durée
    maximale et « masquer ce qui est déjà dans la bibliothèque ». `on_apply(mots, type, minutes,
    masquer)` ; le champ (Tout / Titre / Artiste / Album) est à côté de la barre de recherche."""

    MINUTES = (0, 6, 8, 10, 15, 20)

    def __init__(self, parent: Any, exclude_words: str, mode: str, on_apply: Callable[..., None],
                 max_minutes: int = 0, hide_owned: bool = False) -> None:
        super().__init__(parent, t("filters.title"), 420)
        self._on_apply = on_apply
        self.heading(t("filters.title"))
        self.body.addWidget(label(t("filters.exclude"), "dim"))
        self._words = QLineEdit(exclude_words)
        self._words.setPlaceholderText(t("filters.exclude_placeholder"))
        self._words.returnPressed.connect(self._apply)
        self.body.addWidget(self._words)
        self.body.addWidget(label(t("filters.exclude_hint"), "faint", wrap=True))
        self.body.addWidget(label(t("filters.type"), "dim"))
        self._labels = {m.value: SEARCH_MODE_LABELS[m] for m in SearchMode if m != SearchMode.ARTISTS}
        self._menu = QComboBox()
        self._menu.addItems(list(self._labels.values()))
        self._menu.setCurrentText(self._labels.get(mode, SEARCH_MODE_LABELS[SearchMode.ALL]))
        self.body.addWidget(self._menu)
        self.body.addWidget(label(t("filters.max_duration"), "dim"))
        self._minutes = QComboBox()
        self._minute_labels = {m: (t("filters.any_duration") if m == 0 else t("filters.under_minutes", n=m))
                               for m in self.MINUTES}
        self._minutes.addItems(list(self._minute_labels.values()))
        self._minutes.setCurrentText(self._minute_labels.get(max_minutes, self._minute_labels[0]))
        self.body.addWidget(self._minutes)
        self._hide_owned = QCheckBox(t("filters.hide_owned"))
        self._hide_owned.setChecked(hide_owned)
        self.body.addWidget(self._hide_owned)
        self.footer(t("action.apply"), self._apply)
        self.show_dialog()

    def _apply(self) -> None:
        text = self._menu.currentText()
        value = next((k for k, v in self._labels.items() if v == text), SearchMode.ALL.value)
        minutes = next((k for k, v in self._minute_labels.items() if v == self._minutes.currentText()), 0)
        words = self._words.text().strip()
        self.close()
        self._on_apply(words, value, minutes, self._hide_owned.isChecked())


class MetadataDialog(BaseDialog):
    """Modifier le titre et l'artiste d'un son (base + export.pdb ; le fichier n'est pas renommé)."""

    def __init__(self, parent: Any, title: str, artist: str, on_ok: Callable[[str, str], None]) -> None:
        super().__init__(parent, t("meta.title"), 440)
        self._on_ok = on_ok
        self.heading(t("meta.title"))
        self.body.addWidget(label(t("track.title"), "dim"))
        self._title = QLineEdit(title)
        self.body.addWidget(self._title)
        self.body.addWidget(label(t("track.artist"), "dim"))
        self._artist = QLineEdit(artist)
        self.body.addWidget(self._artist)
        for e in (self._title, self._artist):
            e.returnPressed.connect(self._ok)
        self.footer(t("action.save"), self._ok)
        self.show_dialog()
        self._title.setFocus()
        self._title.selectAll()

    def _ok(self) -> None:
        title, artist = self._title.text().strip(), self._artist.text().strip()
        if title:
            self.close()
            self._on_ok(title, artist)
