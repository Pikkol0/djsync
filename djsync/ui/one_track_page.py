"""1.4.1 (C140, D18, D19) : premier onglet du Diagnostic, « Un son ».

Un champ cherche dans la bibliothèque active (titre, artiste, album) ; le son choisi s'affiche en fiche, avec
ses infos puis quatre actions dessous : modifier les infos, voir ses doublons, mesurer sa qualité, l'afficher
dans l'explorateur. Pas de cartes d'outils : la barre d'onglets du Diagnostic (en haut) les remplace.
Le dernier son choisi est retenu par la fenêtre : revenir sur l'onglet le retrouve.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFormLayout, QFrame, QGridLayout, QListWidget, QListWidgetItem, QScrollArea

from ..i18n import t
from ..models import LibraryTrack
from . import theme
from .dialogs import BaseDialog
from .widgets import CamelotPill, button, hbox, label, line_edit, panel, vbox

MAX_RESULTS = 200          # résultats affichés (le reste : affiner la recherche)


def matches(track: LibraryTrack, words: List[str]) -> bool:
    """Tous les mots cherchés dans titre, artiste ou album (sans tenir compte de la casse)."""
    hay = " ".join(x for x in (track.title, track.artist, track.album or "") if x).casefold()
    return all(w in hay for w in words)


def search(tracks: List[LibraryTrack], text: str) -> List[LibraryTrack]:
    words = [w for w in text.casefold().split() if w]
    found = [x for x in tracks if matches(x, words)] if words else list(tracks)
    found.sort(key=lambda x: ((x.artist or "").casefold(), x.title.casefold()))
    return found


def breakable(path: str) -> str:
    """Chemin qui peut passer à la ligne après chaque « / » ou « \\ » (espace de largeur nulle)."""
    return path.replace("/", "/\u200b").replace("\\", "\\\u200b")


def _duration(seconds: int) -> str:
    m, s = divmod(int(seconds or 0), 60)
    return f"{m}:{s:02d}" if seconds else "—"


class OneTrackPage(BaseDialog):
    as_page = True
    modal = False

    def __init__(self, parent: Any, controller: Any, track_id: Optional[int] = None) -> None:
        super().__init__(parent, t("diagtab.one"), 900, 560)
        self.ctrl = controller
        self.tracks: List[LibraryTrack] = []
        self.shown: List[LibraryTrack] = []
        self.track: Optional[LibraryTrack] = None
        self._want = track_id
        if track_id is None and self._host is not None:
            self._want = getattr(self._host, "_one_track_id", None)
        self._extra: Dict[str, Any] = {}
        from .diag_tabs import add_tabs

        add_tabs(self, controller, "one")
        self.body.addWidget(label(t("one.title"), "h2"))
        self.entry = line_edit(t("one.placeholder"), icon="search")
        self.body.addWidget(self.entry)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._filter)
        self.entry.textChanged.connect(lambda _s: self._timer.start())
        self.entry.returnPressed.connect(self._pick_first)

        main = hbox(spacing=theme.px(10))
        left = vbox(spacing=theme.px(4))
        self.count = label(t("one.loading"), "faint")
        left.addWidget(self.count)
        self.list = QListWidget()
        self.list.setFixedWidth(theme.px(280))
        self.list.currentRowChanged.connect(self._select)
        left.addWidget(self.list, 1)
        main.addLayout(left)

        self.card = panel()
        self.card_lay = vbox(self.card, margins=theme.px(12), spacing=theme.px(6))
        scroll = self.scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.card)
        main.addWidget(scroll, 1)
        self.body.addLayout(main, 1)
        self._empty_card(t("one.pick"))

        self.show_dialog()
        controller.on("library", self._reload)
        self._reload()
        self.entry.setFocus()

    # ------------------------------------------------------------------ données
    def _reload(self, *_a: Any) -> None:
        if not self.winfo_exists():
            return
        lib = self.ctrl.library
        if lib is None:
            return
        if self.track is not None:
            self._want = self.track.content_id

        def ok(tracks: List[LibraryTrack]) -> None:
            if self.winfo_exists() and self.ctrl.library is lib:
                self.tracks = tracks
                self._filter()

        self.ctrl.dispatcher.submit(lib.list_tracks, ok, lambda _e: None, pool="db")

    def _filter(self) -> None:
        if not self.winfo_exists():
            return
        found = search(self.tracks, self.entry.text())
        self.shown = found[:MAX_RESULTS]
        self.list.blockSignals(True)
        self.list.clear()
        for x in self.shown:
            item = QListWidgetItem(f"{x.title}\n{x.artist or '—'}")
            item.setToolTip(x.display_name)
            self.list.addItem(item)
        self.list.blockSignals(False)
        n = len(found)
        if not self.tracks:
            self.count.setText(t("one.empty"))
        elif n > MAX_RESULTS:
            self.count.setText(t("one.count_more", n=n, shown=MAX_RESULTS))
        else:
            self.count.setText(t("one.count", n=n))
        want = self._want if self._want is not None else (self.track.content_id if self.track else None)
        row = next((i for i, x in enumerate(self.shown) if x.content_id == want), -1)
        if row >= 0:
            self.list.setCurrentRow(row)
            self._select(row)
        elif self.track is not None and all(x.content_id != self.track.content_id for x in self.tracks):
            self.track = None                         # son retiré de la bibliothèque
            self._empty_card(t("one.pick"))
        self._want = None

    def _pick_first(self) -> None:
        if self.shown:
            self.list.setCurrentRow(0)
            self.list.setFocus()

    def _select(self, row: int) -> None:
        if not (0 <= row < len(self.shown)):
            return
        self.track = self.shown[row]
        if self._host is not None:
            self._host._one_track_id = self.track.content_id          # retrouvé au retour sur l'onglet
        self._show_card()

    # ------------------------------------------------------------------ fiche
    def _clear_card(self) -> None:
        lay = self.card_lay
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()                              # plus affiché tout de suite (deleteLater attend la boucle)
                w.deleteLater()
            elif item.layout() is not None:
                _drop_layout(item.layout())

    def _empty_card(self, text: str) -> None:
        self._clear_card()
        self.card_lay.addWidget(label(text, "faint", wrap=True))
        self.card_lay.addStretch(1)

    def _show_card(self) -> None:
        x = self.track
        if x is None:
            return
        from .views.library_view import _fmt, extra_values

        self._clear_card()
        self._extra = extra_values(x)
        lay = self.card_lay
        title = label(x.title, "h2", wrap=True)
        lay.addWidget(title)
        lay.addWidget(label(x.artist or "—", "accent", wrap=True))

        form = QFormLayout()
        form.setHorizontalSpacing(theme.px(14))
        form.setVerticalSpacing(theme.px(4))

        def row(key: str, value: Any) -> Any:
            w = value if not isinstance(value, str) else label(value or "—", wrap=True)
            if isinstance(value, str):
                w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label(t(key), "dim"), w)
            return w

        row("track.album", x.album or "")
        row("track.duration", _duration(x.duration_seconds))
        row("track.bpm", f"{x.bpm:.2f}".rstrip("0").rstrip(".") if x.bpm else t("one.not_analysed"))
        key = CamelotPill(x.camelot)
        if x.camelot:
            box = hbox(spacing=theme.px(6))
            box.addWidget(key)
            box.addWidget(label(x.key or "", "dim"))
            box.addStretch(1)
            form.addRow(label(t("track.key"), "dim"), box)
        else:
            key.deleteLater()
            row("track.key", t("one.not_analysed") if not x.is_analysed else "")
        fmt = _fmt(x)
        if self._extra.get("bitrate"):
            fmt += f"  ·  {self._extra['bitrate']}"
        if self._extra.get("rate"):
            fmt += f"  ·  {self._extra['rate']}"
        row("track.format", fmt)
        self.real_lbl = row("track.real_quality", self._extra.get("real") or t("one.not_measured"))
        color = self._extra.get("real__color")
        if color:
            self.real_lbl.setStyleSheet(f"color: {color};")
        row("track.genre", x.genre)
        row("one.year", str(x.year) if x.year else "")
        self.pl_lbl = row("one.playlists", t("one.loading_short"))
        self.file_lbl = row("one.file", breakable(x.path))
        self.file_lbl.setToolTip(x.path)
        lay.addLayout(form)

        # quatre actions sous les infos (D18)
        lay.addSpacing(theme.px(6))
        self.act_grid = QGridLayout()
        self.act_grid.setHorizontalSpacing(theme.px(6))
        self.act_grid.setVerticalSpacing(theme.px(6))
        self.edit_btn = button(t("one.edit"), self._edit, icon="edit")
        self.dup_btn = button(t("one.duplicates"), self._duplicates, icon="duplicates")
        self.quality_btn = button(t("one.quality"), self._quality, icon="wave", tooltip=t("one.quality_tip"))
        reveal_key = "reveal.finder" if sys.platform == "darwin" else "reveal.explorer"
        self.reveal_btn = button(t(reveal_key), self._reveal, icon="folder")
        self.action_buttons = [self.edit_btn, self.dup_btn, self.quality_btn, self.reveal_btn]
        self._cols = 0
        lay.addLayout(self.act_grid)
        self._place_actions()
        self.note = label("", "faint", wrap=True)
        lay.addWidget(self.note)
        lay.addStretch(1)
        self._load_details(x)

    def _place_actions(self) -> None:
        """Les quatre actions sur une ligne, ou deux par ligne quand la fiche est trop étroite (zoom)."""
        acts = getattr(self, "action_buttons", None)
        if not acts:
            return
        try:
            m = self.card_lay.contentsMargins()
            avail = self.scroll.viewport().width() - m.left() - m.right()
            need = sum(b.sizeHint().width() for b in acts) + self.act_grid.horizontalSpacing() * (len(acts) - 1)
        except RuntimeError:
            return
        cols = 4 if need <= avail else 2
        if cols == self._cols:
            return
        self._cols = cols
        for b in acts:
            self.act_grid.removeWidget(b)
        for i, b in enumerate(acts):
            self.act_grid.addWidget(b, i // cols, i % cols)
        for c in range(4):
            self.act_grid.setColumnStretch(c, 0)
        self.act_grid.setColumnStretch(cols, 1)

    def resizeEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(e)
        QTimer.singleShot(0, self._place_actions)

    def _load_details(self, x: LibraryTrack) -> None:
        lib = self.ctrl.library
        if lib is None:
            return

        def work() -> Dict[str, Any]:
            try:
                exists = lib.absolute_path(x).is_file()
            except (OSError, ValueError):
                exists = False
            names = {p.playlist_id: p.name for p in lib.list_playlists()}
            pids = lib.playlists_of([x.content_id]).get(x.content_id, [])
            return {"exists": exists, "playlists": sorted({names[p] for p in pids if p in names}, key=str.casefold)}

        def ok(info: Dict[str, Any]) -> None:
            if not self.winfo_exists() or self.track is not x:
                return
            try:
                pls = info["playlists"]
                self.pl_lbl.setText(", ".join(pls) if pls else t("one.no_playlist"))
                if not info["exists"]:
                    self.file_lbl.setText(f"{breakable(x.path)}\n{t('one.file_missing')}")
                    self.file_lbl.setProperty("role", "warn")
                    from .widgets import restyle

                    restyle(self.file_lbl)
                    self.quality_btn.setEnabled(False)
                    self.reveal_btn.setEnabled(False)
            except RuntimeError:                       # fiche refaite entre-temps
                pass

        self.ctrl.dispatcher.submit(work, ok, lambda _e: None, pool="db")

    # ------------------------------------------------------------------ actions
    def _edit(self) -> None:
        if self.track is None:
            return
        from .track_info_dialog import TrackInfoDialog

        TrackInfoDialog(self, self.ctrl, self.track)

    def _duplicates(self) -> None:
        """Ouvre l'onglet Doublons sur les groupes de ce son ; message si le titre n'en a aucun."""
        x, lib = self.track, self.ctrl.library
        if x is None or lib is None:
            return
        self.dup_btn.setEnabled(False)

        def work() -> List[int]:
            from ..core.duplicates import find_duplicate_groups

            for group in find_duplicate_groups(lib.list_tracks()):
                ids = [y.content_id for y in group]
                if x.content_id in ids:
                    return ids
            return []

        def ok(ids: List[int]) -> None:
            if not self.winfo_exists():
                return
            try:
                self.dup_btn.setEnabled(True)
            except RuntimeError:
                pass
            if not ids:
                self._say(t("one.no_duplicates"))
                return
            from .duplicates_dialog import DuplicatesDialog

            host = self._host
            if host is not None:
                host._drop_diag_page(self, then=lambda: DuplicatesDialog(host, self.ctrl, focus_ids=ids))
            else:
                DuplicatesDialog(self, self.ctrl, focus_ids=ids)

        def err(_e: BaseException) -> None:
            if self.winfo_exists():
                self.dup_btn.setEnabled(True)

        self.ctrl.dispatcher.submit(work, ok, err, pool="tools")

    def _quality(self) -> None:
        """Mesure la qualité réelle (spectre) de ce son seul, puis (1.4.1, C135) ouvre son détail dans
        l'onglet Qualité : meilleure version, gain, remplacement."""
        x = self.track
        if x is None:
            return

        def done(fakes: int) -> None:
            if not self.winfo_exists():
                return
            if self.track is x:
                self._show_card()
            self._say(t("one.quality_fake") if fakes else t("one.quality_ok"))
            win = self.window()
            if hasattr(win, "open_quality") and self.track is x:
                win.open_quality([x.content_id], focus=x.content_id)

        self._say(t("one.quality_running"))
        if not self.ctrl.measure_quality([x], done, None, force=True):
            self._say(t("quality.busy"))

    def _reveal(self) -> None:
        if self.track is None:
            return
        from .reveal import reveal_entry

        reveal_entry(self.ctrl, self.track)[1]()

    def _say(self, text: str) -> None:
        try:
            self.note.setText(text)
        except (RuntimeError, AttributeError):
            pass


def _drop_layout(lay: Any) -> None:
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()                              # plus affiché tout de suite (deleteLater attend la boucle)
            w.deleteLater()
        elif item.layout() is not None:
            _drop_layout(item.layout())
