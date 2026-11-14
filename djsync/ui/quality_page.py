"""Onglet « Qualité » du Diagnostic (1.4.1, C135) : remplace « Mauvaise qualité » et « Améliorer ».

* Portée : toute la bibliothèque, une playlist ou une sélection (ouverte depuis la Bibliothèque).
* Tous les sons de la portée, avec qualité annoncée, qualité mesurée (spectre, C46) et drapeaux (vient d'une
  vidéo, faux sans perte, sous le seuil). Filtres « sous X kbps réels », « vient d'une vidéo », « faux sans
  perte » (un son passe s'il répond à un filtre coché ; aucun filtre : tous les sons).
* « Mesurer la qualité » : mesure en arrière-plan des sons pas encore mesurés, inscrite au volet des tâches
  (C145 : pause, arrêt) ; une mesure interrompue reprend où elle s'était arrêtée (cache du spectre).
* Pour chaque son : meilleure version trouvée et gain. Détail d'un son (double-clic, « Chercher une meilleure
  version ») : la liste de résultats de la page Haute qualité (mêmes colonnes et pastilles), artiste + titre
  modifiables, écart de durée et gain ; Écouter, « Remplacer par celle-ci », Acheter.
* « Remplacer tout ce qui est sûr » (sans perte, même durée) : une seule confirmation pour le lot.
* Remplacement : la fonction existante (playlists gardées, hot cues recalés, sauvegarde), sans modification.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox

from ..i18n import plural, t
from . import theme
from .diag_tabs import add_tabs
from .dialogs import BaseDialog, ConfirmDialog
from .views.cue_column import cue_column, cue_values
from .views.cue_column import fill as cue_column_fill
from .widgets import Column, Row, TrackTable, button, hbox, label, line_edit

FLAG_KEYS = ("video", "fake", "under")


def ignore_key(track: Any) -> str:
    """Même clé que l'ancien onglet « Mauvaise qualité » (« Ignorer » retenu d'une version à l'autre)."""
    return f"q:{track.content_id}:{track.title}"


class QualityPage(BaseDialog):
    as_page = True
    modal = False

    def __init__(self, parent: Any, controller: Any, ids: Optional[Sequence[int]] = None,
                 scope_name: str = "") -> None:
        super().__init__(parent, t("diagtab.quality"), 1000, 600)
        self.ctrl = controller
        self.rows: Dict[str, Any] = {}             # toutes les lignes de la portée
        self.shown: Dict[str, Any] = {}            # lignes qui passent les filtres
        self._queue: List[str] = []
        self._searching = False
        self._loading = True
        self._selection = [int(i) for i in ids] if ids else None
        self._selection_name = scope_name
        self.detail: Optional["QualityDetail"] = None
        add_tabs(self, controller, "quality")

        head = hbox()
        head.addWidget(label(t("quality.page_title"), "h2"))
        self.scope = QComboBox()
        self._fill_scopes()
        self.scope.currentIndexChanged.connect(lambda _i: self._scan())
        head.addWidget(self.scope)
        head.addStretch(1)
        self.count = label(t("improve.scanning"), "dim")
        head.addWidget(self.count)
        self.measure_btn = button("", self._measure, icon="wave", tooltip=t("quality.measure_tip"))
        head.addWidget(self.measure_btn)
        self.recompute_btn = button(t("quality.recompute_all"), self._recompute, icon="wave",
                                    tooltip=t("quality.recompute_all_tip"))
        head.addWidget(self.recompute_btn)
        self.body.addLayout(head)

        filters = hbox()
        self.f_under = QCheckBox(t("quality.filter_under"))
        self.f_under.setChecked(True)
        self.f_kbps = QSpinBox()
        self.f_kbps.setRange(96, 320)
        self.f_kbps.setSingleStep(32)
        self.f_kbps.setSuffix(" kbps")
        self.f_kbps.setValue(int(controller.settings.improve_threshold or 256))
        self.f_video = QCheckBox(t("quality.filter_video"))
        self.f_video.setChecked(True)
        self.f_fake = QCheckBox(t("quality.filter_fake"))
        self.f_fake.setChecked(True)
        for w in (self.f_under, self.f_kbps, self.f_video, self.f_fake):
            filters.addWidget(w)
        for box in (self.f_under, self.f_video, self.f_fake):
            box.toggled.connect(lambda _on: self._fill())
        self.f_kbps.valueChanged.connect(self._kbps_changed)
        filters.addStretch(1)
        self.body.addLayout(filters)
        self.body.addWidget(label(t("quality.intro"), "faint", wrap=True))

        cols = [Column("title", t("track.title"), 240, stretch=True, min_width=140),
                Column("artist", t("track.artist"), 150, priority=2),
                Column("now", t("quality.col_announced"), 100),
                Column("real", t("quality.col_measured"), 100, priority=1),
                Column("flags", t("quality.col_flags"), 150, priority=3),
                Column("found", t("improve.found"), 240, priority=1),
                Column("gain", t("improve.gain"), 140),
                cue_column()]                                          # 1.4.1 (C60) : cues placés
        self.table = TrackTable(self, cols)
        self._cue_marks: Dict[int, Any] = {}

        def _save() -> None:
            try:
                controller.settings.save()
            except OSError:
                pass

        self.table.enable_layout("quality", lambda: controller.settings.table_layouts, _save)
        self.table.set_empty("search", t("quality.empty"))
        self.table.on_select = lambda _ids: self._refresh()
        self.table.on_double = lambda iid: self.open_detail(iid)
        self.table.menu_builder = self._menu
        self.body.addWidget(self.table, 1)

        bar = hbox()
        self.search_btn = button(t("quality.search_one"), self._search_selected, icon="search")
        bar.addWidget(self.search_btn)
        self.search_all_btn = button("", self._search_all, kind="flat", icon="search")
        bar.addWidget(self.search_all_btn)
        self.ignore_btn = button(t("diag.ignore"), self._ignore_selected, kind="flat", icon="close")
        bar.addWidget(self.ignore_btn)
        bar.addStretch(1)
        self.sure_btn = button("", self._apply_sure, icon="check")
        self.sure_btn.setToolTip(t("improve.sure_tip"))
        bar.addWidget(self.sure_btn)
        self.apply_btn = button(t("improve.apply"), self._apply_selected, kind="primary", icon="download")
        bar.addWidget(self.apply_btn)
        self.body.addLayout(bar)
        controller.on("quality_changed", self._quality_changed)
        controller.on("library", self._playlists_changed)
        if not getattr(controller, "playlists", None) and hasattr(controller, "fetch_playlists"):
            controller.fetch_playlists(self._playlists_changed)
        self.show_dialog()
        self._scan()

    # ------------------------------------------------------------------ portée
    def _fill_scopes(self) -> None:
        """Choix de la portée ; la portée en cours reste choisie quand la liste des playlists change."""
        keep = self.scope.currentData() if self.scope.count() else None
        self.scope.blockSignals(True)
        self.scope.clear()
        if self._selection:
            self.scope.addItem(t("quality.scope_selection", n=len(self._selection)), ("sel", None))
        self.scope.addItem(t("quality.scope_library"), ("lib", None))
        for p in list(getattr(self.ctrl, "playlists", None) or []):
            if getattr(p, "is_folder", False):
                continue
            self.scope.addItem(t("quality.scope_playlist", name=p.name), ("pl", p.playlist_id))
        if keep is not None:
            idx = self.scope.findData(keep)
            if idx >= 0:
                self.scope.setCurrentIndex(idx)
        self.scope.blockSignals(False)

    def _playlists_changed(self, *_a: Any) -> None:
        if self.winfo_exists():
            self._fill_scopes()

    def set_scope(self, ids: Optional[Sequence[int]], name: str = "") -> None:
        """Portée « sélection » (sons choisis dans la Bibliothèque) ; None : toute la bibliothèque."""
        self._selection = [int(i) for i in ids] if ids else None
        self._selection_name = name
        self._fill_scopes()
        self.scope.blockSignals(True)
        self.scope.setCurrentIndex(0 if ids else max(0, self.scope.findData(("lib", None))))
        self.scope.blockSignals(False)
        self._scan()

    def _scope_ids(self) -> Optional[List[int]]:
        kind, pid = self.scope.currentData() or ("lib", None)
        if kind == "sel":
            return list(self._selection or [])
        if kind == "pl":
            return self.ctrl.quality_playlist_ids(pid)
        return None

    # ------------------------------------------------------------------ données
    def _scan(self) -> None:
        self._loading = True
        self.count.setText(t("improve.scanning"))
        self.table.show_skeleton()

        def progress(i: int, n: int) -> None:
            if self.winfo_exists() and self._loading:
                self.count.setText(t("diag.progress", i=i, n=n))

        def done(rows: List[Any]) -> None:
            if not self.winfo_exists():
                return
            self._loading = False
            old = self.rows
            self.rows = {}
            for w in rows:                      # une recherche déjà faite reste (nouvelle lecture du fichier)
                key = str(w.track.content_id)
                prev = old.get(key)
                if prev is not None and prev.searched:
                    w.finds, w.results, w.searched, w.chosen = prev.finds, prev.results, True, prev.chosen
                self.rows[key] = w
            self._fill()

        self.ctrl.quality_scan(done, progress, ids=self._scope_ids())

    def _quality_changed(self, *_a: Any) -> None:
        if self.winfo_exists() and not self._loading:
            self._scan()

    def _kbps_changed(self, value: int) -> None:
        self.ctrl.settings.improve_threshold = int(value)
        self.ctrl.save_settings_quiet()
        self._fill()

    def _filtered(self) -> List[Any]:
        from ..core.improve import select

        ignored = set(self.ctrl.settings.diag_ignored)
        rows = [w for w in self.rows.values() if ignore_key(w.track) not in ignored]
        under = int(self.f_kbps.value()) if self.f_under.isChecked() else None
        return select(rows, under=under, video=self.f_video.isChecked(), fake=self.f_fake.isChecked())

    def _row(self, w: Any) -> Row:
        from ..core.improve import announced_label, measured_label

        best = w.best
        found = (f"{best.source_label} · {best.artist} – {best.title}" if best is not None
                 else (t("improve.none") if w.searched else ""))
        flags = [t(f"quality.flag_{k}") for k in w.flags(int(self.f_kbps.value()))]
        values = {"title": w.track.title, "artist": w.track.artist or "", "now": announced_label(w.info),
                  "real": measured_label(w.info) or t("quality.not_measured"), "flags": " · ".join(flags),
                  "found": found, "gain": w.gain}
        if w.video:
            values["flags__tip"] = t("quality.video_tip", reason=w.video)
        if not w.measured:
            values["real__color"] = theme.DIM
        elif w.fake:
            values["real__color"] = theme.WARN
        values.update(cue_values(self._cue_marks.get(w.track.content_id)))      # 1.4.1 (C60)
        if w.gain:
            values["gain__color"] = theme.GOLD if "→ FLAC" in w.gain or "→ WAV" in w.gain or "→ AIFF" in w.gain \
                else theme.GOOD
        return Row(str(w.track.content_id), values, (), w)

    def _fill(self) -> None:
        if self._loading:
            return
        rows = self._filtered()
        self.shown = {str(w.track.content_id): w for w in rows}
        self.table.set_rows([self._row(w) for w in rows], keep_selection=True)
        problems = sum(1 for w in self.rows.values() if w.flags(int(self.f_kbps.value())))
        self.ctrl.set_diag_count("quality", problems)
        missing = [r for r in self.table.all_rows()
                   if r.data is not None and r.data.track.content_id not in self._cue_marks]
        if missing:                                                     # 1.4.1 (C60) : lus une fois par son
            cue_column_fill(self.table, self.ctrl, missing, track_of=lambda r: r.data.track,
                            done=self._cue_marks.update)
        self._refresh()
        self._fill_then_focus()

    def _unmeasured(self) -> List[Any]:
        return [w.track for w in self.rows.values() if not w.measured]

    def _refresh(self) -> None:
        from ..core.improve import sure

        rows = list(self.shown.values())
        searched = sum(1 for w in rows if w.searched)
        found = sum(1 for w in rows if w.best is not None)
        todo = sum(1 for w in rows if not w.searched)
        if not self._loading:
            self.count.setText(t("quality.count", n=len(rows), total=len(self.rows), searched=searched, found=found))
        self.search_all_btn.setText(t("improve.search_all", n=todo))
        self.search_all_btn.setEnabled(bool(todo) and not self._searching)
        n_sure = sum(1 for w in rows if sure(w))
        self.sure_btn.setText(t("improve.apply_sure", n=n_sure))
        self.sure_btn.setEnabled(bool(n_sure))
        sel = self._selected()
        self.apply_btn.setEnabled(any(w.best is not None for w in sel))
        self.search_btn.setEnabled(len(sel) == 1)
        self.ignore_btn.setEnabled(bool(sel))
        running = bool(self.ctrl.quality_running)
        unmeasured = len(self._unmeasured())
        self.measure_btn.setText(t("quality.measure", n=unmeasured))
        self.measure_btn.setEnabled(bool(unmeasured) and not running)
        self.recompute_btn.setText(t("quality.recompute_stop") if running else t("quality.recompute_all"))

    def _selected(self) -> List[Any]:
        return [self.shown[i] for i in self.table.selected_iids() if i in self.shown]

    # ------------------------------------------------------------------ mesure (arrière-plan, C145)
    def _measure(self) -> None:
        tracks = self._unmeasured()
        if not tracks:
            return
        self._start_measure(tracks, force=False)

    def _recompute(self) -> None:
        if self.ctrl.quality_running:
            self.ctrl.stop_quality()
            self.recompute_btn.setEnabled(False)
            return
        ids = self._scope_ids()
        tracks = None if ids is None else [w.track for w in self.rows.values()]
        self._start_measure(tracks, force=True)

    def _start_measure(self, tracks: Optional[List[Any]], force: bool) -> None:
        def progress(i: int, n: int) -> None:
            if self.winfo_exists():
                self.count.setText(t("quality.measuring", i=i, n=n))

        def done(fakes: int) -> None:
            if not self.winfo_exists():
                return
            self.recompute_btn.setEnabled(True)
            self.ctrl.message("ok" if not fakes else "warn", t("quality.measured", n=fakes))
            self._refresh()

        if not self.ctrl.measure_quality(tracks, done, progress, force=force):
            self.ctrl.message("info", t("quality.busy"))
            return
        self._refresh()

    # ------------------------------------------------------------------ recherche (un son à la fois)
    def _search_selected(self) -> None:
        sel = self._selected()
        if len(sel) == 1:
            self.open_detail(str(sel[0].track.content_id))

    def _search_all(self) -> None:
        self._enqueue([k for k, w in self.shown.items() if not w.searched])

    def _enqueue(self, keys: List[str]) -> None:
        self._queue += [k for k in keys if k not in self._queue]
        self._next()

    def _next(self) -> None:
        if self._searching or not self._queue or not self.winfo_exists():
            self._refresh()
            return
        key = self._queue.pop(0)
        w = self.rows.get(key)
        if w is None:
            self._next()
            return
        self._searching = True
        if key in self.shown:
            self.table.update_values(key, found=t("improve.searching"))

        def done(row: Any) -> None:
            self._searching = False
            if not self.winfo_exists():
                return
            self.row_changed(row)
            self._next()

        self.ctrl.quality_search(w, done)
        self._refresh()

    def row_changed(self, row: Any) -> None:
        key = str(row.track.content_id)
        if key in self.shown:
            self.table.update_values(key, **self._row(row).values)
        self._refresh()

    # ------------------------------------------------------------------ détail d'un son
    def open_detail(self, iid: str) -> Optional["QualityDetail"]:
        w = self.rows.get(str(iid))
        if w is None:
            return None
        if self.detail is not None and self.detail.winfo_exists():
            self.detail.close()
        self.detail = QualityDetail(self, w)
        return self.detail

    def focus_track(self, content_id: int) -> Optional["QualityDetail"]:
        """Ouvert depuis « Un son » (C140) : sélectionne le son et ouvre son détail dès qu'il est lu."""
        key = str(content_id)
        if self._loading or key not in self.rows:
            self.__dict__["_pending_focus"] = key
            return None
        if key in self.shown:
            self.table.select([key])
        return self.open_detail(key)

    def _fill_then_focus(self) -> None:
        key = self.__dict__.pop("_pending_focus", None)
        if key is not None and key in self.rows:
            self.focus_track(int(key))

    # ------------------------------------------------------------------ remplacement (validé)
    def confirm(self, rows: List[Any]) -> None:
        """Une seule confirmation pour tout le lot : nombre de sons et sources ; jamais une fenêtre par son."""
        from ..core.improve import choose_batch

        rows = [w for w in rows if w.best is not None]
        if not rows:
            return
        picks = choose_batch(rows)
        sources = sorted({getattr(f, "source_label", "") or getattr(f, "source", "") for f in picks.values()})
        detail = "\n".join(f"• {w.track.title} : {w.gain}" for w in rows[:12]) + ("\n…" if len(rows) > 12 else "")
        detail = t("quality.confirm_sources", sources=", ".join(s for s in sources if s)) + "\n" + detail

        def go() -> None:
            n = self.ctrl.quality_apply(rows)
            for w in rows[:n]:
                self.rows.pop(str(w.track.content_id), None)
            self._fill()

        ConfirmDialog(self, t("improve.confirm_title"),
                      plural("improve.confirm_one", "improve.confirm_many", len(rows)), go,
                      confirm_text=t("improve.apply"), detail=detail)

    def _apply_selected(self) -> None:
        self.confirm(self._selected())

    def _apply_sure(self) -> None:
        from ..core.improve import sure

        self.confirm([w for w in self.shown.values() if sure(w)])

    def _ignore_selected(self) -> None:
        self._ignore(self._selected())

    def _ignore(self, sel: List[Any]) -> None:
        for w in sel:
            key = ignore_key(w.track)
            if key not in self.ctrl.settings.diag_ignored:
                self.ctrl.settings.diag_ignored.append(key)
        self.ctrl.save_settings_quiet()
        self._fill()

    def _menu(self, iids: List[str]) -> list:
        sel = [self.shown[i] for i in iids if i in self.shown]
        if not sel:
            return []
        entries: list = []
        if len(sel) == 1:
            entries.append((t("quality.search_one"), lambda: self.open_detail(str(sel[0].track.content_id)), "search"))
        entries.append((t("improve.search"), lambda: self._enqueue([str(w.track.content_id) for w in sel]), "search"))
        if any(w.best is not None for w in sel):
            entries.append((t("improve.apply"), lambda: self.confirm(sel), "download"))
        if len(sel) == 1:
            from .views.common import buy_entry

            entries += [None, buy_entry(self.ctrl, sel[0].track.artist or "", sel[0].track.title)]
        entries.append((t("diag.ignore"), lambda: self._ignore(sel), "close"))
        if len(sel) == 1:                                   # 1.4.2 (C182) : le même menu d'un son partout
            from .track_menu import track_entries

            common = [e for e in track_entries(self, self.ctrl, [sel[0].track], where="quality")
                      if e is None or e[0] != t("buy.menu")]          # Acheter : déjà plus haut
            entries += [None] + common
        return entries


class QualityDetail(BaseDialog):
    """Détail d'un son : la liste de résultats de la page Haute qualité (mêmes colonnes et pastilles), avec
    l'écart de durée et le gain ; artiste + titre modifiables ; Écouter, « Remplacer par celle-ci », Acheter."""

    def __init__(self, page: QualityPage, row: Any) -> None:
        super().__init__(page, t("quality.detail_title"), 980, 520)
        from ..core.quality import search_terms
        from .views.hq_view import hq_columns

        self.page, self.ctrl, self.row = page, page.ctrl, row
        title, artist = search_terms(row.track)
        from ..core.improve import label_of

        self.heading(t("quality.detail_title"), t("quality.detail_sub", title=row.track.title, now=label_of(row.info)))
        bar = hbox()
        self.artist_edit = line_edit(t("track.artist"))
        self.artist_edit.setText(artist or "")
        self.title_edit = line_edit(t("track.title"))
        self.title_edit.setText(title or "")
        self.title_edit.returnPressed.connect(self.search)
        self.artist_edit.returnPressed.connect(self.search)
        bar.addWidget(self.artist_edit, 1)
        bar.addWidget(self.title_edit, 2)
        self.go_btn = button(t("quality.search_go"), self.search, kind="primary", icon="search")
        bar.addWidget(self.go_btn)
        self.body.addLayout(bar)
        self.state = label("", "dim")
        self.body.addWidget(self.state)

        cols = [c for c in hq_columns() if c.key not in ("dl", "lib")]
        cols.insert(4, Column("gap", t("quality.col_gap"), 70, "e",
                              sort=lambda r: abs(r.values.get("_gap", 0) or 0) if r.data is not None else None))
        cols.insert(5, Column("gain", t("improve.gain"), 140))
        self.table = TrackTable(self, cols)
        self.table.set_empty("search", t("quality.detail_empty"))
        self.table.on_select = lambda _ids: self._refresh()
        self.table.on_double = lambda _iid: self.listen()
        self.body.addWidget(self.table, 1)

        foot = hbox()
        self.listen_btn = button(t("quality.listen"), self.listen, icon="play")
        foot.addWidget(self.listen_btn)
        from .views.common import buy_entry

        self._buy = buy_entry(self.ctrl, row.track.artist or "", row.track.title)     # Acheter (magasins)
        self.buy_btn = button(self._buy[0], self._buy_menu, kind="flat", icon=self._buy[2])
        foot.addWidget(self.buy_btn)
        foot.addStretch(1)
        self.replace_btn = button(t("quality.replace_this"), self.replace, kind="primary", icon="download")
        foot.addWidget(self.replace_btn)
        foot.addWidget(button(t("action.close"), self.close))
        self.body.addLayout(foot)
        self.show_dialog()
        if row.searched:
            self._fill()
        else:
            self.search()

    def _buy_menu(self) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        for name, go in self._buy[1]:
            menu.addAction(name, go)
        menu.popup(self.buy_btn.mapToGlobal(self.buy_btn.rect().bottomLeft()))

    def _query(self) -> str:
        return f"{self.artist_edit.text().strip()} {self.title_edit.text().strip()}".strip()

    def search(self) -> None:
        self.state.setText(t("improve.searching"))
        self.go_btn.setEnabled(False)
        self.table.show_skeleton()

        def done(row: Any) -> None:
            if not self.winfo_exists():
                return
            self.go_btn.setEnabled(True)
            self._fill()
            self.page.row_changed(row)

        self.ctrl.quality_search(self.row, done, query=self._query())

    def _fill(self) -> None:
        from ..core.improve import candidate_label, duration_gap, label_of, order_key
        from .views.hq_view import hq_row

        better = {id(f) for f in self.row.finds}
        found = sorted((f for f in self.row.results if not getattr(f, "is_album", False)),
                       key=lambda f: (id(f) not in better,) + order_key(self.row, f))
        rows = []
        for i, f in enumerate(found):
            r = hq_row(f)
            r.iid = f"r{i}"
            gap = duration_gap(self.row, f)
            r.values["gap"] = "" if gap is None else f"{gap:+d} s"
            r.values["_gap"] = gap or 0
            if id(f) in better:
                r.values["gain"] = f"{label_of(self.row.info)} → {candidate_label(f)}"
                r.values["gain__color"] = theme.GOOD
            rows.append(r)
        self.table.set_rows(rows)
        n_better = sum(1 for f in found if id(f) in better)
        self.state.setText(t("quality.detail_count", n=len(found), better=n_better))
        self._refresh()

    def _current(self) -> Optional[Any]:
        sel = self.table.selected_iids()
        for r in self.table.all_rows():
            if sel and r.iid == sel[0]:
                return r.data
        return None

    def _refresh(self) -> None:
        cur = self._current()
        self.listen_btn.setEnabled(cur is not None)
        self.replace_btn.setEnabled(cur is not None)

    def listen(self) -> None:
        cur = self._current()
        if cur is None:
            return
        if getattr(cur, "slsk", None) is not None:          # C167 : pas d'écoute avant téléchargement
            self.ctrl.play_equivalent(cur)
        else:
            self.ctrl.preview(cur)

    def replace(self) -> None:
        cur = self._current()
        if cur is None:
            return
        self.row.chosen = cur
        self.page.row_changed(self.row)
        self.page.confirm([self.row])
