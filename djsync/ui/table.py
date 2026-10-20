"""TrackTable : tableau Qt (QTableView + modèle maison), sans fioriture.

Tri par clic sur l'en-tête (croissant, décroissant, ordre d'origine), filtre texte + filtre
« métier » (`row_filter`), réordonnancement par glisser-déposer ou Haut/Bas, glisser des lignes
vers un autre widget (playlists), colonnes cliquables (cases, téléchargement), menu contextuel,
colonnes secondaires masquées quand la place manque. La colonne « key » est peinte à la couleur
Camelot de la tonalité. Aucune logique métier : les vues fournissent des `Row`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QByteArray, QMimeData, QModelIndex, QPoint, Qt
from PySide6.QtGui import QColor, QDrag
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QLabel, QMenu, QTableView

from ..i18n import t
from . import theme

MIME_IDS = "application/x-djsync-ids"
MenuEntry = Optional[Tuple[str, Callable[[], None]]]      # None = séparateur
ALIGN = {"w": Qt.AlignLeft | Qt.AlignVCenter, "e": Qt.AlignRight | Qt.AlignVCenter, "center": Qt.AlignCenter}


@dataclass
class Column:
    key: str
    title: str
    width: int = 120
    anchor: str = "w"
    stretch: bool = False
    sortable: bool = True
    sort: Optional[Callable[["Row"], Any]] = None   # clé de tri (défaut : la valeur affichée)
    min_width: int = 40
    on_header: Optional[Callable[[], None]] = None  # clic sur l'en-tête (ex. tout cocher)
    priority: int = 0                                # 0 = toujours visible ; plus grand = masqué d'abord


@dataclass
class Row:
    iid: str
    values: Dict[str, Any]
    tags: Tuple[str, ...] = ()
    data: Any = None

    def search_text(self) -> str:
        return " ".join(str(v) for v in self.values.values()).lower()


def _sort_value(row: Row, col: Column) -> Tuple[int, Any]:
    value = col.sort(row) if col.sort else row.values.get(col.key)
    if value is None or value == "":
        return (1, 0)  # les vides vont toujours à la fin
    return (0, value.lower() if isinstance(value, str) else value)


def camelot_sort(row: Row) -> Any:
    code = row.values.get("key") or ""
    try:
        return (int(code[:-1]), code[-1])
    except (ValueError, IndexError):
        return None


class _Model(QAbstractTableModel):
    def __init__(self, table: "TrackTable") -> None:
        super().__init__()
        self.table = table

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:          # noqa: N802 (API Qt)
        return 0 if parent.isValid() else len(self.table._shown)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:       # noqa: N802
        return 0 if parent.isValid() else len(self.table.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if orientation != Qt.Horizontal or not 0 <= section < len(self.table.columns):
            return None
        col = self.table.columns[section]
        if role == Qt.DisplayRole:
            mark = ""
            if col.key == self.table._sort_key:
                mark = " ▼" if self.table._sort_desc else " ▲"
            return col.title + mark
        if role == Qt.TextAlignmentRole:
            return int(ALIGN.get(col.anchor, ALIGN["w"]))
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self.table._rows.get(self.table._shown[index.row()])
        col = self.table.columns[index.column()]
        if row is None:
            return None
        if role == Qt.DisplayRole:
            v = row.values.get(col.key, "")
            return "" if v is None else str(v)
        if role == Qt.TextAlignmentRole:
            return int(ALIGN.get(col.anchor, ALIGN["w"]))
        if col.key == "key" and row.values.get("key"):
            color = theme.camelot_color(row.values["key"])
            if role == Qt.BackgroundRole:
                return QColor(color)
            if role == Qt.ForegroundRole:
                return QColor(theme.on_color(color))
        if role == Qt.ForegroundRole:
            if col.key == "dl":
                return QColor(theme.ACCENT)
            for tag, color in (("err", theme.ERR), ("dup", theme.WARN), ("playing", theme.ACCENT),
                               ("ok", theme.ACCENT), ("dim", theme.DIM)):
                if tag in row.tags:
                    return QColor(color)
        if role == Qt.ToolTipRole and col.key == "dl":
            return t("action.download")
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.isValid():
            base |= Qt.ItemIsDragEnabled
        return base

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()


class TrackTable(QTableView):
    def __init__(self, parent: Any, columns: Sequence[Column], loader: Any = None, show_covers: bool = False,
                 selectmode: str = "extended", reorderable: bool = False, click_columns: Sequence[str] = (),
                 badges: bool = False) -> None:
        super().__init__(parent)
        self.columns = list(columns)
        self.reorderable = reorderable
        self.drag_out = False
        self._click_cols = set(click_columns)
        self.on_select: Optional[Callable[[List[str]], None]] = None
        self.on_double: Optional[Callable[[str], None]] = None
        self.on_cell_click: Optional[Callable[[str, str], None]] = None
        self.on_reordered: Optional[Callable[[], None]] = None
        self.on_sort_changed: Optional[Callable[[Optional[str], bool], None]] = None
        self.menu_builder: Optional[Callable[[List[str]], List[MenuEntry]]] = None
        self.row_filter: Optional[Callable[[Row], bool]] = None
        self.on_delete: Optional[Callable[[], None]] = None

        self._rows: Dict[str, Row] = {}
        self._order: List[str] = []
        self._shown: List[str] = []
        self._filter = ""
        self._sort_key: Optional[str] = None
        self._sort_desc = False
        self._wanted: List[str] = [c.key for c in self.columns]
        self._auto_hidden: set = set()
        self._press: Optional[QPoint] = None
        self._empty_title = ""
        self._empty_sub = ""

        self._model = _Model(self)
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection if selectmode == "browse"
                              else QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.verticalHeader().hide()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setAcceptDrops(True)
        self.setDragEnabled(False)            # glisser géré à la main (identifiants des lignes)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context)
        head = self.horizontalHeader()
        head.setSectionsClickable(True)
        head.setHighlightSections(False)
        head.setStretchLastSection(False)
        head.sectionClicked.connect(self._heading_clicked)
        self.doubleClicked.connect(self._double)
        self.selectionModel().selectionChanged.connect(lambda *_: self._selected())
        self._empty = QLabel(self.viewport())
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setProperty("role", "dim")
        self.apply_metrics()

    # ------------------------------------------------------------------ échelle
    def apply_metrics(self) -> None:
        """Hauteur de ligne et largeurs au zoom courant (appelé aussi après un changement de zoom)."""
        h = self.fontMetrics().height()
        self.verticalHeader().setDefaultSectionSize(int(h * 1.7))
        self._fit_columns()

    on_scale = apply_metrics

    # --------------------------------------------------------- colonnes adaptatives
    def set_display_columns(self, keys: Sequence[str]) -> None:
        self._wanted = list(keys)
        self._fit_columns()

    def resizeEvent(self, e: Any) -> None:       # noqa: N802
        super().resizeEvent(e)
        self._fit_columns()
        self._place_empty()

    def _width(self, col: Column) -> int:
        """Largeur d'une colonne fixe : celle demandée au zoom courant, au moins son titre en entier."""
        fm = self.horizontalHeader().fontMetrics()
        title = fm.horizontalAdvance(col.title) + theme.px(18)
        return max(theme.px(col.min_width if col.stretch else col.width), title)

    def _fit_columns(self) -> None:
        avail = self.viewport().width()
        cols = {c.key: c for c in self.columns}
        shown = [k for k in self._wanted if k in cols]
        need = sum(self._width(cols[k]) for k in shown)
        hidden: set = set()
        for col in sorted((cols[k] for k in shown if cols[k].priority > 0), key=lambda c: -c.priority):
            if need <= avail:
                break
            hidden.add(col.key)
            need -= self._width(col)
        self._auto_hidden = hidden
        visible = [k for k in shown if k not in hidden]
        head = self.horizontalHeader()
        for i, col in enumerate(self.columns):
            hide = col.key not in visible
            self.setColumnHidden(i, hide)
            if hide:
                continue
            if col.stretch:
                head.setSectionResizeMode(i, QHeaderView.Stretch)
            else:
                head.setSectionResizeMode(i, QHeaderView.Interactive)
                self.setColumnWidth(i, self._width(col))

    @property
    def hidden_columns(self) -> set:
        return set(self._auto_hidden)

    # ------------------------------------------------------------------ données
    def set_rows(self, rows: Sequence[Row], reset_sort: bool = False, keep_selection: bool = True) -> None:
        selected = set(self.selected_iids()) if keep_selection else set()
        top = self.verticalScrollBar().value() if keep_selection else 0
        self._rows = {r.iid: r for r in rows}
        self._order = [r.iid for r in rows]
        if reset_sort:
            self._sort_key, self._sort_desc = None, False
        self._rebuild(selected, top)

    def show_skeleton(self, n: int = 8) -> None:
        """Chargement : le tableau est vidé et indique « Loading… » (plus de lignes factices)."""
        self._rows, self._order, self._shown = {}, [], []
        self._model.refresh()
        self._show_empty(t("common.loading"), "")

    def row(self, iid: str) -> Optional[Row]:
        return self._rows.get(iid)

    def _index_of(self, iid: str) -> int:
        try:
            return self._shown.index(iid)
        except ValueError:
            return -1

    def update_values(self, iid: str, **values: Any) -> None:
        row = self._rows.get(iid)
        if row is None:
            return
        row.values.update(values)
        r = self._index_of(iid)
        if r >= 0:
            self._model.dataChanged.emit(self._model.index(r, 0), self._model.index(r, len(self.columns) - 1))

    def set_tags(self, iid: str, *tags: str) -> None:
        row = self._rows.get(iid)
        if row is None:
            return
        row.tags = tuple(tags)
        self.update_values(iid)

    def refresh_cover(self, iid: str) -> None:
        self.update_values(iid)

    @property
    def count(self) -> int:
        return len(self._shown)

    @property
    def total(self) -> int:
        return len(self._rows)

    def selected_iids(self) -> List[str]:
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        return [self._shown[r] for r in rows if 0 <= r < len(self._shown)]

    def selected_rows(self) -> List[Row]:
        return [self._rows[i] for i in self.selected_iids()]

    def displayed_iids(self) -> List[str]:
        return list(self._shown)

    def displayed_rows(self) -> List[Row]:
        return [self._rows[i] for i in self._shown]

    def all_rows(self) -> List[Row]:
        return [self._rows[i] for i in self._order]

    def select(self, iids: Sequence[str]) -> None:
        sm = self.selectionModel()
        sm.clearSelection()
        first = None
        for iid in iids:
            r = self._index_of(iid)
            if r >= 0:
                sm.select(self._model.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
                first = r if first is None else first
        if first is not None:
            self.scrollTo(self._model.index(first, 0))
            sm.setCurrentIndex(self._model.index(first, 0), QItemSelectionModel.NoUpdate)

    def select_all(self) -> None:
        self.selectAll()

    def clear(self) -> None:
        self.set_rows([])

    def set_empty(self, icon: str, title: str, sub: str = "", action: Any = None) -> None:
        self._empty_title, self._empty_sub = title, sub
        self._update_empty()

    def set_empty_text(self, text: str) -> None:
        self.set_empty("", text)

    # ------------------------------------------------------------- filtre / tri
    def set_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        if text != self._filter:
            self._filter = text
            self._rebuild(set(self.selected_iids()), 0)

    def refilter(self) -> None:
        self._rebuild(set(self.selected_iids()), 0)

    @property
    def filter_active(self) -> bool:
        return bool(self._filter) or self.row_filter is not None

    @property
    def sort_active(self) -> bool:
        return self._sort_key is not None

    @property
    def can_reorder(self) -> bool:
        return self.reorderable and not self.filter_active

    def set_sort(self, key: Optional[str], descending: bool = False) -> None:
        self._sort_key, self._sort_desc = key, descending
        self._rebuild(set(self.selected_iids()), 0)

    def _column(self, key: Optional[str]) -> Optional[Column]:
        return next((c for c in self.columns if c.key == key), None)

    def column_index(self, key: str) -> int:
        return next(i for i, c in enumerate(self.columns) if c.key == key)

    def _heading_clicked(self, section: int) -> None:
        col = self.columns[section]
        if col.on_header:
            col.on_header()
            return
        if not col.sortable:
            return
        if self._sort_key != col.key:
            self._sort_key, self._sort_desc = col.key, False
        elif not self._sort_desc:
            self._sort_desc = True
        else:
            self._sort_key, self._sort_desc = None, False
        self._rebuild(set(self.selected_iids()), 0)
        if self.on_sort_changed:
            self.on_sort_changed(self._sort_key, self._sort_desc)

    def _freeze_sort(self) -> None:
        """Le tri affiché devient l'ordre manuel (point de départ d'un réordonnancement)."""
        if self._sort_key is not None and not self.filter_active:
            self._order = list(self._shown)
            self._sort_key, self._sort_desc = None, False
            if self.on_sort_changed:
                self.on_sort_changed(None, False)

    def _visible_order(self) -> List[str]:
        ids = self._order
        if self.row_filter is not None:
            ids = [i for i in ids if self.row_filter(self._rows[i])]
        if self._filter:
            ids = [i for i in ids if self._filter in self._rows[i].search_text()]
        col = self._column(self._sort_key)
        if col is not None:
            present = [i for i in ids if _sort_value(self._rows[i], col)[0] == 0]
            empty = [i for i in ids if _sort_value(self._rows[i], col)[0] == 1]
            present.sort(key=lambda i: _sort_value(self._rows[i], col), reverse=self._sort_desc)
            ids = present + empty
        return list(ids)

    def _rebuild(self, selected: set, top: int) -> None:
        self._shown = self._visible_order()
        self._model.refresh()
        self.select([i for i in self._shown if i in selected]) if selected else None
        self.verticalScrollBar().setValue(top)
        self._update_empty()

    # ----------------------------------------------------------------- état vide
    def _show_empty(self, title: str, sub: str) -> None:
        self._empty.setText(f"<b>{title}</b>" + (f"<br>{sub}" if sub else ""))
        self._empty.show()
        self._place_empty()

    def _update_empty(self) -> None:
        if self._shown:
            self._empty.hide()
            return
        title, sub = self._empty_title, self._empty_sub
        if self.filter_active and self._rows:
            title, sub = t("empty.filter_title"), t("empty.filter_sub")
        if title:
            self._show_empty(title, sub)
        else:
            self._empty.hide()

    def _place_empty(self) -> None:
        vp = self.viewport()
        w = min(vp.width() - 20, theme.px(460))
        self._empty.setFixedWidth(max(50, w))
        self._empty.adjustSize()
        self._empty.move((vp.width() - self._empty.width()) // 2, int(vp.height() * 0.35))

    # ------------------------------------------------------------------ évènements
    def _selected(self) -> None:
        if self.on_select:
            self.on_select(self.selected_iids())

    def _double(self, index: QModelIndex) -> None:
        if self.on_double and 0 <= index.row() < len(self._shown):
            self.on_double(self._shown[index.row()])

    def keyPressEvent(self, e: Any) -> None:     # noqa: N802
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            sel = self.selected_iids()
            if sel and self.on_double:
                self.on_double(sel[0])
            return
        if e.key() == Qt.Key_Delete and self.on_delete:
            self.on_delete()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e: Any) -> None:   # noqa: N802
        index = self.indexAt(e.position().toPoint())
        if index.isValid() and e.button() == Qt.LeftButton:
            key = self.columns[index.column()].key
            if key in self._click_cols and self.on_cell_click:
                self.on_cell_click(self._shown[index.row()], key)
                return
        self._press = e.position().toPoint() if e.button() == Qt.LeftButton else None
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: Any) -> None:    # noqa: N802
        if (self._press is not None and e.buttons() & Qt.LeftButton and (self.can_reorder or self.drag_out)
                and (e.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            ids = self.selected_iids()
            if ids:
                self._press = None
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(MIME_IDS, QByteArray(",".join(ids).encode()))
                drag.setMimeData(mime)
                drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)
                return
        super().mouseMoveEvent(e)

    # glisser-déposer interne (réordonnancement)
    def dragEnterEvent(self, e: Any) -> None:    # noqa: N802
        if e.source() is self and self.can_reorder and e.mimeData().hasFormat(MIME_IDS):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e: Any) -> None:     # noqa: N802
        if e.source() is self and self.can_reorder:
            e.acceptProposedAction()
            super().dragMoveEvent(e)
        else:
            e.ignore()

    def dropEvent(self, e: Any) -> None:         # noqa: N802
        if e.source() is not self or not self.can_reorder:
            e.ignore()
            return
        ids = bytes(e.mimeData().data(MIME_IDS)).decode().split(",")
        index = self.indexAt(e.position().toPoint())
        if index.isValid():
            target = self._shown[index.row()]
            rect = self.visualRect(index)
            after = e.position().toPoint().y() > rect.center().y()
        else:
            target, after = (self._shown[-1], True) if self._shown else (None, True)
        e.setDropAction(Qt.CopyAction)        # jamais de suppression automatique par Qt
        e.accept()
        if target is not None and target not in ids:
            self._drop(ids, target, after)

    def _drop(self, ids: List[str], target: str, after: bool) -> None:
        self._freeze_sort()
        moving = [i for i in self._order if i in set(ids)]
        rest = [i for i in self._order if i not in set(ids)]
        if target not in rest:
            return
        at = rest.index(target) + (1 if after else 0)
        self._order = rest[:at] + moving + rest[at:]
        self._rebuild(set(moving), self.verticalScrollBar().value())
        if self.on_reordered:
            self.on_reordered()

    def move_selected(self, delta: int) -> bool:
        """Décale la sélection d'un cran (delta = -1 haut, +1 bas). False si impossible."""
        if not self.can_reorder:
            return False
        self._freeze_sort()
        ids = set(self.selected_iids())
        if not ids:
            return False
        pos = sorted(self._order.index(i) for i in ids)
        order = self._order
        if delta < 0:
            if pos[0] == 0:
                return False
            for p in pos:
                order[p - 1], order[p] = order[p], order[p - 1]
        else:
            if pos[-1] == len(order) - 1:
                return False
            for p in reversed(pos):
                order[p + 1], order[p] = order[p], order[p + 1]
        self._rebuild(ids, self.verticalScrollBar().value())
        if self.on_reordered:
            self.on_reordered()
        return True

    # ------------------------------------------------------------- menu contextuel
    def _context(self, pos: QPoint) -> None:
        if not self.menu_builder:
            return
        index = self.indexAt(pos)
        if index.isValid() and self._shown[index.row()] not in self.selected_iids():
            self.select([self._shown[index.row()]])
        entries = self.menu_builder(self.selected_iids())
        if entries:
            popup_menu(self, entries, self.viewport().mapToGlobal(pos))


def popup_menu(widget: Any, entries: Sequence[MenuEntry], global_pos: Any) -> None:
    menu = QMenu(widget)
    for entry in entries:
        if entry is None:
            menu.addSeparator()
        else:
            menu.addAction(entry[0], entry[1])
    menu.exec(global_pos)
