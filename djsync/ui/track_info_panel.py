"""1.4.4 (C138) : volet « Infos » d'un son, à droite de la Bibliothèque.

Ouvert par clic droit ▸ Infos ou la touche I, refermable, état gardé (réglage `track_info_open`) ; il suit la
sélection. En-tête (pochette, titre, artistes, album, année, genre, label), Analyse, Fichier, Origine,
Rekordbox, playlists (cliquables), doublons connus, actions. Un clic sur un champ modifiable le passe en
saisie ; Annuler / Enregistrer n'apparaissent qu'après une modification ; changer de son avec des
modifications non enregistrées demande quoi faire. L'écriture passe par `controller.edit_track`, comme
« Modifier les infos » (TrackInfoDialog, gardée pour la pochette et l'outil Uniformiser).

Un seul chargement par son (`TrackInfoService.load`, hors du fil de l'interface) : pochette, playlists,
cues, grille vérifiée, gain, My Tags. Rien n'est mesuré : la qualité estimée (A04) et le gain ne s'affichent
que s'ils sont déjà connus.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import QFormLayout, QFrame, QGridLayout, QLineEdit, QScrollArea, QWidget

from ..i18n import date_text, num, plural, t
from ..models import LibraryTrack, format_duration, source_from_url
from . import theme
from .dialogs import BaseDialog
from .widgets import CamelotPill, FlowLayout, button, hbox, icon_button, label, panel, restyle, vbox

log = logging.getLogger(__name__)

COVER = 168                 # pochette de l'en-tête (px avant zoom)
MIN_WIDTH = 230             # largeur minimale du volet
DEFAULT_WIDTH = 300
MAX_SHARE = 0.42            # part maximale de la largeur (tableau | volet) : la table reste lisible à 860 px
EDITABLE = ("title", "artist", "album", "year", "genre")


# ====================================================================== service (A3-10 : pas de mixin)
class TrackInfoService:
    """Tenu par le contrôleur (`controller.track_info`) : infos d'un son lues hors du fil de l'interface."""

    def __init__(self, controller: Any) -> None:
        self.ctrl = controller

    def load(self, track: LibraryTrack, ok: Callable[[Dict[str, Any]], None]) -> None:
        lib = self.ctrl.library
        if lib is None:
            return

        def done(info: Dict[str, Any]) -> None:
            if self.ctrl.library is lib:
                ok(info)

        self.ctrl.dispatcher.submit(lambda: collect(lib, track), done,
                                    lambda exc: log.info("Track info not read: %s", exc), pool="db")


def _playlist_paths(lib: Any, cid: int) -> List[Tuple[int, str]]:
    """(identifiant, « Dossier ▸ Playlist ») de chaque playlist du son, dans l'ordre de l'arbre."""
    pls = list(lib.list_playlists())
    by_id = {p.playlist_id: p for p in pls}
    order = {p.playlist_id: i for i, p in enumerate(pls)}
    out = []
    for pid in sorted(lib.playlists_of([cid]).get(cid, []), key=lambda p: order.get(p, 0)):
        p, parts, guard = by_id.get(pid), [], 0
        while p is not None and guard < 20:
            parts.insert(0, p.name)
            p, guard = by_id.get(p.parent_id), guard + 1
        if parts:
            out.append((pid, " ▸ ".join(parts)))
    return out


def collect(lib: Any, x: LibraryTrack) -> Dict[str, Any]:
    """Tout ce que le volet ne peut pas lire sur le son lui-même (thread de la base)."""
    out: Dict[str, Any] = {"exists": False, "abs": "", "art": b"", "playlists": [], "cues": None,
                           "checked": False, "gain": None, "mytags": [], "last_played": ""}
    try:
        path = lib.absolute_path(x)
        out["abs"] = str(path)
        out["exists"] = path.is_file()
    except (OSError, ValueError, AttributeError):
        log.debug("Track path unknown", exc_info=True)
    try:
        art = lib.artwork_file(x)
        if art is not None and art.is_file() and art.stat().st_size < 8_000_000:
            out["art"] = art.read_bytes()
    except Exception:  # noqa: BLE001 - pas de pochette lisible
        log.debug("Artwork not read", exc_info=True)
    try:
        out["playlists"] = _playlist_paths(lib, x.content_id)
    except Exception:  # noqa: BLE001
        log.debug("Playlists not read", exc_info=True)
    try:
        from ..core.cue_marks import read_marks

        out["cues"] = read_marks(lib, [x]).get(x.content_id)
    except Exception:  # noqa: BLE001
        log.debug("Cues not read", exc_info=True)
    try:
        from ..db import grid_marks

        out["checked"] = x.content_id in grid_marks.load(lib.backup_dir)
    except Exception:  # noqa: BLE001
        log.debug("Grid marks not read", exc_info=True)
    if out["exists"]:
        try:
            from ..analysis.loudness import known

            out["gain"] = known(out["abs"])                 # mesuré à l'analyse (C109), jamais calculé ici
        except Exception:  # noqa: BLE001
            log.debug("Gain not read", exc_info=True)
    if hasattr(lib, "track_extras"):
        try:
            d = lib.track_extras([x.content_id]).get(x.content_id) or {}
            out["mytags"], out["last_played"] = list(d.get("mytags") or []), d.get("last_played") or ""
        except Exception:  # noqa: BLE001
            log.debug("Track extras not read", exc_info=True)
    return out


# ====================================================================== champ modifiable d'un clic
_READ_STYLE = "QLineEdit { background: transparent; border: 1px solid transparent; padding-left: 0px; }"


class ClickEdit(QLineEdit):
    """Champ affiché comme un texte ; un clic le passe en saisie, Entrée ou la perte du focus le referme."""

    def __init__(self, text: str = "", on_change: Optional[Callable[[], None]] = None, digits: bool = False,
                 color: str = "") -> None:
        super().__init__(text)
        self._on_change = on_change
        self._color = f" QLineEdit {{ color: {color}; }}" if color else ""
        if digits:
            self.setValidator(QIntValidator(0, 2100, self))
        self.setToolTip(t("info.panel_click_edit"))
        self._set_editing(False)
        self.setCursorPosition(0)
        self.textEdited.connect(lambda _s: self._on_change() if self._on_change else None)
        self.returnPressed.connect(lambda: self._set_editing(False))

    @property
    def editing(self) -> bool:
        return not self.isReadOnly()

    def _set_editing(self, on: bool) -> None:
        self.setReadOnly(not on)
        self.setStyleSheet(("" if on else _READ_STYLE) + self._color)
        self.setCursor(Qt.IBeamCursor if on else Qt.PointingHandCursor)
        if not on:
            self.setCursorPosition(0)
            self.deselect()

    def start_edit(self) -> None:
        if not self.editing:
            self._set_editing(True)
            self.setFocus(Qt.MouseFocusReason)
            self.selectAll()

    def mousePressEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        if not self.editing and e.button() == Qt.LeftButton:
            self.start_edit()
            return
        super().mousePressEvent(e)

    def focusOutEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        super().focusOutEvent(e)
        if self.editing:
            self._set_editing(False)


# ====================================================================== question avant de changer de son
class UnsavedInfoDialog(BaseDialog):
    """Enregistrer / Abandonner / Rester (Échap ou fermeture : rester)."""

    def __init__(self, parent: Any, title: str, on_save: Callable[[], None], on_discard: Callable[[], None],
                 on_stay: Callable[[], None]) -> None:
        super().__init__(parent, t("info.unsaved_title"), 420)
        self._on_stay: Optional[Callable[[], None]] = on_stay
        self.heading(t("info.unsaved_title"))
        self.body.addWidget(label(t("info.unsaved_msg", title=title), wrap=True))
        self.body.addStretch(1)
        row = hbox(spacing=theme.px(6))
        row.addStretch(1)
        self.stay_btn = button(t("info.unsaved_stay"), self.close)
        self.discard_btn = button(t("info.unsaved_discard"), lambda: self._pick(on_discard), kind="danger")
        self.save_btn = button(t("action.save"), lambda: self._pick(on_save), kind="primary")
        self.save_btn.setDefault(True)
        for b in (self.stay_btn, self.discard_btn, self.save_btn):
            row.addWidget(b)
        self.body.addLayout(row)
        self.show_dialog()

    def _pick(self, fn: Callable[[], None]) -> None:
        self._on_stay = None
        self.close()
        fn()

    def closeEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        stay, self._on_stay = self._on_stay, None
        super().closeEvent(e)
        if stay:
            stay()


# ====================================================================== volet
class TrackInfoPanel(QFrame):
    """Volet « Infos ». `host` : la vue qui le tient (callbacks : playlist, autre son, sélection gardée)."""

    def __init__(self, host: Any, controller: Any, on_close: Callable[[], None],
                 on_playlist: Optional[Callable[[int], None]] = None,
                 on_track: Optional[Callable[[int], None]] = None,
                 on_stay: Optional[Callable[[LibraryTrack], None]] = None,
                 dups_of: Optional[Callable[[int], Optional[List[LibraryTrack]]]] = None) -> None:
        super().__init__()
        self.setProperty("role", "panel")
        self.host, self.ctrl = host, controller
        self._on_close, self._on_playlist, self._on_track = on_close, on_playlist, on_track
        self._on_stay, self._dups_of = on_stay, dups_of
        self.track: Optional[LibraryTrack] = None
        self.info: Optional[Dict[str, Any]] = None
        self.fields: Dict[str, ClickEdit] = {}
        self.loads = 0                       # chargements lancés (tests : un seul par son)
        self._asking: Optional[UnsavedInfoDialog] = None
        self._saving = False
        self._want: Optional[LibraryTrack] = None
        self._token = 0
        self.setMinimumWidth(theme.px(MIN_WIDTH))

        lay = vbox(self, margins=theme.px(10), spacing=theme.px(6))
        top = hbox(spacing=theme.px(6))
        top.addWidget(label(t("info.panel_title").upper(), "section"))
        top.addStretch(1)
        top.addWidget(icon_button("close", self.close_panel, t("info.panel_close"), size=14))
        lay.addLayout(top)

        self.card = QWidget()
        self.card_lay = vbox(self.card, margins=0, spacing=theme.px(6))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.card)
        lay.addWidget(self.scroll, 1)

        # Annuler / Enregistrer en bas à droite, seulement après une modification
        self.edit_bar = QWidget()
        eb = hbox(self.edit_bar, spacing=theme.px(6))
        self.changed_lbl = label(t("info.panel_modified"), "warn")
        eb.addWidget(self.changed_lbl)
        eb.addStretch(1)
        self.cancel_btn = button(t("action.cancel"), self.cancel)
        self.save_btn = button(t("action.save"), self.save, kind="primary", icon="check")
        eb.addWidget(self.cancel_btn)
        eb.addWidget(self.save_btn)
        self.edit_bar.hide()
        lay.addWidget(self.edit_bar)

        self._timer = QTimer(self)                   # sélection qui défile au clavier : une fiche à la fin
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._follow_now)
        self._empty(t("info.panel_pick"))

    # ------------------------------------------------------------------ suivre la sélection
    def follow(self, track: Optional[LibraryTrack]) -> None:
        """Son sélectionné (None : aucun ; le son affiché reste)."""
        if track is None:
            return
        self._want = track
        self._timer.start()

    def _follow_now(self) -> None:
        track, self._want = self._want, None
        if track is None or not self._alive():
            return
        if self.track is not None and track.content_id == self.track.content_id:
            self.refresh(track)
            return
        if self.dirty:
            self._ask(track)
            return
        self.show_track(track)

    def refresh(self, track: Optional[LibraryTrack]) -> None:
        """Bibliothèque relue : le son affiché à jour (None : il n'y est plus)."""
        if self.track is None:
            return
        if track is None:
            self._reset()
            self._empty(t("info.panel_pick"))
            return
        if track.content_id != self.track.content_id or self.dirty:
            return
        if _same(track, self.track):
            self.track = track
        else:
            self.show_track(track)                     # infos changées (analyse, écriture) : fiche refaite

    def _ask(self, track: LibraryTrack) -> None:
        if self._asking is not None and self._asking.winfo_exists():
            return
        old = self.track

        def save() -> None:
            self._asking = None
            if not self.save(then=lambda: self.show_track(track)):
                stay()                                 # titre vide : on reste sur le son modifié

        def discard() -> None:
            self._asking = None
            self._reset()
            self.show_track(track)

        def stay() -> None:
            self._asking = None
            if old is not None and self._on_stay is not None:
                self._on_stay(old)

        self._asking = UnsavedInfoDialog(self, old.title if old else "", save, discard, stay)

    # ------------------------------------------------------------------ fiche
    def _alive(self) -> bool:
        from shiboken6 import isValid

        return isValid(self)

    def _clear(self) -> None:
        from .one_track_page import _drop_layout

        _drop_layout(self.card_lay)
        self.fields = {}

    def _empty(self, text: str) -> None:
        self._clear()
        self.card_lay.addWidget(label(text, "faint", wrap=True))
        self.card_lay.addStretch(1)

    def _reset(self) -> None:
        self.track, self.info = None, None
        self._token += 1
        self.edit_bar.hide()

    def show_track(self, x: LibraryTrack) -> None:
        self.track, self.info = x, None
        self._token += 1
        self.edit_bar.hide()
        self._build()
        self.loads += 1
        svc = getattr(self.ctrl, "track_info", None)
        if svc is not None:
            svc.load(x, lambda info, x=x, tok=self._token: self._loaded(x, info, tok))

    def _section(self, text: str) -> QFormLayout:
        self.card_lay.addSpacing(theme.px(4))
        self.card_lay.addWidget(label(text.upper(), "section"))
        form = QFormLayout()
        form.setHorizontalSpacing(theme.px(10))
        form.setVerticalSpacing(theme.px(3))
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.card_lay.addLayout(form)
        return form

    @staticmethod
    def _row(form: QFormLayout, key: str, value: Any, role: str = "") -> Any:
        if isinstance(value, str):
            w = label(value or "—", role, wrap=True)
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
        else:
            w = value
        form.addRow(label(t(key), "dim"), w)
        return w

    def _field(self, form: Optional[QFormLayout], key: str, name: str, value: str, digits: bool = False,
               color: str = "") -> ClickEdit:
        e = ClickEdit(value, self._changed, digits=digits, color=color)
        e.setPlaceholderText("—")
        e.setAccessibleName(t(key))
        self.fields[name] = e
        if form is not None:
            form.addRow(label(t(key), "dim"), e)
        return e

    def _build(self) -> None:
        from .views.library_view import downbeat_pending, extra_values, tempo_profile_of, tempo_text

        x = self.track
        if x is None:
            return
        self._clear()
        ex = extra_values(x)
        lay = self.card_lay

        # ---- en-tête : pochette en grand, titre, artistes, album, année, genre, label
        self.cover = label()
        self.cover.setFixedSize(theme.px(COVER), theme.px(COVER))
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setStyleSheet("border: 1px solid rgba(128,128,128,0.35); border-radius: 6px;")
        self.cover.setText("♪")
        lay.addWidget(self.cover, 0, Qt.AlignHCenter)
        title = self._field(None, "track.title", "title", x.title)
        f = title.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)
        artist = self._field(None, "track.artist", "artist", x.artist or "", color=theme.ACCENT)
        lay.addWidget(artist)
        head = QFormLayout()
        head.setHorizontalSpacing(theme.px(10))
        head.setVerticalSpacing(theme.px(3))
        head.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        lay.addLayout(head)
        self._field(head, "track.album", "album", x.album or "")
        self._field(head, "track.year", "year", str(x.year) if x.year else "", digits=True)
        self._field(head, "track.genre", "genre", x.genre or "")
        self._row(head, "track.label", x.label or "")

        # ---- Analyse
        form = self._section(t("info.sec_analysis"))
        if x.bpm:
            bpm = num(float(f"{x.bpm:.2f}"))
            tempo = tempo_text(tempo_profile_of(x))                          # C69 / C221 : tempo variable
            self._row(form, "track.bpm", f"{bpm}\n{tempo}" if tempo else bpm)
        else:
            self._row(form, "track.bpm", t("one.not_analysed"))
        if x.camelot:
            box = QWidget()
            bl = hbox(box, spacing=theme.px(6))
            bl.addWidget(CamelotPill(x.camelot))
            bl.addWidget(label(x.key or "", "dim"))
            bl.addStretch(1)
            form.addRow(label(t("track.key"), "dim"), box)
        else:
            self._row(form, "track.key", t("one.not_analysed") if not x.is_analysed else "")
        self.grid_lbl = self._row(form, "info.grid", t("lib.an_none") if not x.is_analysed else "…")
        self.downbeat = x.is_analysed and downbeat_pending(x)                 # B125
        if self.downbeat:
            self._row(form, "info.first_beat", t("tempo.to_check"), "warn")
        self.cues_lbl = self._row(form, "track.cues", "…")
        self.gain_lbl = self._row(form, "info.gain", "…")

        # ---- Fichier
        form = self._section(t("info.sec_file"))
        from .views.library_view import _fmt

        fmt = self._row(form, "track.format", _fmt(x))
        if ex.get("format__color"):
            fmt.setStyleSheet(f"color: {ex['format__color']};")
        self._row(form, "track.bitrate", ex.get("bitrate", ""))
        self._row(form, "track.sample_rate", ex.get("rate", ""))
        self._row(form, "track.duration", format_duration(x.duration_seconds) if x.duration_seconds else "")
        self._row(form, "track.size", ex.get("size", ""))
        self._row(form, "info.encoder", _encoder_text(x))
        real = self._row(form, "track.real_quality", ex.get("real") or t("one.not_measured"))  # A04 : si connue
        if ex.get("real__color"):
            real.setStyleSheet(f"color: {ex['real__color']};")
        if ex.get("real__tip"):
            real.setToolTip(ex["real__tip"])
        from .one_track_page import breakable

        path_box = QWidget()
        pb = vbox(path_box, spacing=theme.px(2))
        self.path_lbl = label(breakable(x.path), wrap=True)
        self.path_lbl.setToolTip(x.path)
        self.path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pb.addWidget(self.path_lbl)
        reveal_key = "reveal.finder" if sys.platform == "darwin" else "reveal.explorer"
        self.reveal_btn = button(t(reveal_key), self._reveal, kind="flat", icon="folder")
        pb.addWidget(self.reveal_btn, 0, Qt.AlignLeft)
        form.addRow(label(t("track.path"), "dim"), path_box)
        self._row(form, "track.added", date_text(x.date_added) if x.date_added else "")

        # ---- Origine
        form = self._section(t("info.sec_origin"))
        source, when = _origin(x)
        self._row(form, "track.source", source)
        url = (x.source_url or "").strip()
        if url.startswith(("http://", "https://")):
            link = label(f'<a href="{_html(url)}">{_html(_short(url))}</a>', wrap=True)
            link.setTextFormat(Qt.RichText)
            link.setOpenExternalLinks(True)
            link.setToolTip(url)
            form.addRow(label(t("info.link"), "dim"), link)
        self._row(form, "info.downloaded", when)

        # ---- Rekordbox
        form = self._section(t("info.sec_rekordbox"))
        self._row(form, "track.rating", ex.get("rating", ""))
        col = self._row(form, "track.color", ex.get("color", ""))
        if ex.get("color__dot"):
            col.setText(f'<span style="color:{ex["color__dot"]}">●</span> {_html(ex.get("color", ""))}')
            col.setTextFormat(Qt.RichText)
        self._row(form, "track.comment", x.comment or "")
        self._row(form, "track.plays", str(x.play_count) if x.play_count else "0")
        self.tags_lbl = self._row(form, "track.mytags", "…")
        self.last_lbl = self._row(form, "track.last_played", "…")

        # ---- playlists (cliquables) et doublons connus
        self.card_lay.addSpacing(theme.px(4))
        self.card_lay.addWidget(label(t("track.playlists").upper(), "section"))
        self.pl_box = QWidget()
        self.pl_lay = FlowLayout(self.pl_box, spacing=theme.px(4))
        self.pl_lay.addWidget(label(t("one.loading_short"), "faint"))
        self.card_lay.addWidget(self.pl_box)
        dups = self._dups_of(x.content_id) if self._dups_of is not None else None
        self.dup_buttons: List[Any] = []
        if dups:
            self.card_lay.addWidget(label(t("info.duplicates").upper(), "section"))
            box = QWidget()
            fl = FlowLayout(box, spacing=theme.px(4))
            for d in dups:
                b = button(d.display_name, lambda cid=d.content_id: self._goto_track(cid), kind="flat",
                           icon="duplicates")
                b.setToolTip(d.path)
                fl.addWidget(b)
                self.dup_buttons.append(b)
            self.card_lay.addWidget(box)

        # ---- actions
        self.card_lay.addSpacing(theme.px(6))
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.px(6))
        grid.setVerticalSpacing(theme.px(6))
        self.play_btn = button(t("action.listen"), self._play, icon="play")
        self.grid_btn = button(t("lib.edit_grid").rstrip("…"), self._grid, icon="grid")
        self.grid_btn.setEnabled(x.is_analysed)
        self.spectrum_btn = button(t("spectrum.open"), self._spectrum, icon="wave")
        self.folder_btn = button(t("info.open_folder"), self._open_folder, icon="folder")
        self.cover_btn = button(t("info.panel_cover"), self._cover, kind="flat", icon="edit")
        for i, b in enumerate((self.play_btn, self.grid_btn, self.spectrum_btn, self.folder_btn)):
            grid.addWidget(b, i // 2, i % 2)
        grid.addWidget(self.cover_btn, 2, 0, 1, 2)
        self.card_lay.addLayout(grid)
        self.card_lay.addStretch(1)
        self.scroll.verticalScrollBar().setValue(0)

    def _loaded(self, x: LibraryTrack, info: Dict[str, Any], token: int = -1) -> None:
        if not self._alive() or token != self._token or self.track is None:
            return
        x = self.track
        self.info = info
        try:
            pix = QPixmap()
            if info.get("art") and pix.loadFromData(info["art"]):
                self.cover.setPixmap(pix.scaled(theme.px(COVER), theme.px(COVER), Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation))
            # état de la grille (C16, C69, B125), comme la colonne Analyse
            from .views.library_view import tempo_values

            if x.is_analysed:
                checked = bool(info.get("checked"))
                if checked:
                    text, role = t("lib.an_checked"), "accent"
                elif tempo_values(x):
                    text, role = t("lib.an_tempo"), "warn"
                elif self.downbeat:
                    text, role = t("lib.an_downbeat"), "warn"
                else:
                    text, role = t("info.grid_auto"), ""
                self.grid_lbl.setText(text)
                self.grid_lbl.setProperty("role", role)
                restyle(self.grid_lbl)
            mark = info.get("cues")
            if mark is None or mark.empty:
                self.cues_lbl.setText(t("cues.none"))
            else:
                parts = []
                if mark.hot:
                    parts.append(plural("cues.hot_one", "cues.hot_many", len(mark.hot)))
                if mark.memories:
                    parts.append(plural("cues.memory_one", "cues.memory_many", mark.memories))
                self.cues_lbl.setText(", ".join(parts))
            gain = info.get("gain")
            self.gain_lbl.setText(t("info.gain_db", db=num(float(f"{gain[0]:+.1f}"), "+g")) if gain
                                  else t("one.not_measured"))
            self.tags_lbl.setText(", ".join(info.get("mytags") or []) or "—")
            self.last_lbl.setText(date_text(info["last_played"]) if info.get("last_played") else "—")
            self._fill_playlists(info.get("playlists") or [])
            if not info.get("exists"):
                self.path_lbl.setText(f"{self.path_lbl.text()}\n{t('one.file_missing')}")
                self.path_lbl.setProperty("role", "warn")
                restyle(self.path_lbl)
                for b in (self.reveal_btn, self.folder_btn, self.spectrum_btn, self.play_btn):
                    b.setEnabled(False)
        except RuntimeError:                         # fiche refaite entre-temps
            log.debug("Info card rebuilt meanwhile", exc_info=True)

    def _fill_playlists(self, pls: Sequence[Tuple[int, str]]) -> None:
        while self.pl_lay.count():
            item = self.pl_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.pl_buttons: List[Any] = []
        if not pls:
            self.pl_lay.addWidget(label(t("one.no_playlist"), "faint"))
            return
        for pid, path in pls:
            b = button(path, lambda pid=pid: self._goto_playlist(pid), kind="flat", icon="playlist")
            b.setToolTip(t("lib.open_playlist", name=path))
            self.pl_lay.addWidget(b)
            self.pl_buttons.append(b)
        self.pl_box.updateGeometry()

    # ------------------------------------------------------------------ modifications
    def values(self) -> Dict[str, Any]:
        """Seulement ce qui change par rapport au son (comme TrackInfoDialog.values)."""
        x = self.track
        if x is None or not self.fields:
            return {}
        out: Dict[str, Any] = {}
        get = {k: self.fields[k].text().strip() for k in EDITABLE if k in self.fields}
        if get.get("title", x.title) != x.title:
            out["title"] = get["title"]
        if get.get("artist", "") != (x.artist or ""):
            out["artist"] = get["artist"]
        if get.get("album", "") != (x.album or ""):
            out["album"] = get["album"]
        year = int(get.get("year") or 0)
        if year != int(x.year or 0):
            out["year"] = year
        if get.get("genre", "") != (x.genre or ""):
            out["genre"] = get["genre"]
        return out

    @property
    def dirty(self) -> bool:
        return bool(self.values())

    def _changed(self) -> None:
        on = self.dirty
        self.edit_bar.setVisible(on)
        try:
            self.cover_btn.setEnabled(not on)          # la fenêtre de la pochette repartirait du son enregistré
        except (RuntimeError, AttributeError):
            pass

    def cancel(self) -> None:
        """Annuler : les champs reviennent aux valeurs du son, rien n'est écrit."""
        x = self.track
        if x is None:
            return
        orig = {"title": x.title, "artist": x.artist or "", "album": x.album or "",
                "year": str(x.year) if x.year else "", "genre": x.genre or ""}
        for k, e in self.fields.items():
            e.setText(orig.get(k, ""))
            e._set_editing(False)
        self._changed()

    def save(self, then: Optional[Callable[[], None]] = None) -> bool:
        """Écrit les champs modifiés (base, et fichier selon S05, comme « Modifier les infos »). False : rien
        lancé (titre vide)."""
        x = self.track
        if x is None or self._saving:
            return False
        title = self.fields.get("title")
        if title is not None and not title.text().strip():
            title.start_edit()
            return False
        vals = self.values()
        if not vals:
            self._changed()
            if then is not None:
                then()
            return True
        self._saving = True
        self.save_btn.setEnabled(False)

        def ok(result: Any) -> None:
            self._saving = False
            if not self._alive():
                return
            self.save_btn.setEnabled(True)
            if then is not None:
                then()
                return
            fresh = result if isinstance(result, LibraryTrack) else None
            if self.track is not None and self.track.content_id == x.content_id:
                if fresh is not None:
                    self.show_track(fresh)
                else:
                    self.edit_bar.hide()

        def err(exc: BaseException) -> None:
            self._saving = False
            if self._alive():
                self.save_btn.setEnabled(True)
            self.ctrl._on_error(exc)

        self.ctrl.edit_track(x.content_id, vals, ok, err=err)
        return True

    # ------------------------------------------------------------------ actions
    def close_panel(self) -> None:
        """Croix ou touche I ; modifications non enregistrées : la même question qu'en changeant de son."""
        if not self.dirty:
            self._on_close()
            return
        if self._asking is not None and self._asking.winfo_exists():
            return

        def save() -> None:
            self._asking = None
            self.save(then=self._on_close)

        def discard() -> None:
            self._asking = None
            self.cancel()
            self._on_close()

        def stay() -> None:
            self._asking = None

        self._asking = UnsavedInfoDialog(self, self.track.title if self.track else "", save, discard, stay)

    def _goto_playlist(self, pid: int) -> None:
        if self._on_playlist is not None:
            self._on_playlist(pid)

    def _goto_track(self, cid: int) -> None:
        if self._on_track is not None:
            self._on_track(cid)

    def _play(self) -> None:
        if self.track is not None:
            self.ctrl.play_queue([self.track], 0)

    def _grid(self) -> None:
        if self.track is not None:
            from .track_menu import open_grid

            open_grid(self.ctrl, self.track)

    def _spectrum(self) -> None:
        if self.track is not None:
            from .track_menu import open_spectrum

            open_spectrum(self.host, self.ctrl, self.track)

    def _reveal(self) -> None:
        if self.track is not None:
            from .reveal import reveal_entry

            reveal_entry(self.ctrl, self.track)[1]()

    def _open_folder(self) -> None:
        x = self.track
        if x is None:
            return
        try:
            path = self.ctrl.library.absolute_path(x)
        except Exception:  # noqa: BLE001
            log.debug("Handled error in _open_folder", exc_info=True)
            path = None
        if path is None or not Path(path).parent.is_dir():
            self.ctrl.message("error", self.ctrl.missing_file_text(path or x.path))
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _cover(self) -> None:
        """Pochette (Deezer, fichier, aucune) : la fenêtre « Modifier les infos » d'origine."""
        if self.track is None or self.dirty:
            return
        from .track_info_dialog import TrackInfoDialog

        TrackInfoDialog(self.host, self.ctrl, self.track)


# ====================================================================== petits textes
def _same(a: LibraryTrack, b: Optional[LibraryTrack]) -> bool:
    """Mêmes infos (la position dans la playlist ouverte ne compte pas)."""
    import dataclasses

    return b is not None and dataclasses.replace(a, sequence=0) == dataclasses.replace(b, sequence=0)


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _short(url: str, n: int = 48) -> str:
    bare = url.split("://", 1)[-1]
    return bare if len(bare) <= n else bare[:n - 1] + "…"


def _encoder_text(x: LibraryTrack) -> str:
    """A04 : encodeur lu à l'analyse (registre), jamais relu ici."""
    try:
        from ..analysis.encoder import lookup

        enc = lookup(Path(x.path).name, x.file_size)
    except Exception:  # noqa: BLE001
        log.debug("Encoder not read", exc_info=True)
        enc = None
    if enc is None or not enc.name:
        return ""
    details = [d for d in (enc.mode, enc.profile) if d]
    return enc.name + (f" ({', '.join(details)})" if details else "")


def _origin(x: LibraryTrack) -> Tuple[str, str]:
    """(source, date de téléchargement) : dossier surveillé (C160), sinon le site du lien d'origine."""
    try:
        from ..core import watched

        info = watched.lookup_track(x)
    except Exception:  # noqa: BLE001
        log.debug("Watched folder registry not read", exc_info=True)
        info = None
    if info:
        return t("watch.source"), date_text(info.get("date", ""))
    src = source_from_url(x.source_url)
    if src:
        return src, date_text(x.created or x.date_added)
    return "", ""


def panel_width(saved: int, total: int) -> int:
    """Largeur du volet : la dernière choisie (ou celle par défaut), sans dépasser MAX_SHARE de `total`."""
    want = saved if saved and saved > 0 else theme.px(DEFAULT_WIDTH)
    cap = int(total * MAX_SHARE) if total > 0 else want
    return max(theme.px(MIN_WIDTH), min(want, cap))
