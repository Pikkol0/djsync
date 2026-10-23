"""« Modifier les infos » d'un son (1.2.2, S04) : titre, artistes, album, année, genre, pochette.

Pochette : garder l'actuelle, en choisir une trouvée sur Deezer, prendre une image du PC, ou n'en
mettre aucune. Ouverte depuis la bibliothèque (clic droit), le lecteur et l'outil Uniformiser (dans
ce cas les valeurs sont renvoyées à l'outil au lieu d'être enregistrées tout de suite).
Le fichier audio n'est ni modifié ni renommé.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCompleter, QFileDialog, QFormLayout, QLineEdit, QSpinBox, QWidget

from ..db.base import KEEP
from ..i18n import t
from ..models import LibraryTrack
from . import theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label, vbox

THUMB = 96


class TrackInfoDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any, track: LibraryTrack,
                 initial: Optional[Dict[str, Any]] = None,
                 on_values: Optional[Callable[[Dict[str, Any]], None]] = None,
                 genres: Optional[List[str]] = None) -> None:
        super().__init__(parent, t("info.title"), 560)
        self.ctrl, self.track = controller, track
        self._on_values = on_values
        self._initial = dict(initial or {})
        self._details: Dict[str, Any] = {}
        self._artwork: Any = KEEP           # KEEP | None | octets | URL
        self._candidates: List[Dict[str, str]] = []
        self.heading(t("info.title"), track.display_name)

        form = QFormLayout()
        self.title_e = QLineEdit(self._initial.get("title", track.title))
        self.artist_e = QLineEdit(self._initial.get("artist", track.artist or ""))
        self.artist_e.setPlaceholderText(t("info.artist_hint"))
        self.album_e = QLineEdit(self._initial.get("album", track.album or ""))
        self.year_e = QSpinBox()
        self.year_e.setRange(0, 2100)
        self.year_e.setSpecialValueText("—")
        self.genre_e = QLineEdit(self._initial.get("genre", ""))
        if genres:
            self._set_genres(genres)
        else:
            controller.track_genres(lambda found: self._set_genres(list(found.values())) if self.winfo_exists() else None)
        form.addRow(t("track.title"), self.title_e)
        form.addRow(t("track.artist"), self.artist_e)
        form.addRow(t("track.album"), self.album_e)
        form.addRow(t("info.year"), self.year_e)
        form.addRow(t("info.genre"), self.genre_e)
        self.body.addLayout(form)

        self.body.addWidget(label(t("info.artwork"), "dim"))
        row = hbox(spacing=theme.px(10))
        self.cover = label()
        self.cover.setFixedSize(theme.px(THUMB), theme.px(THUMB))
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setStyleSheet("border: 1px solid rgba(128,128,128,0.4);")
        row.addWidget(self.cover)
        col = vbox(spacing=theme.px(4))
        self.cover_state = label("", "faint", wrap=True)
        col.addWidget(self.cover_state)
        btns = hbox(spacing=theme.px(6))
        self.find_btn = button(t("info.find_covers"), self._find_covers, icon="search")
        btns.addWidget(self.find_btn)
        btns.addWidget(button(t("info.cover_file"), self._cover_file, kind="flat", icon="folder"))
        btns.addWidget(button(t("info.cover_none"), self._cover_none, kind="flat", icon="close"))
        btns.addWidget(button(t("info.cover_keep"), self._cover_keep, kind="flat", icon="back"))
        btns.addStretch(1)
        col.addLayout(btns)
        col.addStretch(1)
        row.addLayout(col, 1)
        self.body.addLayout(row)
        self.found = QWidget()
        self.found_lay = hbox(self.found, spacing=theme.px(6))
        self.found.hide()
        self.body.addWidget(self.found)
        self.footer(t("info.use") if on_values else t("action.save"), self._ok)
        if "artwork" in self._initial:
            self._artwork = self._initial["artwork"]
        self._refresh_cover()
        self.show_dialog()
        controller.track_details(track.content_id, self._loaded)

    def _set_genres(self, genres: List[str]) -> None:
        names = sorted({g for g in genres if g}, key=str.lower)
        if names:
            comp = QCompleter(names, self)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            self.genre_e.setCompleter(comp)

    # ------------------------------------------------------------------ chargement
    def _loaded(self, details: Dict[str, Any]) -> None:
        if not self.winfo_exists():
            return
        self._details = details
        if "album" not in self._initial:
            self.album_e.setText(details.get("album") or "")
        self.year_e.setValue(int(self._initial.get("year", details.get("year") or 0) or 0))
        if "genre" not in self._initial:
            self.genre_e.setText(details.get("genre") or "")
        self._refresh_cover()

    def _show_pixmap(self, data: bytes) -> None:
        pix = QPixmap()
        if data and pix.loadFromData(data):
            self.cover.setPixmap(pix.scaled(theme.px(THUMB), theme.px(THUMB), Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
        else:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("—")

    def _refresh_cover(self) -> None:
        art = self._artwork
        if art is KEEP:
            self.cover_state.setText(t("info.cover_current"))
            path = None
            try:
                lib = self.ctrl.library
                path = lib.artwork_file(self.track) if lib is not None else None
            except Exception:  # noqa: BLE001
                path = None
            if path is not None and path.is_file():
                self._show_pixmap(path.read_bytes())
            else:
                self._show_pixmap(b"")
                self.cover_state.setText(t("info.cover_current_none"))
        elif art is None:
            self.cover_state.setText(t("info.cover_removed"))
            self._show_pixmap(b"")
        elif isinstance(art, bytes):
            self.cover_state.setText(t("info.cover_from_file"))
            self._show_pixmap(art)
        else:
            self.cover_state.setText(t("info.cover_found"))
            self.ctrl.fetch_image(str(art), lambda data: self._show_pixmap(data) if self.winfo_exists() else None)

    # ------------------------------------------------------------------ pochettes
    def _find_covers(self) -> None:
        self.find_btn.setEnabled(False)
        probe = LibraryTrack(self.track.content_id, self.title_e.text(), self.artist_e.text(), self.album_e.text(),
                             0, "", 0.0, 0, None, "", False)

        def show(found: List[Dict[str, str]]) -> None:
            if not self.winfo_exists():
                return
            self.find_btn.setEnabled(True)
            while self.found_lay.count():
                item = self.found_lay.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            if not found:
                self.found_lay.addWidget(label(t("info.no_cover_found"), "faint"))
            for c in found:
                b = button("", lambda u=c["url"]: self._pick(u), kind="flat")
                b.setFixedSize(theme.px(72), theme.px(72))
                b.setToolTip(f"{c.get('album', '')} · {c.get('artist', '')}")
                self.found_lay.addWidget(b)
                self.ctrl.fetch_image(c["url"].replace("1000x1000", "250x250"),
                                      lambda data, btn=b: self._button_icon(btn, data))
            self.found_lay.addStretch(1)
            self.found.show()

        self.ctrl.cover_candidates(probe, show)

    @staticmethod
    def _button_icon(btn: Any, data: bytes) -> None:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon

        from .views.common import alive

        if not alive(btn) or not data:
            return
        pix = QPixmap()
        if pix.loadFromData(data):
            btn.setIcon(QIcon(pix))
            btn.setIconSize(QSize(theme.px(66), theme.px(66)))

    def _pick(self, url: str) -> None:
        self._artwork = url
        self._refresh_cover()

    def _cover_file(self) -> None:
        path, _f = QFileDialog.getOpenFileName(self, t("info.cover_file"), "", t("fb.image_filter"))
        if path:
            try:
                with open(path, "rb") as fh:
                    self._artwork = fh.read()
            except OSError:
                return
            self._refresh_cover()

    def _cover_none(self) -> None:
        self._artwork = None
        self._refresh_cover()

    def _cover_keep(self) -> None:
        self._artwork = KEEP
        self._refresh_cover()

    # ------------------------------------------------------------------ enregistrer
    def values(self) -> Dict[str, Any]:
        """Seulement ce qui change par rapport au son (None = inchangé côté bibliothèque)."""
        d = self._details
        out: Dict[str, Any] = {}
        title, artist = self.title_e.text().strip(), self.artist_e.text().strip()
        if title and title != self.track.title:
            out["title"] = title
        if artist != (self.track.artist or ""):
            out["artist"] = artist
        album = self.album_e.text().strip()
        if album != (d.get("album") if d else (self.track.album or "")):
            out["album"] = album
        if self.year_e.value() != int(d.get("year") or 0):
            out["year"] = self.year_e.value()
        genre = self.genre_e.text().strip()
        if genre != (d.get("genre") or ""):
            out["genre"] = genre
        if self._artwork is not KEEP:
            out["artwork"] = self._artwork
        return out

    def _ok(self) -> None:
        if not self.title_e.text().strip():
            self.title_e.setFocus()
            return
        vals = self.values()
        self.close()
        if self._on_values is not None:
            self._on_values(vals)
        elif vals:
            self.ctrl.edit_track(self.track.content_id, vals)
