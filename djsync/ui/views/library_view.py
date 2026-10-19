"""Vue Bibliothèque (« mini-Rekordbox ») : Collection (tous les sons de la clé) + playlists.

Gauche : « Collection » puis l'arbre des dossiers/playlists. Droite : tableau triable.
Dans une playlist : réordonner (boutons Haut/Bas ou glisser-déposer) puis « Enregistrer l'ordre »
(champ `sequence`). Chaque écriture déclenche d'abord une sauvegarde de exportLibrary.db
(faite par la couche DB).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from tkinter import ttk

from ...models import LibraryTrack, PlaylistInfo, format_duration
from .. import theme
from ..covers import CoverRef, file_cover
from ..dialogs import ConfirmDialog, PlaylistPicker, TextInputDialog
from ..widgets import Column, Row, TrackTable
from .common import View

ALL = "all"
_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


def _fmt(track: LibraryTrack) -> str:
    return _FORMATS.get(track.file_type) or Path(track.path).suffix.lstrip(".").upper()


class LibraryView(View):
    title = "Bibliothèque"

    COLS = [
        Column("pos", "N°", 46, "e", sort=lambda r: r.data.sequence if r.data else 0),
        Column("title", "Titre", 280, stretch=True),
        Column("artist", "Artiste", 190),
        Column("album", "Album", 150),
        Column("bpm", "BPM", 60, "e", sort=lambda r: r.data.bpm or None if r.data else None),
        Column("duration", "Durée", 70, "e", sort=lambda r: r.data.duration_seconds if r.data else 0),
        Column("format", "Format", 64, "center"),
        Column("added", "Ajouté", 90, "center", sort=lambda r: r.data.date_added if r.data else ""),
    ]

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.playlists: List[PlaylistInfo] = []
        self.all_tracks: List[LibraryTrack] = []
        self.current: str = ALL            # ALL ou "p<id>"
        self._dirty = False
        self._loaded_for: Optional[str] = None
        self._reverting = False
        self._by_iid: Dict[str, PlaylistInfo] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ------------------------------------------------------------ gauche : navigation
        nav = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0, width=theme.px(250))
        nav.grid(row=0, column=0, sticky="ns")
        nav.grid_propagate(False)
        nav.grid_rowconfigure(1, weight=1)
        nav.grid_columnconfigure(0, weight=1)
        theme.label(nav, "BIBLIOTHÈQUE", 10, theme.FAINT, "bold", anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(18, 6))
        self.nav = ttk.Treeview(nav, show="tree", selectmode="browse", style="Nav.Treeview")
        self.nav.grid(row=1, column=0, sticky="nsew", padx=(6, 0))
        sb = ctk.CTkScrollbar(nav, command=self.nav.yview, fg_color=theme.SURFACE, button_color=theme.BORDER,
                              width=theme.px(10))
        sb.grid(row=1, column=1, sticky="ns")
        self.nav.configure(yscrollcommand=sb.set)
        self.nav.bind("<<TreeviewSelect>>", self._nav_selected)
        self.nav.bind("<Button-3>", self._nav_context)
        self.nav.tag_configure("section", foreground=theme.TEXT)
        navbar = ctk.CTkFrame(nav, fg_color="transparent")
        navbar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        theme.button(navbar, "＋ Playlist", self._create_playlist, kind="ghost", width=theme.px(110)).pack(side="left")
        self.rename_btn = theme.button(navbar, "Renommer", self._rename_playlist, kind="flat", width=theme.px(80))
        self.rename_btn.pack(side="left", padx=(4, 0))

        # ------------------------------------------------------------- droite : contenu
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(20, 24), pady=(20, 0))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(main, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        self.title_lbl = theme.label(head, "Collection", 20, theme.TEXT, "bold", anchor="w")
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.sub_lbl = theme.label(head, "", 11, theme.DIM, anchor="w")
        self.sub_lbl.grid(row=1, column=0, sticky="w")
        self.filter = theme.entry(head, "Filtrer…", width=theme.px(220))
        self.filter.grid(row=0, column=1, rowspan=2, sticky="e")
        self.filter.bind("<KeyRelease>", lambda _e: self._filter_changed())

        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        self.add_btn = theme.button(bar, "Ajouter à…", self._add_to, kind="ghost", width=theme.px(100))
        self.add_btn.pack(side="left")
        self.move_btn = theme.button(bar, "Déplacer vers…", self._move_to, kind="ghost", width=theme.px(120))
        self.remove_btn = theme.button(bar, "Retirer de la playlist", self._remove, kind="ghost", width=theme.px(160))
        self.delete_btn = theme.button(bar, "Supprimer de la clé", self._delete, kind="danger", width=theme.px(150))
        self.delete_btn.pack(side="right")
        self.save_btn = theme.button(bar, "Enregistrer l'ordre", self._save_order, kind="primary", width=theme.px(180))
        self.down_btn = theme.button(bar, "Bas", lambda: self._move(+1), kind="ghost", width=theme.px(56))
        self.up_btn = theme.button(bar, "Haut", lambda: self._move(-1), kind="ghost", width=theme.px(56))

        self.table = TrackTable(main, self.COLS, loader, reorderable=True)
        self.table.grid(row=2, column=0, sticky="nsew")
        self.table.set_empty_text("Aucune clé connectée.")
        self.table.on_select = lambda _i: self._refresh_buttons()
        self.table.on_double = self._play
        self.table.on_reordered = self._mark_dirty
        self.table.on_sort_changed = lambda *_: self._refresh_buttons()
        self.table.menu_builder = self._menu
        self.table.tree.bind("<Delete>", lambda _e: self._delete())

        self.status = theme.label(main, "", 11, theme.DIM, anchor="w")
        self.status.grid(row=3, column=0, sticky="ew", pady=(6, 12))

        controller.on("library", lambda: self.reload())
        controller.on("drive", lambda: self.reload(full=True))

    # =============================================================== chargement
    def on_show(self) -> None:
        if self._loaded_for != self._drive_key():
            self.reload(full=True)

    def _drive_key(self) -> str:
        return str(self.ctrl.drive.root) if self.ctrl.drive else ""

    def reload(self, full: bool = False) -> None:
        """Recharge la base. L'ordre non enregistré n'est jamais écrasé par un rafraîchissement
        automatique (téléchargement terminé…) : seul le volet de gauche est mis à jour."""
        if not self.ctrl.has_library:
            self.playlists, self.all_tracks, self._dirty = [], [], False
            self._loaded_for = ""
            self._fill_nav()
            self.table.set_rows([], reset_sort=True)
            self.table.set_empty_text("Aucune clé connectée : branchez-la ou choisissez-la dans Paramètres.")
            self._show_header()
            self._refresh_buttons()
            return
        key = self._drive_key()

        def ok(data: Dict[str, Any]) -> None:
            if key != self._drive_key():
                return
            self._loaded_for = key
            self.playlists, self.all_tracks = data["playlists"], data["tracks"]
            if full:
                self.current, self._dirty = ALL, False
            if self.current != ALL and int(self.current[1:]) not in {p.playlist_id for p in self.playlists}:
                self.current, self._dirty = ALL, False
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
        self.nav.insert("", "end", iid=ALL, text=f"  Collection  ·  {len(self.all_tracks)}", tags=("section",))
        children: Dict[int, List[PlaylistInfo]] = {}
        for p in self.playlists:
            children.setdefault(p.parent_id, []).append(p)
        known = {p.playlist_id for p in self.playlists}

        def add(parent_iid: str, parent_id: int) -> None:
            for p in sorted(children.get(parent_id, []), key=lambda q: (q.sequence, q.name.lower())):
                iid = f"p{p.playlist_id}"
                label = f"  {p.name}" if p.is_folder else f"  {p.name}  ·  {p.track_count}"
                self.nav.insert(parent_iid, "end", iid=iid, text=label, open=True)
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
            ConfirmDialog(self, "Ordre non enregistré", "Quitter cette playlist sans enregistrer le nouvel ordre ?",
                          discard, confirm_text="Quitter sans enregistrer", danger=True)
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

    # -------------------------------------------------------------------- tableau
    def _track_row(self, t: LibraryTrack, pos: bool) -> Row:
        lib = self.ctrl.library
        key = f"lib:{t.content_id}:{t.artwork_path or ''}"

        def load() -> Any:
            return file_cover(lib.artwork_file(t), lib.absolute_path(t), key).loader()

        return Row(
            str(t.content_id),
            {"pos": t.sequence if pos else "", "title": t.title, "artist": t.artist, "album": t.album or "",
             "bpm": f"{t.bpm:.0f}" if t.bpm else "—", "duration": format_duration(t.duration_seconds),
             "format": _fmt(t), "added": (t.date_added or "")[:10]},
            CoverRef(key, load), (), t,
        )

    def _fill_table(self) -> None:
        self._show_header()
        self._refresh_buttons()
        if self.current == ALL or self.playlist is None or self.playlist.is_folder:
            tracks = self.all_tracks if self.current == ALL else []
            self._apply_rows(tracks, pos=False)
            self.table.set_empty_text(
                "La clé ne contient encore aucun son." if self.current == ALL
                else "Sélectionnez une playlist dans ce dossier.")
            return
        pid, token = self.playlist.playlist_id, self.current

        def ok(tracks: List[LibraryTrack]) -> None:
            if token != self.current or self._dirty:
                return
            self._apply_rows(tracks, pos=True)
            self.table.set_empty_text("Playlist vide : ajoutez des sons depuis la Collection ou un téléchargement.")

        self.ctrl.playlist_tracks(pid, ok)

    def _apply_rows(self, tracks: List[LibraryTrack], pos: bool) -> None:
        playlist = self.in_playlist
        self.table.reorderable = playlist and bool(self.playlist and self.playlist.is_editable)
        self.table.set_display_columns(
            [c.key for c in self.COLS if c.key != "pos" or playlist])
        self.table.set_rows([self._track_row(t, pos) for t in tracks], reset_sort=True, keep_selection=False)
        self._dirty = False
        self._refresh_buttons()
        self._show_header()

    def _show_header(self) -> None:
        if self.current == ALL:
            self.title_lbl.configure(text="Collection")
            self.sub_lbl.configure(text=f"{len(self.all_tracks)} son(s) sur la clé {self.ctrl.drive_label}")
        elif self.playlist is not None:
            p = self.playlist
            n = self.table.total if self.in_playlist else p.track_count
            kind = "Dossier" if p.is_folder else ("Playlist intelligente (lecture seule)" if not p.is_editable else "Playlist")
            self.title_lbl.configure(text=p.name)
            self.sub_lbl.configure(text=f"{kind}" + ("" if p.is_folder else f"  ·  {n} son(s)"))
        else:
            self.title_lbl.configure(text="Bibliothèque")
            self.sub_lbl.configure(text="")

    def _filter_changed(self) -> None:
        self.table.set_filter(self.filter.get())
        self._refresh_buttons()

    def _mark_dirty(self) -> None:
        for n, iid in enumerate(self.table.displayed_iids(), start=1):  # N° = nouvelle position
            self.table.update_values(iid, pos=n)
        self._dirty = True
        self._refresh_buttons()

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
                self.up_btn.pack(side="left", padx=(20, 0))
                self.down_btn.pack(side="left", padx=(4, 0))
                self.save_btn.pack(side="left", padx=(12, 0))
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
                                text="Enregistrer l'ordre •" if self._dirty else "Enregistrer l'ordre")
        rename_ok = self.playlist is not None and self.playlist.is_editable
        self.rename_btn.configure(state="normal" if rename_ok else "disabled")
        hint = ""
        if playlist and editable:
            hint = ("Glissez les lignes ou utilisez Haut / Bas, puis « Enregistrer l'ordre »."
                    if not self.table.filter_active else "Effacez le filtre pour réordonner.")
        self.status.configure(text=hint)

    def _ids(self) -> List[int]:
        return [int(i) for i in self.table.selected_iids()]

    def _move(self, delta: int) -> None:
        self.table.move_selected(delta)

    def _play(self, iid: str) -> None:
        row = self.table.row(iid)
        if row is not None and row.data is not None:
            self.ctrl.play_library_track(row.data)

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
        PlaylistPicker(self, self.ctrl, "Ajouter à…", f"Ajouter ({len(ids)})",
                       on_ok=lambda pids: self.ctrl.add_to_playlists(ids, pids), multi=True, exclude=exclude,
                       subtitle=f"{len(ids)} son(s) sélectionné(s).")

    def _move_to(self) -> None:
        ids, src = self._ids(), self.playlist
        if not ids or src is None:
            return
        PlaylistPicker(self, self.ctrl, "Déplacer vers…", "Déplacer",
                       on_ok=lambda pids: self.ctrl.move_tracks(ids, src.playlist_id, pids[0]), multi=False,
                       exclude=[src.playlist_id], subtitle=f"{len(ids)} son(s) quittent « {src.name} ».")

    def _remove(self) -> None:
        ids, p = self._ids(), self.playlist
        if ids and p is not None:
            self.ctrl.remove_from_playlist(p.playlist_id, ids)

    def _delete(self) -> None:
        ids = self._ids()
        if not ids or not self.ctrl.has_library:
            return
        names = [r.values["title"] for r in self.table.selected_rows()][:3]
        what = f"« {names[0]} »" if len(ids) == 1 else f"{len(ids)} sons ({', '.join(names)}…)"
        ConfirmDialog(
            self, "Supprimer de la clé", f"Supprimer {what} de la clé USB ?",
            lambda: self.ctrl.delete_tracks(ids, True), confirm_text="Supprimer", danger=True,
            detail="Le son est retiré de toutes les playlists ET le fichier audio est effacé de la clé. "
                   "Une sauvegarde de la base est faite avant la modification.")

    def _create_playlist(self) -> None:
        parent = self.playlist.playlist_id if self.playlist is not None and self.playlist.is_folder else 0
        TextInputDialog(self, "Nouvelle playlist", "Nom de la playlist",
                        lambda name: self.ctrl.create_playlist(name, parent), confirm_text="Créer")

    def _rename_playlist(self) -> None:
        p = self.playlist
        if p is not None and p.is_editable:
            TextInputDialog(self, "Renommer", "Nouveau nom", lambda name: self.ctrl.rename_playlist(p.playlist_id, name),
                            initial=p.name, confirm_text="Renommer")

    def _delete_playlist(self) -> None:
        p = self.playlist
        if p is None:
            return
        detail = ("Le dossier et toutes les playlists qu'il contient seront supprimés. " if p.is_folder else "") + \
                 "Les sons restent dans la Collection et sur la clé."
        ConfirmDialog(self, "Supprimer la playlist", f"Supprimer « {p.name} » ?",
                      lambda: self.ctrl.delete_playlist(p.playlist_id), confirm_text="Supprimer", danger=True,
                      detail=detail)

    # ---------------------------------------------------------------- menus contextuels
    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        entries: list = [("Écouter", lambda: self._play(iids[0])), None, ("Ajouter à…", self._add_to)]
        if self.in_playlist and self.playlist.is_editable:
            entries += [("Déplacer vers…", self._move_to), ("Retirer de la playlist", self._remove)]
        entries += [None, ("Supprimer de la clé…", self._delete)]
        return entries

    def _nav_context(self, e: Any) -> None:
        import tkinter as tk

        iid = self.nav.identify_row(e.y)
        if not iid or iid == ALL:
            return
        self.nav.selection_set(iid)
        p = self._by_iid.get(iid)
        if p is None or not p.is_editable and not p.is_folder:
            return
        menu = tk.Menu(self.nav, tearoff=0, bg=theme.ELEV, fg=theme.TEXT, activebackground=theme.ACCENT_DIM,
                       activeforeground=theme.TEXT, bd=0, font=(theme.FAMILY, 10))
        menu.add_command(label="Renommer…", command=self._rename_playlist)
        menu.add_command(label="Supprimer…", command=self._delete_playlist)
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()
