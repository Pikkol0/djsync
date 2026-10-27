"""Diagnostic de la bibliothèque (V1.1.0) : doublons, sons de mauvaise qualité ou de mauvaise source.

Pour chaque problème, l'utilisateur choisit :
* doublons : l'une des versions déjà présentes (les autres sont supprimées), OU une version propre
  retéléchargée depuis YouTube Music / SoundCloud (toutes les versions présentes sont remplacées) ;
* mauvaise qualité / source : une version propre à retélécharger (remplace l'ancienne dans ses
  playlists, à la même position).
« Ignorer » retire le problème de la liste et s'en souvient (il ne revient pas au diagnostic suivant).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFormLayout, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QWidget,
)

from ..core.duplicates import best_keeper, split_display
from ..i18n import plural, t
from ..models import SOURCE_LABELS, Candidate, LibraryTrack, format_duration
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .duplicates_dialog import _FORMATS, _drop_layout
from .widgets import CamelotPill, button, chip, hbox, icon_button, label, panel, vbox

ALT = 100          # identifiant des boutons radio des versions à retélécharger (100, 101…)


def item_key(kind: str, payload: Any) -> str:
    """Clé stable d'un problème (pour « Ignorer »)."""
    if kind == "dup":
        return "d:" + ",".join(str(x.content_id) for x in sorted(payload, key=lambda x: x.content_id))
    return f"q:{payload.track.content_id}:{payload.track.title}"


class DiagnosticDialog(BaseDialog):
    as_page = True                    # 1.2.3 : page de la fenêtre principale
    modal = False

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("diag.title"), 920, 600)
        self.ctrl = controller
        self.items: List[Tuple[str, Any]] = []          # ("dup", [LibraryTrack…]) | ("source"|"bitrate", QualityIssue)
        self.index = -1
        self._busy = False
        self._loading = True
        self._alts: Dict[str, Optional[List[Candidate]]] = {}     # None = recherche en cours
        self._quality: Dict[int, Any] = {}
        self._choice = QButtonGroup(self)
        self.title_entry: Optional[QLineEdit] = None
        self.artist_entry: Optional[QLineEdit] = None
        self.note: Optional[Any] = None
        self.meta_head: Optional[Any] = None
        self.meta_box: Optional[Any] = None
        from .diag_tabs import add_tabs

        add_tabs(self, controller, "quality")                  # 1.3.1 (C41) : onglet « Mauvaise qualité »

        head = hbox()
        drive = controller.drive
        name = (t("local.name") if controller.is_local else (getattr(drive, "label", "") or str(getattr(drive, "root", ""))))\
            if drive is not None else ""
        head.addWidget(label(t("diagtab.quality_title") + (f" — {name}" if name else ""), "h2"))
        head.addStretch(1)
        self.count = label(t("diag.running"), "dim")
        head.addWidget(self.count)
        self.body.addLayout(head)

        main = hbox(spacing=theme.px(10))
        self.list = QListWidget()
        self.list.setFixedWidth(theme.px(280))
        self.list.currentRowChanged.connect(self._row_changed)
        main.addWidget(self.list)
        self.detail = panel()
        self.detail_lay = vbox(self.detail, margins=theme.px(10), spacing=theme.px(6))
        self.detail_lay.addWidget(label(t("diag.running_sub"), "faint", wrap=True))
        self.detail_lay.addStretch(1)
        main.addWidget(self.detail, 1)
        self.body.addLayout(main, 1)

        bar = hbox()
        bar.addStretch(1)
        self.ignore_btn = button(t("diag.ignore"), self._ignore, icon="close")
        self.apply_btn = button(t("diag.apply"), self._apply, kind="primary", icon="check")
        bar.addWidget(self.ignore_btn)
        bar.addWidget(self.apply_btn)
        bar.addWidget(button(t("action.close"), self.close))
        self.body.addLayout(bar)
        self._refresh_actions()
        self.show_dialog()
        controller.diagnose(self._loaded, self._progress, duplicates=False)

    # ------------------------------------------------------------------ chargement
    def _progress(self, i: int, n: int) -> None:
        if self.winfo_exists() and self._loading:
            self.count.setText(t("diag.progress", i=i, n=n))

    def _loaded(self, diagnosis: Any) -> None:
        if not self.winfo_exists():
            return
        self._loading = False
        ignored = set(self.ctrl.settings.diag_ignored)
        items: List[Tuple[str, Any]] = [("dup", g) for g in diagnosis.duplicates]
        items += [(i.kind, i) for i in diagnosis.issues if i.kind == "source"]
        items += [(i.kind, i) for i in diagnosis.issues if i.kind == "bitrate"]
        self.items = [(k, p) for k, p in items if item_key(k, p) not in ignored]
        self._fill_list()
        self._select(0 if self.items else -1)

    def _fill_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        n = len(self.items)
        self.count.setText(plural("diag.count_one", "diag.count_many", n) if n else t("diag.none_short"))
        if not self._loading:
            self.ctrl.set_diag_count("quality", n)
        current = None
        for idx, (kind, payload) in enumerate(self.items):
            if kind != current:
                current = kind
                total = sum(1 for k, _p in self.items if k == kind)
                head = QListWidgetItem(f"{t('diag.section_' + kind)}  ({total})")
                head.setFlags(Qt.NoItemFlags)
                f = head.font()
                f.setBold(True)
                head.setFont(f)
                self.list.addItem(head)
            track = best_keeper(payload) if kind == "dup" else payload.track
            title, artist = split_display(track.title, track.artist)
            extra = f"×{len(payload)}" if kind == "dup" else payload.reason
            item = QListWidgetItem(f"{title}\n{artist or '—'}  ·  {extra}")
            item.setData(Qt.UserRole, idx)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _row_changed(self, row: int) -> None:
        item = self.list.item(row) if row >= 0 else None
        idx = item.data(Qt.UserRole) if item is not None else None
        if idx is None:
            return
        self._select(int(idx))

    def _row_of(self, idx: int) -> int:
        for r in range(self.list.count()):
            if self.list.item(r).data(Qt.UserRole) == idx:
                return r
        return -1

    # ------------------------------------------------------------------ détail
    def _clear_detail(self) -> None:
        for b in list(self._choice.buttons()):
            self._choice.removeButton(b)
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()                 # sans attendre la destruction différée
                item.widget().deleteLater()
            elif item.layout() is not None:
                _drop_layout(item.layout())
        self.title_entry = self.artist_entry = self.note = self.meta_head = self.meta_box = None

    def _select(self, idx: int) -> None:
        self.index = idx
        row = self._row_of(idx)
        if row >= 0 and self.list.currentRow() != row:
            self.list.blockSignals(True)
            self.list.setCurrentRow(row)
            self.list.blockSignals(False)
        self._render()

    def _render(self) -> None:
        self._clear_detail()
        cur = self.current
        if cur is None:
            self.detail_lay.addWidget(label(t("diag.none_title"), "h2"))
            self.detail_lay.addWidget(label(t("diag.none_sub"), "dim", wrap=True))
            self.detail_lay.addStretch(1)
            self._refresh_actions()
            return
        kind, payload = cur
        lay = self.detail_lay
        if kind == "dup":
            tracks: List[LibraryTrack] = list(payload)
            lay.addWidget(label(t("diag.dup_title", n=len(tracks)), "h2"))
            lay.addWidget(label(t("diag.dup_sub"), "dim", wrap=True))
            missing = [x for x in tracks if x.content_id not in self._quality]
            if missing:
                self.ctrl.track_quality(missing, self._quality_loaded)
            keeper = best_keeper(tracks)
            for k, x in enumerate(tracks):
                lay.addWidget(self._version_row(k, x, tracks, x is keeper))
            ref = keeper
        else:
            issue = payload
            lay.addWidget(label(t("diag.source_title" if kind == "source" else "diag.bitrate_title",
                                  reason=issue.reason), "h2"))
            lay.addWidget(label(t("diag.source_sub" if kind == "source" else "diag.bitrate_sub"), "dim", wrap=True))
            self._quality[issue.track.content_id] = issue.info
            lay.addWidget(self._version_row(-1, issue.track, [issue.track], False))
            ref = issue.track

        lay.addSpacing(theme.px(6))
        lay.addWidget(label(t("diag.alt_title"), "h2"))
        key = item_key(kind, payload)
        alts = self._alts.get(key, "todo")
        if alts == "todo":
            self._alts[key] = None
            self.ctrl.find_alternatives(ref, lambda found, k=key: self._alts_loaded(k, found))
            alts = None
        if alts is None:
            lay.addWidget(label(t("diag.alt_searching"), "faint"))
        elif not alts:
            lay.addWidget(label(t("diag.alt_none"), "dim", wrap=True))
            title, artist = split_display(ref.title, ref.artist)
            lay.addWidget(button(t("diag.search_myself"), lambda q=f"{artist} {title}".strip(): self._search(q),
                                 icon="search"), 0, Qt.AlignLeft)
        else:
            for i, c in enumerate(alts):
                lay.addWidget(self._alt_row(i, c, checked=(kind != "dup" and i == 0)))
        self.note = label(t("diag.replace_note"), "faint", wrap=True)
        lay.addWidget(self.note)

        if kind == "dup":
            lay.addSpacing(theme.px(6))
            title, artist = split_display(ref.title, ref.artist)
            box = QWidget()
            form = QFormLayout(box)
            form.setContentsMargins(0, 0, 0, 0)
            self.title_entry = QLineEdit(title)
            self.artist_entry = QLineEdit(artist)
            self.title_entry.setToolTip(t("dup.metadata_hint"))
            form.addRow(t("track.title"), self.title_entry)
            form.addRow(t("track.artist"), self.artist_entry)
            self.meta_head = label(t("dup.fix_metadata"), "dim")
            lay.addWidget(self.meta_head)
            lay.addWidget(box)
            self.meta_box = box
        lay.addStretch(1)
        self._choice_changed()

    def _version_row(self, k: int, x: LibraryTrack, group: List[LibraryTrack], checked: bool) -> QWidget:
        row = panel(role="banner")
        lay = hbox(row, margins=theme.px(6))
        if k >= 0:
            radio = QRadioButton()
            radio.setChecked(checked)
            self._choice.addButton(radio, k)
            radio.toggled.connect(lambda on: self._choice_changed() if on else None)
            lay.addWidget(radio)
        text = vbox(spacing=0)
        name = label(x.title)
        name.setStyleSheet("font-weight:600;")
        text.addWidget(name)
        from . import levels
        from html import escape

        missing = self.ctrl.file_missing(x)                  # 1.3.0-rc.3 (B20)
        q = self._quality.get(x.content_id)
        fmt, lvl = levels.audio_text(q, x.file_type, missing)     # 1.3.1 (C42, C29)
        info = [escape(x.artist or t("dup.no_artist")), format_duration(x.duration_seconds), levels.html(fmt, lvl),
                f"{x.bpm:.0f} BPM" if x.bpm else escape(t("dup.not_analysed")), (x.date_added or "")[:10]]
        line = label("  ·  ".join(i for i in info if i), "dim")
        line.setTextFormat(Qt.RichText)
        text.addWidget(line)
        lay.addLayout(text, 1)
        if self._is_best(x, group):
            best = chip(t("dup.best_quality"), "chip_good")
            best.setToolTip(t("dup.best_quality_tip"))
            lay.addWidget(best)
        if missing:
            gone = chip(t("diag.file_missing"), "chip_warn")
            gone.setToolTip(self.ctrl.missing_file_text(self.ctrl.library.absolute_path(x)))
            lay.addWidget(gone)
        if x.camelot:
            lay.addWidget(CamelotPill(x.camelot))
        idx = group.index(x)
        play = icon_button("play", lambda g=group, i=idx: self.ctrl.play_queue(g, i), t("action.listen"))
        play.setEnabled(not missing)
        lay.addWidget(play)
        return row

    def _alt_row(self, i: int, c: Candidate, checked: bool) -> QWidget:
        row = panel(role="banner")
        lay = hbox(row, margins=theme.px(6))
        radio = QRadioButton()
        radio.setChecked(checked)
        self._choice.addButton(radio, ALT + i)
        radio.toggled.connect(lambda on: self._choice_changed() if on else None)
        lay.addWidget(radio)
        text = vbox(spacing=0)
        name = label(c.track.title)
        name.setStyleSheet("font-weight:600;")
        text.addWidget(name)
        from . import levels
        from html import escape

        kind = t("track.song") if c.track.is_song else t("track.video")
        exp, lvl = levels.expected_download(c.track.source, getattr(self.ctrl.settings, "audio_format", "m4a"))
        info = [escape(c.track.artist or ""), format_duration(c.track.duration_seconds), escape(kind),
                levels.html(t("diag.match", score=f"{c.score:.0f}"), levels.match_score(c.score)),
                levels.html(exp, lvl)]
        line = label("  ·  ".join(i for i in info if i), "dim")
        line.setTextFormat(Qt.RichText)
        line.setToolTip(t("dup.expected_tip"))
        text.addWidget(line)
        lay.addLayout(text, 1)
        lay.addWidget(chip(SOURCE_LABELS.get(c.track.source, c.track.source)))
        lay.addWidget(icon_button("play", lambda tr=c.track: self.ctrl.preview(tr), t("action.listen")))
        return row

    def _is_best(self, x: LibraryTrack, group: List[LibraryTrack]) -> bool:
        """C42 : la version de meilleure qualité audio du groupe (seulement si toutes sont connues et
        qu'elles diffèrent)."""
        from . import levels

        if len(group) < 2 or any(y.content_id not in self._quality for y in group):
            return False
        rank = {y.content_id: levels.quality_rank(self._quality[y.content_id].bitrate,
                                                  self._quality[y.content_id].lossless) for y in group}
        top = max(rank.values())
        return top > 0 and rank[x.content_id] == top and len(set(rank.values())) > 1 \
            and sum(1 for v in rank.values() if v == top) == 1

    def _quality_loaded(self, found: Dict[int, Any]) -> None:
        if not self.winfo_exists() or not found:
            return
        self._quality.update(found)
        if self.current and self.current[0] == "dup" and any(x.content_id in found for x in self.current[1]):
            self._render_keep_choice()

    def _alts_loaded(self, key: str, found: List[Candidate]) -> None:
        if not self.winfo_exists():
            return
        self._alts[key] = list(found)
        cur = self.current
        if cur is not None and item_key(*cur) == key:
            self._render_keep_choice()

    def _render_keep_choice(self) -> None:
        """Redessine le détail sans perdre le choix ni le titre/artiste saisis."""
        chosen = self._choice.checkedId()
        typed = (self.title_entry.text(), self.artist_entry.text()) if self.title_entry is not None else None
        self._render()
        b = self._choice.button(chosen) if chosen >= 0 else None
        if b is not None:
            b.setChecked(True)
        if typed and self.title_entry is not None:
            self.title_entry.setText(typed[0])
            self.artist_entry.setText(typed[1])

    def _choice_changed(self) -> None:
        alt = self._choice.checkedId() >= ALT
        if self.note is not None:
            self.note.setVisible(alt)
        for w in (self.meta_box, self.meta_head):
            if w is not None:
                try:
                    w.setVisible(not alt)
                except RuntimeError:
                    pass
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        cur = self.current
        ok = cur is not None and not self._busy and self._choice.checkedId() >= 0
        self.apply_btn.setEnabled(ok)
        self.ignore_btn.setEnabled(cur is not None and not self._busy)
        if cur is not None:
            alt = self._choice.checkedId() >= ALT
            self.apply_btn.setText(t("diag.apply_download") if alt else t("diag.apply"))

    # ------------------------------------------------------------------ actions
    @property
    def current(self) -> Optional[Tuple[str, Any]]:
        return self.items[self.index] if 0 <= self.index < len(self.items) else None

    def _search(self, query: str) -> None:
        app = self.parent().window() if self.parent() is not None else None
        if app is not None and hasattr(app, "show_view"):
            app.show_view("search")
            app.views["search"].search_for(query)

    def _drop_current(self) -> None:
        if self.current is None:
            return
        idx = self.index
        self.items.pop(idx)
        self._fill_list()
        self._select(min(idx, len(self.items) - 1))

    def _ignore(self) -> None:
        cur = self.current
        if cur is None:
            return
        self.ctrl.settings.diag_ignored.append(item_key(*cur))
        try:
            self.ctrl.settings.save()
        except Exception:  # noqa: BLE001 - réglages en lecture seule : ignoré pour la session seulement
            pass
        self._drop_current()

    def _apply(self) -> None:
        cur = self.current
        choice = self._choice.checkedId()
        if cur is None or choice < 0:
            return
        kind, payload = cur
        olds: List[LibraryTrack] = list(payload) if kind == "dup" else [payload.track]
        if choice >= ALT:
            alts = self._alts.get(item_key(kind, payload)) or []
            if choice - ALT >= len(alts):
                return
            cand = alts[choice - ALT]
            names = ", ".join(t("fmt.quoted", text=x.title) for x in olds[:3])

            def go() -> None:
                if self.ctrl.replace_with_download(cand.track, olds) is not None:
                    self._drop_current()

            ConfirmDialog(self, t("diag.replace_confirm_title"),
                          t("diag.replace_confirm", names=names, new=cand.track.title,
                            source=SOURCE_LABELS.get(cand.track.source, cand.track.source)),
                          go, confirm_text=t("diag.apply_download"), detail=t("diag.replace_detail"))
            return
        keep = olds[choice]
        others = [x for x in olds if x is not keep]
        title = (self.title_entry.text().strip() if self.title_entry else "") or keep.title
        artist = self.artist_entry.text().strip() if self.artist_entry else keep.artist
        new_title = title if title != keep.title else None
        new_artist = artist if artist != keep.artist else None
        names = ", ".join(t("fmt.quoted", text=x.title) for x in others[:3])

        def go_keep() -> None:
            self._busy = True
            self._refresh_actions()

            def done(_r: Any) -> None:
                self._busy = False
                if self.winfo_exists():
                    self._drop_current()

            def failed(_e: BaseException) -> None:
                self._busy = False
                if self.winfo_exists():
                    self._refresh_actions()

            self.ctrl.resolve_duplicates(keep.content_id, [x.content_id for x in others], new_title, new_artist,
                                         ok=done, err=failed)

        ConfirmDialog(self, t("dup.confirm_title"), t("dup.confirm_msg", n=len(others), names=names, keep=keep.title),
                      go_keep, confirm_text=t("dup.apply_short"), danger=True, detail=t("dup.confirm_detail"))
