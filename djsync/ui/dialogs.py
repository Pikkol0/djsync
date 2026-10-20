"""Fenêtres modales Qt : confirmation, saisie de texte, choix de playlists (avec création), filtres
de recherche, titre / artiste. Toutes s'ouvrent sans bloquer la boucle (`open()`), centrées sur la
fenêtre principale ; Qt les garde dans l'écran et les dimensionne d'après leur contenu."""
from __future__ import annotations

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
               show_cancel: bool = True) -> Any:
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
                 confirm_text: str = "") -> None:
        super().__init__(parent, title, 400)
        self._on_ok = on_ok
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
        if text:
            self.close()
            self._on_ok(text)


class PlaylistPicker(BaseDialog):
    """Cocher une ou plusieurs playlists, ou en créer une. `on_ok(liste d'identifiants)`."""

    def __init__(self, parent: Any, controller: Any, title: str, confirm_text: str,
                 on_ok: Callable[[List[int]], None], multi: bool = True, preselect: Sequence[int] = (),
                 new_name: str = "", exclude: Sequence[int] = (), allow_empty: bool = False,
                 subtitle: str = "") -> None:
        super().__init__(parent, title, 440, 480)
        self.ctrl = controller
        self._on_ok, self._multi, self._allow_empty = on_ok, multi, allow_empty
        self._exclude = set(exclude)
        self._checked: set = set(preselect)
        self._vars: Dict[int, QCheckBox] = {}
        self.heading(title, subtitle)
        area = QScrollArea()
        area.setWidgetResizable(True)
        self._list = QWidget()
        self._list_lay = vbox(self._list, margins=theme.px(6), spacing=theme.px(2))
        area.setWidget(self._list)
        self.body.addWidget(area, 1)
        row = hbox()
        self._new = QLineEdit(new_name)
        self._new.setPlaceholderText(t("picker.new_name"))
        self._new.returnPressed.connect(self._create)
        row.addWidget(self._new, 1)
        row.addWidget(button("+ " + t("action.create"), self._create))
        self.body.addLayout(row)
        self._ok_btn = self.footer(confirm_text, self._confirm)
        self.show_dialog()
        self._reload()

    @staticmethod
    def _paths(playlists: List[PlaylistInfo], exclude: set) -> List[tuple]:
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
        def show(playlists: List[PlaylistInfo]) -> None:
            if self._closed:
                return
            while self._list_lay.count():
                item = self._list_lay.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._vars.clear()
            rows = self._paths(playlists, self._exclude)
            if tick is not None:
                self._checked = {tick} if not self._multi else self._checked | {tick}
            if not rows:
                self._list_lay.addWidget(label(t("picker.none"), "faint"))
            for text, p in rows:
                cb = QCheckBox(f"{text}   ·   {p.track_count}")
                cb.setChecked(p.playlist_id in self._checked)
                cb.toggled.connect(lambda on, pid=p.playlist_id: self._toggled(pid, on))
                self._vars[p.playlist_id] = cb
                self._list_lay.addWidget(cb)
            self._list_lay.addStretch(1)
            self._refresh_ok()

        self.ctrl.fetch_playlists(show)

    def _toggled(self, pid: int, on: bool) -> None:
        if on:
            if not self._multi:
                for other, cb in self._vars.items():
                    if other != pid and cb.isChecked():
                        cb.blockSignals(True)
                        cb.setChecked(False)
                        cb.blockSignals(False)
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

        self.ctrl.create_playlist(name, 0, ok=done, err=fail)

    def _confirm(self) -> None:
        ids = self._selected()
        if not ids and not self._allow_empty:
            return
        self.close()
        self._on_ok(ids)


class FiltersPopup(BaseDialog):
    """Options de recherche avancées : mots à exclure + type de résultat."""

    def __init__(self, parent: Any, exclude_words: str, mode: str, on_apply: Callable[[str, str], None]) -> None:
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
        self._labels = {m.value: SEARCH_MODE_LABELS[m] for m in SearchMode}
        self._menu = QComboBox()
        self._menu.addItems(list(self._labels.values()))
        self._menu.setCurrentText(self._labels.get(mode, SEARCH_MODE_LABELS[SearchMode.ALL]))
        self.body.addWidget(self._menu)
        self.footer(t("action.apply"), self._apply)
        self.show_dialog()

    def _apply(self) -> None:
        text = self._menu.currentText()
        value = next((k for k, v in self._labels.items() if v == text), SearchMode.ALL.value)
        words = self._words.text().strip()
        self.close()
        self._on_apply(words, value)


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
        self.body.addWidget(label(t("meta.hint"), "faint", wrap=True))
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
