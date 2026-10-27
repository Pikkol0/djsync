"""Outil « Doublons » : retrouve les sons présents plusieurs fois sur la clé, laisse choisir lequel
garder, corriger son titre / artiste, et supprime les autres.

Exemple : « Daft Punk - One More Time (Clip Officiel) » (artiste vide) et « One More Time »
(Daft Punk). Le son gardé prend la place des doublons dans toutes leurs playlists (même
position) ; la base est sauvegardée avant la modification.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QWidget,
)

from ..core.duplicates import best_keeper, split_display
from ..i18n import plural, t
from ..models import LibraryTrack, format_duration
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import CamelotPill, button, chip, hbox, icon_button, label, panel, vbox

_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


class DuplicatesDialog(BaseDialog):
    as_page = True                    # 1.2.3 : page de la fenêtre principale
    modal = False

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("dup.title"), 820, 540)
        self.ctrl = controller
        self.groups: List[List[LibraryTrack]] = []
        self.index = -1
        self._busy = False
        self._keep = QButtonGroup(self)
        self.title_entry: Optional[QLineEdit] = None
        self._pl_labels: dict = {}
        self.artist_entry: Optional[QLineEdit] = None
        self.cues_combo: Optional[QComboBox] = None          # 1.3.0 (C13) : de quelle version viennent les cues
        self._cue_counts: dict = {}
        self._cues_touched = False
        from .diag_tabs import add_tabs

        add_tabs(self, controller, "dup")                      # 1.3.1 (C41) : onglet « Doublons »

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
        controller.find_duplicates(self._loaded, self._progress)

    def _progress(self, i: int, n: int) -> None:
        if self.winfo_exists() and not self.groups:
            self.count.setText(t("dup.comparing", i=i, n=n))

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
        self.ctrl.set_diag_count("dup", len(self.groups))
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
        self.cues_combo = None
        self._cue_counts = {}
        self._cues_touched = False
        self._pl_labels = {}

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
        token = self.index

        def show_playlists(found: dict) -> None:           # 1.2.1 (C11)
            if not self.winfo_exists() or self.index != token:
                return
            for cid, lbl in self._pl_labels.items():
                names = found.get(cid) or []
                lbl.setText(t("dup.in_playlists", names=", ".join(names)) if names else t("dup.in_no_playlist"))

        self.ctrl.track_playlists([x.content_id for x in group], show_playlists)
        matches = getattr(self.ctrl, "duplicate_matches", {}) or {}
        if any(getattr(matches.get(x.content_id), "verdict", "") == "variant" for x in group):
            self.detail_lay.addWidget(label(t("dup.variant_warning"), "warn", wrap=True))
        # 1.3.0 (C13) : choisir la version dont on garde les hot cues
        self.cues_box = QWidget()
        cues_lay = hbox(self.cues_box, spacing=theme.px(6))
        cues_lay.addWidget(label(t("dup.cues_from"), "dim"))
        self.cues_combo = QComboBox()
        self.cues_combo.activated.connect(lambda _i: setattr(self, "_cues_touched", True))
        cues_lay.addWidget(self.cues_combo, 1)
        self.cues_box.hide()
        self.detail_lay.addWidget(self.cues_box)

        def show_cues(found: dict) -> None:
            if not self.winfo_exists() or self.index != token:
                return
            self._cue_counts = {cid: sum(1 for c in cues if c.slot) for cid, cues in found.items()}
            self._fill_cues_combo()

        self.ctrl.load_group_cues(group, show_cues)
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

    def _fill_cues_combo(self) -> None:
        """Versions qui ont des hot cues ; par défaut : la version gardée si elle en a, sinon celle qui en
        a le plus (reportées sur la version gardée par alignement du son)."""
        combo = self.cues_combo
        group = self.current_group
        if combo is None or group is None:
            return
        with_cues = [x for x in group if self._cue_counts.get(x.content_id)]
        if not with_cues:
            self.cues_box.hide()
            return
        keep = group[self.keep_index()]
        current = combo.currentData() if self._cues_touched else None
        combo.clear()
        combo.addItem(t("dup.cues_keep_own"), None)
        for x in with_cues:
            k = group.index(x) + 1
            mine = t("dup.cues_kept_version") if x is keep else ""
            combo.addItem(t("dup.cues_version", k=k, n=self._cue_counts[x.content_id], title=x.title) + mine,
                          x.content_id)
        if current is not None and combo.findData(current) >= 0:
            combo.setCurrentIndex(combo.findData(current))
        elif self._cue_counts.get(keep.content_id):
            combo.setCurrentIndex(combo.findData(keep.content_id))
        else:
            best = max(with_cues, key=lambda x: self._cue_counts[x.content_id])
            combo.setCurrentIndex(combo.findData(best.content_id))
        self.cues_box.show()

    def cues_from(self) -> Optional[int]:
        if self.cues_combo is None or not self.cues_box.isVisible():
            return None
        return self.cues_combo.currentData()

    def _audio_chip(self, x: LibraryTrack) -> Optional[QWidget]:
        """1.3.0 (B02) : verdict de la comparaison du son avec la version de référence."""
        matches = getattr(self.ctrl, "duplicate_matches", {}) or {}
        if x.content_id not in matches:
            return None
        m = matches[x.content_id]
        if m == "reference":
            return chip(t("dup.audio_reference"))
        if m is None:
            c = chip(t("dup.audio_unknown"))
            c.setToolTip(t("dup.audio_unknown_tip"))
            return c
        from . import levels

        pct = int(round(m.share * 100))
        if m.verdict == "same":
            c = chip(t("dup.audio_same"), levels.CHIP_ROLE[levels.GOOD])          # C29 : vert, quel que soit l'accent
        else:
            c = chip(t("dup.audio_variant", pct=pct), levels.CHIP_ROLE[levels.similarity(pct)])
        c.setToolTip(t("dup.audio_tip", pct=int(round(m.share * 100)), shift=f"{m.shift_ms / 1000:+.2f}"))
        return c

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
        pl = label("", "faint", wrap=True)
        self._pl_labels[x.content_id] = pl
        text.addWidget(pl)
        lay.addLayout(text, 1)
        audio = self._audio_chip(x)
        if audio is not None:
            lay.addWidget(audio)
        missing = self.ctrl.file_missing(x)                   # 1.3.0-rc.3 (B20)
        if missing:
            gone = chip(t("diag.file_missing"), "chip_warn")
            gone.setToolTip(self.ctrl.missing_file_text(self.ctrl.library.absolute_path(x)))
            lay.addWidget(gone)
        if x.camelot:
            lay.addWidget(CamelotPill(x.camelot))
        # 1.2.1 (C12) : écouter le début (intro) ou le milieu de chaque version pour comparer
        start = button(t("dup.listen_start"), lambda: self._listen(k, 0.0), icon="play", tooltip=t("dup.listen_start_tip"))
        middle = button(t("dup.listen_middle"), lambda: self._listen(k, 0.45), kind="flat",
                        tooltip=t("dup.listen_middle_tip"))
        for b in (start, middle):
            b.setEnabled(not missing)
            lay.addWidget(b)
        return row

    def _listen(self, k: int, at: float) -> None:
        from PySide6.QtCore import QTimer

        from ..audio.player import PLAYING

        group = self.groups[self.index]
        self.ctrl.play_queue(group, k)
        if at <= 0:
            return
        player = self.ctrl.player

        def seek_when_ready(tries: int = 0) -> None:
            if player.state == PLAYING and player.duration > 0:
                player.seek(player.duration * at)
            elif tries < 50 and self.winfo_exists():
                QTimer.singleShot(100, lambda: seek_when_ready(tries + 1))

        QTimer.singleShot(100, seek_when_ready)

    def keep_index(self) -> int:
        return max(0, self._keep.checkedId())

    def _keeper_changed(self) -> None:
        if self.title_entry is None or not (0 <= self.index < len(self.groups)):
            return
        group = self.groups[self.index]
        x = group[self.keep_index()]
        if not self._cues_touched:
            self._fill_cues_combo()
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
                                         ok=done, err=failed, cues_from=cues_from)

        cues_from = self.cues_from()
        if cues_from == keep.content_id:
            cues_from = None

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
