"""« Transférer des playlists » (1.4.2, C23) : page de la fenêtre principale.

Quatre sens (Clé → Ordinateur, Ordinateur → Clé, Clé → autre clé, Synchroniser les deux). Arbre à cases de la
bibliothèque de départ (un dossier coche son contenu, « Tout sélectionner », recherche) ; en synchronisation, un
arbre par côté. « Comparer » ne fait que lire ; la revue montre une ligne par playlist et l'espace nécessaire.
Les playlists présentes des deux côtés demandent un choix (Fusionner / Garder les deux / Garder l'arrivée) :
un choix en haut, obligatoire, rien de présélectionné, modifiable ligne par ligne. Rien n'est écrit avant
« Appliquer ». Le moteur est dans db/transfer.py ; rien n'y est jamais retiré.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHeaderView, QProgressBar, QScrollArea,
                               QStackedWidget, QTreeWidget, QTreeWidgetItem, QWidget)

from ..db import transfer as T
from ..i18n import t
from . import icons, theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label, line_edit, panel, vbox

DIRECTIONS = ("usb2pc", "pc2usb", "usb2usb", "sync")
ACTION_KEYS = {T.MERGE: "transfer.act_merge", T.KEEP_BOTH: "transfer.act_both", T.KEEP_DEST: "transfer.act_keep"}


def human_size(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    return f"{max(0, n) / (1 << 20):.0f} MB"


class _Side(QWidget):
    """Arbre à cases des playlists d'une bibliothèque."""

    def __init__(self, page: "TransferPage") -> None:
        super().__init__()
        self.page = page
        self.end: Optional[Any] = None
        self._token = 0
        lay = vbox(self, spacing=theme.px(4))
        self.title = label("", "h2")
        lay.addWidget(self.title)
        row = hbox(spacing=theme.px(6))
        self.search = line_edit(t("transfer.search"))
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search, 1)
        self.all_btn = button(t("transfer.select_all"), self.select_all, kind="flat")
        self.none_btn = button(t("transfer.select_none"), lambda: self.select_all(False), kind="flat")
        row.addWidget(self.all_btn)
        row.addWidget(self.none_btn)
        lay.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.setMinimumHeight(theme.px(180))
        self.tree.itemChanged.connect(self._changed)
        lay.addWidget(self.tree, 1)
        self.count = label("", "dim")
        lay.addWidget(self.count)
        self._items: Dict[int, QTreeWidgetItem] = {}
        self._kind: Dict[int, Any] = {}
        self._busy = False

    # ------------------------------------------------------------------ chargement
    def load(self, end: Optional[Any], precheck: Tuple[int, ...] = ()) -> None:
        self._token += 1
        token = self._token
        self.end = end
        self.tree.clear()
        self._items.clear()
        self._kind.clear()
        self.title.setText(end.name if end is not None else "")
        self.count.setText(t("transfer.loading") if end is not None else "")
        if end is None:
            self.page._update_setup()
            return

        def ok(playlists: List[Any]) -> None:
            if token == self._token:
                self._fill(playlists, precheck)

        def err(exc: BaseException) -> None:
            if token == self._token:
                self.count.setText(str(exc))
                self.page._update_setup()

        self.page.ctrl.transfer_playlists(end, ok, err)

    def _fill(self, playlists: List[Any], precheck: Tuple[int, ...]) -> None:
        self._busy = True
        kids: Dict[int, List[Any]] = {}
        for p in playlists:
            kids.setdefault(p.parent_id, []).append(p)

        def add(parent_item: Any, parent_id: int, depth: int = 0) -> None:
            if depth > 32:
                return
            for p in sorted(kids.get(parent_id, []), key=lambda p: (not p.is_folder, p.sequence, p.playlist_id)):
                it = QTreeWidgetItem(parent_item)
                self._items[p.playlist_id], self._kind[p.playlist_id] = it, p
                it.setData(0, Qt.UserRole, p.playlist_id)
                if p.is_folder:
                    it.setText(0, p.name)
                    it.setIcon(0, icons.qicon("folder", color=theme.DIM))
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    it.setCheckState(0, Qt.Unchecked)
                    add(it, p.playlist_id, depth + 1)
                    it.setExpanded(True)
                elif p.is_editable:
                    it.setText(0, f"{p.name}  ({p.track_count})")
                    it.setIcon(0, icons.qicon("playlist", color=theme.DIM))
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.Checked if p.playlist_id in precheck else Qt.Unchecked)
                else:                                          # playlist intelligente : jamais copiée
                    it.setText(0, f"{p.name}  ({t('transfer.smart_short')})")
                    it.setIcon(0, icons.qicon("playlist", color=theme.DIM))
                    it.setFlags(Qt.NoItemFlags)
                    it.setToolTip(0, t("transfer.st_smart"))

        add(self.tree.invisibleRootItem(), 0)
        for pid in precheck:                                   # un dossier précoché coche son contenu
            it = self._items.get(pid)
            if it is not None and self._kind[pid].is_folder:
                it.setCheckState(0, Qt.Checked)
        self._busy = False
        self._changed()

    # ------------------------------------------------------------------ sélection
    def checked(self) -> List[int]:
        return [pid for pid, it in self._items.items()
                if self._kind[pid].is_editable and it.checkState(0) == Qt.Checked]

    def select_all(self, on: bool = True) -> None:
        self._busy = True
        for pid, it in self._items.items():
            if self._kind[pid].is_editable and not it.isHidden():
                it.setCheckState(0, Qt.Checked if on else Qt.Unchecked)
        self._busy = False
        self._changed()

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()

        def visit(it: QTreeWidgetItem) -> bool:
            own = needle in it.text(0).lower()
            shown = False
            for i in range(it.childCount()):
                shown = visit(it.child(i)) or shown
            if own and not shown:                              # un dossier trouvé montre tout son contenu
                for i in range(it.childCount()):
                    self._show_all(it.child(i))
            it.setHidden(not (own or shown))
            return own or shown

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            visit(root.child(i))

    def _show_all(self, it: QTreeWidgetItem) -> None:
        it.setHidden(False)
        for i in range(it.childCount()):
            self._show_all(it.child(i))

    def _changed(self, *_a: Any) -> None:
        if self._busy:
            return
        n = len(self.checked())
        self.count.setText(t("transfer.n_checked", n=n))
        self.page._update_setup()


class TransferPage(BaseDialog):
    as_page = True
    modal = False
    back_keeps_page = True

    def __init__(self, parent: Any, controller: Any, precheck: Tuple[int, ...] = ()) -> None:
        super().__init__(parent, t("transfer.title"), 860, 640)
        self.ctrl = controller
        self.ends: List[Any] = []
        self.jobs: List[Tuple[Any, Any, Any]] = []             # (départ, arrivée, Comparison)
        self.results: List[Any] = []
        self.running = False
        self._precheck = tuple(precheck)
        self._rows: List[Tuple[Any, QCheckBox, Optional[QComboBox], Any]] = []
        self.heading(t("transfer.title"), t("transfer.sub"))
        self.pages = QStackedWidget()
        self.body.addWidget(self.pages, 1)
        self._build_setup()
        self._build_review()
        self._build_run()
        self._build_summary()
        self.reload_ends()

    # ================================================================== 1. sélection
    def _build_setup(self) -> None:
        w = QWidget()
        lay = vbox(w, spacing=theme.px(8))
        row = hbox(spacing=theme.px(8))
        row.addWidget(label(t("transfer.direction")))
        self.direction = QComboBox()
        for key in DIRECTIONS:
            self.direction.addItem(t(f"transfer.dir_{key}"), key)
        self.direction.currentIndexChanged.connect(self._direction_changed)
        row.addWidget(self.direction)
        self.from_label = label(t("transfer.from"))
        row.addWidget(self.from_label)
        self.from_box = QComboBox()
        self.from_box.currentIndexChanged.connect(self._ends_changed)
        row.addWidget(self.from_box, 1)
        self.to_label = label(t("transfer.to"))
        row.addWidget(self.to_label)
        self.to_box = QComboBox()
        self.to_box.currentIndexChanged.connect(self._ends_changed)
        row.addWidget(self.to_box, 1)
        lay.addLayout(row)
        self.setup_note = label("", "dim", wrap=True)
        lay.addWidget(self.setup_note)
        trees = hbox(spacing=theme.px(12))
        self.side_a, self.side_b = _Side(self), _Side(self)
        trees.addWidget(self.side_a, 1)
        trees.addWidget(self.side_b, 1)
        lay.addLayout(trees, 1)
        foot = hbox(spacing=theme.px(6))
        self.setup_status = label("", "dim", wrap=True)
        foot.addWidget(self.setup_status, 1)
        self.compare_btn = button(t("transfer.compare"), self.compare, kind="primary")
        self.compare_btn.setToolTip(t("transfer.compare_tip"))
        foot.addWidget(self.compare_btn)
        lay.addLayout(foot)
        self.pages.addWidget(w)
        self.setup_page = w

    def reload_ends(self) -> None:
        """Bibliothèques disponibles ; le sens proposé part de la bibliothèque ouverte."""
        self.ends = list(self.ctrl.transfer_ends())
        usb = [e for e in self.ends if not e.is_local]
        local = [e for e in self.ends if e.is_local]
        ok = {"usb2pc": bool(usb and local), "pc2usb": bool(usb and local), "usb2usb": len(usb) >= 2,
              "sync": len(self.ends) >= 2}
        model = self.direction.model()
        for i, key in enumerate(DIRECTIONS):
            model.item(i).setEnabled(ok[key])
        active = next((e for e in self.ends if e.active), None)
        want = "pc2usb" if (active is not None and active.is_local) else "usb2pc"
        first = next((k for k in (want,) + DIRECTIONS if ok[k]), None)
        self.direction.blockSignals(True)
        self.direction.setCurrentIndex(DIRECTIONS.index(first) if first else 0)
        self.direction.blockSignals(False)
        self._possible = first is not None
        self._direction_changed()

    def direction_key(self) -> str:
        return self.direction.currentData() or DIRECTIONS[0]

    def _direction_changed(self, *_a: Any) -> None:
        key = self.direction_key()
        usb = [e for e in self.ends if not e.is_local]
        local = [e for e in self.ends if e.is_local]
        froms = {"usb2pc": usb, "pc2usb": local, "usb2usb": usb, "sync": self.ends}[key]
        tos = {"usb2pc": local, "pc2usb": usb, "usb2usb": usb, "sync": self.ends}[key]
        active = next((e for e in self.ends if e.active), None)
        for box, ends, prefer in ((self.from_box, froms, True), (self.to_box, tos, False)):
            box.blockSignals(True)
            box.clear()
            for e in ends:
                box.addItem(e.name, e.key)
            if active is not None and active in ends and (prefer or key != "usb2usb"):
                box.setCurrentIndex(ends.index(active))
            box.blockSignals(False)
        if key in ("usb2usb", "sync") and self.from_box.currentData() == self.to_box.currentData():
            other = next((i for i in range(self.to_box.count())
                          if self.to_box.itemData(i) != self.from_box.currentData()), -1)
            if other >= 0:
                self.to_box.setCurrentIndex(other)
        self.from_label.setText(t("transfer.between") if key == "sync" else t("transfer.from"))
        self.to_label.setText(t("transfer.and") if key == "sync" else t("transfer.to"))
        self.side_b.setVisible(key == "sync")
        self._ends_changed()

    def _end(self, box: QComboBox) -> Optional[Any]:
        return next((e for e in self.ends if e.key == box.currentData()), None)

    def _ends_changed(self, *_a: Any) -> None:
        a, b = self._end(self.from_box), self._end(self.to_box)
        sync = self.direction_key() == "sync"
        pre = self._precheck
        self.side_a.load(a, pre if (a is not None and a.active) else ())
        self.side_b.load(b if sync else None, pre if (sync and b is not None and b.active) else ())
        self._update_setup()

    def _update_setup(self) -> None:
        if not hasattr(self, "compare_btn"):
            return
        a, b = self._end(self.from_box), self._end(self.to_box)
        sync = self.direction_key() == "sync"
        problem = ""
        if not getattr(self, "_possible", True):
            problem = t("transfer.need_two")
        elif a is None or b is None or a.key == b.key:
            problem = t("transfer.same_ends")
        n = len(self.side_a.checked()) + (len(self.side_b.checked()) if sync else 0)
        self.setup_note.setText(t("transfer.note_sync") if sync else t("transfer.note_oneway"))
        self.setup_status.setText(problem or (t("transfer.n_checked", n=n) if n else t("transfer.check_some")))
        self.compare_btn.setEnabled(not problem and n > 0 and not self.running)

    # ================================================================== 2. Comparer → revue
    def compare(self) -> None:
        a, b = self._end(self.from_box), self._end(self.to_box)
        if a is None or b is None or a.key == b.key:
            return
        jobs = [(a, b, self.side_a.checked())]
        if self.direction_key() == "sync":
            jobs.append((b, a, self.side_b.checked()))
        jobs = [j for j in jobs if j[2]]
        if not jobs:
            return
        self.compare_btn.setEnabled(False)
        self.setup_status.setText(t("transfer.comparing"))

        def ok(comps: List[Any]) -> None:
            self.jobs = [(ja, jb, comp) for (ja, jb, _ids), comp in zip(jobs, comps)]
            self._show_review()

        def err(exc: BaseException) -> None:
            self.setup_status.setText(str(exc))
            self.compare_btn.setEnabled(True)

        def progress(i: int, n: int, name: str) -> None:
            self.setup_status.setText(t("transfer.comparing_n", i=i, n=n, name=name))

        self.ctrl.transfer_compare(jobs, ok, err, progress)

    def _build_review(self) -> None:
        w = QWidget()
        lay = vbox(w, spacing=theme.px(8))
        self.review_title = label("", "h2")
        lay.addWidget(self.review_title)
        self.choice_box = panel()
        row = hbox(self.choice_box, margins=theme.px(10), spacing=theme.px(8))
        self.choice_label = label(t("transfer.choice"), wrap=True)
        row.addWidget(self.choice_label, 1)
        self.choice = QComboBox()
        self.choice.addItem(t("transfer.choose"), "")
        for action in T.ACTIONS:
            self.choice.addItem(t(ACTION_KEYS[action]), action)
            self.choice.setItemData(self.choice.count() - 1, t(ACTION_KEYS[action] + "_tip"), Qt.ToolTipRole)
        self.choice.currentIndexChanged.connect(self._global_choice)
        row.addWidget(self.choice)
        lay.addWidget(self.choice_box)
        self.table = QTreeWidget()
        self.table.setColumnCount(3)
        self.table.setHeaderLabels([t("transfer.col_playlist"), t("transfer.col_state"), t("transfer.col_action")])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setRootIsDecorated(True)
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.header().setStretchLastSection(False)
        self.table.itemChanged.connect(self._line_toggled)
        lay.addWidget(self.table, 1)
        self.review_info = label("", "dim", wrap=True)
        lay.addWidget(self.review_info)
        self.review_warn = label("", "warn", wrap=True)
        lay.addWidget(self.review_warn)
        foot = hbox(spacing=theme.px(6))
        foot.addWidget(button(t("transfer.back_select"), self._back_to_setup, icon="back"))
        foot.addStretch(1)
        self.apply_btn = button(t("transfer.apply"), self.apply, kind="primary", icon="check")
        foot.addWidget(self.apply_btn)
        lay.addLayout(foot)
        self.pages.addWidget(w)
        self.review_page = w

    def _state_text(self, line: Any) -> str:
        if line.status == T.SMART:
            return t("transfer.st_smart")
        if line.status == T.SAME:
            return t("transfer.st_same_more", n=line.dst_only) if line.dst_only else t("transfer.st_same")
        if line.status == T.NEW:
            text = t("transfer.st_new", n=line.add)
            if line.case_clash:
                text += " · " + t("transfer.st_case", name=line.case_clash)
            return text
        return t("transfer.st_merge", n=line.add, common=line.common)

    def _show_review(self) -> None:
        self.table.blockSignals(True)
        self.table.clear()
        self._rows = []
        conflicts = 0
        for a, b, comp in self.jobs:
            head = QTreeWidgetItem(self.table, [t("transfer.job", src=a.name, dst=b.name), "", ""])
            font = head.font(0)
            font.setBold(True)
            head.setFont(0, font)
            head.setFlags(Qt.ItemIsEnabled)
            for line in comp.lines:
                it = QTreeWidgetItem(head, [" / ".join(line.path), self._state_text(line), ""])
                it.setData(0, Qt.UserRole, len(self._rows))
                combo: Optional[QComboBox] = None
                if line.selectable:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.Checked if line.selected else Qt.Unchecked)
                else:
                    it.setFlags(Qt.NoItemFlags)
                if line.status == T.CONFLICT:
                    conflicts += 1
                    combo = QComboBox()
                    combo.addItem(t("transfer.choose"), "")
                    for action in T.ACTIONS:
                        combo.addItem(t(ACTION_KEYS[action]), action)
                    combo.setCurrentIndex(max(0, combo.findData(line.action)))
                    combo.currentIndexChanged.connect(lambda _i, ln=line, c=combo: self._line_choice(ln, c))
                    self.table.setItemWidget(it, 2, combo)
                    for name in line.add_names:                # détail dépliable : sons ajoutés par une fusion
                        sub = QTreeWidgetItem(it, ["+ " + name, "", ""])
                        sub.setFlags(Qt.ItemIsEnabled)
                self._rows.append((line, it, combo, comp))
            head.setExpanded(True)
        self.table.blockSignals(False)
        self.choice_box.setVisible(conflicts > 0)
        self.choice.blockSignals(True)
        self.choice.setCurrentIndex(0)                         # rien de présélectionné
        self.choice.blockSignals(False)
        self.choice_label.setText(t("transfer.choice", n=conflicts))
        self.review_title.setText(t("transfer.review_title"))
        self.pages.setCurrentWidget(self.review_page)
        self._update_review()

    def _global_choice(self, *_a: Any) -> None:
        action = self.choice.currentData()
        if not action:
            return
        for line, _it, combo, _comp in self._rows:
            if combo is not None:
                line.action = action
                combo.blockSignals(True)
                combo.setCurrentIndex(combo.findData(action))
                combo.blockSignals(False)
        self._update_review()

    def _line_choice(self, line: Any, combo: QComboBox) -> None:
        line.action = combo.currentData() or ""
        self._update_review()

    def _line_toggled(self, it: QTreeWidgetItem, _col: int) -> None:
        idx = it.data(0, Qt.UserRole)
        if idx is None or not (0 <= idx < len(self._rows)):
            return
        line = self._rows[idx][0]
        if line.selectable:
            line.selected = it.checkState(0) == Qt.Checked
            self._update_review()

    def _update_review(self) -> None:
        parts: List[str] = []
        warn: List[str] = []
        writes = 0
        for a, b, comp in self.jobs:
            lines = [ln for ln in comp.lines if ln.will_write]
            writes += len(lines)
            new = sum(1 for ln in lines if ln.status == T.NEW or ln.action == T.KEEP_BOTH)
            merged = sum(1 for ln in lines if ln.status == T.CONFLICT and ln.action == T.MERGE)
            need = comp.needed()
            parts.append(t("transfer.sum_job", dst=b.name, new=new, merged=merged, copy=comp.tracks_to_copy(),
                           size=human_size(need), free=human_size(comp.free)))
            if not comp.enough_space:
                warn.append(t("transfer.no_space", dst=b.name, size=human_size(need), free=human_size(comp.free)))
            if b.is_local and lines and self._rekordbox_open():
                warn.append(t("transfer.rekordbox_open"))
        missing = sum(comp.missing_choices for _a, _b, comp in self.jobs)
        if missing:
            warn.append(t("transfer.choice_missing", n=missing))
        if len(self.jobs) == 2 and any(ln.status == T.CONFLICT and ln.action == T.MERGE
                                       for _a, _b, comp in self.jobs for ln in comp.lines):
            parts.append(t("transfer.order_note"))
        parts.append(t("transfer.nothing_removed"))
        self.review_info.setText("\n".join(parts))
        self.review_warn.setText("\n".join(warn))
        self.review_warn.setVisible(bool(warn))
        blocked = any(not comp.enough_space for _a, _b, comp in self.jobs) \
            or any(b.is_local and self._rekordbox_open() and any(ln.will_write for ln in comp.lines)
                   for _a, b, comp in self.jobs)
        self.apply_btn.setEnabled(writes > 0 and not missing and not blocked and not self.running)

    def _rekordbox_open(self) -> bool:
        try:
            from ..db.local_library import rekordbox_running

            return bool(rekordbox_running())
        except Exception:  # noqa: BLE001
            return False

    def _back_to_setup(self) -> None:
        self.jobs = []
        self.pages.setCurrentWidget(self.setup_page)
        self._update_setup()

    # ================================================================== 3. Appliquer
    def _build_run(self) -> None:
        w = QWidget()
        lay = vbox(w, spacing=theme.px(10))
        lay.addStretch(1)
        self.run_title = label(t("transfer.running"), "h2")
        lay.addWidget(self.run_title)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.run_detail = label("", "dim", wrap=True)
        lay.addWidget(self.run_detail)
        row = hbox()
        row.addStretch(1)
        self.stop_btn = button(t("transfer.stop"), self.stop, icon="stop")
        self.stop_btn.setToolTip(t("transfer.stop_tip"))
        row.addWidget(self.stop_btn)
        lay.addLayout(row)
        lay.addStretch(2)
        self.pages.addWidget(w)
        self.run_page = w

    def apply(self) -> None:
        jobs = [(a, b, comp) for a, b, comp in self.jobs if any(ln.will_write for ln in comp.lines)]
        if not jobs or any(comp.missing_choices for _a, _b, comp in jobs):
            return
        self.bar.setRange(0, 0)
        self.run_detail.setText("")
        self.stop_btn.setEnabled(True)
        self.run_title.setText(t("transfer.running"))

        def ok(results: List[Any]) -> None:
            self.running = False
            self.results = results
            self._show_summary(jobs, results)

        def err(exc: BaseException) -> None:
            self.running = False
            self._show_summary(jobs, [], str(exc))

        def progress(i: int, n: int, title: str) -> None:
            self.bar.setRange(0, max(1, n))
            self.bar.setValue(i)
            self.run_detail.setText(t("transfer.progress", i=i, n=n, title=title))

        if not self.ctrl.transfer_apply(jobs, ok, err, progress):
            self.ctrl.message("info", t("msg.tool_busy"))
            return
        self.running = True
        self.pages.setCurrentWidget(self.run_page)

    def stop(self) -> None:
        self.ctrl.transfer_stop()
        self.stop_btn.setEnabled(False)
        self.run_title.setText(t("transfer.stopping"))

    # ================================================================== 4. résumé
    def _build_summary(self) -> None:
        w = QWidget()
        lay = vbox(w, spacing=theme.px(8))
        self.sum_title = label("", "h2")
        lay.addWidget(self.sum_title)
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = vbox(inner, margins=theme.px(4))
        self.sum_text = label("", wrap=True)
        self.sum_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        inner_lay.addWidget(self.sum_text)
        inner_lay.addStretch(1)
        area.setWidget(inner)
        lay.addWidget(area, 1)
        foot = hbox(spacing=theme.px(6))
        foot.addWidget(button(t("transfer.again"), self._again, icon="back"))
        foot.addStretch(1)
        foot.addWidget(button(t("action.close"), self.close, kind="primary"))
        lay.addLayout(foot)
        self.pages.addWidget(w)
        self.summary_page = w

    def summary_lines(self, jobs: List[Tuple[Any, Any, Any]], results: List[Any], error: str = "") -> List[str]:
        out: List[str] = []
        if error:
            out.append(t("transfer.failed", error=error))
        for (a, b, _comp), res in zip(jobs, results):
            out.append(t("transfer.job", src=a.name, dst=b.name))
            out.append("  " + t("transfer.res_playlists", created=res.created, merged=res.merged, folders=res.folders))
            out.append("  " + t("transfer.res_tracks", copied=res.copied, reused=res.reused, added=res.added))
            if res.different:
                out.append("  " + t("transfer.res_different", n=res.different))
            if res.failed:
                out.append("  " + t("transfer.res_failed", n=res.failed))
            for r in res.lines:
                if r.name:
                    out.append("  " + t("transfer.res_renamed", old=" / ".join(r.path), new=r.name))
            for problem in res.problems[:20]:
                out.append("    - " + problem)
            if res.stopped:
                out.append("  " + t("transfer.res_stopped"))
            if res.restore_point and not b.is_local:
                out.append("  " + t("transfer.res_restore_usb", dst=b.name))
            elif b.is_local and res.done:
                out.append("  " + t("transfer.res_restore_local"))
            if res.pdb_state and res.pdb_state not in ("ok", "off", "absent"):
                out.append("  " + t("transfer.res_pdb", state=res.pdb_state))
        if len(results) < len(jobs) and not error:
            out.append(t("transfer.res_stopped"))
        return out

    def _show_summary(self, jobs: List[Tuple[Any, Any, Any]], results: List[Any], error: str = "") -> None:
        stopped = any(r.stopped for r in results) or (len(results) < len(jobs) and not error)
        self.sum_title.setText(t("transfer.failed_title") if error else
                               t("transfer.stopped_title") if stopped else t("transfer.done_title"))
        self.sum_text.setText("\n".join(self.summary_lines(jobs, results, error)))
        self.pages.setCurrentWidget(self.summary_page)
        if error:
            self.ctrl.message("error", t("transfer.failed", error=error))
        else:
            self.ctrl.message("ok", t("transfer.done_msg", n=sum(r.done for r in results)))

    def _again(self) -> None:
        self.jobs, self.results = [], []
        self._precheck = ()
        self.reload_ends()
        self.pages.setCurrentWidget(self.setup_page)


def open_transfer(parent: Any, controller: Any, precheck: Tuple[int, ...] = ()) -> Optional[TransferPage]:
    """Ouvre la page (ou y revient si un transfert est en cours ou en revue)."""
    win = parent.window() if parent is not None else None
    if win is not None and hasattr(win, "reopen_dialog_page"):
        page = win.reopen_dialog_page(TransferPage)
        if page is not None:
            return page
    page = TransferPage(parent, controller, precheck)
    page.show_dialog()
    return page
