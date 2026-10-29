"""Outil « Doublons » : retrouve les sons présents plusieurs fois sur la clé, laisse choisir lequel
garder, corriger son titre / artiste, et supprime les autres.

Exemple : « Daft Punk - One More Time (Clip Officiel) » (artiste vide) et « One More Time »
(Daft Punk). Le son gardé prend la place des doublons dans toutes leurs playlists (même
position) ; la base est sauvegardée avant la modification.
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QProgressBar,
    QFrame, QLabel, QRadioButton, QScrollArea, QWidget,
)

from ..core.duplicates import best_keeper, split_display
from ..i18n import plural, t
from ..models import SOURCE_LABELS, LibraryTrack, format_duration
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .widgets import CamelotPill, button, chip, hbox, icon_button, label, panel, vbox

_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}
ALT = 100          # 1.3.1 (C42) : boutons des versions à retélécharger (100, 101…)


class DuplicatesDialog(BaseDialog):
    as_page = True                    # 1.2.3 : page de la fenêtre principale
    modal = False

    def __init__(self, parent: Any, controller: Any, focus_ids: Optional[List[int]] = None, full: bool = False,
                 keep_id: Optional[int] = None) -> None:
        super().__init__(parent, t("dup.title"), 820, 540)
        self.ctrl = controller
        self.groups: List[List[LibraryTrack]] = []
        self.verified: List[bool] = []                       # rc.5 (C63) : son du groupe vérifié
        # 1.3.2 (C80) : sons au même titre mais au son différent : gardés à l'écran, grisés, jamais supprimés
        self.apart: List[List[LibraryTrack]] = []            # par groupe : écartés par l'empreinte
        self.same_titles: List[List[LibraryTrack]] = []     # groupes sans aucun vrai doublon
        self._same_index = -1
        self._priority: List[List[LibraryTrack]] = []       # 1.3.2 (C84) : groupes demandés en premier
        self._pending: List[dict] = []                       # 1.3.2 (C82) : fusions en attente (Annuler)
        self._refining: Optional[List[LibraryTrack]] = None
        self._focus = set(focus_ids or [])
        self._keep_id = keep_id                              # version choisie dans le Diagnostic
        self._full = full
        self.index = -1
        self._busy = False
        self._keep = QButtonGroup(self)
        self.title_entry: Optional[QLineEdit] = None
        self._pl_labels: dict = {}
        self.artist_entry: Optional[QLineEdit] = None
        self.cues_combo: Optional[QComboBox] = None          # 1.3.0 (C13) : de quelle version viennent les cues
        self._cue_counts: dict = {}
        self._cues_touched = False
        self._group_cues: dict = {}                           # 1.3.2 (C79) : {son: [cues]} du groupe affiché
        self._cue_strips: dict = {}
        self.cues_summary: Optional[QLabel] = None
        # 1.3.1 (C42) : qualité audio de chaque version (lue dans le fichier) et versions à retélécharger
        self._quality: dict = {}
        self._info_labels: dict = {}
        self._best_slots: dict = {}
        self._keep_touched = False
        self._auto_keep = False
        self._alts: dict = {}               # index du groupe -> [Candidate] (None : recherche en cours)
        self.alt_box: Optional[Any] = None
        from .diag_tabs import add_tabs

        add_tabs(self, controller, "dup")                      # 1.3.1 (C41) : onglet « Doublons »

        head = hbox()
        head.addWidget(label(t("dup.title"), "h2"))
        head.addStretch(1)
        self.count = label(t("dup.searching"), "dim")
        head.addWidget(self.count)
        self.body.addLayout(head)
        # 1.3.2 (C84) : fine barre d'avancement (recherche par titre, puis vérification par le son)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(theme.px(3))
        self.bar.setRange(0, 0)
        self.body.addWidget(self.bar)

        main = hbox(spacing=theme.px(10))
        self.list = QListWidget()
        self.list.setFixedWidth(theme.px(240))
        self.list.currentRowChanged.connect(self._select)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)       # C84 : « Vérifier ce groupe maintenant »
        self.list.customContextMenuRequested.connect(self._list_menu)
        main.addWidget(self.list)
        self.detail = panel()
        self.detail_lay = vbox(self.detail, margins=theme.px(10), spacing=theme.px(6))
        self.detail_lay.addWidget(label(t("dup.searching"), "faint"))
        self.detail_lay.addStretch(1)
        # 1.3.2 (B34) : le détail d'un groupe défile au lieu de tasser ses versions (beaucoup de versions,
        # petite fenêtre, aperçu des cues C79) ; la barre d'actions reste visible en bas, hors de la zone.
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setWidget(self.detail)
        main.addWidget(self.detail_scroll, 1)
        self.body.addLayout(main, 1)

        bar = hbox()
        # 1.3.0-rc.5 (C62) : choix « pas un doublon » retenus, réversibles
        self.ignored_btn = button("", self._show_ignored, kind="flat", icon="menu", tooltip=t("dup.ignored_tip"))
        bar.addWidget(self.ignored_btn)
        bar.addWidget(button(t("dup.full_scan"), self._full_scan, kind="flat", icon="search",
                             tooltip=t("dup.full_scan_tip")))
        bar.addStretch(1)
        self.undo_btn = button("", self._undo_last, kind="flat", icon="back")      # C82
        self.undo_btn.hide()
        bar.addWidget(self.undo_btn)
        self.later_btn = button(t("dup.later"), self._skip, kind="flat", tooltip=t("dup.later_tip"))
        self.skip_btn = button(t("dup.skip"), self._not_duplicates, icon="close", tooltip=t("dup.skip_tip"))
        self.apply_btn = button(t("dup.apply"), self._apply, kind="primary", icon="check")
        bar.addWidget(self.later_btn)
        bar.addWidget(self.skip_btn)
        bar.addWidget(self.apply_btn)
        bar.addWidget(button(t("action.close"), self.close))
        self.body.addLayout(bar)
        self._refresh_actions()
        self.show_dialog()
        if full:
            controller.message("info", t("dup.full_running"))
        controller.find_duplicates(self._loaded, self._progress, full=full)

    def _progress(self, i: int, n: int) -> None:
        if self.winfo_exists() and not self.groups:
            self.count.setText(t("dup.title_search", n=n))

    # ------------------------------------------------------------------ rc.5 (C63) : son vérifié groupe par groupe
    def _refine_next(self) -> None:
        if not self.winfo_exists() or self._refining is not None:
            return
        todo = [i for i, ok in enumerate(self.verified) if not ok]
        if not todo:
            self._update_count()
            return
        # C84 : d'abord les groupes demandés (clic droit, « Vérifier maintenant »), puis celui affiché
        asked = [next((i for i in todo if self.groups[i] is g), -1) for g in self._priority]
        asked = [i for i in asked if i >= 0]
        i = asked[0] if asked else (self.index if self.index in todo else todo[0])
        self._priority = [g for g in self._priority if g is not self.groups[i]]
        group = self.groups[i]
        self._refining = group
        self._update_count()
        self.ctrl.refine_duplicate_group(list(group), lambda subs, g=group: self._refined(g, subs))

    def _refined(self, group: List[LibraryTrack], subs: List[List[LibraryTrack]]) -> None:
        self._refining = None
        if not self.winfo_exists():
            return
        idx = next((i for i, g in enumerate(self.groups) if g is group), -1)
        if idx >= 0:
            ids = {x.content_id for x in group}
            subs = [[x for x in sg if x.content_id in ids] for sg in subs]
            subs = [sg for sg in subs if len(sg) > 1]
            shown = idx == self.index
            changed = [x.content_id for x in group] != [x.content_id for x in (subs[0] if subs else [])]
            kept = {x.content_id for sg in subs for x in sg}
            gone = [x for x in group if x.content_id not in kept]       # C80 : même titre, son différent
            self._sync_apart()
            if subs:
                self.groups[idx], self.verified[idx], self.apart[idx] = subs[0], True, gone
                for sg in subs[1:]:
                    self.groups.append(sg)
                    self.verified.append(True)
                    self.apart.append([])
            else:
                self.groups.pop(idx)
                self.verified.pop(idx)
                self.apart.pop(idx)
                self.same_titles.append(gone)
            self._fill_list()
            if not self._busy and (shown or not subs):
                self._select(min(self.index if self.index != idx or subs else idx, len(self.groups) - 1)
                             if self.groups else -1)
            elif shown and changed:
                self._select(idx)
        self._refine_next()

    def _update_count(self) -> None:
        todo = sum(1 for ok in self.verified if not ok)
        n = len(self.groups)
        self.ctrl.set_diag_count("dup", n)                     # 1.3.1 (C41) : compteur de l'onglet
        if todo:
            self.count.setText(t("dup.audio_checking", i=n - todo, n=n))
            self.bar.setRange(0, max(1, len(self.verified)))   # C84
            self.bar.setValue(len(self.verified) - todo)
            self.bar.show()
        else:
            self.count.setText(plural("dup.groups_one", "dup.groups_many", n))
            self.bar.hide()
        self.ignored_btn.setText(t("dup.ignored_btn", n=len(self.ctrl.duplicate_ignores.entries)))

    # ------------------------------------------------------------------ liste
    def _loaded(self, groups: List[List[LibraryTrack]]) -> None:
        if not self.winfo_exists():
            return
        self.groups = groups
        self.verified = [False] * len(groups)
        self.apart = [[] for _ in groups]
        self.same_titles = []
        self._fill_list()
        start = next((i for i, g in enumerate(groups) if self._focus & {x.content_id for x in g}), 0)
        self._select(start if groups else -1)
        self._refine_next()

    def _fill_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for i, g in enumerate(self.groups):
            k = best_keeper(g)
            title, artist = split_display(k.title, k.artist)
            item = QListWidgetItem(f"{title}\n{artist or '—'}  ·  ×{len(g)}")
            if i < len(self.verified) and not self.verified[i]:
                queued = any(g is p for p in self._priority) or g is self._refining
                item.setToolTip(t("dup.unchecked_next") if queued else t("dup.unchecked"))
                item.setForeground(QColor(theme.DIM))
            self.list.addItem(item)
        if self.same_titles:                                   # 1.3.2 (C80) : section repliée en bas
            head = QListWidgetItem(t("dup.same_titles_head", n=len(self.same_titles)))
            head.setFlags(Qt.NoItemFlags)
            head.setForeground(QColor(theme.DIM))
            self.list.addItem(head)
            for g in self.same_titles:
                k = g[0]
                title, artist = split_display(k.title, k.artist)
                item = QListWidgetItem(f"{title}\n{artist or '—'}  ·  ≠ {len(g)}")
                item.setForeground(QColor(theme.DIM))
                item.setToolTip(t("dup.same_titles_tip"))
                self.list.addItem(item)
        self._update_count()
        self.list.blockSignals(False)

    def _clear_detail(self) -> None:
        for b in list(self._keep.buttons()):
            self._keep.removeButton(b)
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                _drop_layout(item.layout())
        self.title_entry = self.artist_entry = None
        self.cues_combo = None
        self._cue_counts = {}
        self._cues_touched = False
        self._group_cues = {}
        self._cue_strips = {}
        self.cues_summary = None
        self._pl_labels = {}
        self._info_labels = {}
        self._best_slots = {}
        self._keep_touched = False
        self.alt_box = None

    def _sync_apart(self) -> None:
        while len(self.apart) < len(self.groups):
            self.apart.append([])
        del self.apart[len(self.groups):]

    def _select(self, i: int) -> None:
        self._same_index = -1
        if i > len(self.groups) and self.same_titles:          # 1.3.2 (C80) : section « mêmes titres »
            j = i - len(self.groups) - 1
            if 0 <= j < len(self.same_titles):
                self._show_same_titles(i, j)
                return
        self.index = i
        if 0 <= i < self.list.count() and self.list.currentRow() != i:
            self.list.blockSignals(True)
            self.list.setCurrentRow(i)
            self.list.blockSignals(False)
        self._clear_detail()
        self.detail_scroll.verticalScrollBar().setValue(0)         # B34 : un nouveau groupe s'affiche en haut
        if not (0 <= i < len(self.groups)):
            self.detail_lay.addWidget(label(t("dup.none_title"), "h2"))
            self.detail_lay.addWidget(label(t("dup.none_sub"), "dim", wrap=True))
            self.detail_lay.addStretch(1)
            self._refresh_actions()
            return
        group = self.groups[i]
        keeper = best_keeper(group)
        if self._keep_id is not None:
            keeper = next((x for x in group if x.content_id == self._keep_id), keeper)
        if i < len(self.verified) and not self.verified[i]:          # C84
            vrow = hbox(spacing=theme.px(6))
            vrow.addWidget(label(t("dup.unchecked_detail"), "faint"))
            vrow.addStretch(1)
            if group is not self._refining:
                vrow.addWidget(button(t("dup.verify_now"), lambda: self.verify_now(self.index), kind="flat",
                                      icon="search"))
            self.detail_lay.addLayout(vrow)
        self.detail_lay.addWidget(label(t("dup.choose"), "dim"))
        for k, x in enumerate(group):
            self.detail_lay.addWidget(self._version_row(k, x, x is keeper))
        self._sync_apart()
        if self.apart[i]:                                      # 1.3.2 (C80) : grisés, jamais supprimés
            self.detail_lay.addWidget(label(t("dup.apart_title"), "dim"))
            for x in self.apart[i]:
                self.detail_lay.addWidget(self._apart_row(x, group))
        token = self.index

        def show_playlists(found: dict) -> None:           # 1.2.1 (C11)
            if not self.winfo_exists() or self.index != token:
                return
            for cid, lbl in self._pl_labels.items():
                names = found.get(cid) or []
                lbl.setText(t("dup.in_playlists", names=", ".join(names)) if names else t("dup.in_no_playlist"))

        self.ctrl.track_playlists([x.content_id for x in group], show_playlists)
        matches = getattr(self.ctrl, "duplicate_matches", {}) or {}
        if any(getattr(matches.get(x.content_id), "verdict", "") == "variant" for x in group):
            self.detail_lay.addWidget(label(t("dup.variant_warning"), "warn", wrap=True))
        # 1.3.0 (C13) : choisir la version dont on garde les hot cues
        self.cues_box = QWidget()
        cues_lay = hbox(self.cues_box, spacing=theme.px(6))
        cues_lay.addWidget(label(t("dup.cues_from"), "dim"))
        self.cues_combo = QComboBox()
        self.cues_combo.activated.connect(lambda _i: setattr(self, "_cues_touched", True))
        self.cues_combo.currentIndexChanged.connect(lambda _i: self._show_cue_summary())     # C79
        cues_lay.addWidget(self.cues_combo, 1)
        self.cues_box.hide()
        self.detail_lay.addWidget(self.cues_box)
        self.cues_summary = label("", "faint", wrap=True)     # 1.3.2 (C79) : ce que la fusion gardera
        self.cues_summary.hide()
        self.detail_lay.addWidget(self.cues_summary)

        strips = self._cue_strips                             # C79 : une lecture lancée pour un détail redessiné
                                                              # depuis (même groupe) ne doit pas l'écraser

        def show_cues(found: dict) -> None:
            if not self.winfo_exists() or self.index != token or strips is not self._cue_strips:
                return
            self._cue_counts = {cid: sum(1 for c in cues if c.slot) for cid, cues in found.items()}
            self._group_cues = dict(found)
            for cid, strip in self._cue_strips.items():
                strip.set_cues(found.get(cid) or [])
            self._fill_cues_combo()
            self._show_cue_summary()

        self.ctrl.load_group_cues(group, show_cues)

        def show_quality(found: dict) -> None:              # 1.3.1 (C42)
            self._quality.update(found)
            if self.winfo_exists() and self.index == token:
                self._show_quality(group)

        todo = [x for x in group if x.content_id not in self._quality]
        if todo:
            self.ctrl.track_quality(todo, show_quality)
        else:
            self._show_quality(group)
        # versions propres à retélécharger (réseau : seulement à la demande)
        alt_head = hbox(spacing=theme.px(6))
        self.alt_btn = button(t("dup.find_clean"), self._find_alternatives, kind="flat", icon="download",
                              tooltip=t("dup.find_clean_tip"))
        alt_head.addWidget(self.alt_btn)
        alt_head.addStretch(1)
        self.detail_lay.addLayout(alt_head)
        self.alt_box = vbox(spacing=theme.px(4))
        self.detail_lay.addLayout(self.alt_box)
        if self.index in self._alts:
            self._show_alternatives()
        self.detail_lay.addSpacing(theme.px(8))
        self.detail_lay.addWidget(label(t("dup.fix_metadata"), "h2"))
        title, artist = split_display(keeper.title, keeper.artist)
        form = QFormLayout()
        self.title_entry = QLineEdit(title)
        self.artist_entry = QLineEdit(artist)
        form.addRow(t("track.title"), self.title_entry)
        form.addRow(t("track.artist"), self.artist_entry)
        self.detail_lay.addLayout(form)
        self.title_entry.setToolTip(t("dup.metadata_hint"))
        self.detail_lay.addStretch(1)
        self._refresh_actions()

    def _fill_cues_combo(self) -> None:
        """Versions qui ont des hot cues ; par défaut : la version gardée si elle en a, sinon celle qui en
        a le plus (reportées sur la version gardée par alignement du son)."""
        combo = self.cues_combo
        group = self.current_group
        if combo is None or group is None:
            return
        with_cues = [x for x in group if self._cue_counts.get(x.content_id)]
        if not with_cues:
            self.cues_box.hide()
            self._show_cue_summary()
            return
        keep = group[self.keep_index()]
        current = combo.currentData() if self._cues_touched else None
        combo.clear()
        combo.addItem(t("dup.cues_keep_own"), None)
        for x in with_cues:
            k = group.index(x) + 1
            mine = t("dup.cues_kept_version") if x is keep else ""
            combo.addItem(t("dup.cues_version", k=k, n=self._cue_counts[x.content_id], title=x.title) + mine,
                          x.content_id)
        if current is not None and combo.findData(current) >= 0:
            combo.setCurrentIndex(combo.findData(current))
        elif self._cue_counts.get(keep.content_id):
            combo.setCurrentIndex(combo.findData(keep.content_id))
        else:
            best = max(with_cues, key=lambda x: self._cue_counts[x.content_id])
            combo.setCurrentIndex(combo.findData(best.content_id))
        self.cues_box.show()

    def _cue_source(self) -> Optional[LibraryTrack]:
        """Version dont les cues seront gardées à la fusion (la version gardée par défaut)."""
        group = self.current_group
        if not group:
            return None
        src = self.cues_from()
        return next((x for x in group if x.content_id == src), None) or group[self.keep_index()]

    def _show_cue_summary(self) -> None:
        """1.3.2 (C79) : la version source est mise en avant ; une ligne résume ce que la fusion donnera."""
        src = self._cue_source()
        for cid, strip in self._cue_strips.items():
            strip.set_highlight(src is not None and cid == src.content_id)
        lbl = self.cues_summary
        if lbl is None:
            return
        if src is None or not self._group_cues:
            lbl.hide()
            return
        from .cue_strip import cue_summary

        hot, loops, mem = cue_summary(self._group_cues.get(src.content_id) or [])
        lbl.setText(t("dup.cues_result", hot=hot, loops=loops, mem=mem) if hot or mem else t("dup.cues_result_none"))
        lbl.show()

    def _open_cues(self, x: LibraryTrack) -> None:
        """1.3.2 (C79) : ouvrir Grille et cues de ce son, sans passer par le lecteur ; Retour = Doublons (B29)."""
        if not x.is_analysed:
            self.ctrl.message("info", t("grid.not_analysed"))
            return
        self.ctrl._emit("open_grid", x)

    def cues_from(self) -> Optional[int]:
        if self.cues_combo is None or not self.cues_box.isVisible():
            return None
        return self.cues_combo.currentData()

    def _audio_chip(self, x: LibraryTrack) -> Optional[QWidget]:
        """1.3.0 (B02) : verdict de la comparaison du son avec la version de référence."""
        matches = getattr(self.ctrl, "duplicate_matches", {}) or {}
        if x.content_id not in matches:
            return None
        m = matches[x.content_id]
        if m == "reference":
            return chip(t("dup.audio_reference"))
        if m is None:
            c = chip(t("dup.audio_unknown"))
            c.setToolTip(t("dup.audio_unknown_tip"))
            return c
        from . import levels

        pct = int(round(m.share * 100))
        if m.verdict == "same":
            c = chip(t("dup.audio_same"), levels.CHIP_ROLE[levels.GOOD])          # C29 : vert, quel que soit l'accent
        else:
            c = chip(t("dup.audio_variant", pct=pct), levels.CHIP_ROLE[levels.similarity(pct)])
        c.setToolTip(t("dup.audio_tip", pct=int(round(m.share * 100)), shift=f"{m.shift_ms / 1000:+.2f}"))
        return c

    def _version_row(self, k: int, x: LibraryTrack, checked: bool) -> QWidget:
        row = panel(role="banner")
        lay = hbox(row, margins=theme.px(6))
        radio = QRadioButton()
        radio.setChecked(checked)
        self._keep.addButton(radio, k)
        radio.toggled.connect(lambda on: self._keeper_changed() if on else None)
        lay.addWidget(radio)
        text = vbox(spacing=0)
        name = label(x.title)
        name.setStyleSheet("font-weight:600;")
        text.addWidget(name)
        info_lbl = label("", "dim")
        info_lbl.setTextFormat(Qt.RichText)
        self._info_labels[x.content_id] = info_lbl
        info_lbl.setText(self._info_text(x))
        text.addWidget(info_lbl)
        from .cue_strip import CueStrip

        strip = CueStrip(int((x.duration_seconds or 0) * 1000))   # 1.3.2 (C79) : où sont les cues
        if x.content_id in self._group_cues:
            strip.set_cues(self._group_cues[x.content_id])
        self._cue_strips[x.content_id] = strip
        text.addWidget(strip)
        pl = label("", "faint", wrap=True)
        self._pl_labels[x.content_id] = pl
        text.addWidget(pl)
        lay.addLayout(text, 1)
        best = hbox(spacing=0)                                # C42 : « meilleure qualité », une fois connue
        self._best_slots[x.content_id] = best
        lay.addLayout(best)
        audio = self._audio_chip(x)
        if audio is not None:
            lay.addWidget(audio)
        missing = self.ctrl.file_missing(x)                   # 1.3.0-rc.3 (B20)
        if missing:
            gone = chip(t("diag.file_missing"), "chip_warn")
            gone.setToolTip(self.ctrl.missing_file_text(self.ctrl.library.absolute_path(x)))
            lay.addWidget(gone)
        if x.camelot:
            lay.addWidget(CamelotPill(x.camelot))
        # 1.2.1 (C12) : écouter le début (intro) ou le milieu de chaque version pour comparer
        start = button(t("dup.listen_start"), lambda: self._listen(k, 0.0), icon="play", tooltip=t("dup.listen_start_tip"))
        middle = button(t("dup.listen_middle"), lambda: self._listen(k, 0.45), kind="flat",
                        tooltip=t("dup.listen_middle_tip"))
        cues = button(t("dup.open_cues"), lambda: self._open_cues(x), kind="flat", icon="grid",
                      tooltip=t("dup.open_cues_tip"))           # 1.3.2 (C79) : sans passer par le lecteur
        for b in (start, middle, cues):
            b.setEnabled(not missing)
            lay.addWidget(b)
        out = button(t("dup.exclude"), lambda: self._exclude(k), kind="flat", icon="close",
                     tooltip=t("dup.exclude_tip"))              # rc.5 (C62)
        lay.addWidget(out)
        return row

    # ------------------------------------------------------------ 1.3.1 (C42) : qualité
    def _info_text(self, x: LibraryTrack) -> str:
        from html import escape

        from . import levels

        missing = self.ctrl.file_missing(x)
        fmt, lvl = levels.audio_text(self._quality.get(x.content_id), x.file_type, missing)
        info = [escape(x.artist or t("dup.no_artist")), format_duration(x.duration_seconds), levels.html(fmt, lvl),
                f"{x.bpm:.0f} BPM" if x.bpm else escape(t("dup.not_analysed")), (x.date_added or "")[:10]]
        return "  ·  ".join(i for i in info if i)

    def _best(self, group: List[LibraryTrack]) -> Optional[LibraryTrack]:
        """Version de meilleure qualité audio (seulement si toutes sont connues et qu'une seule l'emporte)."""
        from . import levels

        if len(group) < 2 or any(y.content_id not in self._quality or self._quality[y.content_id] is None
                                 for y in group):
            return None
        rank = {y.content_id: levels.quality_rank(self._quality[y.content_id].bitrate,
                                                  self._quality[y.content_id].lossless) for y in group}
        top = max(rank.values())
        winners = [y for y in group if rank[y.content_id] == top]
        return winners[0] if top > 0 and len(winners) == 1 else None

    def _show_quality(self, group: List[LibraryTrack]) -> None:
        for x in group:
            lbl = self._info_labels.get(x.content_id)
            if lbl is not None:
                lbl.setText(self._info_text(x))
        best = self._best(group)
        for x in group:
            slot = self._best_slots.get(x.content_id)
            if slot is None:
                continue
            _drop_layout(slot)
            if best is not None and x is best:
                c = chip(t("dup.best_quality"), "chip_good")
                c.setToolTip(t("dup.best_quality_tip"))
                slot.addWidget(c)
        # proposer par défaut de garder la meilleure qualité (le titre proposé reste le plus propre)
        if best is not None and not self._keep_touched and self.keep_index() != group.index(best):
            b = self._keep.button(group.index(best))
            if b is not None:
                self._auto_keep = True
                b.setChecked(True)
                self._auto_keep = False

    # --------------------------------------------- versions propres à retélécharger
    def _find_alternatives(self) -> None:
        group = self.current_group
        if group is None:
            return
        idx = self.index
        if idx in self._alts:
            self._show_alternatives()
            return
        self._alts[idx] = None
        self._show_alternatives()

        def done(found: List[Any]) -> None:
            self._alts[idx] = found
            if self.winfo_exists() and self.index == idx:
                self._show_alternatives()

        self.ctrl.find_alternatives(best_keeper(group), done)

    def _show_alternatives(self) -> None:
        box = self.alt_box
        if box is None:
            return
        for b in list(self._keep.buttons()):
            if self._keep.id(b) >= ALT:
                self._keep.removeButton(b)
        _drop_layout(box)
        found = self._alts.get(self.index)
        self.alt_btn.setEnabled(self.index not in self._alts)
        if found is None:
            box.addWidget(label(t("diag.alt_searching"), "faint"))
            return
        if not found:
            box.addWidget(label(t("diag.alt_none"), "faint", wrap=True))
            return
        from html import escape

        from . import levels

        for i, c in enumerate(found):
            row = panel(role="banner")
            lay = hbox(row, margins=theme.px(6))
            radio = QRadioButton()
            self._keep.addButton(radio, ALT + i)
            radio.toggled.connect(lambda on: self._keeper_changed() if on else None)
            lay.addWidget(radio)
            text = vbox(spacing=0)
            name = label(c.track.title)
            name.setStyleSheet("font-weight:600;")
            text.addWidget(name)
            exp, lvl = levels.expected_download(c.track.source, getattr(self.ctrl.settings, "audio_format", "m4a"))
            kind = t("track.song") if c.track.is_song else t("track.video")
            line = label("  ·  ".join([escape(c.track.artist or ""), format_duration(c.track.duration_seconds),
                                       escape(kind), levels.html(exp, lvl)]), "dim")
            line.setTextFormat(Qt.RichText)
            line.setToolTip(levels.expected_tip(getattr(self.ctrl.settings, "audio_format", "m4a")))
            text.addWidget(line)
            lay.addLayout(text, 1)
            lay.addWidget(chip(SOURCE_LABELS.get(c.track.source, c.track.source)))
            lay.addWidget(icon_button("play", lambda _c=False, tr=c.track: self.ctrl.preview(tr), t("action.listen")))
            box.addWidget(row)

    def _listen(self, k: int, at: float) -> None:
        from PySide6.QtCore import QTimer

        from ..audio.player import PLAYING

        group = self.groups[self.index]
        self.ctrl.play_queue(group, k)
        if at <= 0:
            return
        player = self.ctrl.player

        def seek_when_ready(tries: int = 0) -> None:
            if player.state == PLAYING and player.duration > 0:
                player.seek(player.duration * at)
            elif tries < 50 and self.winfo_exists():
                QTimer.singleShot(100, lambda: seek_when_ready(tries + 1))

        QTimer.singleShot(100, seek_when_ready)

    # ------------------------------------------------------------ 1.3.2 (C84) : vérifier un groupe en priorité
    def _list_menu(self, pos: Any) -> None:
        row = self.list.indexAt(pos).row()
        if not (0 <= row < len(self.groups)) or self.verified[row]:
            return
        menu = QMenu(self)
        menu.addAction(t("dup.verify_now"), lambda: self.verify_now(row))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def verify_now(self, i: int) -> None:
        """Le groupe passe en tête de file : vérifié juste après celui en cours."""
        if not (0 <= i < len(self.groups)) or self.verified[i]:
            return
        g = self.groups[i]
        self._priority = [g] + [x for x in self._priority if x is not g]
        self._fill_list()
        self._refine_next()

    # ------------------------------------------------------------ 1.3.2 (C80) : même titre, son différent
    def _apart_row(self, x: LibraryTrack, others: List[LibraryTrack]) -> QWidget:
        row = panel(role="banner")
        row.setEnabled(True)
        lay = hbox(row, margins=theme.px(6))
        text = vbox(spacing=0)
        name = label(x.title, "dim")
        text.addWidget(name)
        text.addWidget(label(self._plain_info(x), "faint"))
        lay.addLayout(text, 1)
        lay.addWidget(chip(t("dup.audio_different")))
        play = button(t("dup.listen_start"), lambda: self.ctrl.play_queue([x], 0), kind="flat", icon="play")
        play.setEnabled(not self.ctrl.file_missing(x))
        lay.addWidget(play)
        lay.addWidget(button(t("dup.edit_title"), lambda: self._edit_title(x), kind="flat", icon="edit",
                             tooltip=t("dup.edit_title_tip")))
        lay.addWidget(button(t("dup.exclude"), lambda: self._set_apart(x, others), kind="flat", icon="close",
                             tooltip=t("dup.apart_exclude_tip")))
        return row

    def _plain_info(self, x: LibraryTrack) -> str:
        bits = [x.artist or t("dup.no_artist"), format_duration(x.duration_seconds),
                f"{x.bpm:.0f} BPM" if x.bpm else "", (x.date_added or "")[:10]]
        return "  ·  ".join(b for b in bits if b)

    def _show_same_titles(self, row: int, j: int) -> None:
        self.index = -1
        self._same_index = j
        if self.list.currentRow() != row:
            self.list.blockSignals(True)
            self.list.setCurrentRow(row)
            self.list.blockSignals(False)
        self._clear_detail()
        group = self.same_titles[j]
        self.detail_lay.addWidget(label(t("dup.same_titles_title"), "h2"))
        self.detail_lay.addWidget(label(t("dup.same_titles_sub"), "dim", wrap=True))
        for x in group:
            self.detail_lay.addWidget(self._apart_row(x, [o for o in group if o is not x]))
        self.detail_lay.addStretch(1)
        self._refresh_actions()

    def _edit_title(self, x: LibraryTrack) -> None:
        from .track_info_dialog import TrackInfoDialog

        TrackInfoDialog(self, self.ctrl, x)

    def _set_apart(self, x: LibraryTrack, others: List[LibraryTrack]) -> None:
        """« Ce n'est pas un doublon » sur un son grisé : retenu, il ne revient plus avec ces sons."""
        if others:
            self.ctrl.duplicate_ignores.add(x, others)
        self.ctrl.message("info", t("dup.excluded_msg", title=x.title))
        for lst in self.apart:
            if x in lst:
                lst.remove(x)
        for g in list(self.same_titles):
            if x in g:
                g.remove(x)
                if len(g) < 2:
                    self.same_titles.remove(g)
        j, i = self._same_index, self.index
        self._fill_list()
        if j >= 0:
            self._select(len(self.groups) + 1 + min(j, len(self.same_titles) - 1) if self.same_titles
                         else min(max(i, 0), len(self.groups) - 1))
        else:
            self._select(i)

    def keep_index(self) -> int:
        cid = self._keep.checkedId()
        return cid if 0 <= cid < ALT else 0

    def download_choice(self) -> Optional[Any]:
        """Version à retélécharger choisie (Candidate), sinon None."""
        cid = self._keep.checkedId()
        found = self._alts.get(self.index) or []
        return found[cid - ALT] if cid >= ALT and 0 <= cid - ALT < len(found) else None

    def _keeper_changed(self) -> None:
        if not self._auto_keep:
            self._keep_touched = True
        self.apply_btn.setText(t("diag.apply_download") if self.download_choice() is not None else t("dup.apply"))
        if self.title_entry is None or not (0 <= self.index < len(self.groups)) or self.download_choice() is not None:
            return
        group = self.groups[self.index]
        x = group[self.keep_index()]
        if not self._cues_touched:
            self._fill_cues_combo()
        self._show_cue_summary()
        if self._auto_keep:                 # meilleure qualité choisie d'office : le titre le plus propre reste
            return
        title, artist = split_display(x.title, x.artist)
        current = (self.title_entry.text().strip(), self.artist_entry.text().strip())
        if current[0] and not any(split_display(g.title, g.artist) == current for g in group):
            return                                  # l'utilisateur a déjà corrigé à la main : on garde
        self.title_entry.setText(title)
        self.artist_entry.setText(artist)

    def _refresh_actions(self) -> None:
        ok = 0 <= self.index < len(self.groups) and not self._busy
        self.apply_btn.setEnabled(ok)
        self.skip_btn.setEnabled(ok)
        self.later_btn.setEnabled(ok)

    # ------------------------------------------------------------------ actions
    def _skip(self) -> None:
        if 0 <= self.index < len(self.groups):
            self.groups.pop(self.index)
            if self.index < len(self.verified):
                self.verified.pop(self.index)
            if self.index < len(self.apart):
                self.apart.pop(self.index)
            idx = self.index
            self._fill_list()
            self._select(min(idx, len(self.groups) - 1))
            self._refine_next()

    def _exclude(self, k: int) -> None:
        """rc.5 (C62) : ce son n'est pas un doublon des autres du groupe (retenu) ; le reste du groupe
        peut toujours être fusionné."""
        group = self.current_group
        if group is None or self._busy or not (0 <= k < len(group)):
            return
        x = group[k]
        self.ctrl.duplicate_ignores.add(x, [o for o in group if o is not x])
        self.ctrl.message("info", t("dup.excluded_msg", title=x.title))
        if len(group) <= 2:
            self._skip()
            return
        group.pop(k)
        self._fill_list()
        self._select(self.index)

    def _not_duplicates(self) -> None:
        group = self.current_group
        if group is None or self._busy:
            return
        self.ctrl.duplicate_ignores.add_group(group)
        self.ctrl.message("info", t("dup.group_ignored_msg"))
        self._skip()

    def _show_ignored(self) -> None:
        IgnoredDialog(self, self.ctrl, self._reload)

    def _full_scan(self) -> None:
        self._reload(full=True)

    def _reload(self, full: bool = False) -> None:
        if not self.winfo_exists() or self._busy:
            return
        self.groups, self.verified, self._refining = [], [], None
        self.apart, self.same_titles = [], []
        self._fill_list()
        self._select(-1)
        self.count.setText(t("dup.searching"))
        if full:
            self.ctrl.message("info", t("dup.full_running"))
        self.ctrl.find_duplicates(self._loaded, self._progress, full=full)

    def _apply(self) -> None:
        if not (0 <= self.index < len(self.groups)) or self.title_entry is None:
            return
        group = self.groups[self.index]
        clean = self.download_choice()
        if clean is not None:                           # C42 : une version propre remplace tout le groupe
            def replace() -> None:
                if self.ctrl.replace_with_download(clean.track, group) is not None:
                    self._skip()

            ConfirmDialog(self, t("dup.confirm_title"), t("dup.replace_all_msg", n=len(group), title=clean.track.title),
                          replace, confirm_text=t("diag.apply_download"), danger=True, detail=t("dup.confirm_detail"))
            return
        keep = group[self.keep_index()]
        others = [x for x in group if x is not keep]
        title = self.title_entry.text().strip() or keep.title
        artist = self.artist_entry.text().strip()
        new_title = title if title != keep.title else None
        new_artist = artist if artist != keep.artist else None

        cues_from = self.cues_from()
        if cues_from == keep.content_id:
            cues_from = None
        # 1.3.2 (C82) : plus de fenêtre de confirmation. Le groupe quitte la liste tout de suite ; la
        # fusion n'est écrite qu'après le délai choisi (10 s), « Annuler » remet tout comme avant.
        pos = self.index
        state = {"group": group, "apart": self.apart[pos] if pos < len(self.apart) else [], "pos": pos,
                 "title": keep.title}

        def failed(_e: BaseException) -> None:
            if self.winfo_exists():
                self._put_back(state)

        delay = int(getattr(self.ctrl.settings, "merge_undo_s", 10) or 10)
        state["token"] = self.ctrl.schedule_duplicates_merge(
            keep.content_id, [x.content_id for x in others], new_title, new_artist, cues_from=cues_from,
            delay_s=delay, ok=lambda _r: self._merge_done(state), err=failed)
        self._pending.append(state)
        self._skip()
        self.ctrl.message("ok", t("dup.merge_pending", n=len(others), title=keep.title, s=delay))
        self.ctrl._emit("message_action", t("dup.undo"), lambda: self._undo(state))
        self._show_pending()

    def _merge_done(self, state: dict) -> None:
        if state in self._pending:
            self._pending.remove(state)
        if self.winfo_exists():
            self._show_pending()

    def _undo(self, state: dict) -> None:
        if state not in self._pending or not self.ctrl.cancel_merge(state["token"]):
            return
        self._pending.remove(state)
        self.ctrl.message("info", t("dup.merge_undone", title=state["title"]))
        if self.winfo_exists():
            self._put_back(state)
            self._show_pending()

    def _undo_last(self) -> None:
        if self._pending:
            self._undo(self._pending[-1])

    def _put_back(self, state: dict) -> None:
        pos = min(max(0, state["pos"]), len(self.groups))
        self.groups.insert(pos, state["group"])
        self.verified.insert(pos, True)
        self._sync_apart()
        self.apart.insert(pos, state["apart"])
        del self.apart[len(self.groups):]
        self._fill_list()
        self._select(pos)

    def _show_pending(self) -> None:
        n = len(self._pending)
        self.undo_btn.setText(t("dup.pending_btn", n=n))
        self.undo_btn.setVisible(n > 0)

    @property
    def current_group(self) -> Optional[List[LibraryTrack]]:
        return self.groups[self.index] if 0 <= self.index < len(self.groups) else None


class IgnoredDialog(BaseDialog):
    """rc.5 (C62) : les paires « pas un doublon » retenues ; Annuler un choix ou tout rétablir."""

    def __init__(self, parent: Any, controller: Any, on_change: Any) -> None:
        super().__init__(parent, t("dup.ignored_title"), 560, 420)
        self.ctrl, self.on_change = controller, on_change
        self.changed = False
        self.body.addWidget(label(t("dup.ignored_sub"), "dim", wrap=True))
        self.list = QListWidget()
        self.body.addWidget(self.list, 1)
        bar = hbox()
        self.undo_btn = button(t("dup.restore"), self._undo, icon="back")
        self.all_btn = button(t("dup.restore_all"), self._undo_all, kind="flat")
        bar.addWidget(self.undo_btn)
        bar.addWidget(self.all_btn)
        bar.addStretch(1)
        bar.addWidget(button(t("action.close"), self.close))
        self.body.addLayout(bar)
        self._fill()
        self.show_dialog()

    def _fill(self) -> None:
        self.list.clear()
        entries = list(reversed(self.ctrl.duplicate_ignores.entries))     # les plus récents d'abord
        for e in entries:
            item = QListWidgetItem(t("dup.ignored_row", a=e.get("ta") or e["a"], b=e.get("tb") or e["b"])
                                   + f"\n{(e.get('at') or '')[:16].replace('T', ' ')}")
            item.setData(256, e)
            self.list.addItem(item)
        if not entries:
            self.list.addItem(QListWidgetItem(t("dup.ignored_none")))
        self.undo_btn.setEnabled(bool(entries))
        self.all_btn.setEnabled(bool(entries))

    def _undo(self) -> None:
        picked = [i.data(256) for i in self.list.selectedItems() if i.data(256)]
        if not picked and self.list.currentItem() is not None and self.list.currentItem().data(256):
            picked = [self.list.currentItem().data(256)]
        if picked:
            self.ctrl.duplicate_ignores.remove(picked)
            self.changed = True
            self._fill()

    def _undo_all(self) -> None:
        self.ctrl.duplicate_ignores.clear()
        self.changed = True
        self._fill()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt
        if self.changed and self.on_change is not None:
            self.on_change()
        super().closeEvent(event)


def _drop_layout(lay: Any) -> None:
    while lay.count():
        item = lay.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _drop_layout(item.layout())
