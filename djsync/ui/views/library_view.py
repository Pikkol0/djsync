"""Vue Bibliothèque (« mini-Rekordbox ») : « Tous les titres » + dossiers et playlists de la clé.

Gauche : « Tous les titres » puis l'arbre des dossiers/playlists (nombre de sons). Droite : en-tête
(nombre de sons, durée totale, dernier ajout), barre d'outils, tableau triable avec pastille
Camelot colorée. Dans une playlist : réordonner (Haut/Bas ou glisser) puis « Enregistrer l'ordre ».
Glisser des sons sur une playlist de gauche les y ajoute. Filtre harmonique : ne garder que les
sons compatibles (même clé, ±1, relative) avec le son choisi.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from tkinter import ttk

from ...core.camelot import neighbors
from ...i18n import plural, t
from ...models import LibraryTrack, PlaylistInfo, format_duration
from .. import theme
from ..covers import CoverRef, file_cover
from ..dialogs import ConfirmDialog, PlaylistPicker, TextInputDialog
from ..icons import ctk_icon
from ..widgets import Column, Row, TrackTable, icon_button, popup_menu
from .common import View

ALL = "all"
_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


def _fmt(track: LibraryTrack) -> str:
    return _FORMATS.get(track.file_type) or Path(track.path).suffix.lstrip(".").upper()


def total_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return t("lib.duration_hm", h=h, m=m) if h else t("lib.duration_m", m=m)


class LibraryView(View):
    NAV_W = 240

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.playlists: List[PlaylistInfo] = []
        self.all_tracks: List[LibraryTrack] = []
        self.stats: Dict[int, Any] = {}
        self.current: str = ALL            # ALL ou "p<id>"
        self._dirty = False
        self._loaded_for: Optional[str] = None
        self._reverting = False
        self._by_iid: Dict[str, PlaylistInfo] = {}
        self._harmonic: Optional[LibraryTrack] = None
        self._drop_target: Optional[str] = None
        self._loading = False

        self.cols = [
            Column("pos", t("track.position"), 46, "e", sort=lambda r: r.data.sequence if r.data else 0),
            Column("title", t("track.title"), 260, stretch=True, min_width=170),
            Column("artist", t("track.artist"), 170, priority=1),
            Column("album", t("track.album"), 140, priority=5),
            Column("bpm", t("track.bpm"), 58, "e", priority=2, sort=lambda r: r.data.bpm or None if r.data else None),
            Column("duration", t("track.duration"), 64, "e", priority=3,
                   sort=lambda r: r.data.duration_seconds if r.data else 0),
            Column("format", t("track.format"), 60, "center", priority=6),
            Column("added", t("track.added"), 98, "center", priority=4,
                   sort=lambda r: r.data.date_added if r.data else ""),
        ]

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ------------------------------------------------------------ gauche : navigation
        nav = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0, width=self.NAV_W)
        nav.grid(row=0, column=0, sticky="ns")
        nav.grid_propagate(False)
        nav.grid_rowconfigure(1, weight=1)
        nav.grid_columnconfigure(0, weight=1)
        self.nav_frame = nav
        theme.label(nav, t("lib.section").upper(), 10, theme.FAINT, "bold", anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(18, 6))
        self.nav = ttk.Treeview(nav, show="tree", selectmode="browse", style="Nav.Treeview")
        self.nav.grid(row=1, column=0, sticky="nsew", padx=(6, 0))
        sb = ctk.CTkScrollbar(nav, command=self.nav.yview, fg_color=theme.SURFACE, button_color=theme.BORDER, width=10)
        sb.grid(row=1, column=1, sticky="ns")
        self.nav.configure(yscrollcommand=sb.set)
        self.nav.bind("<<TreeviewSelect>>", self._nav_selected)
        self.nav.bind("<Button-3>", self._nav_context)
        self.nav.tag_configure("section", foreground=theme.TEXT)
        self.nav.tag_configure("folder", foreground=theme.DIM)
        self.nav.tag_configure("droptarget", background=theme.ACCENT_DIM, foreground=theme.ACCENT)
        navbar = ctk.CTkFrame(nav, fg_color="transparent")
        navbar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        theme.button(navbar, "＋ " + t("lib.playlist"), self._create_playlist, kind="ghost", width=104).pack(side="left")
        icon_button(navbar, "grid", self._create_folder, t("lib.new_folder"), size=32).pack(side="left", padx=(6, 0))
        self.rename_btn = icon_button(navbar, "edit", self._rename_playlist, t("action.rename"), size=32)
        self.rename_btn.pack(side="left", padx=(6, 0))

        # ------------------------------------------------------------- droite : contenu
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(18, 22), pady=(18, 0))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(main, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        self.title_lbl = theme.label(head, t("lib.all_tracks"), 20, theme.TEXT, "bold", anchor="w")
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.sub_lbl = theme.label(head, "", 11, theme.DIM, anchor="w")
        self.sub_lbl.grid(row=1, column=0, sticky="w")
        self.filter = theme.entry(head, t("lib.filter"), width=200)
        self.filter.grid(row=0, column=1, rowspan=2, sticky="e")
        self.filter.bind("<KeyRelease>", lambda _e: self._filter_changed())

        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        self.bar = bar
        self.add_btn = theme.button(bar, t("lib.add_to"), self._add_to, kind="ghost", width=96)
        self.add_btn.pack(side="left")
        self.move_btn = theme.button(bar, t("lib.move_to"), self._move_to, kind="ghost", width=110)
        self.remove_btn = theme.button(bar, t("lib.remove"), self._remove, kind="ghost", width=96)
        self.up_btn = icon_button(bar, "up", lambda: self._move(-1), t("lib.up"), size=32)
        self.down_btn = icon_button(bar, "down", lambda: self._move(+1), t("lib.down"), size=32)
        self.save_btn = theme.button(bar, t("lib.save_order"), self._save_order, kind="primary", width=150)
        self.delete_btn = icon_button(bar, "trash", self._delete, t("lib.delete"), size=32)
        self.delete_btn.configure(border_color=theme.ERR_DIM, hover_color=theme.ERR_DIM,
                                  image=ctk_icon("trash", 18, theme.ERR))
        self.delete_btn.pack(side="right")
        self.tools_btn = icon_button(bar, "menu", self._tools_menu, t("lib.tools"), size=32)
        self.tools_btn.pack(side="right", padx=(0, 6))
        self.harm_btn = theme.button(bar, t("lib.harmonic"), self._toggle_harmonic, kind="ghost", width=110)
        self.harm_btn.configure(image=ctk_icon("key", 16, theme.TEXT), compound="left")
        self.harm_btn.pack(side="right", padx=(0, 6))

        self.banner = ctk.CTkFrame(main, fg_color=theme.ACCENT_DIM, corner_radius=8)
        self.banner_lbl = theme.label(self.banner, "", 11, theme.TEXT, anchor="w")
        self.banner_lbl.pack(side="left", padx=12, pady=6)
        ctk.CTkButton(self.banner, text="", image=ctk_icon("close", 14, theme.TEXT), width=26, height=26,
                      fg_color="transparent", hover_color=theme.BORDER, command=self._clear_harmonic).pack(
            side="right", padx=6)

        self.table = TrackTable(main, self.cols, loader, reorderable=True, badges=True)
        self.table.grid(row=3, column=0, sticky="nsew")
        self.table.drag_out = True
        self.table.set_empty("usb", t("lib.no_drive_title"), t("lib.no_drive_sub"))
        self.table.on_select = lambda _i: self._refresh_buttons()
        self.table.on_double = self._play
        self.table.on_reordered = self._mark_dirty
        self.table.on_sort_changed = lambda *_: self._refresh_buttons()
        self.table.menu_builder = self._menu
        self.table.on_drag_over = self._drag_over
        self.table.on_drop_outside = self._drop_outside
        self.table.tree.bind("<Delete>", lambda _e: self._delete())

        self.status = theme.label(main, "", 11, theme.DIM, anchor="w")
        self.status.grid(row=4, column=0, sticky="ew", pady=(6, 12))

        self.bind("<Configure>", self._resized, add="+")
        controller.on("library", lambda: self.reload())
        controller.on("drive", lambda: self.reload(full=True))
        controller.on("queue", self._mark_playing)
        controller.on("player", lambda kind, _p: self._mark_playing() if kind == "loaded" else None)

    # =============================================================== chargement
    def on_show(self) -> None:
        if self._loaded_for != self._drive_key():
            self.reload(full=True)

    def on_scale(self) -> None:
        super().on_scale()
        self._fill_nav()

    def _resized(self, e: Any) -> None:
        """Volet des playlists : 22 % de la largeur, entre 170 et 260 (unités logiques)."""
        if e.widget is not self:
            return
        logical = e.width / max(theme.ui_factor() * theme._DPI, 0.1)
        width = int(max(170, min(260, logical * 0.22)))
        if abs(width - getattr(self, "_nav_w", 0)) >= 6:
            self._nav_w = width
            self.nav_frame.configure(width=width)

    def _drive_key(self) -> str:
        return str(self.ctrl.drive.root) if self.ctrl.drive else ""

    def reload(self, full: bool = False) -> None:
        """Recharge la base. L'ordre non enregistré n'est jamais écrasé par un rafraîchissement
        automatique (téléchargement terminé…) : seul le volet de gauche est mis à jour."""
        if not self.ctrl.has_library:
            self.playlists, self.all_tracks, self.stats, self._dirty = [], [], {}, False
            self._loaded_for = ""
            self._fill_nav()
            self.table.set_rows([], reset_sort=True)
            self.table.set_empty("usb", t("lib.no_drive_title"), t("lib.no_drive_sub"))
            self._show_header()
            self._refresh_buttons()
            return
        key = self._drive_key()
        if full or not self.all_tracks:
            self.table.show_skeleton(10)

        def ok(data: Dict[str, Any]) -> None:
            if key != self._drive_key() or not self.winfo_exists():
                return
            self._loaded_for = key
            self.playlists, self.all_tracks, self.stats = data["playlists"], data["tracks"], data.get("stats", {})
            if full:
                self.current, self._dirty = ALL, False
            if self.current != ALL and int(self.current[1:]) not in {p.playlist_id for p in self.playlists}:
                self.current, self._dirty = ALL, False
            if self._harmonic is not None:
                self._harmonic = next((x for x in self.all_tracks if x.content_id == self._harmonic.content_id), None)
            self._fill_nav()
            if self._dirty:
                self._show_header()
                return
            self._fill_table()

        self.ctrl.load_library(ok)

    # ----------------------------------------------------------------- navigation
    def _fill_nav(self) -> None:
        self._reverting = True
        self.nav.delete(*self.nav.get_children())
        self._by_iid = {f"p{p.playlist_id}": p for p in self.playlists}
        self.nav.insert("", "end", iid=ALL, text=f"  {t('lib.all_tracks')}  ·  {len(self.all_tracks)}",
                        image=self._nav_icon("music"), tags=("section",))
        children: Dict[int, List[PlaylistInfo]] = {}
        for p in self.playlists:
            children.setdefault(p.parent_id, []).append(p)
        known = {p.playlist_id for p in self.playlists}

        def add(parent_iid: str, parent_id: int) -> None:
            for p in sorted(children.get(parent_id, []), key=lambda q: (q.sequence, q.name.lower())):
                iid = f"p{p.playlist_id}"
                label = f"  {p.name}" if p.is_folder else f"  {p.name}  ·  {p.track_count}"
                self.nav.insert(parent_iid, "end", iid=iid, text=label, open=True,
                                image=self._nav_icon("grid" if p.is_folder else "library"),
                                tags=("folder",) if p.is_folder else ())
                if p.is_folder:
                    add(iid, p.playlist_id)

        add("", 0)
        for orphan in [pid for pid in children if pid != 0 and pid not in known]:
            add("", orphan)  # parent introuvable : à la racine plutôt que perdu
        target = self.current if self.nav.exists(self.current) else ALL
        self.current = target
        self.nav.selection_set(target)
        self.nav.focus(target)
        self._reverting = False

    def _nav_icon(self, name: str) -> Any:
        from PIL import ImageTk

        from ..icons import pil_icon

        cache = self.__dict__.setdefault("_nav_icons", {})
        size = theme.tkpx(16)
        key = (name, size)
        if key not in cache:
            cache[key] = ImageTk.PhotoImage(pil_icon(name, size, theme.DIM))
        return cache[key]

    def _nav_selected(self, _e: Any = None) -> None:
        if self._reverting:
            return
        sel = self.nav.selection()
        if not sel or sel[0] == self.current:
            return
        new = sel[0]
        if self._dirty:
            def revert() -> None:
                self._reverting = True
                self.nav.selection_set(self.current)
                self._reverting = False

            def discard() -> None:
                self._dirty = False
                self._goto(new)

            revert()
            ConfirmDialog(self, t("lib.unsaved_title"), t("lib.unsaved_msg"), discard,
                          confirm_text=t("lib.unsaved_leave"), danger=True)
            return
        self._goto(new)

    def _goto(self, iid: str) -> None:
        self.current = iid
        self._reverting = True
        self.nav.selection_set(iid)
        self._reverting = False
        self.filter.delete(0, "end")
        self.table.set_filter("")
        self._fill_table()

    @property
    def playlist(self) -> Optional[PlaylistInfo]:
        return self._by_iid.get(self.current)

    @property
    def in_playlist(self) -> bool:
        p = self.playlist
        return p is not None and not p.is_folder

    # -------------------------------------------------------- glisser vers une playlist
    def _nav_target(self, x_root: int, y_root: int) -> Optional[PlaylistInfo]:
        nx, ny = self.nav.winfo_rootx(), self.nav.winfo_rooty()
        if not (0 <= x_root - nx < self.nav.winfo_width() and 0 <= y_root - ny < self.nav.winfo_height()):
            return None
        p = self._by_iid.get(self.nav.identify_row(y_root - ny))
        return p if p is not None and p.is_editable else None

    def _drag_over(self, _ids: List[str], x_root: int, y_root: int) -> bool:
        target = self._nav_target(x_root, y_root) if x_root >= 0 else None
        iid = f"p{target.playlist_id}" if target else None
        if iid != self._drop_target:
            if self._drop_target and self.nav.exists(self._drop_target):
                p = self._by_iid.get(self._drop_target)
                self.nav.item(self._drop_target, tags=("folder",) if p and p.is_folder else ())
            self._drop_target = iid
            if iid:
                self.nav.item(iid, tags=("droptarget",))
        return target is not None

    def _drop_outside(self, ids: List[str], x_root: int, y_root: int) -> None:
        target = self._nav_target(x_root, y_root)
        self._drag_over([], -1, -1)
        if target is None:
            return
        cids = [int(i) for i in ids]
        if self.in_playlist and self.playlist and self.playlist.playlist_id == target.playlist_id:
            return
        self.ctrl.add_to_playlists(cids, [target.playlist_id])

    # -------------------------------------------------------------------- tableau
    def _track_row(self, x: LibraryTrack, pos: bool) -> Row:
        lib = self.ctrl.library
        key = f"lib:{x.content_id}:{x.artwork_path or ''}"

        def load() -> Any:
            return file_cover(lib.artwork_file(x), lib.absolute_path(x), key).loader()

        code = x.camelot
        return Row(
            str(x.content_id),
            {"pos": x.sequence if pos else "", "title": x.title, "artist": x.artist, "album": x.album or "",
             "bpm": f"{x.bpm:.0f}" if x.bpm else "—", "duration": format_duration(x.duration_seconds),
             "format": _fmt(x), "added": (x.date_added or "")[:10], "key": code or ""},
            CoverRef(key, load), (), x, badge=(code, theme.camelot_color(code)) if code else ("", theme.FAINT),
        )

    def _fill_table(self) -> None:
        self._show_header()
        self._refresh_buttons()
        if self.current == ALL or self.playlist is None or self.playlist.is_folder:
            tracks = self.all_tracks if self.current == ALL else []
            self._apply_rows(tracks, pos=False)
            if self.current == ALL:
                self.table.set_empty("music", t("lib.empty_all_title"), t("lib.empty_all_sub"),
                                     (t("tab.search"), lambda: self.ctrl._emit("navigate", "search")))
            else:
                self.table.set_empty("grid", t("lib.empty_folder_title"), t("lib.empty_folder_sub"))
            return
        pid, token = self.playlist.playlist_id, self.current
        self.table.show_skeleton(6)

        def ok(tracks: List[LibraryTrack]) -> None:
            if token != self.current or self._dirty:
                return
            self._apply_rows(tracks, pos=True)
            self.table.set_empty("library", t("lib.empty_playlist_title"), t("lib.empty_playlist_sub"))

        self.ctrl.playlist_tracks(pid, ok)

    def _apply_rows(self, tracks: List[LibraryTrack], pos: bool) -> None:
        playlist = self.in_playlist
        self.table.reorderable = playlist and bool(self.playlist and self.playlist.is_editable)
        self.table.set_display_columns([c.key for c in self.cols if c.key != "pos" or playlist])
        self.table.set_rows([self._track_row(x, pos) for x in tracks], reset_sort=True, keep_selection=False)
        self._dirty = False
        self._apply_harmonic()
        self._mark_playing()
        self._refresh_buttons()
        self._show_header()

    def _show_header(self) -> None:
        if self.current == ALL:
            st = self.stats.get(0)
            self.title_lbl.configure(text=t("lib.all_tracks"))
            parts = [plural("lib.tracks_one", "lib.tracks_many", len(self.all_tracks))]
            if st is not None and st.total_seconds:
                parts.append(total_duration(st.total_seconds))
            if st is not None and st.last_added:
                parts.append(t("lib.last_added", date=st.last_added))
            self.sub_lbl.configure(text="  ·  ".join(parts))
        elif self.playlist is not None:
            p = self.playlist
            st = self.stats.get(p.playlist_id)
            kind = t("lib.kind_folder") if p.is_folder else (t("lib.kind_smart") if not p.is_editable else t("lib.kind_playlist"))
            parts = [kind]
            if not p.is_folder:
                n = self.table.total if self.in_playlist and not self._loading else p.track_count
                parts.append(plural("lib.tracks_one", "lib.tracks_many", n))
                if st is not None and st.total_seconds:
                    parts.append(total_duration(st.total_seconds))
                if st is not None and st.last_added:
                    parts.append(t("lib.updated", date=st.last_added))
            self.title_lbl.configure(text=p.name)
            self.sub_lbl.configure(text="  ·  ".join(parts))
        else:
            self.title_lbl.configure(text=t("tab.library"))
            self.sub_lbl.configure(text="")

    def _filter_changed(self) -> None:
        self.table.set_filter(self.filter.get())
        self._refresh_buttons()

    def _mark_dirty(self) -> None:
        for n, iid in enumerate(self.table.displayed_iids(), start=1):  # N° = nouvelle position
            self.table.update_values(iid, pos=n)
        self._dirty = True
        self._refresh_buttons()

    def _mark_playing(self) -> None:
        item = self.ctrl.current_item
        playing = str(item.item.content_id) if item is not None and item.kind == "library" else None
        for row in self.table.all_rows():
            want = row.iid == playing
            has = "playing" in row.tags
            if want != has:
                self.table.set_tags(row.iid, *(("playing",) if want else ()))

    # ------------------------------------------------------------- filtre harmonique
    def _toggle_harmonic(self) -> None:
        if self._harmonic is not None:
            self._clear_harmonic()
            return
        base = self._selected_tracks()[:1]
        if not base:
            item = self.ctrl.current_item
            base = [item.item] if item is not None and item.kind == "library" else []
        if not base or not base[0].camelot:
            self.ctrl.message("info", t("lib.harmonic_pick"))
            return
        self.set_harmonic(base[0])

    def set_harmonic(self, track: LibraryTrack) -> None:
        self._harmonic = track
        self._apply_harmonic()
        self._refresh_buttons()

    def _clear_harmonic(self) -> None:
        self._harmonic = None
        self._apply_harmonic()
        self._refresh_buttons()

    def _apply_harmonic(self) -> None:
        base = self._harmonic
        if base is None or not base.camelot:
            self.table.row_filter = None
            self.banner.grid_forget()
        else:
            keys = set(neighbors(base.camelot))
            bpm = base.bpm
            self.table.row_filter = lambda r: bool(r.data and r.data.camelot in keys)
            text = t("lib.harmonic_banner", code=base.camelot, title=base.title, keys=", ".join(neighbors(base.camelot)))
            if bpm:
                text += "  ·  " + t("lib.harmonic_bpm", bpm=f"{bpm:.0f}")
            self.banner_lbl.configure(text=text)
            self.banner.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.table.refilter()

    # -------------------------------------------------------------------- boutons
    def _refresh_buttons(self) -> None:
        sel = self.table.selected_iids()
        playlist = self.in_playlist
        editable = playlist and bool(self.playlist and self.playlist.is_editable)
        for b in (self.move_btn, self.remove_btn, self.save_btn, self.down_btn, self.up_btn):
            b.pack_forget()
        if playlist:
            self.move_btn.pack(side="left", padx=(8, 0))
            self.remove_btn.pack(side="left", padx=(8, 0))
            if editable:
                self.up_btn.pack(side="left", padx=(16, 0))
                self.down_btn.pack(side="left", padx=(4, 0))
                self.save_btn.pack(side="left", padx=(8, 0))
        has = bool(sel) and self.ctrl.has_library
        self.add_btn.configure(state="normal" if has else "disabled")
        self.delete_btn.configure(state="normal" if has else "disabled")
        self.move_btn.configure(state="normal" if has and editable else "disabled")
        self.remove_btn.configure(state="normal" if has and editable else "disabled")
        can_move = has and editable and not self.table.filter_active
        self.up_btn.configure(state="normal" if can_move else "disabled")
        self.down_btn.configure(state="normal" if can_move else "disabled")
        can_save = editable and not self.table.filter_active and (self._dirty or self.table.sort_active)
        self.save_btn.configure(state="normal" if can_save else "disabled",
                                text=t("lib.save_order") + (" •" if self._dirty else ""))
        rename_ok = self.playlist is not None and (self.playlist.is_editable or self.playlist.is_folder)
        self.rename_btn.configure(state="normal" if rename_ok else "disabled")
        on = self._harmonic is not None
        self.harm_btn.configure(fg_color=theme.ACCENT_DIM if on else "transparent",
                                text_color=theme.ACCENT if on else theme.TEXT,
                                image=ctk_icon("key", 16, theme.ACCENT if on else theme.TEXT))
        hint = ""
        if playlist and editable:
            hint = t("lib.hint_reorder") if not self.table.filter_active else t("lib.hint_clear_filter")
        elif self.ctrl.has_library and self.table.total:
            hint = t("lib.hint_drag")
        self.status.configure(text=hint)

    def _ids(self) -> List[int]:
        return [int(i) for i in self.table.selected_iids()]

    def _selected_tracks(self) -> List[LibraryTrack]:
        return [r.data for r in self.table.selected_rows() if r.data is not None]

    def _move(self, delta: int) -> None:
        self.table.move_selected(delta)

    def _play(self, iid: str) -> None:
        rows = self.table.displayed_rows()
        tracks = [r.data for r in rows if r.data is not None]
        row = self.table.row(iid)
        if row is not None and row.data in tracks:
            self.ctrl.play_queue(tracks, tracks.index(row.data))

    # --------------------------------------------------------------------- actions
    def _save_order(self) -> None:
        p = self.playlist
        if p is None or self.table.filter_active:
            return
        ids = [int(i) for i in self.table.displayed_iids()]
        if not ids:
            return

        def done(_r: Any) -> None:
            self._dirty = False
            self._fill_table()

        self._dirty = False
        self.ctrl.save_order(p.playlist_id, ids, ok=done)

    def _add_to(self) -> None:
        ids = self._ids()
        if not ids:
            return
        exclude = [self.playlist.playlist_id] if self.in_playlist else []
        PlaylistPicker(self, self.ctrl, t("lib.add_to"), t("lib.add_n", n=len(ids)),
                       on_ok=lambda pids: self.ctrl.add_to_playlists(ids, pids), multi=True, exclude=exclude,
                       subtitle=plural("lib.selected_one", "lib.selected_many", len(ids)))

    def _move_to(self) -> None:
        ids, src = self._ids(), self.playlist
        if not ids or src is None:
            return
        PlaylistPicker(self, self.ctrl, t("lib.move_to"), t("lib.move"),
                       on_ok=lambda pids: self.ctrl.move_tracks(ids, src.playlist_id, pids[0]), multi=False,
                       exclude=[src.playlist_id], subtitle=t("lib.move_sub", n=len(ids), name=src.name))

    def _remove(self) -> None:
        ids, p = self._ids(), self.playlist
        if ids and p is not None:
            self.ctrl.remove_from_playlist(p.playlist_id, ids)

    def _delete(self) -> None:
        ids = self._ids()
        if not ids or not self.ctrl.has_library:
            return
        names = [r.values["title"] for r in self.table.selected_rows()][:3]
        what = t("fmt.quoted", text=names[0]) if len(ids) == 1 else t("lib.delete_many", n=len(ids), names=", ".join(names))
        ConfirmDialog(self, t("lib.delete_title"), t("lib.delete_msg", what=what),
                      lambda: self.ctrl.delete_tracks(ids, True), confirm_text=t("action.delete"), danger=True,
                      detail=t("lib.delete_detail"))

    def _create_playlist(self) -> None:
        parent = self.playlist.playlist_id if self.playlist is not None and self.playlist.is_folder else 0
        TextInputDialog(self, t("lib.new_playlist"), t("lib.playlist_name"),
                        lambda name: self.ctrl.create_playlist(name, parent), confirm_text=t("action.create"))

    def _create_folder(self) -> None:
        parent = self.playlist.playlist_id if self.playlist is not None and self.playlist.is_folder else 0
        TextInputDialog(self, t("lib.new_folder"), t("lib.folder_name"),
                        lambda name: self.ctrl.create_folder(name, parent), confirm_text=t("action.create"))

    def _rename_playlist(self) -> None:
        p = self.playlist
        if p is not None and (p.is_editable or p.is_folder):
            TextInputDialog(self, t("action.rename"), t("lib.new_name"),
                            lambda name: self.ctrl.rename_playlist(p.playlist_id, name),
                            initial=p.name, confirm_text=t("action.rename"))

    def _delete_playlist(self) -> None:
        p = self.playlist
        if p is None:
            return
        detail = (t("lib.delete_folder_detail") + " " if p.is_folder else "") + t("lib.delete_playlist_detail")
        ConfirmDialog(self, t("lib.delete_playlist_title"), t("lib.delete_playlist_msg", name=p.name),
                      lambda: self.ctrl.delete_playlist(p.playlist_id), confirm_text=t("action.delete"), danger=True,
                      detail=detail)

    # ------------------------------------------------------------- analyse, grille, doublons
    def _analyse(self, tracks: Optional[List[LibraryTrack]] = None) -> None:
        if not self.ctrl.has_library:
            return
        from ..analysis_dialog import AnalysisDialog

        AnalysisDialog(self, self.ctrl, tracks)

    def _edit_grid(self) -> None:
        tracks = self._selected_tracks()
        if not tracks:
            return
        if not tracks[0].is_analysed:
            self.ctrl.message("info", t("grid.not_analysed"))
            return
        from ..grid_editor import GridEditor

        GridEditor(self, self.ctrl, tracks[0])

    def _edit_metadata(self) -> None:
        tracks = self._selected_tracks()
        if not tracks:
            return
        from ..dialogs import MetadataDialog

        x = tracks[0]
        MetadataDialog(self, x.title, x.artist,
                       lambda title, artist: self.ctrl.update_metadata(x.content_id, title, artist))

    def _duplicates(self) -> None:
        if not self.ctrl.has_library:
            return
        from ..duplicates_dialog import DuplicatesDialog

        DuplicatesDialog(self, self.ctrl)

    def _tools_menu(self) -> None:
        sel = self._selected_tracks()
        entries: list = []
        if sel:
            entries.append((t("lib.analyse_selection", n=len(sel)), lambda: self._analyse(sel)))
        entries += [(t("lib.analyse_missing"), lambda: self._analyse(None)), None]
        if len(sel) == 1:
            entries += [(t("lib.edit_grid"), self._edit_grid), (t("action.edit_metadata"), self._edit_metadata)]
        entries.append((t("lib.find_duplicates"), self._duplicates))
        b = self.tools_btn
        popup_menu(b, entries, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    # ---------------------------------------------------------------- menus contextuels
    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        entries: list = [(t("action.listen"), lambda: self._play(iids[0])), None, (t("lib.add_to"), self._add_to)]
        if self.in_playlist and self.playlist.is_editable:
            entries += [(t("lib.move_to"), self._move_to), (t("lib.remove"), self._remove)]
        tracks = self._selected_tracks()
        entries += [None, (t("lib.analyse_selection", n=len(iids)), lambda: self._analyse(tracks))]
        if len(tracks) == 1:
            entries += [(t("lib.edit_grid"), self._edit_grid), (t("action.edit_metadata"), self._edit_metadata)]
            if tracks[0].camelot:
                entries.append((t("lib.show_compatible", code=tracks[0].camelot), lambda: self.set_harmonic(tracks[0])))
        entries += [None, (t("lib.delete") + "…", self._delete)]
        return entries

    def _nav_context(self, e: Any) -> None:
        iid = self.nav.identify_row(e.y)
        if not iid or iid == ALL:
            return
        self.nav.selection_set(iid)
        p = self._by_iid.get(iid)
        if p is None or not p.is_editable and not p.is_folder:
            return
        popup_menu(self.nav, [(t("action.rename") + "…", self._rename_playlist),
                              (t("action.delete") + "…", self._delete_playlist)], e.x_root, e.y_root)
