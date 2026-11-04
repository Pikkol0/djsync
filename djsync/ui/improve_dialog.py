"""Onglet « Améliorer » du Diagnostic (1.4.0, C47) : les sons de qualité insuffisante, la meilleure
version trouvée pour chacun et le gain ; remplacer un son, une sélection, ou tout ce qui est sûr (sans
perte, même durée), après confirmation. Liens « Acheter » pour ceux sans version gratuite."""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtWidgets import QCheckBox

from ..i18n import plural, t
from . import theme
from .diag_tabs import add_tabs
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import Column, Row, TrackTable, button, hbox, label


class ImproveDialog(BaseDialog):
    as_page = True
    modal = False

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("diagtab.improve"), 960, 580)
        self.ctrl = controller
        self.weaks: Dict[str, Any] = {}
        self._queue: List[str] = []
        self._searching = False
        add_tabs(self, controller, "improve")

        head = hbox()
        head.addWidget(label(t("improve.title"), "h2"))
        head.addStretch(1)
        self.count = label(t("improve.scanning"), "dim")
        head.addWidget(self.count)
        self.lossless_only = QCheckBox(t("improve.lossless_only"))
        self.lossless_only.toggled.connect(lambda _on: self._scan())
        head.addWidget(self.lossless_only)
        self.body.addLayout(head)
        self.body.addWidget(label(t("improve.intro", kbps=controller.settings.improve_threshold), "faint", wrap=True))

        cols = [Column("title", t("track.title"), 240, stretch=True, min_width=140),
                Column("artist", t("track.artist"), 160, priority=2),
                Column("now", t("improve.now"), 110),
                Column("found", t("improve.found"), 260, priority=1),
                Column("gain", t("improve.gain"), 150)]
        self.table = TrackTable(self, cols)
        self.table.set_empty("search", t("improve.empty"))
        self.table.on_select = lambda _ids: self._refresh()
        self.table.menu_builder = self._menu
        self.body.addWidget(self.table, 1)

        bar = hbox()
        self.search_btn = button(t("improve.search"), self._search_selected, icon="search")
        bar.addWidget(self.search_btn)
        self.search_all_btn = button("", self._search_all, kind="flat", icon="search")
        bar.addWidget(self.search_all_btn)
        bar.addStretch(1)
        self.sure_btn = button("", self._apply_sure, icon="check")
        self.sure_btn.setToolTip(t("improve.sure_tip"))
        bar.addWidget(self.sure_btn)
        self.apply_btn = button(t("improve.apply"), self._apply_selected, kind="primary", icon="download")
        bar.addWidget(self.apply_btn)
        self.body.addLayout(bar)
        self.show_dialog()
        self._scan()

    # ------------------------------------------------------------------ données
    def _scan(self) -> None:
        self.count.setText(t("improve.scanning"))
        self.table.show_skeleton()

        def progress(i: int, n: int) -> None:
            if self.winfo_exists():
                self.count.setText(t("diag.progress", i=i, n=n))

        def done(weaks: List[Any]) -> None:
            if not self.winfo_exists():
                return
            self.weaks = {str(w.track.content_id): w for w in weaks}
            self.ctrl.set_diag_count("improve", len(weaks))
            self._fill()

        self.ctrl.improve_scan(done, progress, lossless_only=self.lossless_only.isChecked())

    def _row(self, w: Any) -> Row:
        from ..core.improve import label_of

        best = w.best
        found = (f"{best.source_label} · {best.artist} – {best.title}" if best is not None
                 else (t("improve.none") if w.searched else ""))
        values = {"title": w.track.title, "artist": w.track.artist or "", "now": label_of(w.info), "found": found,
                  "gain": w.gain}
        if w.gain:
            values["gain__color"] = theme.GOLD if "→ FLAC" in w.gain or "→ WAV" in w.gain or "→ AIFF" in w.gain \
                else theme.GOOD
        return Row(str(w.track.content_id), values, (), w)

    def _fill(self) -> None:
        self.table.set_rows([self._row(w) for w in self.weaks.values()], keep_selection=True)
        self._refresh()

    def _refresh(self) -> None:
        from ..core.improve import sure

        searched = sum(1 for w in self.weaks.values() if w.searched)
        found = sum(1 for w in self.weaks.values() if w.best is not None)
        todo = sum(1 for w in self.weaks.values() if not w.searched)
        self.count.setText(t("improve.count", n=len(self.weaks), searched=searched, found=found))
        self.search_all_btn.setText(t("improve.search_all", n=todo))
        self.search_all_btn.setEnabled(bool(todo) and not self._searching)
        n_sure = sum(1 for w in self.weaks.values() if sure(w))
        self.sure_btn.setText(t("improve.apply_sure", n=n_sure))
        self.sure_btn.setEnabled(bool(n_sure))
        sel = self._selected()
        self.apply_btn.setEnabled(any(w.best is not None for w in sel))
        self.search_btn.setEnabled(bool(sel))

    def _selected(self) -> List[Any]:
        return [self.weaks[i] for i in self.table.selected_iids() if i in self.weaks]

    # ------------------------------------------------------------------ recherche (un son à la fois)
    def _search_selected(self) -> None:
        self._enqueue([str(w.track.content_id) for w in self._selected()])

    def _search_all(self) -> None:
        self._enqueue([k for k, w in self.weaks.items() if not w.searched])

    def _enqueue(self, keys: List[str]) -> None:
        self._queue += [k for k in keys if k not in self._queue]
        self._next()

    def _next(self) -> None:
        if self._searching or not self._queue or not self.winfo_exists():
            self._refresh()
            return
        key = self._queue.pop(0)
        w = self.weaks.get(key)
        if w is None:
            self._next()
            return
        self._searching = True
        self.table.update_values(key, found=t("improve.searching"))

        def done(weak: Any) -> None:
            self._searching = False
            if not self.winfo_exists():
                return
            row = self._row(weak)
            self.table.update_values(key, **row.values)
            self._next()

        self.ctrl.improve_search(w, done)
        self._refresh()

    # ------------------------------------------------------------------ remplacement (validé)
    def _confirm(self, weaks: List[Any]) -> None:
        weaks = [w for w in weaks if w.best is not None]
        if not weaks:
            return
        detail = "\n".join(f"• {w.track.title} : {w.gain}" for w in weaks[:12]) + ("\n…" if len(weaks) > 12 else "")

        def go() -> None:
            n = self.ctrl.improve_apply(weaks)
            for w in weaks[:n]:
                self.weaks.pop(str(w.track.content_id), None)
            self._fill()

        ConfirmDialog(self, t("improve.confirm_title"),
                      plural("improve.confirm_one", "improve.confirm_many", len(weaks)), go,
                      confirm_text=t("improve.apply"), detail=detail)

    def _apply_selected(self) -> None:
        self._confirm(self._selected())

    def _apply_sure(self) -> None:
        from ..core.improve import sure

        self._confirm([w for w in self.weaks.values() if sure(w)])

    def _menu(self, iids: List[str]) -> list:
        sel = [self.weaks[i] for i in iids if i in self.weaks]
        if not sel:
            return []
        entries: list = [(t("improve.search"), lambda: self._enqueue([str(w.track.content_id) for w in sel]), "search")]
        if any(w.best is not None for w in sel):
            entries.append((t("improve.apply"), lambda: self._confirm(sel), "download"))
        if len(sel) == 1:
            from .views.common import buy_entry

            entries += [None, buy_entry(self.ctrl, sel[0].track.artist or "", sel[0].track.title)]
        entries.append((t("improve.hide"), lambda: self._hide(sel), "close"))
        return entries

    def _hide(self, sel: List[Any]) -> None:
        for w in sel:
            self.weaks.pop(str(w.track.content_id), None)
        self._fill()
