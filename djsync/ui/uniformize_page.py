"""Page « Uniformiser » (1.2.2, C14) : propositions son par son, validation à la main.

Chaque son : « avant → après » champ par champ (titre, artistes, album, année, genre, pochette),
chaque changement coché ou non et modifiable. « Valider » retient le son (gardé entre deux sessions),
« Ignorer » le met de côté, « Modifier… » ouvre l'éditeur d'infos. « Enregistrer les sons validés »
écrit seulement ceux-là, en une fois (une sauvegarde). Rien n'est écrit sans validation.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QScrollArea, QSplitter, QWidget

from ..core.uniformize import Proposal
from ..db.base import KEEP
from ..i18n import plural, t
from ..models import LibraryTrack
from . import theme
from .widgets import Column, Row, TrackTable, button, hbox, label, panel, vbox

STATES = ("todo", "validated", "ignored", "applied", "clean", "scanning")
FIELD_KEYS = {"title": "track.title", "artist": "track.artist", "album": "track.album", "year": "info.year",
              "genre": "info.genre", "artwork": "info.artwork"}


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


class UniformizePage(QWidget):
    def __init__(self, parent: Any, controller: Any, tracks: List[LibraryTrack], scope: str,
                 on_close: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.ctrl, self.scope = controller, scope
        self._on_close = on_close
        self._closed = False
        self._cancel = False
        self.tracks: Dict[int, LibraryTrack] = {x.content_id: x for x in tracks}
        self.props: Dict[int, Proposal] = {}
        self.details: Dict[int, Dict[str, Any]] = {}
        self.store = controller.review_store()
        self._scanned = 0
        self._to_scan = 0
        self._current: Optional[int] = None
        self._edits: Dict[str, Any] = {}

        body = vbox(self, margins=theme.px(18), spacing=theme.px(8))
        head = hbox()
        head.addWidget(button(t("grid.back"), self.close, kind="flat", icon="back"))
        titles = vbox(spacing=0)
        titles.addWidget(label(t("uni.title", scope=scope), "title"))
        self.info = label("", "dim")
        titles.addWidget(self.info)
        head.addLayout(titles, 1)
        head.addWidget(label(t("uni.show"), "dim"))
        self._filters = {"todo": t("uni.f_todo"), "validated": t("uni.f_validated"), "ignored": t("uni.f_ignored"),
                         "done": t("uni.f_done"), "all": t("uni.f_all")}
        self.filter = QComboBox()
        self.filter.addItems(list(self._filters.values()))
        self.filter.currentTextChanged.connect(lambda _t: self._fill())
        head.addWidget(self.filter)
        self.save_btn = button("", self._save, kind="primary", icon="check")
        head.addWidget(self.save_btn)
        body.addLayout(head)
        body.addWidget(label(t("uni.intro"), "faint", wrap=True))

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        cols = [Column("state", t("uni.col_state"), 110), Column("title", t("track.title"), 220, stretch=True, min_width=150),
                Column("artist", t("track.artist"), 150, priority=2), Column("new", t("uni.col_new"), 260, priority=1),
                Column("conf", t("uni.col_conf"), 110, priority=3)]
        self.table = TrackTable(self, cols, selectmode="browse")
        self.table.set_empty("check", t("uni.empty"))
        self.table.on_select = lambda ids: self._select(int(ids[0]) if ids else None)
        split.addWidget(self.table)
        right = QScrollArea()
        right.setWidgetResizable(True)
        self.detail = panel()
        self.detail_lay = vbox(self.detail, margins=theme.px(12), spacing=theme.px(8))
        right.setWidget(self.detail)
        split.addWidget(right)
        split.setSizes([theme.px(560), theme.px(480)])
        body.addWidget(split, 1)
        self._fill()
        self._refresh_save()
        self._start_scan()
        self._show_detail()

    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return not self._closed and isValid(self)

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

    def _state_text(self, st: str) -> str:
        return t(f"uni.st_{st}")

    def _row(self, cid: int) -> Row:
        x = self.tracks[cid]
        st = self.state(cid)
        prop = self.props.get(cid)
        new = ""
        conf = ""
        if st == "validated":
            v = self.store.values(x)
            new = " · ".join(str(v[k]) for k in ("artist", "title") if isinstance(v.get(k), str)) or t("uni.st_validated")
        elif prop is not None and not prop.empty:
            vals = prop.values(only_checked=False)
            new = " · ".join(str(vals[k]) for k in ("artist", "title") if k in vals) or ", ".join(
                t(FIELD_KEYS[c.field]) for c in prop.changes)
        if prop is not None:
            conf = {"sure": t("uni.conf_sure", score=prop.score), "rules": t("uni.conf_rules"),
                    "doubtful": t("uni.conf_doubtful")}[prop.confidence]
        tags = {"validated": ("ok",), "ignored": ("dim",), "applied": ("dim",), "clean": ("dim",),
                "scanning": ("dim",)}.get(st, ())
        return Row(str(cid), {"state": self._state_text(st), "title": x.title, "artist": x.artist or "", "new": new,
                              "conf": conf}, tags, x)

    def _visible(self, cid: int) -> bool:
        f = next((k for k, v in self._filters.items() if v == self.filter.currentText()), "todo")
        st = self.state(cid)
        return {"todo": st in ("todo", "scanning"), "validated": st == "validated", "ignored": st == "ignored",
                "done": st in ("applied", "clean"), "all": True}[f]

    def _fill(self) -> None:
        rows = [self._row(cid) for cid in self.tracks if self._visible(cid)]
        self.table.set_rows(rows, keep_selection=True)
        self._refresh_info()

    def _update_row(self, cid: int) -> None:
        if self.table.row(str(cid)) is None:
            if self._visible(cid):
                self._fill()
            return
        if not self._visible(cid):
            self._fill()
            return
        r = self._row(cid)
        row = self.table.row(str(cid))
        row.tags = r.tags
        self.table.update_values(str(cid), **r.values)

    def _refresh_info(self) -> None:
        counts = {s: 0 for s in STATES}
        for cid in self.tracks:
            counts[self.state(cid)] += 1
        parts = [t("uni.count_todo", n=counts["todo"]), t("uni.count_validated", n=counts["validated"]),
                 t("uni.count_done", n=counts["applied"] + counts["clean"])]
        if self._scanned < self._to_scan and not self._cancel:
            parts.insert(0, t("uni.scanning", i=self._scanned, n=self._to_scan))
        self.info.setText("  ·  ".join(parts))
        self._refresh_save()

    def _refresh_save(self) -> None:
        n = sum(1 for cid in self.tracks if self.state(cid) == "validated")
        self.save_btn.setText(t("uni.save_n", n=n))
        self.save_btn.setEnabled(n > 0)

    # ------------------------------------------------------------------ analyse
    def _start_scan(self) -> None:
        todo = [x for x in self.tracks.values() if self.store.state(x) not in ("applied", "ignored", "validated")]
        self._to_scan = len(todo)
        if not todo:
            return
        self.ctrl.uniformize_scan(todo, self._scanned_one, self._scan_done, lambda: self._cancel)

    def _scanned_one(self, track: LibraryTrack, details: Dict[str, Any], prop: Proposal) -> None:
        if not self.winfo_exists():
            return
        self._scanned += 1
        self.details[track.content_id] = details
        self.props[track.content_id] = prop
        self._update_row(track.content_id)
        if self._current is None and self.state(track.content_id) == "todo":
            self.table.select([str(track.content_id)])
        elif self._current == track.content_id:
            self._show_detail()
        self._refresh_info()

    def _scan_done(self) -> None:
        if self.winfo_exists():
            self._scanned = self._to_scan
            self._refresh_info()

    # ------------------------------------------------------------------ détail
    def _select(self, cid: Optional[int]) -> None:
        self._current = cid
        self._show_detail()

    def _clear_detail(self) -> None:
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                lay = item.layout()
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget() is not None:
                        sub.widget().deleteLater()
        self._edits = {}

    def _show_detail(self) -> None:
        self._clear_detail()
        cid = self._current
        if cid is None or cid not in self.tracks:
            self.detail_lay.addWidget(label(t("uni.pick"), "faint", wrap=True))
            self.detail_lay.addStretch(1)
            return
        x = self.tracks[cid]
        st = self.state(cid)
        prop = self.props.get(cid)
        self.detail_lay.addWidget(label(x.display_name, "h2"))
        self.detail_lay.addWidget(label(self._state_text(st), "accent" if st == "validated" else "dim"))
        if st == "scanning":
            self.detail_lay.addWidget(label(t("uni.wait"), "faint", wrap=True))
        elif st in ("applied", "clean"):
            self.detail_lay.addWidget(label(t("uni.nothing"), "faint", wrap=True))
        elif st == "validated":
            for k, v in _decode(self.store.values(x)).items():
                shown = t("info.cover_removed") if (k == "artwork" and v is None) else (
                    t("info.cover_new") if k == "artwork" else str(v))
                self.detail_lay.addWidget(label(f"{t(FIELD_KEYS.get(k, k))} : {shown}", "", wrap=True))
        elif prop is not None:
            if prop.deezer:
                txt = t("uni.deezer_sure" if prop.confidence == "sure" else "uni.deezer_unsure", score=prop.score,
                        title=prop.deezer.get("title", ""), artists=", ".join(prop.deezer.get("artists") or []))
            else:
                txt = t("uni.deezer_none")
            self.detail_lay.addWidget(label(txt, "faint", wrap=True))
            for ch in prop.changes:
                self.detail_lay.addWidget(self._change_row(ch))
        btns = hbox(spacing=theme.px(6))
        if st in ("todo", "ignored", "clean", "applied"):
            if st != "clean" and st != "applied":
                self.validate_btn = button(t("uni.validate"), self._validate, kind="primary", icon="check")
                btns.addWidget(self.validate_btn)
            btns.addWidget(button(t("uni.edit"), self._edit, icon="edit"))
        if st == "todo":
            btns.addWidget(button(t("uni.ignore"), self._ignore, kind="flat", icon="close"))
        if st in ("validated", "ignored"):
            btns.addWidget(button(t("uni.reset"), self._reset, kind="flat", icon="refresh"))
        btns.addStretch(1)
        self.detail_lay.addLayout(btns)
        self.detail_lay.addStretch(1)

    def _change_row(self, ch: Any) -> QWidget:
        box = panel(role="banner")
        lay = vbox(box, margins=theme.px(8), spacing=theme.px(4))
        top = hbox(spacing=theme.px(6))
        cb = QCheckBox(t(FIELD_KEYS.get(ch.field, ch.field)))
        cb.setChecked(ch.checked)
        cb.toggled.connect(lambda on, c=ch: setattr(c, "checked", on))
        top.addWidget(cb)
        top.addStretch(1)
        lay.addLayout(top)
        if ch.field == "artwork":
            row = hbox(spacing=theme.px(8))
            row.addWidget(label(t("uni.cover_none_now"), "faint"))
            img = label()
            img.setFixedSize(theme.px(96), theme.px(96))
            row.addWidget(img)
            row.addStretch(1)
            lay.addLayout(row)
            self.ctrl.fetch_image(str(ch.new).replace("1000x1000", "250x250"),
                                  lambda data, w=img: self._set_img(w, data))
        else:
            old = label(t("uni.before", value=ch.old if ch.old not in (None, "", 0) else "—"), "faint", wrap=True)
            lay.addWidget(old)
            edit = QLineEdit(str(ch.new))
            edit.textEdited.connect(lambda text, c=ch: setattr(c, "new", int(text) if c.field == "year" and text.isdigit()
                                                                else text))
            self._edits[ch.field] = edit
            lay.addWidget(edit)
        return box

    @staticmethod
    def _set_img(widget: Any, data: bytes) -> None:
        from .views.common import alive

        pix = QPixmap()
        if alive(widget) and data and pix.loadFromData(data):
            widget.setPixmap(pix.scaled(widget.width(), widget.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ------------------------------------------------------------------ actions
    def _next_todo(self, after: int) -> None:
        ids = self.table.displayed_iids()
        cand = [i for i in ids if self.state(int(i)) == "todo"]
        if not cand:
            self._current = None
            self._show_detail()
            return
        later = [i for i in cand if ids.index(i) > (ids.index(str(after)) if str(after) in ids else -1)]
        self.table.select([(later or cand)[0]])

    def _validate(self, values: Optional[Dict[str, Any]] = None) -> None:
        cid = self._current
        if cid is None:
            return
        x = self.tracks[cid]
        if values is None:
            prop = self.props.get(cid)
            values = prop.values() if prop is not None else {}
        if not values:
            self.ctrl.message("info", t("uni.nothing_checked"))
            return
        self.store.set(x, "validated", _encode(values))
        self._update_row(cid)
        self._refresh_info()
        self._next_todo(cid)

    def _ignore(self) -> None:
        cid = self._current
        if cid is None:
            return
        self.store.set(self.tracks[cid], "ignored")
        self._update_row(cid)
        self._refresh_info()
        self._next_todo(cid)

    def _reset(self) -> None:
        cid = self._current
        if cid is None:
            return
        self.store.set(self.tracks[cid], "")
        if cid not in self.props:                 # jamais analysé (validé ou ignoré à la session d'avant)
            self._to_scan += 1
            self.ctrl.uniformize_scan([self.tracks[cid]], self._scanned_one, self._scan_done, lambda: self._cancel)
        self._update_row(cid)
        self._show_detail()
        self._refresh_info()

    def _edit(self) -> None:
        from .track_info_dialog import TrackInfoDialog

        cid = self._current
        if cid is None:
            return
        x = self.tracks[cid]
        prop = self.props.get(cid)
        initial: Dict[str, Any] = {}
        if prop is not None:
            for ch in prop.changes:
                if ch.checked:
                    initial[ch.field] = ch.new
        TrackInfoDialog(self, self.ctrl, x, initial=initial, on_values=lambda vals, c=cid: self._edited(c, vals))

    def _edited(self, cid: int, values: Dict[str, Any]) -> None:
        if not self.winfo_exists():
            return
        self._current = cid
        if values:
            self._validate(values)

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
                self._show_detail()

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
