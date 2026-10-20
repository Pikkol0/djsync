"""Outil « Doublons » : retrouve les sons présents plusieurs fois sur la clé, laisse choisir lequel
garder, corriger son titre / artiste, et supprime les autres.

Exemple : « Daft Punk - One More Time (Clip Officiel) » (artiste vide) et « One More Time »
(Daft Punk). Le son gardé prend la place des doublons dans toutes leurs playlists (même
position) ; la base est sauvegardée avant la modification.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtWidgets import (
    QButtonGroup, QFormLayout, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QWidget,
)

from ..core.duplicates import best_keeper, split_display
from ..i18n import plural, t
from ..models import LibraryTrack, format_duration
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import CamelotPill, button, hbox, icon_button, label, panel, vbox

_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


class DuplicatesDialog(BaseDialog):
    modal = False

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("dup.title"), 820, 540)
        self.ctrl = controller
        self.groups: List[List[LibraryTrack]] = []
        self.index = -1
        self._busy = False
        self._keep = QButtonGroup(self)
        self.title_entry: Optional[QLineEdit] = None
        self.artist_entry: Optional[QLineEdit] = None

        head = hbox()
        head.addWidget(label(t("dup.title"), "h2"))
        head.addStretch(1)
        self.count = label(t("dup.searching"), "dim")
        head.addWidget(self.count)
        self.body.addLayout(head)

        main = hbox(spacing=theme.px(10))
        self.list = QListWidget()
        self.list.setFixedWidth(theme.px(240))
        self.list.currentRowChanged.connect(self._select)
        main.addWidget(self.list)
        self.detail = panel()
        self.detail_lay = vbox(self.detail, margins=theme.px(10), spacing=theme.px(6))
        self.detail_lay.addWidget(label(t("dup.searching"), "faint"))
        self.detail_lay.addStretch(1)
        main.addWidget(self.detail, 1)
        self.body.addLayout(main, 1)

        bar = hbox()
        bar.addStretch(1)
        self.skip_btn = button(t("dup.skip"), self._skip, icon="close")
        self.apply_btn = button(t("dup.apply"), self._apply, kind="primary", icon="check")
        bar.addWidget(self.skip_btn)
        bar.addWidget(self.apply_btn)
        bar.addWidget(button(t("action.close"), self.close))
        self.body.addLayout(bar)
        self._refresh_actions()
        self.show_dialog()
        controller.find_duplicates(self._loaded)

    # ------------------------------------------------------------------ liste
    def _loaded(self, groups: List[List[LibraryTrack]]) -> None:
        if not self.winfo_exists():
            return
        self.groups = groups
        self._fill_list()
        self._select(0 if groups else -1)

    def _fill_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        self.count.setText(plural("dup.groups_one", "dup.groups_many", len(self.groups)))
        for g in self.groups:
            k = best_keeper(g)
            title, artist = split_display(k.title, k.artist)
            self.list.addItem(QListWidgetItem(f"{title}\n{artist or '—'}  ·  ×{len(g)}"))
        self.list.blockSignals(False)

    def _clear_detail(self) -> None:
        for b in list(self._keep.buttons()):
            self._keep.removeButton(b)
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                _drop_layout(item.layout())
        self.title_entry = self.artist_entry = None

    def _select(self, i: int) -> None:
        self.index = i
        if 0 <= i < self.list.count() and self.list.currentRow() != i:
            self.list.blockSignals(True)
            self.list.setCurrentRow(i)
            self.list.blockSignals(False)
        self._clear_detail()
        if not (0 <= i < len(self.groups)):
            self.detail_lay.addWidget(label(t("dup.none_title"), "h2"))
            self.detail_lay.addWidget(label(t("dup.none_sub"), "dim", wrap=True))
            self.detail_lay.addStretch(1)
            self._refresh_actions()
            return
        group = self.groups[i]
        keeper = best_keeper(group)
        self.detail_lay.addWidget(label(t("dup.choose"), "dim"))
        for k, x in enumerate(group):
            self.detail_lay.addWidget(self._version_row(k, x, x is keeper))
        self.detail_lay.addSpacing(theme.px(8))
        self.detail_lay.addWidget(label(t("dup.fix_metadata"), "h2"))
        title, artist = split_display(keeper.title, keeper.artist)
        form = QFormLayout()
        self.title_entry = QLineEdit(title)
        self.artist_entry = QLineEdit(artist)
        form.addRow(t("track.title"), self.title_entry)
        form.addRow(t("track.artist"), self.artist_entry)
        self.detail_lay.addLayout(form)
        self.title_entry.setToolTip(t("dup.metadata_hint"))
        self.detail_lay.addStretch(1)
        self._refresh_actions()

    def _version_row(self, k: int, x: LibraryTrack, checked: bool) -> QWidget:
        row = panel(role="banner")
        lay = hbox(row, margins=theme.px(6))
        radio = QRadioButton()
        radio.setChecked(checked)
        self._keep.addButton(radio, k)
        radio.toggled.connect(lambda on: self._keeper_changed() if on else None)
        lay.addWidget(radio)
        text = vbox(spacing=0)
        name = label(x.title)
        name.setStyleSheet("font-weight:600;")
        text.addWidget(name)
        info = [x.artist or t("dup.no_artist"), format_duration(x.duration_seconds), _FORMATS.get(x.file_type, ""),
                f"{x.bpm:.0f} BPM" if x.bpm else t("dup.not_analysed"), (x.date_added or "")[:10]]
        text.addWidget(label("  ·  ".join(i for i in info if i), "dim"))
        lay.addLayout(text, 1)
        if x.camelot:
            lay.addWidget(CamelotPill(x.camelot))
        lay.addWidget(icon_button("play", lambda: self.ctrl.play_queue(self.groups[self.index], k), t("action.listen")))
        return row

    def keep_index(self) -> int:
        return max(0, self._keep.checkedId())

    def _keeper_changed(self) -> None:
        if self.title_entry is None or not (0 <= self.index < len(self.groups)):
            return
        group = self.groups[self.index]
        x = group[self.keep_index()]
        title, artist = split_display(x.title, x.artist)
        current = (self.title_entry.text().strip(), self.artist_entry.text().strip())
        if current[0] and not any(split_display(g.title, g.artist) == current for g in group):
            return                                  # l'utilisateur a déjà corrigé à la main : on garde
        self.title_entry.setText(title)
        self.artist_entry.setText(artist)

    def _refresh_actions(self) -> None:
        ok = 0 <= self.index < len(self.groups) and not self._busy
        self.apply_btn.setEnabled(ok)
        self.skip_btn.setEnabled(ok)

    # ------------------------------------------------------------------ actions
    def _skip(self) -> None:
        if 0 <= self.index < len(self.groups):
            self.groups.pop(self.index)
            idx = self.index
            self._fill_list()
            self._select(min(idx, len(self.groups) - 1))

    def _apply(self) -> None:
        if not (0 <= self.index < len(self.groups)) or self.title_entry is None:
            return
        group = self.groups[self.index]
        keep = group[self.keep_index()]
        others = [x for x in group if x is not keep]
        title = self.title_entry.text().strip() or keep.title
        artist = self.artist_entry.text().strip()
        new_title = title if title != keep.title else None
        new_artist = artist if artist != keep.artist else None
        names = ", ".join(t("fmt.quoted", text=x.title) for x in others[:3])

        def go() -> None:
            self._busy = True
            self._refresh_actions()

            def done(_r: Any) -> None:
                self._busy = False
                if self.winfo_exists():
                    self._skip()

            def failed(_e: BaseException) -> None:
                self._busy = False
                if self.winfo_exists():
                    self._refresh_actions()

            self.ctrl.resolve_duplicates(keep.content_id, [x.content_id for x in others], new_title, new_artist,
                                         ok=done, err=failed)

        ConfirmDialog(self, t("dup.confirm_title"), t("dup.confirm_msg", n=len(others), names=names, keep=keep.title),
                      go, confirm_text=t("dup.apply_short"), danger=True, detail=t("dup.confirm_detail"))

    @property
    def current_group(self) -> Optional[List[LibraryTrack]]:
        return self.groups[self.index] if 0 <= self.index < len(self.groups) else None


def _drop_layout(lay: Any) -> None:
    while lay.count():
        item = lay.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _drop_layout(item.layout())
