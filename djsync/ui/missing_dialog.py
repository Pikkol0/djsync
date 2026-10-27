"""Onglet « Fichiers introuvables » du Diagnostic (1.3.1, C43).

Liste les sons de la bibliothèque dont le fichier n'existe plus (supprimé, renommé, dossier déplacé,
disque non branché) et propose pour chacun :
* Remplacer par une version identique déjà dans la bibliothèque (elle prend sa place dans les
  playlists ; ses hot cues sont repris si elle n'en a pas) ;
* Relier au fichier du même nom trouvé ailleurs (dossier déplacé) : même son, rien d'autre ne change ;
* Retélécharger une version propre (comme « Mauvaise qualité ») ;
* Retirer l'entrée de la bibliothèque (et de ses playlists).
Sur l'ordinateur, un son dont le disque n'est pas branché est signalé : rien n'est proposé par défaut.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QListWidget, QListWidgetItem, QRadioButton

from ..core.duplicates import split_display
from ..i18n import plural, t
from ..models import Candidate, format_duration
from . import theme
from .dialogs import BaseDialog
from .diag_tabs import add_tabs
from .duplicates_dialog import _drop_layout
from .widgets import button, hbox, label, panel, vbox

REPLACE, RELINK, DOWNLOAD, REMOVE = 0, 1, 2, 3
ALT = 100


class MissingFilesDialog(BaseDialog):
    as_page = True
    modal = False

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("diagtab.missing"), 900, 560)
        self.ctrl = controller
        self.items: List[Any] = []
        self.index = -1
        self._busy = False
        self._choice = QButtonGroup(self)
        self._alts: dict = {}                      # content_id -> [Candidate] (None : recherche en cours)
        self._alt_box: Optional[Any] = None
        add_tabs(self, controller, "missing")

        head = hbox()
        head.addWidget(label(t("missing.title"), "h2"))
        head.addStretch(1)
        self.count = label(t("missing.searching"), "dim")
        head.addWidget(self.count)
        self.body.addLayout(head)

        main = hbox(spacing=theme.px(10))
        self.list = QListWidget()
        self.list.setFixedWidth(theme.px(280))
        self.list.currentRowChanged.connect(self._select)
        main.addWidget(self.list)
        self.detail = panel()
        self.detail_lay = vbox(self.detail, margins=theme.px(10), spacing=theme.px(6))
        self.detail_lay.addWidget(label(t("missing.searching_sub"), "faint", wrap=True))
        self.detail_lay.addStretch(1)
        main.addWidget(self.detail, 1)
        self.body.addLayout(main, 1)

        bar = hbox()
        self.remove_all_btn = button(t("missing.remove_all"), self._remove_all, kind="flat", icon="trash")
        self.remove_all_btn.setToolTip(t("missing.remove_all_tip"))
        bar.addWidget(self.remove_all_btn)
        bar.addStretch(1)
        self.skip_btn = button(t("missing.skip"), self._skip, icon="next")
        self.apply_btn = button(t("missing.apply"), self._apply, kind="primary", icon="check")
        bar.addWidget(self.skip_btn)
        bar.addWidget(self.apply_btn)
        bar.addWidget(button(t("action.close"), self.close))
        self.body.addLayout(bar)
        self._refresh_actions()
        self.show_dialog()
        controller.find_missing(self._loaded)

    # ------------------------------------------------------------------ liste
    def _loaded(self, items: List[Any]) -> None:
        if not self.winfo_exists():
            return
        self.items = items
        self._fill_list()
        self._select(0 if items else -1)

    def _fill_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        n = len(self.items)
        self.count.setText(plural("missing.count_one", "missing.count_many", n) if n else t("missing.none_short"))
        for it in self.items:
            title, artist = split_display(it.track.title, it.track.artist)
            extra = "  ·  " + t("missing.offline_short") if it.offline else ""
            item = QListWidgetItem(f"{title}\n{artist or '—'}{extra}")
            if it.offline:
                item.setForeground(Qt.gray)
            self.list.addItem(item)
        self.list.blockSignals(False)

    @property
    def current(self) -> Optional[Any]:
        return self.items[self.index] if 0 <= self.index < len(self.items) else None

    def _clear_detail(self) -> None:
        for b in list(self._choice.buttons()):
            self._choice.removeButton(b)
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                _drop_layout(item.layout())
        self._alt_box = None

    def _select(self, i: int) -> None:
        self.index = i
        if 0 <= i < self.list.count() and self.list.currentRow() != i:
            self.list.blockSignals(True)
            self.list.setCurrentRow(i)
            self.list.blockSignals(False)
        self._clear_detail()
        it = self.current
        if it is None:
            self.detail_lay.addWidget(label(t("missing.none_title"), "h2"))
            self.detail_lay.addWidget(label(t("missing.none_sub"), "dim", wrap=True))
            self.detail_lay.addStretch(1)
            self._refresh_actions()
            return
        x = it.track
        title, artist = split_display(x.title, x.artist)
        self.detail_lay.addWidget(label(title, "h2"))
        self.detail_lay.addWidget(label(f"{artist or '—'}  ·  {format_duration(x.duration_seconds)}"
                                        + (f"  ·  {x.bpm:.0f} BPM" if x.bpm else ""), "dim"))
        path = label(t("missing.expected", path=it.path), "faint", wrap=True)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_lay.addWidget(path)
        self.detail_lay.addWidget(label(t("dup.in_playlists", names=", ".join(it.playlists)) if it.playlists
                                        else t("dup.in_no_playlist"), "dim", wrap=True))
        if it.offline:
            self.detail_lay.addWidget(label(t("missing.offline"), "warn", wrap=True))
        self.detail_lay.addSpacing(theme.px(6))
        self.detail_lay.addWidget(label(t("missing.what"), "dim"))
        default = None
        for k, cand in enumerate(it.candidates[:5]):
            ct, ca = split_display(cand.title, cand.artist)
            r = self._radio(t("missing.replace_by", title=ct, artist=ca or "—",
                              duration=format_duration(cand.duration_seconds)), REPLACE * 1000 + k)
            r.setToolTip(t("missing.replace_tip"))
            default = default or r
        if it.found is not None:
            r = self._radio(t("missing.relink", path=str(it.found)), RELINK * 1000)
            r.setToolTip(t("missing.relink_tip"))
            default = default or r
        dl = self._radio(t("missing.download"), DOWNLOAD * 1000)
        dl.toggled.connect(lambda on: on and self._search_alternatives())
        rm = self._radio(t("missing.remove"), REMOVE * 1000)
        rm.setToolTip(t("missing.remove_tip"))
        self._alt_box = vbox(spacing=theme.px(4))
        self.detail_lay.addLayout(self._alt_box)
        if default is not None and not it.offline:
            default.setChecked(True)
        self.detail_lay.addStretch(1)
        self._refresh_actions()

    def _radio(self, text: str, cid: int) -> QRadioButton:
        r = QRadioButton(text)
        self._choice.addButton(r, cid)
        r.toggled.connect(lambda _on: self._refresh_actions())
        self.detail_lay.addWidget(r)
        return r

    # ------------------------------------------------------------ retéléchargement
    def _search_alternatives(self) -> None:
        it = self.current
        if it is None or self._alt_box is None:
            return
        cid = it.track.content_id
        if cid in self._alts:
            self._show_alts(cid)
            return
        self._alts[cid] = None
        self._show_alts(cid)

        def done(found: List[Candidate]) -> None:
            self._alts[cid] = found
            if self.winfo_exists() and self.current is it:
                self._show_alts(cid)

        self.ctrl.find_alternatives(it.track, done)

    def _show_alts(self, cid: int) -> None:
        box = self._alt_box
        if box is None:
            return
        while box.count():
            w = box.takeAt(0).widget()
            if w is not None:
                if isinstance(w, QRadioButton):
                    self._alt_group().removeButton(w)
                w.deleteLater()
        found = self._alts.get(cid)
        if found is None:
            box.addWidget(label(t("diag.alt_searching"), "faint"))
            return
        if not found:
            box.addWidget(label(t("diag.alt_none"), "faint", wrap=True))
            return
        group = self._alt_group()
        for k, c in enumerate(found):
            from . import levels

            exp, _lvl = levels.expected_download(c.track.source, getattr(self.ctrl.settings, "audio_format", "m4a"))
            r = QRadioButton(f"   {c.track.title} — {c.track.artist}  ·  {format_duration(c.track.duration_seconds)}"
                             f"  ·  {exp}")                                  # C42 : qualité attendue
            r.setToolTip(t("dup.expected_tip"))
            group.addButton(r, ALT + k)
            r.toggled.connect(lambda _on: self._refresh_actions())
            box.addWidget(r)
            if k == 0:
                r.setChecked(True)
        self._refresh_actions()

    def _alt_group(self) -> QButtonGroup:
        if not hasattr(self, "_alts_group"):
            self._alts_group = QButtonGroup(self)
        return self._alts_group

    # ------------------------------------------------------------------ actions
    def _choice_id(self) -> int:
        return self._choice.checkedId()

    def _refresh_actions(self) -> None:
        it = self.current
        cid = self._choice_id()
        ok = it is not None and not self._busy and cid >= 0
        if ok and cid // 1000 == DOWNLOAD:
            found = self._alts.get(it.track.content_id)
            ok = bool(found) and self._alt_group().checkedId() >= ALT
        self.apply_btn.setEnabled(bool(ok))
        self.skip_btn.setEnabled(it is not None and not self._busy)
        self.remove_all_btn.setEnabled(not self._busy and any(not i.offline for i in self.items))

    def _skip(self) -> None:
        if self.current is None:
            return
        self._select(min(self.index + 1, len(self.items) - 1) if self.index + 1 < len(self.items) else self.index)

    def _done_current(self) -> None:
        if not self.winfo_exists():
            return
        self._busy = False
        if 0 <= self.index < len(self.items):
            del self.items[self.index]
        self.ctrl.set_diag_count("missing", len(self.items))
        self._fill_list()
        self._select(min(self.index, len(self.items) - 1))

    def _failed(self, exc: Any) -> None:
        self._busy = False
        self.ctrl._on_error(exc)
        if self.winfo_exists():
            self._refresh_actions()

    def _apply(self) -> None:
        it = self.current
        cid = self._choice_id()
        if it is None or cid < 0 or self._busy:
            return
        kind, k = divmod(cid, 1000)
        x = it.track
        if kind == DOWNLOAD:
            found = self._alts.get(x.content_id) or []
            j = self._alt_group().checkedId() - ALT
            if not 0 <= j < len(found):
                return
            if self.ctrl.replace_with_download(found[j].track, [x]) is not None:
                self.ctrl.message("info", t("missing.download_queued", title=found[j].track.title))
                self._done_current()
            return
        self._busy = True
        self._refresh_actions()
        done = lambda _r=None: self._done_current()      # noqa: E731
        if kind == REPLACE:
            self.ctrl.replace_missing(x.content_id, it.candidates[k].content_id, done, self._failed)
        elif kind == RELINK and it.found is not None:
            self.ctrl.relink_missing(x.content_id, Path(it.found), done, self._failed)
        elif kind == REMOVE:
            self.ctrl.remove_missing([x.content_id], done, self._failed)
        else:
            self._busy = False

    def _remove_all(self) -> None:
        from .dialogs import ConfirmDialog

        ids = [i.track.content_id for i in self.items if not i.offline]
        if not ids:
            return

        def go() -> None:
            self._busy = True
            self._refresh_actions()

            def done(_r: Any = None) -> None:
                if not self.winfo_exists():
                    return
                self._busy = False
                self.items = [i for i in self.items if i.offline]
                self.ctrl.set_diag_count("missing", len(self.items))
                self._fill_list()
                self._select(0 if self.items else -1)

            self.ctrl.remove_missing(ids, done, self._failed)

        ConfirmDialog(self, t("missing.remove_all"), plural("missing.remove_all_one", "missing.remove_all_many", len(ids)),
                      go, confirm_text=t("missing.remove_all"), danger=True, detail=t("missing.remove_all_detail"))
