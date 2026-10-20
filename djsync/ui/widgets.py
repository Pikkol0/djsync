"""TrackTable : tableau léger (ttk.Treeview) avec pochettes asynchrones, tri, filtre,
réordonnancement (boutons ou glisser-déposer), menu contextuel et colonne à cocher.

Aucune logique métier : les vues fournissent des `Row` et reçoivent des callbacks.
La colonne #0 du Treeview sert à la pochette (seul endroit où Tk accepte une image).
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import customtkinter as ctk

from . import theme
from .covers import CoverLoader, CoverRef

ASC, DESC = " ▲", " ▼"
MenuEntry = Optional[Tuple[str, Callable[[], None]]]  # None = séparateur


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


@dataclass
class Row:
    iid: str
    values: Dict[str, Any]
    cover: Optional[CoverRef] = None
    tags: Tuple[str, ...] = ()
    data: Any = None

    def search_text(self) -> str:
        return " ".join(str(v) for v in self.values.values()).lower()


def _sort_value(row: Row, col: Column) -> Tuple[int, Any]:
    value = col.sort(row) if col.sort else row.values.get(col.key)
    if value is None or value == "":
        return (1, 0)  # les vides vont toujours à la fin
    return (0, value.lower() if isinstance(value, str) else value)


class TrackTable(ctk.CTkFrame):
    def __init__(
        self,
        parent: Any,
        columns: Sequence[Column],
        loader: Optional[CoverLoader] = None,
        show_covers: bool = True,
        selectmode: str = "extended",
        reorderable: bool = False,
        click_columns: Sequence[str] = (),
    ) -> None:
        super().__init__(parent, fg_color=theme.SURFACE, corner_radius=8)
        self.columns = list(columns)
        self._loader = loader if show_covers else None
        self._show_covers = show_covers and loader is not None
        self.reorderable = reorderable
        self._click_cols = set(click_columns)

        self.on_select: Optional[Callable[[List[str]], None]] = None
        self.on_double: Optional[Callable[[str], None]] = None
        self.on_cell_click: Optional[Callable[[str, str], None]] = None
        self.on_reordered: Optional[Callable[[], None]] = None
        self.on_sort_changed: Optional[Callable[[Optional[str], bool], None]] = None
        self.menu_builder: Optional[Callable[[List[str]], List[MenuEntry]]] = None

        self._rows: Dict[str, Row] = {}
        self._order: List[str] = []       # ordre « manuel » complet
        self._shown: List[str] = []       # ordre affiché (filtre + tri appliqués)
        self._filter = ""
        self._sort_key: Optional[str] = None
        self._sort_desc = False
        self._photos: Dict[str, Any] = {}  # références (Tk perd l'image si l'objet est collecté)
        self._covered: set = set()
        self._drag: Optional[Dict[str, Any]] = None
        self._drop_iid: Optional[str] = None
        self._after_cover: Optional[str] = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self, columns=[c.key for c in self.columns], selectmode=selectmode,
            show=("tree headings" if self._show_covers else "headings"),
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)
        self._scroll = ctk.CTkScrollbar(
            self, command=self.tree.yview, fg_color=theme.SURFACE, button_color=theme.BORDER,
            button_hover_color=theme.FAINT, width=theme.px(12),
        )
        self._scroll.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)
        self.tree.configure(yscrollcommand=self._on_yscroll)

        if self._show_covers:
            self.tree.column("#0", width=theme.tkpx(theme.COVER_SIZE + 16), minwidth=theme.tkpx(theme.COVER_SIZE + 16),
                             stretch=False, anchor="center")
            self.tree.heading("#0", text="")
        for col in self.columns:
            self.tree.column(col.key, width=theme.tkpx(col.width), minwidth=theme.tkpx(col.min_width),
                             stretch=col.stretch, anchor=col.anchor)
            self.tree.heading(col.key, text=col.title, anchor=col.anchor,
                              command=lambda c=col: self._heading_clicked(c))

        self.tree.tag_configure("dup", foreground=theme.WARN)
        self.tree.tag_configure("err", foreground=theme.ERR)
        self.tree.tag_configure("dim", foreground=theme.DIM)
        self.tree.tag_configure("ok", foreground=theme.ACCENT)
        self.tree.tag_configure("drop", background=theme.BORDER)

        self._empty = theme.label(self, "", 12, theme.FAINT, justify="center")
        self._empty_text = ""

        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Double-1>", self._double)
        self.tree.bind("<ButtonPress-1>", self._press)
        self.tree.bind("<B1-Motion>", self._motion)
        self.tree.bind("<ButtonRelease-1>", self._release)
        self.tree.bind("<Button-3>", self._context)
        self.tree.bind("<Button-2>", self._context)
        self.tree.bind("<Configure>", lambda _e: self._schedule_covers())
        self.tree.bind("<MouseWheel>", lambda _e: self._schedule_covers(), add="+")
        self.tree.bind("<Button-4>", lambda _e: self._schedule_covers(), add="+")
        self.tree.bind("<Button-5>", lambda _e: self._schedule_covers(), add="+")

    # ------------------------------------------------------------------ données
    def set_rows(self, rows: Sequence[Row], reset_sort: bool = False, keep_selection: bool = True) -> None:
        selected = set(self.tree.selection()) if keep_selection else set()
        top = self.tree.yview()[0] if keep_selection else 0.0
        self._rows = {r.iid: r for r in rows}
        self._order = [r.iid for r in rows]
        self._covered &= set(self._rows)
        for iid in [i for i in self._photos if i not in self._rows]:
            del self._photos[iid]
        if reset_sort:
            self._sort_key, self._sort_desc = None, False
        self._rebuild(selected, top)

    def row(self, iid: str) -> Optional[Row]:
        return self._rows.get(iid)

    def update_values(self, iid: str, **values: Any) -> None:
        row = self._rows.get(iid)
        if row is None:
            return
        row.values.update(values)
        if self.tree.exists(iid):
            for key, val in values.items():
                if key in {c.key for c in self.columns}:
                    self.tree.set(iid, key, val)

    def set_tags(self, iid: str, *tags: str) -> None:
        row = self._rows.get(iid)
        if row is None:
            return
        row.tags = tuple(tags)
        if self.tree.exists(iid):
            self.tree.item(iid, tags=tags)

    @property
    def count(self) -> int:
        return len(self._shown)

    @property
    def total(self) -> int:
        return len(self._rows)

    def selected_iids(self) -> List[str]:
        sel = set(self.tree.selection())
        return [i for i in self._shown if i in sel]  # dans l'ordre d'affichage

    def selected_rows(self) -> List[Row]:
        return [self._rows[i] for i in self.selected_iids()]

    def displayed_iids(self) -> List[str]:
        return list(self._shown)

    def all_rows(self) -> List[Row]:
        return [self._rows[i] for i in self._order]

    def select(self, iids: Sequence[str]) -> None:
        present = [i for i in iids if self.tree.exists(i)]
        self.tree.selection_set(present)
        if present:
            self.tree.see(present[0])

    def select_all(self) -> None:
        self.tree.selection_set(self._shown)

    def clear(self) -> None:
        self.set_rows([])

    def set_display_columns(self, keys: Sequence[str]) -> None:
        """Affiche seulement ces colonnes (la colonne cachée garde ses données)."""
        self.tree.configure(displaycolumns=list(keys))

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self._update_empty()

    # ------------------------------------------------------------------- filtre / tri
    def set_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        if text != self._filter:
            self._filter = text
            self._rebuild(set(self.tree.selection()), 0.0)

    @property
    def filter_active(self) -> bool:
        return bool(self._filter)

    @property
    def sort_active(self) -> bool:
        return self._sort_key is not None

    @property
    def can_reorder(self) -> bool:
        return self.reorderable and not self._filter

    def set_sort(self, key: Optional[str], descending: bool = False) -> None:
        self._sort_key, self._sort_desc = key, descending
        self._rebuild(set(self.tree.selection()), 0.0)

    def _heading_clicked(self, col: Column) -> None:
        if col.on_header:
            col.on_header()
            return
        if not col.sortable:
            return
        if self._sort_key != col.key:
            self._sort_key, self._sort_desc = col.key, False
        elif not self._sort_desc:
            self._sort_desc = True
        else:  # 3e clic : retour à l'ordre par défaut
            self._sort_key, self._sort_desc = None, False
        self._rebuild(set(self.tree.selection()), 0.0)
        if self.on_sort_changed:
            self.on_sort_changed(self._sort_key, self._sort_desc)

    def _freeze_sort(self) -> None:
        """Le tri affiché devient l'ordre manuel (point de départ d'un réordonnancement)."""
        if self._sort_key is not None and not self._filter:
            self._order = list(self._shown)
            self._sort_key, self._sort_desc = None, False
            self._update_headings()
            if self.on_sort_changed:
                self.on_sort_changed(None, False)

    def _update_headings(self) -> None:
        for col in self.columns:
            mark = (DESC if self._sort_desc else ASC) if col.key == self._sort_key else ""
            self.tree.heading(col.key, text=col.title + mark)

    # ----------------------------------------------------------------- construction
    def _visible_order(self) -> List[str]:
        ids = self._order
        if self._filter:
            ids = [i for i in ids if self._filter in self._rows[i].search_text()]
        if self._sort_key is not None:
            col = next((c for c in self.columns if c.key == self._sort_key), None)
            if col is not None:
                present = [i for i in ids if _sort_value(self._rows[i], col)[0] == 0]
                empty = [i for i in ids if _sort_value(self._rows[i], col)[0] == 1]
                present.sort(key=lambda i: _sort_value(self._rows[i], col), reverse=self._sort_desc)
                ids = present + empty
        return list(ids)

    def _rebuild(self, selected: set, top: float) -> None:
        self.tree.delete(*self.tree.get_children())
        self._shown = self._visible_order()
        placeholder = self._loader.placeholder_photo() if self._show_covers else None
        keys = [c.key for c in self.columns]
        for iid in self._shown:
            row = self._rows[iid]
            kw: Dict[str, Any] = {"values": [row.values.get(k, "") for k in keys], "tags": row.tags}
            if self._show_covers:
                kw["image"] = self._photos.get(iid) or placeholder
            self.tree.insert("", "end", iid=iid, **kw)
        keep = [i for i in self._shown if i in selected]
        if keep:
            self.tree.selection_set(keep)
        if top:
            self.tree.yview_moveto(top)
        self._update_headings()
        self._update_empty()
        self._schedule_covers()

    def _update_empty(self) -> None:
        if self._shown:
            self._empty.place_forget()
            return
        text = "Aucun résultat pour ce filtre." if (self._filter and self._rows) else self._empty_text
        if text:
            self._empty.configure(text=text)
            self._empty.place(relx=0.5, rely=0.45, anchor="center")
        else:
            self._empty.place_forget()

    # ------------------------------------------------------------------- pochettes
    def _on_yscroll(self, first: str, last: str) -> None:
        self._scroll.set(first, last)
        self._schedule_covers()

    def _schedule_covers(self) -> None:
        if not self._show_covers or self._after_cover is not None:
            return
        self._after_cover = self.after(60, self._load_visible_covers)

    def _load_visible_covers(self) -> None:
        self._after_cover = None
        if not self._show_covers or not self.winfo_exists():
            return
        step = max(8, theme.tkpx(theme.ROW_HEIGHT))
        height = self.tree.winfo_height()
        seen: List[str] = []
        for y in range(step // 2 + theme.tkpx(24), max(height, step) + step, step):
            iid = self.tree.identify_row(y)
            if iid and iid not in seen:
                seen.append(iid)
        for iid in seen:
            row = self._rows.get(iid)
            if row is None or row.cover is None or iid in self._covered:
                continue
            self._covered.add(iid)
            self._loader.request(row.cover, lambda photo, i=iid: self._set_photo(i, photo))

    def _set_photo(self, iid: str, photo: Any) -> None:
        self._photos[iid] = photo
        if self.tree.exists(iid):
            self.tree.item(iid, image=photo)

    # ------------------------------------------------------------------ évènements
    def _selected(self, _e: Any = None) -> None:
        if self.on_select:
            self.on_select(self.selected_iids())

    def _double(self, e: Any) -> None:
        if self.tree.identify_region(e.x, e.y) in ("heading", "separator"):
            return
        iid = self.tree.identify_row(e.y)
        if iid and self.on_double:
            self.on_double(iid)

    def _column_key_at(self, x: int) -> str:
        ident = self.tree.identify_column(x)  # "#0", "#1"…
        try:
            n = int(ident.lstrip("#"))
        except ValueError:
            return ""
        idx = n - 1
        return self.columns[idx].key if 0 <= idx < len(self.columns) else ""

    def _press(self, e: Any) -> Optional[str]:
        self._drag = None
        if self.tree.identify_region(e.x, e.y) not in ("cell", "tree"):
            return None
        iid = self.tree.identify_row(e.y)
        if not iid:
            return None
        key = self._column_key_at(e.x)
        if key in self._click_cols and self.on_cell_click:
            self.on_cell_click(iid, key)
            return "break"
        if self.can_reorder and not (e.state & 0x0005):  # ni Maj ni Ctrl
            sel = self.selected_iids()
            if iid in sel and len(sel) > 1:
                self._drag = {"ids": sel, "moved": False, "y": e.y, "press": iid}
                return "break"
            self._drag = {"ids": [iid], "moved": False, "y": e.y, "press": iid}
        return None

    def _set_drop(self, iid: Optional[str]) -> None:
        if iid == self._drop_iid:
            return
        if self._drop_iid and self.tree.exists(self._drop_iid):
            row = self._rows.get(self._drop_iid)
            self.tree.item(self._drop_iid, tags=row.tags if row else ())
        self._drop_iid = iid
        if iid and self.tree.exists(iid):
            row = self._rows.get(iid)
            self.tree.item(iid, tags=((row.tags if row else ()) + ("drop",)))

    def _motion(self, e: Any) -> Optional[str]:
        d = self._drag
        if not d:
            return None
        if not d["moved"] and abs(e.y - d["y"]) < 6:
            return "break" if len(d["ids"]) > 1 else None
        d["moved"] = True
        self.tree.configure(cursor="hand2")
        height = self.tree.winfo_height()
        if e.y < theme.tkpx(40):
            self.tree.yview_scroll(-1, "units")
        elif e.y > height - theme.tkpx(24):
            self.tree.yview_scroll(1, "units")
        target = self.tree.identify_row(e.y)
        self._set_drop(target if target and target not in d["ids"] else None)
        return "break"

    def _release(self, e: Any) -> Optional[str]:
        d, self._drag = self._drag, None
        self.tree.configure(cursor="")
        target = self._drop_iid
        self._set_drop(None)
        if not d:
            return None
        if not d["moved"]:
            if len(d["ids"]) > 1:  # simple clic sur une ligne d'une sélection multiple
                self.tree.selection_set([d["press"]])
                return "break"
            return None
        if target and target not in d["ids"]:
            box = self.tree.bbox(target)
            after = bool(box) and e.y > box[1] + box[3] / 2
            self._drop(d["ids"], target, after)
        return "break"

    def _drop(self, ids: List[str], target: str, after: bool) -> None:
        self._freeze_sort()
        moving = [i for i in self._order if i in set(ids)]
        rest = [i for i in self._order if i not in set(ids)]
        if target not in rest:
            return
        at = rest.index(target) + (1 if after else 0)
        self._order = rest[:at] + moving + rest[at:]
        self._rebuild(set(moving), self.tree.yview()[0])
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
        self._rebuild(ids, self.tree.yview()[0])
        self.tree.see(next(iter(i for i in self._shown if i in ids)))
        if self.on_reordered:
            self.on_reordered()
        return True

    # --------------------------------------------------------------- menu contextuel
    def _context(self, e: Any) -> None:
        if not self.menu_builder:
            return
        iid = self.tree.identify_row(e.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set([iid])
        entries = self.menu_builder(self.selected_iids())
        if not entries:
            return
        menu = tk.Menu(
            self.tree, tearoff=0, bg=theme.ELEV, fg=theme.TEXT, activebackground=theme.ACCENT_DIM,
            activeforeground=theme.TEXT, bd=0, relief="flat", font=(theme.FAMILY, 10),
        )
        for entry in entries:
            if entry is None:
                menu.add_separator()
            else:
                menu.add_command(label=entry[0], command=entry[1])
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()


# ----------------------------------------------------------------- petits composants
def pill(parent: Any, text: str, color: str = theme.DIM) -> ctk.CTkLabel:
    return theme.label(parent, text, 11, color)


def toolbar(parent: Any) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    return frame
