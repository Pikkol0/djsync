"""Page « Uniformiser » (1.2.2, C14 ; refaite en 1.3.0, C25).

Sur le modèle du Diagnostic : chaque son sur deux lignes alignées, « Actuellement » (tel qu'il est dans
la bibliothèque) puis « Après » (tel qu'il sera). Les sons sont affichés les uns à la suite des autres,
sûrs d'abord ; chacun est validé d'un clic ou d'Entrée et le suivant prend sa place.

  * un clic dans un champ de la ligne « Après » le modifie sur place ; la couleur d'écriture dit ce qui
    change (accent) et ce qui est incertain (orange) ; « ↺ » dans le champ remet la valeur actuelle ;
  * pochette : survol = croix pour la supprimer ; sans pochette, l'icône d'envoi ouvre le sélecteur de
    fichiers (glisser-déposer une image marche aussi) ;
  * « Chercher autrement » : texte libre, Entrée relance la recherche pour ce son, les autres résultats
    s'affichent dessous (un clic pour en choisir un) ;
  * clavier : Entrée valider, I ignorer, F chercher, Espace écouter, ↑ / ↓ son précédent / suivant,
    Ctrl+Z annuler la dernière validation.
Rien n'est écrit avant « Enregistrer » ; la progression est gardée entre deux sessions.
"""
from __future__ import annotations

import base64
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIntValidator, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QToolButton, QWidget)

from ..core.uniformize import Proposal
from ..db.base import KEEP
from ..i18n import plural, t
from ..models import LibraryTrack
from . import theme
from .icons import qicon
from .widgets import button, chip, hbox, label, restyle, vbox

STATES = ("todo", "validated", "ignored", "applied", "clean", "scanning")
FIELDS = ("title", "artist", "album", "year", "genre")
FIELD_KEYS = {"title": "track.title", "artist": "track.artist", "album": "track.album", "year": "info.year",
              "genre": "info.genre", "artwork": "info.artwork"}
PAGE = 30                       # blocs affichés à la fois (« Afficher les suivants »)
COVER = 56
ORDER = {"sure": 0, "rules": 1, "doubtful": 2}


def _encode(values: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(values)
    if isinstance(out.get("artwork"), bytes):
        out["artwork"] = "b64:" + base64.b64encode(out["artwork"]).decode("ascii")
    return out


def _decode(values: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(values)
    art = out.get("artwork")
    if isinstance(art, str) and art.startswith("b64:"):
        out["artwork"] = base64.b64decode(art[4:])
    return out


def _pix(data: bytes, size: int) -> Optional[QPixmap]:
    pix = QPixmap()
    if data and pix.loadFromData(data):
        return pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return None


# ============================================================================ pochette
class CoverBox(QLabel):
    """Pochette de la ligne « Après » : survol = croix pour supprimer ; vide = icône d'envoi (clic =
    choisir un fichier) ; accepte le glisser-déposer d'une image."""

    def __init__(self, on_file: Callable[[bytes], None], on_remove: Callable[[], None], editable: bool = True) -> None:
        super().__init__()
        self._on_file, self._on_remove = on_file, on_remove
        self._has_image = False
        self.editable = editable
        size = theme.px(COVER)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"border: 1px solid {theme.BORDER}; border-radius: {theme.px(6)}px;")
        self.setAcceptDrops(editable)
        self.remove_btn = QToolButton(self)
        self.remove_btn.setIcon(qicon("close", 12, theme.TEXT))
        self.remove_btn.setToolTip(t("uni.cover_remove"))
        self.remove_btn.setStyleSheet(f"QToolButton {{ background: rgba(0,0,0,0.65); border: 0; border-radius: "
                                      f"{theme.px(9)}px; }}")
        self.remove_btn.setFixedSize(theme.px(18), theme.px(18))
        self.remove_btn.move(size - theme.px(20), theme.px(2))
        self.remove_btn.clicked.connect(lambda: self._on_remove())
        self.remove_btn.hide()

    def show_image(self, data: Optional[bytes]) -> None:
        pix = _pix(data or b"", theme.px(COVER))
        self._has_image = pix is not None
        if pix is not None:
            self.setPixmap(pix)
            self.setToolTip(t("uni.cover_hover"))
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setPixmap(qicon("up", 22, theme.FAINT).pixmap(QSize(theme.px(22), theme.px(22))))
            self.setToolTip(t("uni.cover_upload") if self.editable else "")
            self.setCursor(Qt.PointingHandCursor if self.editable else Qt.ArrowCursor)

    def enterEvent(self, e: Any) -> None:            # noqa: N802
        self.remove_btn.setVisible(self._has_image and self.editable)
        super().enterEvent(e)

    def leaveEvent(self, e: Any) -> None:            # noqa: N802
        self.remove_btn.hide()
        super().leaveEvent(e)

    def mousePressEvent(self, e: Any) -> None:       # noqa: N802
        if self.editable and not self._has_image and e.button() == Qt.LeftButton:
            self.pick_file()
        super().mousePressEvent(e)

    def pick_file(self) -> None:
        path, _f = QFileDialog.getOpenFileName(self, t("info.cover_file"), "", t("fb.image_filter"))
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return
        if _pix(data, 8) is not None:
            self._on_file(data)

    def dragEnterEvent(self, e: Any) -> None:        # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: Any) -> None:             # noqa: N802
        urls = e.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self._load(urls[0].toLocalFile())


# ============================================================================ un son
class CandidateCard(QFrame):
    """1.3.0-rc.3 (B19) : résultat de « Chercher autrement » sur deux lignes, hauteur d'après la police
    (rien n'est coupé à 125-150 %), texte trop long terminé par « … » et complet au survol."""

    def __init__(self, title: str, sub: str, on_pick: Any) -> None:
        super().__init__()
        self._on_pick = on_pick
        self.setObjectName("candCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{title}\n{sub}\n\n{t('uni.pick_tip')}")
        self.setStyleSheet(f"#candCard {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; "
                           f"border-radius: {theme.px(6)}px; }} #candCard:hover {{ border-color: {theme.ACCENT}; }}")
        lay = vbox(self, margins=theme.px(8), spacing=theme.px(2))
        self._texts = [(label("", ""), title), (label("", "faint"), sub)]
        for lbl, _txt in self._texts:
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            lay.addWidget(lbl)
        fm = self.fontMetrics()
        self.setMinimumHeight(2 * fm.lineSpacing() + 2 * theme.px(8) + theme.px(4))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._elide()

    def _elide(self) -> None:
        for lbl, txt in self._texts:
            w = max(20, lbl.width() if lbl.width() > 20 else self.width() - 2 * theme.px(8))
            lbl.setText(lbl.fontMetrics().elidedText(txt, Qt.ElideRight, w))

    def resizeEvent(self, e: Any) -> None:          # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def mousePressEvent(self, e: Any) -> None:       # noqa: N802
        if e.button() == Qt.LeftButton:
            self._on_pick()


class TrackBlock(QFrame):
    """Un son : en-tête (confiance, boutons), ligne « Actuellement », ligne « Après », Chercher autrement."""

    def __init__(self, page: "UniformizePage", cid: int) -> None:
        super().__init__()
        self.page, self.cid = page, cid
        self.track: LibraryTrack = page.tracks[cid]
        self.details: Dict[str, Any] = page.details.get(cid, {})
        self.prop: Optional[Proposal] = page.props.get(cid)
        self.current: Dict[str, Any] = {
            "title": self.track.title or "", "artist": self.track.artist or "",
            "album": self.details.get("album", self.track.album or "") or "",
            "year": int(self.details.get("year") or 0), "genre": self.details.get("genre") or ""}
        self.uncertain: set = set()
        self.artwork: Any = KEEP                    # KEEP | None | octets | URL Deezer
        self.edits: Dict[str, QLineEdit] = {}
        self.setObjectName("uniBlock")
        self.setFocusPolicy(Qt.ClickFocus)
        lay = vbox(self, margins=theme.px(10), spacing=theme.px(6))

        head = hbox(spacing=theme.px(8))
        st = page.state(cid)
        conf = self.prop.confidence if self.prop is not None else ""
        if st == "scanning":
            head.addWidget(chip(t("uni.st_scanning")))
        elif conf:
            role = {"sure": "chip_ok", "rules": "chip", "doubtful": "chip_warn"}[conf]
            head.addWidget(chip({"sure": t("uni.conf_sure", score=self.prop.score), "rules": t("uni.conf_rules"),
                                 "doubtful": t("uni.conf_doubtful")}[conf], role))
        if st in ("validated", "ignored", "applied", "clean"):
            head.addWidget(chip(t(f"uni.st_{st}"), "chip_ok" if st in ("validated", "applied") else "chip"))
        note = self._note()
        self.note = label(note, "faint")
        self.note.setToolTip(note)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.note, 1)
        play = QToolButton()
        play.setIcon(qicon("play", 14, theme.DIM))
        play.setToolTip(t("uni.listen"))
        play.clicked.connect(lambda: page.listen(cid))
        head.addWidget(play)
        if st in ("validated", "ignored"):
            head.addWidget(button(t("uni.reset"), lambda: page.reset(cid), kind="flat", icon="refresh"))
        else:
            head.addWidget(button(t("uni.ignore"), lambda: page.ignore(cid), kind="flat", icon="close",
                                  tooltip=t("uni.ignore_tip")))
            self.validate_btn = button(t("uni.validate"), lambda: page.validate(cid), kind="primary", icon="check",
                                       tooltip=t("uni.validate_tip"))
            head.addWidget(self.validate_btn)
        lay.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.px(8))
        grid.setVerticalSpacing(theme.px(4))
        grid.addWidget(label(t("uni.now"), "faint"), 0, 0)
        grid.addWidget(label(t("uni.after"), "dim"), 1, 0)
        self.cover_now = QLabel()
        self.cover_now.setFixedSize(theme.px(COVER), theme.px(COVER))
        self.cover_now.setAlignment(Qt.AlignCenter)
        self.cover_now.setStyleSheet(f"border: 1px solid {theme.BORDER}; border-radius: {theme.px(6)}px;")
        grid.addWidget(self.cover_now, 0, 1)
        editable = st not in ("applied",)
        self.cover_new = CoverBox(self._cover_file, self._cover_remove, editable)
        grid.addWidget(self.cover_new, 1, 1)
        stretch = {"title": 3, "artist": 3, "album": 2, "year": 0, "genre": 2}      # B19 : genre plus large
        for col, f in enumerate(FIELDS, start=2):
            now = label(str(self.current[f] or "—") if f != "year" else (str(self.current[f]) if self.current[f] else "—"),
                        "faint")
            now.setToolTip(f"{t(FIELD_KEYS[f])} : {now.text()}")
            now.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            grid.addWidget(now, 0, col)
            e = QLineEdit()
            e.setPlaceholderText(t(FIELD_KEYS[f]))
            e.setToolTip(t(FIELD_KEYS[f]))
            if f == "year":
                e.setValidator(QIntValidator(0, 2100, e))
                e.setFixedWidth(theme.px(84))
            else:
                e.setMinimumWidth(theme.px(110) if f == "genre" else theme.px(60))
            e.setReadOnly(not editable)
            e.textChanged.connect(lambda txt, w=e, k=f: w.setToolTip(f"{t(FIELD_KEYS[k])} : {txt}" if txt else t(FIELD_KEYS[k])))
            revert = e.addAction(qicon("back", 14, theme.DIM), QLineEdit.TrailingPosition)
            revert.setToolTip(t("uni.revert"))
            revert.triggered.connect(lambda _=False, k=f: self._revert(k))
            e.textEdited.connect(lambda _txt, k=f: self._edited(k))
            e.returnPressed.connect(self.page.focus_page)
            self.edits[f] = e
            e._revert_action = revert                                         # type: ignore[attr-defined]
            grid.addWidget(e, 1, col)
            grid.setColumnStretch(col, stretch[f])
        lay.addLayout(grid)

        search = hbox(spacing=theme.px(6))
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("uni.search_hint"))
        self.search.setToolTip(t("uni.search_tip"))
        self.search.returnPressed.connect(lambda: page.search(cid, self.search.text()))
        search.addWidget(label(t("uni.search_other"), "faint"))
        search.addWidget(self.search, 1)
        search.addWidget(button(t("action.search"), lambda: page.search(cid, self.search.text()), kind="flat",
                                icon="search"))
        lay.addLayout(search)
        self.cands = QWidget()
        self.cands_lay = QGridLayout(self.cands)          # B19 : cartes sur 3 colonnes, retour à la ligne
        self.cands_lay.setContentsMargins(0, 0, 0, 0)
        self.cands_lay.setSpacing(theme.px(6))
        self.cands.hide()
        lay.addWidget(self.cands)

        self._fill_values()
        self._load_covers()
        if self.prop is not None and self.prop.deezer.get("candidates") and conf != "sure":
            self.show_candidates(self.prop.deezer["candidates"])
        self.set_current(False)

    # ------------------------------------------------------------------ valeurs
    def _note(self) -> str:
        p = self.prop
        if p is None:
            return ""
        if p.deezer:
            return t("uni.deezer_sure" if p.confidence == "sure" else "uni.deezer_unsure", score=p.score,
                     title=p.deezer.get("title", ""), artists=", ".join(p.deezer.get("artists") or []))
        return t("uni.deezer_none")

    def _fill_values(self) -> None:
        after = dict(self.current)
        st = self.page.state(self.cid)
        self.uncertain = set()
        if st == "validated":
            vals = _decode(self.page.store.values(self.track))
            for k, v in vals.items():
                if k in after:
                    after[k] = v
            self.artwork = vals.get("artwork", KEEP)
        elif self.prop is not None:
            for ch in self.prop.changes:
                if ch.field == "artwork":
                    self.artwork = ch.new
                    if not ch.checked:
                        self.uncertain.add("artwork")
                elif ch.field in after:
                    after[ch.field] = ch.new
                    if not ch.checked:
                        self.uncertain.add(ch.field)
        for f, e in self.edits.items():
            v = after[f]
            e.setText(str(v) if f != "year" else (str(v) if v else ""))
            e.setCursorPosition(0)
            self._paint(f)
        if not self.search.text():
            t_, a_ = after["title"], after["artist"]
            self.search.setText(f"{a_.split(',')[0].strip()} {t_}".strip())

    def value(self, f: str) -> Any:
        txt = self.edits[f].text().strip()
        if f == "year":
            return int(txt) if txt.isdigit() else 0
        return txt

    def _paint(self, f: str) -> None:
        e = self.edits[f]
        changed = self.value(f) != self.current[f]
        color = theme.WARN if (changed and f in self.uncertain) else (theme.ACCENT if changed else theme.DIM)
        e.setStyleSheet(f"QLineEdit {{ color: {color}; }}")
        e._revert_action.setVisible(changed)                                   # type: ignore[attr-defined]

    def _edited(self, f: str) -> None:
        self.uncertain.discard(f)
        self._paint(f)
        self.page._touched = True
        self.page.make_current(self.cid)

    def _revert(self, f: str) -> None:
        v = self.current[f]
        self.edits[f].setText(str(v) if f != "year" else (str(v) if v else ""))
        self.edits[f].setCursorPosition(0)
        self.uncertain.discard(f)
        self._paint(f)

    def values(self) -> Dict[str, Any]:
        """Ce qui change par rapport à la bibliothèque (ce qui sera enregistré)."""
        out: Dict[str, Any] = {}
        for f in FIELDS:
            v = self.value(f)
            if f == "title" and not v:
                continue
            if v != self.current[f]:
                out[f] = v
        if self.artwork is not KEEP:
            out["artwork"] = self.artwork
        return out

    def apply_proposal(self, prop: Proposal) -> None:
        """Résultat choisi (Chercher autrement) : la ligne « Après » est remplie avec."""
        self.prop = prop
        self.page.props[self.cid] = prop
        self.note.setText(self._note())
        self.artwork = KEEP
        self._fill_values()
        self._load_covers()

    # ------------------------------------------------------------------ pochettes
    def _load_covers(self) -> None:
        data = b""
        try:
            lib = self.page.ctrl.library
            path = lib.artwork_file(self.track) if lib is not None else None
            if path is not None and path.is_file():
                data = path.read_bytes()
        except Exception:  # noqa: BLE001
            data = b""
        self._now_bytes = data
        pix = _pix(data, theme.px(COVER))
        if pix is not None:
            self.cover_now.setPixmap(pix)
        else:
            self.cover_now.setText("—")
        self._show_new_cover()

    def _show_new_cover(self) -> None:
        art = self.artwork
        if art is KEEP:
            self.cover_new.show_image(self._now_bytes)
        elif art is None:
            self.cover_new.show_image(None)
        elif isinstance(art, bytes):
            self.cover_new.show_image(art)
        else:
            self.cover_new.show_image(None)
            self.page.ctrl.fetch_image(str(art).replace("1000x1000", "250x250"),
                                       lambda data, w=self.cover_new: w.show_image(data) if self.page.alive(w) else None)
        changed = art is not KEEP
        border = theme.WARN if (changed and "artwork" in self.uncertain) else (theme.ACCENT if changed else theme.BORDER)
        self.cover_new.setStyleSheet(f"border: {2 if changed else 1}px solid {border}; border-radius: {theme.px(6)}px;")

    def _cover_file(self, data: bytes) -> None:
        self.artwork = data
        self.uncertain.discard("artwork")
        self._show_new_cover()

    def _cover_remove(self) -> None:
        # sans pochette actuelle, retirer celle proposée revient à ne rien changer
        self.artwork = None if self._now_bytes else KEEP
        self.uncertain.discard("artwork")
        self._show_new_cover()

    # ------------------------------------------------------------------ candidats
    def show_candidates(self, cands: List[Dict[str, Any]]) -> None:
        while self.cands_lay.count():
            item = self.cands_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not cands:
            self.cands_lay.addWidget(label(t("uni.search_none"), "faint"), 0, 0)
        cols = 3
        for i, c in enumerate(cands[:5], start=1):
            d = int(c.get("duration") or 0)
            gap = d - int(self.track.duration_seconds or 0) if d else None
            txt = f"{i}. {', '.join(a for a in c.get('artists') or [] if a)} – {c.get('title', '')}"
            sub = " · ".join(x for x in (c.get("album") or "", f"{d // 60}:{d % 60:02d}" if d else "",
                                         (f"{gap:+d} s" if gap else "=") if gap is not None else "") if x)
            card = CandidateCard(txt, sub, lambda cand=c: self.page.pick(self.cid, cand))
            self.cands_lay.addWidget(card, (i - 1) // cols, (i - 1) % cols)
        for col in range(cols):
            self.cands_lay.setColumnStretch(col, 1)
        self.cands.show()
        self.cands.updateGeometry()
        self.updateGeometry()

    # ------------------------------------------------------------------ état
    def set_current(self, on: bool) -> None:
        border = theme.ACCENT if on else theme.BORDER
        self.setStyleSheet(f"#uniBlock {{ background: {theme.ELEV}; border: {2 if on else 1}px solid {border}; "
                           f"border-radius: {theme.px(10)}px; }}")

    def mousePressEvent(self, e: Any) -> None:       # noqa: N802
        self.page._touched = True
        self.page.make_current(self.cid)
        super().mousePressEvent(e)


# ============================================================================ la page
class UniformizePage(QWidget):
    def __init__(self, parent: Any, controller: Any, tracks: List[LibraryTrack], scope: str,
                 on_close: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.ctrl, self.scope = controller, scope
        self._on_close = on_close
        self._closed = False
        self._cancel = False
        self.tracks: Dict[int, LibraryTrack] = {x.content_id: x for x in tracks}
        self.order: List[int] = [x.content_id for x in tracks]
        self.props: Dict[int, Proposal] = {}
        self.details: Dict[int, Dict[str, Any]] = {}
        self.store = controller.review_store()
        self.blocks: Dict[int, TrackBlock] = {}
        self._shown: List[int] = []
        self._limit = PAGE
        self._scanned = 0
        self._to_scan = 0
        self._current: Optional[int] = None
        self._history: List[int] = []                # validations / ignorés, pour Ctrl+Z
        self.scan_finished = False
        self._touched = False                        # l'utilisateur a choisi un son : on ne le déplace plus
        self._refill = QTimer(self)
        self._refill.setSingleShot(True)
        self._refill.setInterval(250)
        self._refill.timeout.connect(self._fill)
        # 1.3.0-rc.3 (B18) : sons analysés ajoutés par paquets (au plus 4 fois par seconde), sans tout redessiner
        self._pending: List[int] = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(250)
        self._flush_timer.timeout.connect(self._flush_pending)
        self.setFocusPolicy(Qt.StrongFocus)

        body = vbox(self, margins=theme.px(18), spacing=theme.px(8))
        head = hbox()
        head.addWidget(button(t("grid.back"), self.close, kind="flat", icon="back"))
        titles = vbox(spacing=0)
        titles.addWidget(label(t("uni.title", scope=scope), "title"))
        info_row = hbox(spacing=theme.px(8))
        self.scan_bar = QProgressBar()                     # B18 : avancement à gauche, à place fixe
        self.scan_bar.setTextVisible(False)
        self.scan_bar.setFixedWidth(theme.px(140))
        self.scan_bar.hide()
        info_row.addWidget(self.scan_bar, 0, Qt.AlignVCenter)
        self.info = label("", "dim")
        info_row.addWidget(self.info)
        info_row.addStretch(1)
        titles.addLayout(info_row)
        head.addLayout(titles, 1)
        head.addWidget(label(t("uni.show"), "dim"))
        self._filters = {"todo": t("uni.f_todo"), "validated": t("uni.f_validated"), "ignored": t("uni.f_ignored"),
                         "done": t("uni.f_done"), "all": t("uni.f_all")}
        self.filter = QComboBox()
        self.filter.addItems(list(self._filters.values()))
        self.filter.currentTextChanged.connect(lambda _t: self._fill(reset_limit=True))
        head.addWidget(self.filter)
        self.save_btn = button("", self._save, kind="primary", icon="check")
        head.addWidget(self.save_btn)
        body.addLayout(head)
        body.addWidget(label(t("uni.intro2"), "faint", wrap=True))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.list_lay = vbox(holder, spacing=theme.px(8))
        self.list_lay.addStretch(1)
        self.scroll.setWidget(holder)
        body.addWidget(self.scroll, 1)

        for seq, fn in (("Ctrl+Z", self.undo), ("Up", lambda: self._move(-1)), ("Down", lambda: self._move(1))):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self._fill(reset_limit=True)
        self._start_scan()

    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return not self._closed and isValid(self)

    @staticmethod
    def alive(w: Any) -> bool:
        from .views.common import alive

        return alive(w)

    # ------------------------------------------------------------------ états
    def state(self, cid: int) -> str:
        track = self.tracks[cid]
        st = self.store.state(track)
        if st:
            return st
        prop = self.props.get(cid)
        if prop is None:
            return "scanning"
        return "clean" if prop.empty else "todo"

    def _visible(self, cid: int) -> bool:
        f = next((k for k, v in self._filters.items() if v == self.filter.currentText()), "todo")
        st = self.state(cid)
        return {"todo": st == "todo", "validated": st == "validated", "ignored": st == "ignored",
                "done": st in ("applied", "clean"), "all": True}[f]

    def _sort_key(self, cid: int) -> Any:
        p = self.props.get(cid)
        return (ORDER.get(p.confidence, 3) if p is not None else 4, self.order.index(cid))

    def _fill(self, reset_limit: bool = False) -> None:
        if not self.winfo_exists():
            return
        if reset_limit:
            self._limit = PAGE
        wanted = sorted((cid for cid in self.tracks if self._visible(cid)), key=self._sort_key)
        shown = wanted[:self._limit]
        bar = self.scroll.verticalScrollBar().value()
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.blocks = {}
        if not shown:
            msg = t("uni.scan_wait") if self._scanned < self._to_scan and not self._cancel else t("uni.empty")
            self.list_lay.addWidget(label(msg, "faint", wrap=True))
        for cid in shown:
            blk = TrackBlock(self, cid)
            self.blocks[cid] = blk
            self.list_lay.addWidget(blk)
        if len(wanted) > len(shown):
            more = button(t("uni.more", n=len(wanted) - len(shown)), self._more, kind="flat")
            self.list_lay.addWidget(more)
        self.list_lay.addStretch(1)
        self._shown = shown
        if self._current not in self.blocks:
            self._current = shown[0] if shown else None
        if self._current is not None:
            self.blocks[self._current].set_current(True)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(bar) if self.winfo_exists() else None)
        self._refresh_info()

    def _more(self) -> None:
        self._limit += PAGE
        self._fill()

    def _refresh_info(self) -> None:
        counts = {s: 0 for s in STATES}
        for cid in self.tracks:
            counts[self.state(cid)] += 1
        parts = [t("uni.count_todo", n=counts["todo"]), t("uni.count_validated", n=counts["validated"]),
                 t("uni.count_done", n=counts["applied"] + counts["clean"])]
        scanning = self._scanned < self._to_scan and not self._cancel
        if scanning:
            parts.insert(0, t("uni.scanning", i=self._scanned, n=self._to_scan))
        if hasattr(self, "scan_bar"):
            self.scan_bar.setVisible(scanning)
            self.scan_bar.setRange(0, max(1, self._to_scan))
            self.scan_bar.setValue(self._scanned)
        self.info.setText("  ·  ".join(parts))
        n = counts["validated"]
        self.save_btn.setText(t("uni.save_n", n=n))
        self.save_btn.setEnabled(n > 0)

    # ------------------------------------------------------------------ analyse
    def _start_scan(self) -> None:
        todo = [x for x in self.tracks.values() if self.store.state(x) not in ("applied", "ignored", "validated")]
        self._to_scan = len(todo)
        if todo:
            self.ctrl.uniformize_scan(todo, self._scanned_one, self._scan_done, lambda: self._cancel)

    def _scanned_one(self, track: LibraryTrack, details: Dict[str, Any], prop: Proposal) -> None:
        if not self.winfo_exists():
            return
        self._scanned += 1
        self.details[track.content_id] = details
        self.props[track.content_id] = prop
        # nouveaux blocs ajoutés en bas tant que la liste n'est pas pleine (rien ne bouge au-dessus), par paquets
        if self._visible(track.content_id) and track.content_id not in self.blocks and track.content_id not in self._pending:
            self._pending.append(track.content_id)
            if not self._flush_timer.isActive():
                self._flush_timer.start()
        self._refresh_info()

    def _flush_pending(self) -> None:
        if not self.winfo_exists():
            return
        todo, self._pending = self._pending, []
        if not self._shown:
            self._fill()
            return
        holder = self.scroll.widget()
        bar = self.scroll.verticalScrollBar().value()
        holder.setUpdatesEnabled(False)
        try:
            for cid in todo:
                if len(self._shown) >= self._limit or cid in self.blocks or not self._visible(cid):
                    continue
                self._append(cid)
        finally:
            holder.setUpdatesEnabled(True)
        self.scroll.verticalScrollBar().setValue(bar)

    def _append(self, cid: int) -> None:
        if not self._shown:
            self._fill()
            return
        blk = TrackBlock(self, cid)
        blk.setParent(self.scroll.widget())                 # jamais affiché hors de la liste (B18)
        self.blocks[cid] = blk
        self.list_lay.insertWidget(self.list_lay.count() - 1, blk)
        self._shown.append(cid)

    def _scan_done(self) -> None:
        if self.winfo_exists():
            self._scanned = self._to_scan
            self.scan_finished = True
            self._flush_pending()
            # sûrs d'abord, une fois tout analysé : seulement si rien n'a encore été touché et si l'ordre
            # change vraiment (B18 : sinon la liste ne bouge pas)
            wanted = sorted((cid for cid in self.tracks if self._visible(cid)), key=self._sort_key)[:self._limit]
            if not self._touched and wanted != self._shown:
                self._current = None
                self._fill()
            else:
                self._refresh_info()

    # ------------------------------------------------------------------ navigation
    def make_current(self, cid: Optional[int], scroll: bool = False) -> None:
        if cid == self._current and not scroll:
            return
        old = self.blocks.get(self._current) if self._current is not None else None
        if old is not None and self.alive(old):
            old.set_current(False)
        self._current = cid
        blk = self.blocks.get(cid) if cid is not None else None
        if blk is not None:
            blk.set_current(True)
            if scroll:
                self.scroll.ensureWidgetVisible(blk, 0, theme.px(40))

    def _move(self, step: int) -> None:
        self._touched = True
        if not self._shown:
            return
        i = self._shown.index(self._current) if self._current in self._shown else -1
        j = max(0, min(len(self._shown) - 1, i + step))
        self.make_current(self._shown[j], scroll=True)

    def focus_page(self) -> None:
        self.setFocus()

    def keyPressEvent(self, e: Any) -> None:         # noqa: N802
        key, cid = e.key(), self._current
        if cid is not None and cid in self.blocks:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.validate(cid)
                return
            if key == Qt.Key_I:
                self.ignore(cid)
                return
            if key == Qt.Key_F:
                self.blocks[cid].search.setFocus()
                self.blocks[cid].search.selectAll()
                return
            if key == Qt.Key_Space:
                self.listen(cid)
                return
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ actions
    def _after_action(self, cid: int) -> None:
        """Le bloc traité quitte la liste (selon le filtre) ; le suivant devient le son courant."""
        i = self._shown.index(cid) if cid in self._shown else 0
        if self._visible(cid):
            blk = self.blocks.get(cid)
            if blk is not None:                          # reste affiché (filtre « Tous ») : on le redessine
                self._fill()
            return
        blk = self.blocks.pop(cid, None)
        if blk is not None:
            self.list_lay.removeWidget(blk)
            blk.hide()
            blk.deleteLater()
        self._shown = [c for c in self._shown if c != cid]
        nxt = self._shown[min(i, len(self._shown) - 1)] if self._shown else None
        self._current = None
        self.make_current(nxt, scroll=True)
        if not self._shown:
            self._fill()
        self._refresh_info()
        self.setFocus()

    def validate(self, cid: int) -> None:
        blk = self.blocks.get(cid)
        if blk is None:
            return
        values = blk.values()
        if not values:
            self.ctrl.message("info", t("uni.nothing_changes"))
            return
        self.store.set(self.tracks[cid], "validated", _encode(values))
        self._history.append(cid)
        self._after_action(cid)

    def ignore(self, cid: int) -> None:
        self.store.set(self.tracks[cid], "ignored")
        self._history.append(cid)
        self._after_action(cid)

    def reset(self, cid: int) -> None:
        self.store.set(self.tracks[cid], "")
        if cid not in self.props:                 # jamais analysé (validé ou ignoré à la session d'avant)
            self._to_scan += 1
            self.ctrl.uniformize_scan([self.tracks[cid]], self._scanned_one, self._scan_done, lambda: self._cancel)
        self._fill()

    def undo(self) -> None:
        """Ctrl+Z : le dernier son validé ou ignoré revient dans la liste « À revoir »."""
        while self._history:
            cid = self._history.pop()
            if self.store.state(self.tracks[cid]) in ("validated", "ignored"):
                self.store.set(self.tracks[cid], "")
                self._current = cid
                self._fill()
                self.make_current(cid, scroll=True)
                return

    def listen(self, cid: int) -> None:
        """Écoute : depuis le milieu du son (on reconnaît vite un morceau)."""
        track = self.tracks[cid]
        self.ctrl.play_queue([track], 0)
        player = self.ctrl.player
        half = max(0.0, (track.duration_seconds or 0) / 2.0)

        def seek(tries: int = 0) -> None:
            from ..audio.player import PLAYING

            if player.state == PLAYING and player.duration > 0:
                player.seek(half)
            elif tries < 40 and self.winfo_exists():
                QTimer.singleShot(100, lambda: seek(tries + 1))

        QTimer.singleShot(100, seek)

    def search(self, cid: int, text: str) -> None:
        blk = self.blocks.get(cid)
        if blk is None or not text.strip():
            return
        self.make_current(cid)

        def got(cands: List[Dict[str, Any]]) -> None:
            b = self.blocks.get(cid)
            if not self.winfo_exists() or b is None or not self.alive(b):
                return
            b.show_candidates(cands)
            if cands:
                self.pick(cid, cands[0])

        self.ctrl.uniformize_search(text.strip(), int(self.tracks[cid].duration_seconds or 0), got)

    def pick(self, cid: int, cand: Dict[str, Any]) -> None:
        def got(prop: Proposal) -> None:
            b = self.blocks.get(cid)
            if self.winfo_exists() and b is not None and self.alive(b):
                b.apply_proposal(prop)

        self.ctrl.uniformize_pick(self.tracks[cid], self.details.get(cid, {}), cand, got)

    def _save(self) -> None:
        items = []
        for cid, x in self.tracks.items():
            if self.state(cid) == "validated":
                vals = _decode(self.store.values(x))
                if vals.get("artwork") is KEEP:
                    vals.pop("artwork")
                items.append((x, vals))
        if not items:
            return
        self.save_btn.setEnabled(False)

        def done(updated: List[LibraryTrack]) -> None:
            for after in updated or []:
                self.store.mark_applied(after)
                if after.content_id in self.tracks:
                    self.tracks[after.content_id] = after
            if self.winfo_exists():
                self._fill()

        self.ctrl.uniformize_apply(items, ok=done)

    # ------------------------------------------------------------------ fermeture
    def close(self) -> bool:                  # noqa: D401
        if self._closed:
            return True
        n = sum(1 for cid in self.tracks if self.state(cid) == "validated")
        if n and not getattr(self, "_leaving", False):
            from .dialogs import ConfirmDialog

            def leave() -> None:
                self._leaving = True
                self.close()

            ConfirmDialog(self, t("uni.leave_title"), plural("uni.leave_one", "uni.leave_many", n),
                          lambda: (self._save(), leave()), confirm_text=t("uni.save_n", n=n),
                          on_cancel=leave, detail=t("uni.leave_detail"))
            return False
        self._closed = True
        self._cancel = True
        cb, self._on_close = self._on_close, None
        if cb:
            cb()
        return True


# ============================================================================ portée (Accueil)
class ScopeDialog:
    """1.3.0 (C25) : depuis l'Accueil, choisir les sons à uniformiser."""

    def __init__(self, parent: Any, controller: Any) -> None:
        from .dialogs import BaseDialog

        self.ctrl = controller
        lib = controller.library
        if lib is None:
            controller.message("error", t("msg.no_drive"))
            return
        dlg = BaseDialog(parent, t("uni.scope_title"), 460)
        self.dlg = dlg
        dlg.heading(t("uni.scope_title"), t("uni.scope_sub"))
        self.choice = QComboBox()
        self.choice.addItems([t("uni.scope_problems"), t("uni.scope_all"), t("uni.scope_recent"),
                              t("uni.scope_playlist")])
        dlg.body.addWidget(self.choice)
        self.playlists = QComboBox()
        self._pls: List[Any] = []
        dlg.body.addWidget(self.playlists)
        self.playlists.hide()
        self.choice.currentIndexChanged.connect(lambda i: self.playlists.setVisible(i == 3))
        dlg.footer(t("uni.scope_open"), self._ok)
        controller.dispatcher.submit(lambda: [p for p in lib.list_playlists() if not p.is_folder],
                                     self._playlists, lambda exc: None, pool="db")
        dlg.show_dialog()

    def _playlists(self, pls: List[Any]) -> None:
        if not self.dlg.winfo_exists():
            return
        self._pls = pls
        self.playlists.addItems([p.name for p in pls])

    def _ok(self) -> None:
        from ..core.uniformize import needs_review

        i = self.choice.currentIndex()
        lib = self.ctrl.library
        self.dlg.close()
        if lib is None:
            return
        name = self.choice.currentText()

        def work() -> List[LibraryTrack]:
            if i == 3:
                if not self._pls:
                    return []
                return list(lib.get_playlist_tracks(self._pls[self.playlists.currentIndex()].playlist_id))
            tracks = list(lib.list_tracks())
            if i == 0:
                return [x for x in tracks if needs_review(x)]
            if i == 2:
                return sorted(tracks, key=lambda x: x.date_added or "", reverse=True)[:50]
            return tracks

        def ok(tracks: List[LibraryTrack]) -> None:
            if not tracks:
                self.ctrl.message("info", t("uni.no_tracks"))
                return
            scope = self._pls[self.playlists.currentIndex()].name if i == 3 and self._pls else name
            self.ctrl._emit("open_uniformize", tracks, scope)

        self.ctrl.dispatcher.submit(work, ok, self.ctrl._on_error, pool="db")
