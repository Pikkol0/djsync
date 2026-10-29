"""Panneau « Suggestions » de la Bibliothèque (1.3.1, C30) : sons pour enchaîner.

Référence : le son en lecture, ou le son sélectionné (le dernier des deux qui a changé). 10 à 20 sons
classés par score (`core.suggest`) : pastille Camelot, BPM avec écart coloré (échelle C29), raison en
clair. Double-clic : écouter ; « + » : ajouter à la playlist ouverte ; glisser vers une playlist de
l'arbre. Portée : toute la bibliothèque ou la playlist ouverte. Le but, à terme : aider à construire
la playlist d'une soirée (l'auteur).
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QComboBox, QListWidget, QListWidgetItem, QSizePolicy, QSpinBox, QWidget

from ..core.suggest import DEFAULT_TOLERANCE, Suggestion, suggestions
from ..i18n import t
from . import levels, theme
from .table import MIME_IDS
from .widgets import CamelotPill, hbox, icon_button, label, panel, vbox

LIMIT = 20
REFRESH_DELAY_MS = 60


class _List(QListWidget):
    """Liste des suggestions ; glisser un son vers une playlist de l'arbre l'y ajoute."""

    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setResizeMode(QListWidget.Adjust)

    def startDrag(self, _actions: Any) -> None:     # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(MIME_IDS, QByteArray(str(item.data(Qt.UserRole)).encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class SuggestionsPanel(QWidget):
    def __init__(self, view: Any, controller: Any) -> None:
        super().__init__()
        self.view, self.ctrl = view, controller
        self.ref: Optional[Any] = None
        self.items: List[Suggestion] = []
        box = panel(role="sidebar")
        outer = vbox(self, margins=0, spacing=0)
        outer.addWidget(box)
        lay = vbox(box, margins=theme.px(10), spacing=theme.px(6))
        head = hbox(spacing=theme.px(6))
        head.addWidget(label(t("sug.title").upper(), "section"))
        head.addStretch(1)
        head.addWidget(icon_button("close", lambda: view.show_suggestions(False), t("action.close"), size=14))
        lay.addLayout(head)
        self.ref_lbl = label(t("sug.pick"), "dim", wrap=True)
        lay.addWidget(self.ref_lbl)
        opts = hbox(spacing=theme.px(6))
        self.scope = QComboBox()
        self.scope.addItems([t("sug.scope_all"), t("sug.scope_playlist")])
        self.scope.setToolTip(t("sug.scope_tip"))
        self.scope.currentIndexChanged.connect(lambda _i: self.refresh())
        opts.addWidget(self.scope, 1)
        self.scope.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.tol = QSpinBox()
        self.tol.setRange(1, 20)
        self.tol.setPrefix("BPM ±")
        self.tol.setSuffix(" %")
        self.tol.setValue(int(getattr(controller.settings, "suggest_tolerance", DEFAULT_TOLERANCE) or DEFAULT_TOLERANCE))
        self.tol.setToolTip(t("sug.tolerance_tip"))
        self.tol.setFixedWidth(self.tol.fontMetrics().horizontalAdvance("BPM ±20 %") + theme.px(44))
        self.tol.valueChanged.connect(self._tol_changed)
        opts.addWidget(self.tol)
        lay.addLayout(opts)
        self.list = _List()
        self.list.itemDoubleClicked.connect(lambda it: self._play(it))
        lay.addWidget(self.list, 1)
        self.empty = label("", "faint", wrap=True)
        lay.addWidget(self.empty)
        lay.addWidget(label(t("sug.hint"), "faint", wrap=True))
        self.setMinimumWidth(theme.px(300))
        self.setMaximumWidth(theme.px(400))
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.setInterval(REFRESH_DELAY_MS)
        self._pending.timeout.connect(self.refresh)

    # ------------------------------------------------------------------ données
    def set_reference(self, track: Optional[Any]) -> None:
        if track is None or (self.ref is not None and track.content_id == self.ref.content_id
                             and track.bpm == self.ref.bpm):
            return
        self.ref = track
        self._pending.start()          # 1.3.1-rc.2 (B38) : une seule mise à jour après des sélections rapides

    def _tol_changed(self, value: int) -> None:
        self.ctrl.settings.suggest_tolerance = int(value)
        self.refresh()

    def _pool(self) -> List[Any]:
        if self.scope.currentIndex() == 1 and self.view.in_playlist:
            return [r.data for r in self.view.table.all_rows() if r.data is not None]
        return list(self.view.all_tracks)

    def refresh(self) -> None:
        if not self.isVisible() and not self.ref:
            return
        self._pending.stop()
        self.list.clear()
        ref = self.ref
        if ref is None:
            self.ref_lbl.setText(t("sug.pick"))
            self.items = []
            self.empty.setText("")
            return
        code = ref.camelot or "?"
        bpm = f"{ref.bpm:.0f}" if ref.bpm else "?"
        self.ref_lbl.setText(t("sug.after", title=ref.title, code=code, bpm=bpm))
        if not ref.bpm:
            self.items = []
            self.empty.setText(t("sug.no_bpm"))
            return
        self.items = suggestions(ref, self._pool(), LIMIT, float(self.tol.value()))
        self.empty.setText("" if self.items else t("sug.none"))
        for s in self.items:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, s.track.content_id)
            w = self._row(s)
            item.setSizeHint(QSize(0, w.sizeHint().height() + theme.px(4)))
            self.list.addItem(item)
            self.list.setItemWidget(item, w)

    def _row(self, s: Suggestion) -> QWidget:
        x = s.track
        w = QWidget()
        row = hbox(w, margins=theme.px(4), spacing=theme.px(6))
        pill = CamelotPill(x.camelot, w)
        pill.setFixedSize(theme.px(34), pill.fontMetrics().height() + theme.px(4))
        row.addWidget(pill, 0, Qt.AlignVCenter)
        # 1.3.1-rc.2 (B38) : les textes dans un widget qui a un parent dès le départ. Une mise en page
        # imbriquée sans parent (vbox() puis addLayout) était détruite après ses textes quand la liste se
        # vidait : plantage natif de Qt (QWidgetItemV2::~QWidgetItemV2), surtout sur Mac.
        box = QWidget(w)
        texts = vbox(box, spacing=0)
        name = label(x.title, "")
        name.setToolTip(f"{x.title} — {x.artist or '—'}")
        texts.addWidget(name)
        who = label(x.artist or "—", "dim")
        level = levels.bpm_gap(s.bpm_gap or 0)
        gap = f"{s.bpm_gap:+.1f} %" if s.bpm_gap else "="
        half = {0.5: " (×½)", 2.0: " (×2)"}.get(s.ratio, "")
        detail = label("", "dim")
        detail.setTextFormat(Qt.RichText)
        detail.setText(f"{x.bpm:.0f} BPM {levels.html(gap + half, level)} · {t('sug.key_' + s.key_reason)}")
        for lbl in (name, who, detail):
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)     # coupés, jamais de défilement
            texts.addWidget(lbl)
        row.addWidget(box, 1)
        if self.view.in_playlist and self.view.playlist is not None and self.view.playlist.is_editable:
            if self.view.table.row(str(x.content_id)) is not None:
                done = label("✓", "accent")
                done.setToolTip(t("sug.in_playlist"))
                row.addWidget(done)
            else:
                row.addWidget(icon_button("plus", lambda _c=False, cid=x.content_id: self._add(cid), t("sug.add"),
                                          size=14))
        return w

    # ------------------------------------------------------------------ actions
    def _play(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.UserRole)
        tracks = [s.track for s in self.items]
        idx = next((i for i, x in enumerate(tracks) if x.content_id == cid), None)
        if idx is not None:
            self.ctrl.play_queue(tracks, idx)

    def _add(self, cid: int) -> None:
        p = self.view.playlist
        if p is None or not p.is_editable:
            return
        self.ctrl.add_to_playlists([cid], [p.playlist_id])     # ajouté à la fin de la playlist ouverte
