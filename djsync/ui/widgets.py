"""TrackTable : tableau léger (ttk.Treeview) avec pochettes asynchrones, tri, filtre,
réordonnancement (boutons ou glisser-déposer), glisser vers l'extérieur (playlists), menu
contextuel, colonnes adaptatives, lignes « squelette » pendant un chargement et état vide illustré.

Aucune logique métier : les vues fournissent des `Row` et reçoivent des callbacks.
La colonne #0 du Treeview sert à la pochette (seul endroit où Tk accepte une image) ; avec
`badges=True`, la pastille Camelot colorée y est dessinée à droite de la pochette.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import customtkinter as ctk

from ..i18n import t
from . import theme
from .covers import BADGE_W, CoverLoader, CoverRef
from .icons import ctk_icon

ASC, DESC = " ▲", " ▼"
MenuEntry = Optional[Tuple[str, Callable[[], None]]]  # None = séparateur
SKELETON = "__skeleton"


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
    cover: Optional[CoverRef] = None
    tags: Tuple[str, ...] = ()
    data: Any = None
    badge: Optional[Tuple[str, str]] = None          # (texte, couleur) : pastille Camelot

    def search_text(self) -> str:
        return " ".join(str(v) for v in self.values.values()).lower()


def _sort_value(row: Row, col: Column) -> Tuple[int, Any]:
    value = col.sort(row) if col.sort else row.values.get(col.key)
    if value is None or value == "":
        return (1, 0)  # les vides vont toujours à la fin
    return (0, value.lower() if isinstance(value, str) else value)


def camelot_sort(row: Row) -> Any:
    """Tri par roue Camelot : 1A, 1B, 2A… (sons sans tonalité à la fin)."""
    if not row.badge:
        return None
    code = row.badge[0]
    try:
        return (int(code[:-1]), code[-1])
    except ValueError:
        return None


class EmptyState(ctk.CTkFrame):
    """Message centré « rien ici » : icône, titre, explication, bouton facultatif."""

    def __init__(self, parent: Any) -> None:
        super().__init__(parent, fg_color="transparent")
        self.icon = ctk.CTkLabel(self, text="")
        self.icon.pack(pady=(0, 8))
        self.title = theme.label(self, "", 14, theme.DIM, "bold", justify="center")
        self.title.pack()
        self.sub = theme.label(self, "", 11, theme.FAINT, justify="center", wraplength=360)
        self.sub.pack(pady=(4, 0))
        self.btn = theme.button(self, "", None, kind="ghost", width=150)

    def set(self, icon: str, title: str, sub: str = "", action: Optional[Tuple[str, Callable[[], None]]] = None) -> None:
        self.icon.configure(image=ctk_icon(icon, 40, theme.FAINT))
        self.title.configure(text=title)
        self.sub.configure(text=sub)
        self.sub.pack_forget()
        if sub:
            self.sub.pack(pady=(4, 0))
        self.btn.pack_forget()
        if action:
            self.btn.configure(text=action[0], command=action[1])
            self.btn.pack(pady=(12, 0))


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
        badges: bool = False,
    ) -> None:
        super().__init__(parent, fg_color=theme.SURFACE, corner_radius=8)
        self.columns = list(columns)
        self._loader = loader if show_covers else None
        self._show_covers = show_covers and loader is not None
        self._badges = badges and self._show_covers
        self.reorderable = reorderable
        self.drag_out = False                           # glisser des lignes hors du tableau (playlists)
        self._click_cols = set(click_columns)
        self._tree_col = Column("#0", "", sort=camelot_sort) if self._badges else None

        self.on_select: Optional[Callable[[List[str]], None]] = None
        self.on_double: Optional[Callable[[str], None]] = None
        self.on_cell_click: Optional[Callable[[str, str], None]] = None
        self.on_reordered: Optional[Callable[[], None]] = None
        self.on_sort_changed: Optional[Callable[[Optional[str], bool], None]] = None
        self.menu_builder: Optional[Callable[[List[str]], List[MenuEntry]]] = None
        self.on_drag_over: Optional[Callable[[List[str], int, int], bool]] = None   # survol hors du tableau
        self.on_drop_outside: Optional[Callable[[List[str], int, int], None]] = None
        self.row_filter: Optional[Callable[[Row], bool]] = None                     # filtre « métier »

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
        self._after_fit: Optional[str] = None
        self._wanted: List[str] = [c.key for c in self.columns]
        self._auto_hidden: set = set()
        self._skeleton = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self, columns=[c.key for c in self.columns], selectmode=selectmode,
            show=("tree headings" if self._show_covers else "headings"),
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)
        self._scroll = ctk.CTkScrollbar(
            self, command=self.tree.yview, fg_color=theme.SURFACE, button_color=theme.BORDER,
            button_hover_color=theme.FAINT, width=12,
        )
        self._scroll.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)
        self.tree.configure(yscrollcommand=self._on_yscroll)
        self._apply_widths()
        for col in self.columns:
            self.tree.heading(col.key, text=col.title, anchor=col.anchor,
                              command=lambda c=col: self._heading_clicked(c))
        if self._show_covers:
            self.tree.heading("#0", text=t("track.key") if self._badges else "",
                              command=(lambda: self._heading_clicked(self._tree_col)) if self._badges else "")

        self.tree.tag_configure("dup", foreground=theme.WARN)
        self.tree.tag_configure("err", foreground=theme.ERR)
        self.tree.tag_configure("dim", foreground=theme.DIM)
        self.tree.tag_configure("ok", foreground=theme.ACCENT)
        self.tree.tag_configure("drop", background=theme.BORDER)
        self.tree.tag_configure("playing", foreground=theme.ACCENT)
        self.tree.tag_configure("skeleton", foreground=theme.BORDER)

        self._empty = EmptyState(self)
        self._empty_spec: Tuple[Any, ...] = ("music", "", "", None)

        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Double-1>", self._double)
        self.tree.bind("<Return>", lambda _e: self._enter())
        self.tree.bind("<ButtonPress-1>", self._press)
        self.tree.bind("<B1-Motion>", self._motion)
        self.tree.bind("<ButtonRelease-1>", self._release)
        self.tree.bind("<Button-3>", self._context)
        self.tree.bind("<Button-2>", self._context)
        self.tree.bind("<Configure>", lambda _e: (self._schedule_covers(), self._schedule_fit()))
        self.tree.bind("<MouseWheel>", lambda _e: self._schedule_covers(), add="+")
        self.tree.bind("<Button-4>", lambda _e: self._schedule_covers(), add="+")
        self.tree.bind("<Button-5>", lambda _e: self._schedule_covers(), add="+")
        self.tree.bind("<Control-a>", lambda _e: (self.select_all(), "break")[1])

    # ------------------------------------------------------------------ échelle
    def _cover_width(self) -> int:
        w = theme.COVER_SIZE + 16 + (BADGE_W + 6 if self._badges else 0)
        return theme.tkpx(w)

    def _apply_widths(self) -> None:
        if self._show_covers:
            self.tree.column("#0", width=self._cover_width(), minwidth=self._cover_width(), stretch=False,
                             anchor="center")
        for col in self.columns:
            self.tree.column(col.key, width=theme.tkpx(col.width), minwidth=theme.tkpx(col.min_width),
                             stretch=col.stretch, anchor=col.anchor)

    def on_scale(self) -> None:
        """Après un changement d'échelle : colonnes, pochettes (nouvelle taille) et lignes."""
        self._apply_widths()
        self._photos.clear()
        self._covered.clear()
        self._rebuild(set(self.tree.selection()), self.tree.yview()[0])
        self._schedule_fit()

    # ------------------------------------------------------------- colonnes adaptatives
    def set_display_columns(self, keys: Sequence[str]) -> None:
        """Colonnes voulues par la vue ; les moins importantes sont masquées si la place manque."""
        self._wanted = list(keys)
        self._fit_columns()

    def _schedule_fit(self) -> None:
        if self._after_fit is None:
            self._after_fit = self.after(80, self._fit_columns)

    def _fit_columns(self) -> None:
        self._after_fit = None
        if not self.winfo_exists():
            return
        avail = self.tree.winfo_width()
        if avail <= 1:
            self.tree.configure(displaycolumns=self._wanted)
            return
        cols = {c.key: c for c in self.columns}
        shown = [k for k in self._wanted if k in cols]
        need = (self._cover_width() if self._show_covers else 0) + sum(theme.tkpx(cols[k].width) for k in shown)
        hidden: set = set()
        stretch_min = sum(theme.tkpx(cols[k].min_width) - theme.tkpx(cols[k].width) for k in shown if cols[k].stretch)
        need += stretch_min                    # une colonne extensible peut descendre à sa largeur minimale
        for col in sorted((cols[k] for k in shown if cols[k].priority > 0), key=lambda c: -c.priority):
            if need <= avail:
                break
            hidden.add(col.key)
            need -= theme.tkpx(col.width)
        visible = [k for k in shown if k not in hidden]
        if hidden != self._auto_hidden or list(self.tree.cget("displaycolumns")) != visible:
            self._auto_hidden = hidden
            self.tree.configure(displaycolumns=visible)
        # largeurs remises à plat : les colonnes fixes à leur taille, l'espace restant aux extensibles
        # (sinon Tk garde l'élargissement précédent et pousse des colonnes hors de la vue)
        fixed = sum(theme.tkpx(cols[k].width) for k in visible if not cols[k].stretch)
        stretch = [k for k in visible if cols[k].stretch]
        free = avail - (self._cover_width() if self._show_covers else 0) - fixed - 2
        for k in visible:
            if cols[k].stretch:
                share = max(theme.tkpx(cols[k].min_width), free // max(1, len(stretch)))
                self.tree.column(k, width=share)
            else:
                self.tree.column(k, width=theme.tkpx(cols[k].width))

    @property
    def hidden_columns(self) -> set:
        return set(self._auto_hidden)

    # ------------------------------------------------------------------ données
    def set_rows(self, rows: Sequence[Row], reset_sort: bool = False, keep_selection: bool = True) -> None:
        self._skeleton = False
        selected = set(self.tree.selection()) if keep_selection else set()
        top = self.tree.yview()[0] if keep_selection else 0.0
        old = self._rows
        self._rows = {r.iid: r for r in rows}
        self._order = [r.iid for r in rows]
        # V0.2.4 : une ligne déjà affichée dont la pastille (tonalité trouvée par l'analyse) ou la pochette a
        # changé doit être redessinée ; avant, l'ancienne image (sans pastille) restait jusqu'au redémarrage.
        changed = {iid for iid, r in self._rows.items() if iid in old and
                   (old[iid].badge != r.badge or getattr(old[iid].cover, "key", None) != getattr(r.cover, "key", None))}
        self._covered &= set(self._rows) - changed
        for iid in [i for i in self._photos if i not in self._rows or i in changed]:
            del self._photos[iid]
        if reset_sort:
            self._sort_key, self._sort_desc = None, False
        self._rebuild(selected, top)

    def show_skeleton(self, n: int = 8) -> None:
        """Lignes grisées pendant un chargement (recherche, playlist)."""
        self._skeleton = True
        self._empty.place_forget()
        self.tree.delete(*self.tree.get_children())
        keys = [c.key for c in self.columns]
        widths = {c.key: max(3, c.width // 14) for c in self.columns}
        placeholder = self._loader.placeholder_photo() if self._show_covers else None
        for i in range(n):
            vals = ["▬" * max(2, widths[k] - (i * 3 + j) % 4) if k not in ("chk", "dl") else "" for j, k in enumerate(keys)]
            kw: Dict[str, Any] = {"values": vals, "tags": ("skeleton",)}
            if placeholder is not None:
                kw["image"] = placeholder
            self.tree.insert("", "end", iid=f"{SKELETON}{i}", **kw)

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

    def refresh_cover(self, iid: str) -> None:
        """La pochette (ou la pastille) d'une ligne a changé : rechargement si visible."""
        self._covered.discard(iid)
        self._photos.pop(iid, None)
        self._schedule_covers()

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

    def displayed_rows(self) -> List[Row]:
        return [self._rows[i] for i in self._shown]

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

    def set_empty(self, icon: str, title: str, sub: str = "",
                  action: Optional[Tuple[str, Callable[[], None]]] = None) -> None:
        self._empty_spec = (icon, title, sub, action)
        self._update_empty()

    def set_empty_text(self, text: str) -> None:
        self.set_empty("music", text)

    # ------------------------------------------------------------------- filtre / tri
    def set_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        if text != self._filter:
            self._filter = text
            self._rebuild(set(self.tree.selection()), 0.0)

    def refilter(self) -> None:
        """À appeler quand `row_filter` change."""
        self._rebuild(set(self.tree.selection()), 0.0)

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
        self._rebuild(set(self.tree.selection()), 0.0)

    def _column(self, key: Optional[str]) -> Optional[Column]:
        if key == "#0":
            return self._tree_col
        return next((c for c in self.columns if c.key == key), None)

    def _heading_clicked(self, col: Optional[Column]) -> None:
        if col is None:
            return
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
        if self._sort_key is not None and not self.filter_active:
            self._order = list(self._shown)
            self._sort_key, self._sort_desc = None, False
            self._update_headings()
            if self.on_sort_changed:
                self.on_sort_changed(None, False)

    def _update_headings(self) -> None:
        for col in self.columns + ([self._tree_col] if self._tree_col else []):
            mark = (DESC if self._sort_desc else ASC) if col.key == self._sort_key else ""
            title = t("track.key") if col.key == "#0" else col.title
            self.tree.heading(col.key, text=title + mark)

    # ----------------------------------------------------------------- construction
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

    def _placeholder(self, row: Row) -> Any:
        return self._loader.placeholder_photo(row.badge if self._badges else None)

    def _rebuild(self, selected: set, top: float) -> None:
        self._skeleton = False
        self.tree.delete(*self.tree.get_children())
        self._shown = self._visible_order()
        keys = [c.key for c in self.columns]
        for iid in self._shown:
            row = self._rows[iid]
            kw: Dict[str, Any] = {"values": [row.values.get(k, "") for k in keys], "tags": row.tags}
            if self._show_covers:
                kw["image"] = self._photos.get(iid) or self._placeholder(row)
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
        if self._shown or self._skeleton:
            self._empty.place_forget()
            return
        icon, title, sub, action = self._empty_spec
        if self.filter_active and self._rows:
            icon, title, sub, action = "filter", t("empty.filter_title"), t("empty.filter_sub"), None
        if title:
            self._empty.set(icon, title, sub, action)
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
            self._loader.request(row.cover, lambda photo, i=iid: self._set_photo(i, photo),
                                 badge=row.badge if self._badges else None)

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
        if iid and iid in self._rows and self.on_double:
            self.on_double(iid)

    def _enter(self) -> None:
        sel = self.selected_iids()
        if sel and self.on_double:
            self.on_double(sel[0])

    def _column_key_at(self, x: int) -> str:
        ident = self.tree.identify_column(x)  # "#0", "#1"… (index dans les colonnes AFFICHÉES)
        try:
            n = int(ident.lstrip("#"))
        except ValueError:
            return ""
        shown = list(self.tree.cget("displaycolumns"))
        if shown in (["#all"], ("#all",)):
            shown = [c.key for c in self.columns]
        return shown[n - 1] if 0 < n <= len(shown) else ""

    def _press(self, e: Any) -> Optional[str]:
        self._drag = None
        if self.tree.identify_region(e.x, e.y) not in ("cell", "tree"):
            return None
        iid = self.tree.identify_row(e.y)
        if not iid or iid not in self._rows:
            return None
        key = self._column_key_at(e.x)
        if key in self._click_cols and self.on_cell_click:
            self.on_cell_click(iid, key)
            return "break"
        if (self.can_reorder or self.drag_out) and not (e.state & 0x0005):  # ni Maj ni Ctrl
            sel = self.selected_iids()
            if iid in sel and len(sel) > 1:
                self._drag = {"ids": sel, "moved": False, "y": e.y, "x": e.x, "press": iid, "out": False}
                return "break"
            self._drag = {"ids": [iid], "moved": False, "y": e.y, "x": e.x, "press": iid, "out": False}
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

    def _outside(self, e: Any) -> bool:
        w, h = self.tree.winfo_width(), self.tree.winfo_height()
        return not (0 <= e.x < w and 0 <= e.y < h)

    def _motion(self, e: Any) -> Optional[str]:
        d = self._drag
        if not d:
            return None
        if not d["moved"] and abs(e.y - d["y"]) < 6 and abs(e.x - d["x"]) < 12:
            return "break" if len(d["ids"]) > 1 else None
        d["moved"] = True
        if self.drag_out and self._outside(e):
            d["out"] = True
            self._set_drop(None)
            hover = self.on_drag_over(d["ids"], e.x_root, e.y_root) if self.on_drag_over else False
            self.tree.configure(cursor="plus" if hover else "X_cursor")
            return "break"
        if d["out"] and self.on_drag_over:
            self.on_drag_over([], -1, -1)            # retour dans le tableau : fin du survol
        d["out"] = False
        if not self.can_reorder:
            self.tree.configure(cursor="hand2")
            return "break"
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
        if d["out"]:
            if self.on_drag_over:
                self.on_drag_over([], -1, -1)
            if self.on_drop_outside:
                self.on_drop_outside(d["ids"], e.x_root, e.y_root)
            return "break"
        if self.can_reorder and target and target not in d["ids"]:
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
        if iid and iid not in self._rows:
            return
        if iid and iid not in self.tree.selection():
            self.tree.selection_set([iid])
        entries = self.menu_builder(self.selected_iids())
        if entries:
            popup_menu(self.tree, entries, e.x_root, e.y_root)


# ----------------------------------------------------------------- petits composants
def popup_menu(widget: Any, entries: Sequence[MenuEntry], x: int, y: int) -> None:
    """Menu contextuel au thème (police à l'échelle de l'interface)."""
    menu = tk.Menu(
        widget, tearoff=0, bg=theme.ELEV, fg=theme.TEXT, activebackground=theme.ACCENT_DIM,
        activeforeground=theme.TEXT, bd=0, relief="flat", font=theme.tk_font(10),
    )
    for entry in entries:
        if entry is None:
            menu.add_separator()
        else:
            menu.add_command(label=entry[0], command=entry[1])
    try:
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()


def icon_button(parent: Any, icon: str, command: Any = None, tooltip: str = "", size: int = 34,
                kind: str = "ghost") -> ctk.CTkButton:
    """Bouton carré à icône seule (Filtres, Rechercher, Précédent…). `tooltip` : bulle d'aide."""
    primary = kind == "primary"
    color = theme.ON_ACCENT if primary else theme.TEXT
    btn = ctk.CTkButton(
        parent, text="", image=ctk_icon(icon, 18, color), width=size, height=size, corner_radius=8,
        fg_color=theme.ACCENT if primary else "transparent", hover_color=theme.ACCENT_HOVER if primary else theme.ELEV,
        border_width=0 if primary else 1, border_color=theme.BORDER, command=command,
    )
    if tooltip:
        Tooltip(btn, tooltip)
    return btn


class Tooltip:
    """Bulle d'aide au survol (boutons à icône seule)."""

    def __init__(self, widget: Any, text: str, delay: int = 450) -> None:
        self.widget, self.text, self.delay = widget, text, delay
        self._after: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e: Any = None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:  # noqa: BLE001
                pass
            self._after = None

    def _show(self) -> None:
        if not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.configure(bg=theme.BORDER)
        tk.Label(tip, text=self.text, bg=theme.ELEV, fg=theme.TEXT, font=theme.tk_font(9), padx=8, pady=4).pack(
            padx=1, pady=1)
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _e: Any = None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class CamelotPill(ctk.CTkLabel):
    """Pastille Camelot colorée (lecteur, filtre harmonique)."""

    def __init__(self, parent: Any, code: Optional[str] = None) -> None:
        super().__init__(parent, text="", corner_radius=6, height=20, width=38, font=theme.font(10, "bold"))
        self.set(code)

    def set(self, code: Optional[str]) -> None:
        if code:
            color = theme.camelot_color(code)
            self.configure(text=code, fg_color=color, text_color=theme.on_color(color))
        else:
            self.configure(text="", fg_color="transparent")
