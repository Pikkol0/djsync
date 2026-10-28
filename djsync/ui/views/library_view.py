"""Vue Bibliothèque (« mini-Rekordbox ») : « Tous les titres », « Non analysés », dossiers et playlists.

Gauche : arbre de navigation (nombre de titres). Glisser des titres du tableau sur une playlist
de l'arbre les y ajoute. Droite : en-tête (nombre de titres, durée totale, dernier ajout), barre
d'outils, tableau triable (colonne « Key » à la couleur Camelot). Dans une playlist : réordonner
(glisser ou ↑ / ↓) puis « Enregistrer l'ordre ». Filtre harmonique : ne garder que les titres
compatibles (même clé, ±1, relative) avec le titre choisi. « Non analysés » : analyse en
arrière-plan (file commune du contrôleur), progression, arrêt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QProgressBar, QSplitter, QTreeWidget, QTreeWidgetItem, QWidget,
)

from ...core.camelot import neighbors
from ...i18n import plural, t
from ...models import LibraryTrack, PlaylistInfo, format_duration, source_from_url
from .. import theme
from ..dialogs import ConfirmDialog, PlaylistPicker, TextInputDialog
from ..table import MIME_IDS, camelot_sort, popup_menu
from ..icons import qicon
from ..widgets import (
    Column, Row, TrackTable, button, hbox, icon_button, icon_label, label, line_edit, panel, restyle, vbox,
)
from .common import focus_list, View

ALL = "all"
TODO = "todo"             # titres pas encore analysés
_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


def _fmt(track: LibraryTrack) -> str:
    return _FORMATS.get(track.file_type) or Path(track.path).suffix.lstrip(".").upper()


EXTRA_COLUMNS = ("genre", "year", "label", "bitrate", "rate", "rating", "color", "plays", "created", "size",
                 "comment", "path")
# Couleurs des sons Rekordbox (identifiants 1 à 8, même ordre dans exportLibrary.db et master.db)
TRACK_COLORS = {1: "#F06EB4", 2: "#E5464A", 3: "#F08C2E", 4: "#E8D23C", 5: "#4CC38A", 6: "#3CC8D2",
                7: "#3C78E6", 8: "#9A5BE0"}


def extra_values(x: LibraryTrack) -> Dict[str, Any]:
    """1.3.1 (C37) : valeurs affichées des colonnes de métadonnées."""
    color = TRACK_COLORS.get(x.color)
    out: Dict[str, Any] = {
        "genre": x.genre, "year": str(x.year) if x.year else "", "label": x.label,
        "bitrate": t("unit.kbps", n=x.bitrate) if x.bitrate else "",
        "rate": t("unit.khz", n=f"{x.sample_rate / 1000:g}") if x.sample_rate else "",
        "rating": "★" * x.rating + "☆" * (5 - x.rating) if x.rating else "",
        "color": t(f"color.{x.color}") if color else "",
        "plays": str(x.play_count) if x.play_count else "",
        "created": x.created, "size": t("unit.mb", n=f"{x.file_size / 1e6:.1f}") if x.file_size else "",
        "comment": x.comment, "path": x.path,
    }
    if color:
        out["color__dot"] = color
    return out


def total_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return t("lib.duration_hm", h=h, m=m) if h else t("lib.duration_m", m=m)


class NavTree(QTreeWidget):
    """Arbre de navigation ; accepte les titres glissés depuis le tableau (ajout à une playlist)."""

    def __init__(self, view: "LibraryView") -> None:
        super().__init__()
        self.view = view
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.setIconSize(QSize(theme.px(16), theme.px(16)))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setIndentation(theme.px(14))
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def _target(self, e: Any) -> Optional[PlaylistInfo]:
        item = self.itemAt(e.position().toPoint())
        if item is None:
            return None
        p = self.view._by_iid.get(item.data(0, Qt.UserRole))
        return p if p is not None and p.is_editable else None

    def dragEnterEvent(self, e: Any) -> None:    # noqa: N802
        if e.mimeData().hasFormat(MIME_IDS):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e: Any) -> None:     # noqa: N802
        target = self._target(e)
        if target is not None:
            e.setDropAction(Qt.CopyAction)
            e.accept()
            item = self.itemAt(e.position().toPoint())
            self.setCurrentItem(item)
        else:
            e.ignore()

    def dragLeaveEvent(self, e: Any) -> None:    # noqa: N802
        self.view._select_nav(self.view.current)

    def dropEvent(self, e: Any) -> None:         # noqa: N802
        target = self._target(e)
        self.view._select_nav(self.view.current)
        if target is None:
            e.ignore()
            return
        e.setDropAction(Qt.CopyAction)
        e.accept()
        ids = [int(i) for i in bytes(e.mimeData().data(MIME_IDS)).decode().split(",") if i]
        self.view._drop_on(target, ids)


class LibraryView(View):
    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, controller, loader)
        self.playlists: List[PlaylistInfo] = []
        self.all_tracks: List[LibraryTrack] = []
        self.stats: Dict[int, Any] = {}
        self.current: str = ALL            # ALL, TODO ou "p<id>"
        self._dirty = False
        self._loaded_for: Optional[str] = None
        self._reverting = False
        self._by_iid: Dict[str, PlaylistInfo] = {}
        self._items: Dict[str, QTreeWidgetItem] = {}
        self._harmonic: Optional[LibraryTrack] = None

        self.cols = [
            Column("pos", t("track.position"), 40, "e", sort=lambda r: r.data.sequence if r.data else 0),
            Column("key", t("track.key"), 44, "center", sort=camelot_sort),
            Column("title", t("track.title"), 260, stretch=True, min_width=170),
            Column("artist", t("track.artist"), 170, priority=1),
            Column("album", t("track.album"), 140, priority=5),
            Column("bpm", t("track.bpm"), 52, "e", priority=2, sort=lambda r: r.data.bpm or None if r.data else None),
            Column("duration", t("track.duration"), 58, "e", priority=3,
                   sort=lambda r: r.data.duration_seconds if r.data else 0),
            Column("format", t("track.format"), 56, "center", priority=6),
            Column("source", t("track.source"), 130, priority=5),
            Column("added", t("track.added"), 104, "center", priority=4,
                   sort=lambda r: r.data.date_added if r.data else ""),
            # 1.3.1 (C37) : toutes les métadonnées, masquées par défaut (bouton « Colonnes »)
            Column("genre", t("track.genre"), 110),
            Column("year", t("track.year"), 52, "e", sort=lambda r: r.data.year or None if r.data else None),
            Column("label", t("track.label"), 120),
            Column("bitrate", t("track.bitrate"), 78, "e", sort=lambda r: r.data.bitrate or None if r.data else None),
            Column("rate", t("track.sample_rate"), 78, "e",
                   sort=lambda r: r.data.sample_rate or None if r.data else None),
            Column("rating", t("track.rating"), 76, "center", sort=lambda r: r.data.rating or None if r.data else None),
            Column("color", t("track.color"), 86, sort=lambda r: r.data.color or None if r.data else None),
            Column("plays", t("track.plays"), 64, "e", sort=lambda r: r.data.play_count or None if r.data else None),
            Column("created", t("track.created"), 96, "center", sort=lambda r: r.data.created or None if r.data else None),
            Column("size", t("track.size"), 70, "e", sort=lambda r: r.data.file_size or None if r.data else None),
            Column("comment", t("track.comment"), 180),
            Column("path", t("track.path"), 240),
        ]

        self.root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        self.root.addWidget(split)

        # ------------------------------------------------------------ gauche : navigation
        left = panel(role="sidebar")
        lv = vbox(left, margins=theme.px(8), spacing=theme.px(6))
        lv.addWidget(label(t("lib.section").upper(), "section"))
        self.nav = NavTree(self)
        self.nav.itemSelectionChanged.connect(self._nav_selected)
        self.nav.customContextMenuRequested.connect(self._nav_context)
        lv.addWidget(self.nav, 1)
        nb = hbox(spacing=theme.px(4))
        nb.addWidget(button(t("lib.playlist"), self._create_playlist, icon="plus", tooltip=t("lib.new_playlist")))
        nb.addWidget(button(t("lib.folder"), self._create_folder, icon="folder", tooltip=t("lib.new_folder")))
        self.rename_btn = icon_button("edit", self._rename_playlist, t("action.rename"))
        nb.addWidget(self.rename_btn)
        nb.addStretch(1)
        lv.addLayout(nb)
        split.addWidget(left)

        # ------------------------------------------------------------- droite : contenu
        main = QWidget()
        mv = vbox(main, margins=theme.px(14), spacing=theme.px(6))
        head = hbox()
        titles = vbox(spacing=0)
        self.title_lbl = label(t("lib.all_tracks"), "title")
        self.sub_lbl = label("", "dim")
        titles.addWidget(self.title_lbl)
        titles.addWidget(self.sub_lbl)
        head.addLayout(titles, 1)
        self.filter = line_edit(t("lib.filter"), "search")
        self.filter.setMaximumWidth(theme.px(240))
        self.filter.textEdited.connect(lambda _t: self._filter_changed())
        head.addWidget(self.filter, 0, Qt.AlignTop)
        mv.addLayout(head)

        bar = hbox(spacing=theme.px(6))
        self.add_btn = button(t("lib.add_to"), self._add_to, icon="plus")
        self.move_btn = button(t("lib.move_to"), self._move_to, icon="move")
        self.remove_btn = button(t("lib.remove"), self._remove, icon="close")
        self.up_btn = icon_button("up", lambda: self._move(-1), t("lib.up"))
        self.down_btn = icon_button("down", lambda: self._move(+1), t("lib.down"))
        self.save_btn = button(t("lib.save_order"), self._save_order, kind="primary", icon="check")
        self.analyse_btn = button("", self._analyse_toggle, kind="primary", icon="wave")
        self.analysis_bar = QProgressBar()
        self.analysis_bar.setTextVisible(False)
        self.analysis_bar.setRange(0, 1000)
        self.analysis_bar.setFixedWidth(theme.px(140))
        for w in (self.add_btn, self.move_btn, self.remove_btn, self.up_btn, self.down_btn, self.save_btn,
                  self.analyse_btn, self.analysis_bar):
            bar.addWidget(w)
        bar.addStretch(1)
        self.harm_btn = button(t("lib.harmonic"), self._toggle_harmonic, icon="key", tooltip=t("lib.harmonic_pick"))
        self.harm_btn.setCheckable(True)
        bar.addWidget(self.harm_btn)
        self.sug_btn = button(t("sug.title"), lambda: self.show_suggestions(self.sug_btn.isChecked()),
                              icon="playlist", tooltip=t("sug.tip"))           # 1.3.1 (C30)
        self.sug_btn.setCheckable(True)
        bar.addWidget(self.sug_btn)
        self.cols_btn = button(t("table.columns"), self._columns_menu, icon="columns", tooltip=t("lib.columns_tip"))
        bar.addWidget(self.cols_btn)
        self.tools_btn = icon_button("menu", self._tools_menu, t("lib.tools"))
        bar.addWidget(self.tools_btn)
        self.delete_btn = button("", self._delete, kind="danger", icon="trash", tooltip=t("lib.delete"))
        bar.addWidget(self.delete_btn)
        mv.addLayout(bar)

        self.banner = panel(role="banner")
        bl = hbox(self.banner, margins=theme.px(8), spacing=theme.px(8))
        bl.addWidget(icon_label("key", 16, theme.ACCENT))
        self.banner_lbl = label("")
        bl.addWidget(self.banner_lbl, 1)
        self.harm_bpm = QComboBox()                               # 1.3.1 (C30) : BPM ± x %
        self.harm_bpm.addItems([t("lib.harmonic_bpm_any"), "BPM ±3 %", "BPM ±6 %", "BPM ±10 %"])
        self.harm_bpm.setToolTip(t("lib.harmonic_bpm_tip"))
        self.harm_bpm.currentIndexChanged.connect(lambda _i: self._apply_harmonic())
        bl.addWidget(self.harm_bpm)
        bl.addWidget(icon_button("close", self._clear_harmonic, t("action.close"), size=14))
        self.banner.hide()
        mv.addWidget(self.banner)

        self.table = TrackTable(self, self.cols, reorderable=True)
        self.remember_layout(self.table, "library", default_hidden=("album", "format") + EXTRA_COLUMNS,
                             new_keys=EXTRA_COLUMNS)
        self.table.drag_out = True
        self.table.set_empty("usb", t("lib.no_drive_title"))
        self.table.on_select = lambda _i: (self._refresh_buttons(), self._suggest_from_selection())
        self.table.on_double = self._play
        self.table.on_reordered = self._mark_dirty
        self.table.on_sort_changed = self._sort_changed
        self.table.menu_builder = self._menu
        self.table.on_delete = self._delete
        from ..suggestions_panel import SuggestionsPanel

        content = hbox(spacing=theme.px(8))
        content.addWidget(self.table, 1)
        self.suggestions = SuggestionsPanel(self, controller)
        self.suggestions.hide()
        content.addWidget(self.suggestions)
        mv.addLayout(content, 1)
        split.addWidget(main)
        split.setStretchFactor(1, 1)
        split.setSizes([theme.px(220), theme.px(900)])

        controller.on("library", lambda: self.reload())
        controller.on("drive", lambda: self.reload(full=True))
        controller.on("queue", self._mark_playing)
        controller.on("player", lambda kind, _p: (self._mark_playing(), self._suggest_from_player())
                      if kind == "loaded" else None)
        controller.on("analysis", self._analysis_changed)
        controller.on("show_unanalysed", self.show_unanalysed)
        self._refresh_buttons()
        if controller.settings.suggestions_open:
            self.show_suggestions(True, remember=False)

    # ------------------------------------------------------------- 1.3.1 (C30) : suggestions
    def show_suggestions(self, on: bool, remember: bool = True) -> None:
        self.suggestions.setVisible(on)
        self.sug_btn.setChecked(on)
        if remember and self.ctrl.settings.suggestions_open != on:
            self.ctrl.settings.suggestions_open = on
            self.ctrl.save_settings_quiet()
        if on:
            sel = self._selected_tracks()[:1]
            if sel:
                self.suggestions.set_reference(sel[0])
            else:
                self._suggest_from_player()
            self.suggestions.refresh()

    def _suggest_from_selection(self) -> None:
        if self.suggestions.isVisible():
            sel = self._selected_tracks()
            if len(sel) == 1:
                self.suggestions.set_reference(sel[0])

    def _suggest_from_player(self) -> None:
        if not self.suggestions.isVisible():
            return
        cid = self.ctrl.current_library_id()
        found = [x for x in self.all_tracks if x.content_id == cid]
        if found:
            self.suggestions.set_reference(found[0])

    # =============================================================== chargement
    def on_show(self) -> None:
        if self._loaded_for != self._drive_key():
            self.reload(full=True)

    def _drive_key(self) -> str:
        return str(self.ctrl.drive.root) if self.ctrl.drive else ""

    def reload(self, full: bool = False) -> None:
        """Recharge la base. L'ordre non enregistré n'est jamais écrasé par un rafraîchissement
        automatique (téléchargement terminé…) : seul le volet de gauche est mis à jour."""
        if not self.winfo_exists():
            return
        if not self.ctrl.has_library:
            self.playlists, self.all_tracks, self.stats, self._dirty = [], [], {}, False
            self._loaded_for = ""
            self._fill_nav()
            self.table.set_empty("usb", t("lib.no_drive_title"))
            self.table.set_rows([], reset_sort=True)
            self._show_header()
            self._refresh_buttons()
            return
        key = self._drive_key()
        if full or not self.all_tracks:
            self.table.show_skeleton()

        def ok(data: Dict[str, Any]) -> None:
            if key != self._drive_key() or not self.winfo_exists():
                return
            self._loaded_for = key
            self.playlists, self.all_tracks, self.stats = data["playlists"], data["tracks"], data.get("stats", {})
            if full:
                self.current, self._dirty = ALL, False
            if self.current not in (ALL, TODO) and int(self.current[1:]) not in {p.playlist_id for p in self.playlists}:
                self.current, self._dirty = ALL, False
            if self._harmonic is not None:
                self._harmonic = next((x for x in self.all_tracks if x.content_id == self._harmonic.content_id), None)
            ref = self.suggestions.ref                           # C30 : infos à jour (analyse, BPM)
            if ref is not None:
                self.suggestions.ref = next((x for x in self.all_tracks if x.content_id == ref.content_id), None)
            if self.suggestions.isVisible():
                self.suggestions.refresh()
            self._fill_nav()
            if self._dirty:
                self._show_header()
                return
            self._fill_table()

        self.ctrl.load_library(ok)

    # ----------------------------------------------------------------- navigation
    def _fill_nav(self) -> None:
        self._reverting = True
        self.nav.clear()
        self._items = {}
        self._by_iid = {f"p{p.playlist_id}": p for p in self.playlists}

        def item(parent: Any, iid: str, text: str, color: str = "", icon: str = "playlist",
                 count: Any = "") -> QTreeWidgetItem:
            it = QTreeWidgetItem([text, str(count)])
            it.setData(0, Qt.UserRole, iid)
            it.setIcon(0, qicon(icon, 16, color or theme.DIM))
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            it.setForeground(1, _qcolor(theme.FAINT))
            if color:
                it.setForeground(0, _qcolor(color))
            (parent.addChild(it) if isinstance(parent, QTreeWidgetItem) else self.nav.addTopLevelItem(it))
            self._items[iid] = it
            return it

        item(None, ALL, t("lib.all_tracks"), icon="music", count=len(self.all_tracks))
        todo = self._unanalysed_count()
        item(None, TODO, t("lib.unanalysed"), theme.WARN if todo else "", icon="wave", count=todo)
        children: Dict[int, List[PlaylistInfo]] = {}
        for p in self.playlists:
            children.setdefault(p.parent_id, []).append(p)
        known = {p.playlist_id for p in self.playlists}

        def add(parent: Any, parent_id: int) -> None:
            for p in sorted(children.get(parent_id, []), key=lambda q: (q.sequence, q.name.lower())):
                iid = f"p{p.playlist_id}"
                it = item(parent, iid, p.name, icon="folder" if p.is_folder else "playlist",
                          count="" if p.is_folder else p.track_count)
                if p.is_folder:
                    add(it, p.playlist_id)
                    it.setExpanded(True)

        add(None, 0)
        for orphan in [pid for pid in children if pid != 0 and pid not in known]:
            add(None, orphan)          # parent introuvable : à la racine plutôt que perdu
        if self.current not in self._items:
            self.current = ALL
        self._select_nav(self.current)
        self._reverting = False

    def _select_nav(self, iid: str) -> None:
        it = self._items.get(iid)
        if it is not None:
            old, self._reverting = self._reverting, True
            self.nav.setCurrentItem(it)
            self._reverting = old

    def _nav_selected(self) -> None:
        if self._reverting:
            return
        it = self.nav.currentItem()
        new = it.data(0, Qt.UserRole) if it is not None else None
        if not new or new == self.current:
            return
        if self._dirty:
            self._select_nav(self.current)

            def discard() -> None:
                self._dirty = False
                self._goto(new)

            ConfirmDialog(self, t("lib.unsaved_title"), t("lib.unsaved_msg"), discard,
                          confirm_text=t("lib.unsaved_leave"), danger=True)
            return
        self._goto(new)

    def _goto(self, iid: str) -> None:
        self.current = iid
        self._select_nav(iid)
        self.filter.clear()
        self.table.set_filter("")
        self._fill_table()

    @property
    def playlist(self) -> Optional[PlaylistInfo]:
        return self._by_iid.get(self.current)

    @property
    def in_playlist(self) -> bool:
        p = self.playlist
        return p is not None and not p.is_folder

    def _drop_on(self, target: PlaylistInfo, ids: List[int]) -> None:
        """Titres glissés sur une playlist de l'arbre : ajoutés à la fin."""
        if not ids or (self.in_playlist and self.playlist.playlist_id == target.playlist_id):
            return
        self.ctrl.add_to_playlists(ids, [target.playlist_id])

    # -------------------------------------------------------------------- tableau
    def _unanalysed(self) -> List[LibraryTrack]:
        return [x for x in self.all_tracks if not x.is_analysed]

    def _unanalysed_count(self) -> int:
        return len(self._unanalysed())

    def _track_row(self, x: LibraryTrack, pos: bool) -> Row:
        return Row(
            str(x.content_id),
            {"pos": x.sequence if pos else "", "key": x.camelot or "", "title": x.title, "artist": x.artist,
             "album": x.album or "", "bpm": f"{x.bpm:.0f}" if x.bpm else "—",
             "duration": format_duration(x.duration_seconds), "format": _fmt(x), "added": (x.date_added or "")[:10],
             "source": source_from_url(x.source_url), **extra_values(x)},
            (), x,
        )

    def _columns_menu(self) -> None:
        self.table.columns_menu(self.cols_btn.mapToGlobal(self.cols_btn.rect().bottomLeft()))

    def _fill_table(self) -> None:
        self._show_header()
        self._refresh_buttons()
        if self.current == TODO:
            self.table.set_empty("check", t("lib.empty_todo_title"))
            self._apply_rows(self._unanalysed(), pos=False)
            return
        if self.current == ALL or self.playlist is None or self.playlist.is_folder:
            tracks = self.all_tracks if self.current == ALL else []
            if self.current == ALL:
                self.table.set_empty("music", t("lib.empty_all_title"))
            else:
                self.table.set_empty("folder", t("lib.empty_folder_title"))
            self._apply_rows(tracks, pos=False)
            return
        pid, token = self.playlist.playlist_id, self.current
        self.table.show_skeleton()

        def ok(tracks: List[LibraryTrack]) -> None:
            if token != self.current or self._dirty or not self.winfo_exists():
                return
            self.table.set_empty("playlist", t("lib.empty_playlist_title"))
            self._apply_rows(tracks, pos=True)

        self.ctrl.playlist_tracks(pid, ok)

    def _apply_rows(self, tracks: List[LibraryTrack], pos: bool) -> None:
        playlist = self.in_playlist
        self.table.reorderable = playlist and bool(self.playlist and self.playlist.is_editable)
        self.table.set_display_columns([c.key for c in self.cols if c.key != "pos" or playlist])
        self.table.set_rows([self._track_row(x, pos) for x in tracks], reset_sort=True, keep_selection=False)
        saved = self.ctrl.settings.playlist_sorts.get(self._sort_slot())
        if saved and any(c.key == saved[0] for c in self.cols):     # 1.2.1 (C04) : tri retenu
            self.table.set_sort(saved[0], bool(saved[1]))
        self._dirty = False
        self._apply_harmonic()
        self._mark_playing()
        self._refresh_buttons()
        self._show_header()

    def _show_header(self) -> None:
        if self.current == TODO:
            self.title_lbl.setText(t("lib.unanalysed"))
            parts = [plural("lib.tracks_one", "lib.tracks_many", self._unanalysed_count())]
            q = self.ctrl.analysis
            if q.running:
                parts.append(t("lib.analysing", i=q.done, n=q.total) + (f"  ·  {q.current}" if q.current else ""))
            self.sub_lbl.setText("  ·  ".join(parts))
        elif self.current == ALL:
            st = self.stats.get(0)
            self.title_lbl.setText(t("lib.all_tracks"))
            parts = [plural("lib.tracks_one", "lib.tracks_many", len(self.all_tracks))]
            if st is not None and st.total_seconds:
                parts.append(total_duration(st.total_seconds))
            if st is not None and st.last_added:
                parts.append(t("lib.last_added", date=st.last_added))
            self.sub_lbl.setText("  ·  ".join(parts))
        elif self.playlist is not None:
            p = self.playlist
            st = self.stats.get(p.playlist_id)
            kind = t("lib.kind_folder") if p.is_folder else (t("lib.kind_smart") if not p.is_editable
                                                              else t("lib.kind_playlist"))
            parts = [kind]
            if not p.is_folder:
                n = self.table.total if self.in_playlist else p.track_count
                parts.append(plural("lib.tracks_one", "lib.tracks_many", n))
                if st is not None and st.total_seconds:
                    parts.append(total_duration(st.total_seconds))
                if st is not None and st.last_added:
                    parts.append(t("lib.updated", date=st.last_added))
            self.title_lbl.setText(p.name)
            self.sub_lbl.setText("  ·  ".join(parts))
        else:
            self.title_lbl.setText(t("tab.library"))
            self.sub_lbl.setText("")

    def _filter_changed(self) -> None:
        self.table.set_filter(self.filter.text())
        self._refresh_buttons()

    def _mark_dirty(self) -> None:
        for n, iid in enumerate(self.table.displayed_iids(), start=1):  # N° = nouvelle position
            self.table.update_values(iid, pos=n)
        self._dirty = True
        self._refresh_buttons()

    def _mark_playing(self) -> None:
        if not self.winfo_exists():
            return
        cid = self.ctrl.current_library_id()
        playing = str(cid) if cid is not None else None
        for row in self.table.all_rows():
            want = row.iid == playing
            if want != ("playing" in row.tags):
                self.table.set_tags(row.iid, *(("playing",) if want else ()))

    # ------------------------------------------------------------- filtre harmonique
    def _toggle_harmonic(self) -> None:
        if self._harmonic is not None:
            self._clear_harmonic()
            return
        base = self._selected_tracks()[:1]
        if not base:
            cid = self.ctrl.current_library_id()
            base = [x for x in self.all_tracks if x.content_id == cid]
        if not base or not base[0].camelot:
            self.ctrl.message("info", t("lib.harmonic_pick"))
            self.harm_btn.setChecked(False)
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
            self.banner.hide()
        else:
            keys = set(neighbors(base.camelot))
            tol = (0, 3, 6, 10)[max(0, self.harm_bpm.currentIndex())]
            if tol and base.bpm:
                from ...core.suggest import bpm_gap

                def ok(r: Row) -> bool:
                    gap = bpm_gap(base.bpm, r.data.bpm)[0] if r.data else None
                    return bool(r.data and r.data.camelot in keys and gap is not None and abs(gap) <= tol)
                self.table.row_filter = ok
            else:
                self.table.row_filter = lambda r: bool(r.data and r.data.camelot in keys)
            text = t("lib.harmonic_banner", code=base.camelot, title=base.title, keys=", ".join(neighbors(base.camelot)))
            if base.bpm:
                text += "  ·  " + t("lib.harmonic_bpm", bpm=f"{base.bpm:.0f}")
            self.banner_lbl.setText(text)
            self.banner.show()
        self.table.refilter()

    # -------------------------------------------------------------------- boutons
    def _sort_slot(self) -> str:
        drive = self.ctrl.drive
        return f"{getattr(drive, 'label', '') or getattr(drive, 'root', '')}|{self.current}"

    def _sort_changed(self, key: Optional[str], desc: bool) -> None:
        """1.2.1 (C04) : le tri choisi pour cette playlist est retenu (changement de vue, redémarrage)."""
        sorts = self.ctrl.settings.playlist_sorts
        slot = self._sort_slot()
        if key is None:
            sorts.pop(slot, None)
        else:
            sorts.pop(slot, None)                  # en dernier : les plus anciens partent d'abord (500 max)
            sorts[slot] = [key, bool(desc)]
        try:
            self.ctrl.settings.save()
        except OSError:
            pass
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        sel = self.table.selected_iids()
        playlist = self.in_playlist
        editable = playlist and bool(self.playlist and self.playlist.is_editable)
        todo = self.current == TODO
        for w in (self.move_btn, self.remove_btn):
            w.setVisible(playlist)
        for w in (self.up_btn, self.down_btn, self.save_btn):
            w.setVisible(bool(editable))
        has = bool(sel) and self.ctrl.has_library
        self.add_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.move_btn.setEnabled(has and editable)
        self.remove_btn.setEnabled(has and editable)
        can_move = has and editable and not self.table.filter_active
        self.up_btn.setEnabled(can_move)
        self.down_btn.setEnabled(can_move)
        can_save = editable and not self.table.filter_active and (self._dirty or self.table.sort_active)
        self.save_btn.setEnabled(bool(can_save))
        self.save_btn.setText(t("lib.save_order") + (" •" if self._dirty else ""))
        self.rename_btn.setEnabled(self.playlist is not None and (self.playlist.is_editable or self.playlist.is_folder))
        self.harm_btn.setChecked(self._harmonic is not None)
        # « Non analysés » : lancer / arrêter l'analyse en arrière-plan
        q = self.ctrl.analysis
        self.analyse_btn.setVisible(todo)
        self.analysis_bar.setVisible(todo and q.running)
        if todo:
            if q.running:
                self.analyse_btn.setText(t("lib.analyse_stop"))
                self.analyse_btn.setProperty("kind", "danger")
                self.analyse_btn.setIcon(qicon("stop", 16, theme.ERR))
                self.analyse_btn.setEnabled(not q.cancelled)
                self.analysis_bar.setValue(int(1000 * q.done / max(1, q.total)))
            else:
                n = self._unanalysed_count()
                self.analyse_btn.setText(t("lib.analyse_all", n=n))
                self.analyse_btn.setProperty("kind", "primary")
                self.analyse_btn.setIcon(qicon("wave", 16, theme.ON_ACCENT))
                self.analyse_btn.setEnabled(bool(n) and self.ctrl.has_library)
            restyle(self.analyse_btn)
        tip = t("lib.hint_clear_filter") if self.table.filter_active else ""
        for b, base in ((self.up_btn, t("lib.up")), (self.down_btn, t("lib.down")), (self.save_btn, "")):
            b.setToolTip(tip or base)

    def _ids(self) -> List[int]:
        return [int(i) for i in self.table.selected_iids()]

    def _selected_tracks(self) -> List[LibraryTrack]:
        return [r.data for r in self.table.selected_rows() if r.data is not None]

    def _move(self, delta: int) -> None:
        self.table.move_selected(delta)

    def _play(self, iid: str) -> None:
        tracks = [r.data for r in self.table.displayed_rows() if r.data is not None]
        row = self.table.row(iid)
        if row is not None and row.data in tracks:
            self.ctrl.play_queue(tracks, tracks.index(row.data))
            focus_list(self.table)

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
            if self.winfo_exists():
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
        what = t("fmt.quoted", text=names[0]) if len(ids) == 1 else t("lib.delete_many", n=len(ids),
                                                                       names=", ".join(names))
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
        """Sélection : fenêtre de lancement (option « analyser à nouveau »). Sans sélection : vue « Non
        analysés » et analyse lancée en arrière-plan."""
        if not self.ctrl.has_library:
            return
        if tracks is None:
            self.show_unanalysed()
            self._analyse_all()
            return
        if all(not x.is_analysed for x in tracks):          # rien à choisir : on lance directement
            self.ctrl.analyze([x.content_id for x in tracks])
            return
        from ..analysis_dialog import AnalysisDialog

        AnalysisDialog(self, self.ctrl, tracks)

    def _analyse_all(self) -> None:
        todo = self._unanalysed()
        if todo:
            self.ctrl.analyze([x.content_id for x in todo])
        else:
            self.ctrl.message("info", t("analysis.nothing_missing"))

    def _analyse_toggle(self) -> None:
        if self.ctrl.analysis.running:
            self.ctrl.stop_analysis()
        else:
            self._analyse_all()

    def show_unanalysed(self) -> None:
        """Ouvre Bibliothèque ▸ « Non analysés » (Accueil, Paramètres, barre latérale)."""
        self.ctrl._emit("navigate", "library")
        if self.current != TODO:
            if self._dirty:
                self._select_nav(TODO)
                self._nav_selected()
            elif TODO in self._items:
                self._goto(TODO)
            else:
                self.current = TODO

    def reveal(self, content_id: int) -> None:
        """Montre un titre dans « Tous les titres » (lecteur ▸ Afficher dans la bibliothèque)."""
        iid = str(content_id)
        if self.current != ALL and not self._dirty:
            self._goto(ALL)
        elif self.current == ALL and self.table.filter_active:
            self.filter.clear()
            self.table.set_filter("")
        row = self.table.row(iid)
        if row is None:
            return
        if self._harmonic is not None and self.table.row_filter and not self.table.row_filter(row):
            self._clear_harmonic()
        self.table.select([iid])

    def _analysis_changed(self) -> None:
        if not self.winfo_exists():
            return
        if self.current == TODO:
            self._show_header()
        self._refresh_buttons()

    def _edit_grid(self) -> None:
        tracks = self._selected_tracks()
        if not tracks:
            return
        if not tracks[0].is_analysed:
            self.ctrl.message("info", t("grid.not_analysed"))
            return
        self.ctrl._emit("open_grid", tracks[0])

    def _edit_metadata(self) -> None:
        tracks = self._selected_tracks()
        if not tracks:
            return
        from ..track_info_dialog import TrackInfoDialog

        TrackInfoDialog(self, self.ctrl, tracks[0])

    def _scope_name(self) -> str:
        if self.in_playlist and self.playlist is not None:
            return self.playlist.name
        return t("lib.all_tracks")

    def _uniformize(self) -> None:
        """1.2.2 (C14) : les sons affichés (playlist ou toute la bibliothèque)."""
        if not self.ctrl.has_library:
            return
        tracks = [r.data for r in self.table.displayed_rows() if r.data is not None]
        if not tracks:
            self.ctrl.message("info", t("uni.no_tracks"))
            return
        self.ctrl._emit("open_uniformize", tracks, self._scope_name())

    def _uniformize_playlist(self, p: PlaylistInfo) -> None:
        def ok(tracks: List[LibraryTrack]) -> None:
            if tracks:
                self.ctrl._emit("open_uniformize", tracks, p.name)
            else:
                self.ctrl.message("info", t("uni.no_tracks"))

        self.ctrl.playlist_tracks(p.playlist_id, ok)

    def _genre_playlists(self) -> None:
        if not self.ctrl.has_library:
            return
        from ..genre_dialog import GenrePlaylistsDialog

        GenrePlaylistsDialog(self, self.ctrl)

    def _duplicates(self) -> None:
        if not self.ctrl.has_library:
            return
        self.window().open_diagnostic("dup")             # 1.3.1 (C41) : onglet Doublons du Diagnostic

    def _tools_menu(self) -> None:
        sel = self._selected_tracks()
        entries: list = []
        if sel:
            entries.append((t("lib.analyse_selection", n=len(sel)), lambda: self._analyse(sel), "wave"))
        entries += [(t("lib.analyse_missing"), lambda: self._analyse(None), "wave"), None]
        if len(sel) == 1:
            entries += [(t("lib.edit_grid"), self._edit_grid, "grid"),
                        (t("action.edit_metadata"), self._edit_metadata, "edit")]
        entries.append((t("lib.find_duplicates"), self._duplicates, "duplicates"))
        entries.append((t("uni.menu_scope", scope=self._scope_name()) + "…", self._uniformize, "tag"))
        entries.append((t("genre.menu") + "…", self._genre_playlists, "playlist"))
        target = sel or None
        entries.append((t("meta.complete_sel", n=len(sel)) if sel else t("meta.complete_all"),
                        lambda: self._complete_metadata(target), "tag"))
        b = self.tools_btn
        popup_menu(b, entries, b.mapToGlobal(b.rect().bottomLeft()))

    # ---------------------------------------------------------------- menus contextuels
    def _menu(self, iids: List[str]) -> list:
        if not iids:
            return []
        entries: list = [(t("action.listen"), lambda: self._play(iids[0]), "play"), None,
                         (t("lib.add_to"), self._add_to, "plus")]
        if self.in_playlist and self.playlist.is_editable:
            entries += [(t("lib.move_to"), self._move_to, "move"), (t("lib.remove"), self._remove, "close")]
        tracks = self._selected_tracks()
        entries += [None, (t("lib.analyse_selection", n=len(iids)), lambda: self._analyse(tracks), "wave")]
        if len(tracks) == 1:
            entries += [(t("lib.edit_grid"), self._edit_grid, "grid"),
                        (t("action.edit_metadata"), self._edit_metadata, "edit")]
            if tracks[0].camelot:
                entries.append((t("lib.show_compatible", code=tracks[0].camelot), lambda: self.set_harmonic(tracks[0]),
                                "key"))
        entries.append((t("meta.complete_sel", n=len(tracks)), lambda: self._complete_metadata(tracks), "tag"))
        entries += [None, (t("lib.delete") + "…", self._delete, "trash")]
        return entries

    def _complete_metadata(self, tracks: Any) -> None:
        if self.ctrl.tool_busy:
            self.ctrl.message("warn", t("tools.busy"))
            return
        if tracks is None:
            self.ctrl.dispatcher.submit(lambda: [x.content_id for x in self.ctrl.library.list_tracks()],
                                        self.ctrl.complete_metadata, self.ctrl._on_error, pool="db")
        else:
            self.ctrl.complete_metadata([x.content_id for x in tracks])

    def _copy_playlist(self, playlist_id: int, target: Any, name: str) -> None:
        if self.ctrl.tool_busy:
            self.ctrl.message("warn", t("tools.busy"))
            return
        from ..dialogs import ConfirmDialog

        ConfirmDialog(self, t("copy.title"), t("copy.confirm", target=name),
                      lambda: self.ctrl.copy_playlist(playlist_id, target), confirm_text=t("copy.ok"),
                      detail=t("copy.detail"))

    def _nav_context(self, pos: Any) -> None:
        it = self.nav.itemAt(pos)
        iid = it.data(0, Qt.UserRole) if it is not None else None
        if not iid or iid in (ALL, TODO):
            return
        self.nav.setCurrentItem(it)
        p = self._by_iid.get(iid)
        if p is None:
            return
        entries: list = []
        if p.is_editable:
            for name, target in self.ctrl.copy_targets():
                entries.append((t("copy.to", target=name) + "…",
                                lambda pid=p.playlist_id, tg=target, n=name: self._copy_playlist(pid, tg, n), "copy"))
            if entries:
                entries.append(None)
        if not p.is_folder:
            entries.append((t("uni.menu") + "…", lambda pl=p: self._uniformize_playlist(pl), "tag"))
            entries.append(None)
        if p.is_editable or p.is_folder:
            entries += [(t("action.rename") + "…", self._rename_playlist, "edit"),
                        (t("action.delete") + "…", self._delete_playlist, "trash")]
        popup_menu(self.nav, entries, self.nav.viewport().mapToGlobal(pos))


def _qcolor(color: str) -> Any:
    from PySide6.QtGui import QColor

    return QColor(color)
