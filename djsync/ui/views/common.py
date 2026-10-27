"""Éléments partagés par les vues Qt : classe de base, lignes de résultats, popup de téléchargement."""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from PySide6.QtWidgets import QWidget

from ...i18n import get_language, plural, t
from ...models import TrackResult
from .. import theme
from ..dialogs import PlaylistPicker
from ..widgets import Column, Row, TrackTable, hbox, label, vbox

CHECKED, UNCHECKED = "■", "□"
DOWNLOAD_GLYPH = "↓"            # colonne « télécharger ce son » (cliquable)


def alive(widget: Any) -> bool:
    """Le widget Qt existe-t-il encore (pas détruit côté C++) ?"""
    try:
        from shiboken6 import isValid

        return widget is not None and isValid(widget)
    except ImportError:          # pragma: no cover
        return widget is not None


def focus_list(table: Any) -> None:
    """1.2.0-rc.4 (B07) : après « Écouter », le curseur reste souvent dans le champ de recherche (sur
    Mac, un clic sur un bouton ne lui prend pas le focus) et Espace y tape un espace au lieu de mettre
    en pause. On rend le focus à la liste, sauf si l'utilisateur n'était pas en train d'écrire."""
    from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit

    if isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)) and alive(table):
        table.setFocus()


def human_size(n: float) -> str:
    """Taille lisible : « 12.4 GB » (EN) / « 12,4 Go » (FR)."""
    fr = get_language() == "fr"
    units = ("o", "Ko", "Mo", "Go", "To") if fr else ("B", "KB", "MB", "GB", "TB")
    for i, unit in enumerate(units):
        if n < 1024 or i == len(units) - 1:
            text = f"{n:.0f}" if i < 2 else f"{n:.1f}"
            return f"{text.replace('.', ',') if fr else text} {unit}"
        n /= 1024
    return str(n)


class View(QWidget):
    """Une page de l'application. `on_show()` est appelé à chaque affichage."""

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent)
        self.ctrl, self.loader = controller, loader
        self.root = vbox(self, margins=theme.px(18), spacing=theme.px(8))

    def on_show(self) -> None:
        pass

    def on_scale(self) -> None:
        """Changement de zoom : les tableaux recalculent hauteur de ligne et largeurs."""
        for w in self.findChildren(TrackTable):
            w.apply_metrics()

    def remember_layout(self, table: TrackTable, key: str, default_hidden: Sequence[str] = (),
                        new_keys: Sequence[str] = ()) -> None:
        """1.2.1 (C05) : colonnes affichées et largeurs de ce tableau retenues dans les réglages."""
        def save() -> None:
            try:
                self.ctrl.settings.save()
            except OSError:
                pass

        table.enable_layout(key, lambda: self.ctrl.settings.table_layouts, save, default_hidden, new_keys)

    def focus_filter(self) -> None:
        entry = getattr(self, "filter", None) or getattr(self, "entry", None) or getattr(self, "url", None)
        if entry is not None:
            entry.setFocus()
            entry.selectAll()

    def header(self, text: str, sub: str = "") -> Any:
        row = hbox(spacing=theme.px(10))
        row.addWidget(label(text, "title"))
        if sub:
            row.addWidget(label(sub, "faint"))
        row.addStretch(1)
        return row

    def winfo_exists(self) -> bool:
        """Faux si la vue a été détruite (rappel asynchrone arrivé après une reconstruction)."""
        return alive(self)


def result_columns(with_check: bool = False, with_download: bool = True) -> List[Column]:
    cols: List[Column] = []
    if with_check:
        cols.append(Column("chk", "", 30, "center", sortable=False))
    cols += [
        Column("title", t("track.title"), 300, stretch=True, min_width=170),
        Column("artist", t("track.artist"), 190, priority=1),
        Column("type", t("track.type"), 70, "center", priority=4),
        Column("views", t("track.views"), 80, "e", priority=3,
               sort=lambda r: r.data.views if r.data and r.data.views is not None else None),
        Column("duration", t("track.duration"), 64, "e", priority=2,
               sort=lambda r: r.data.duration_seconds if r.data else 0),
        Column("lib", t("track.in_library"), 80, "center", priority=5),
        Column("source", t("track.source"), 130, priority=4),
    ]
    if with_download:
        cols.append(Column("dl", "", 36, "center", sortable=False, min_width=30))
    return cols


def result_row(track: TrackResult, checked: Optional[bool] = None) -> Row:
    values = {
        "title": track.title, "artist": track.artist, "type": track.kind_label,
        "views": track.views_str, "duration": track.duration_str,
        "lib": t("track.already") if track.is_duplicate else "", "dl": DOWNLOAD_GLYPH,
        "source": track.source_label,
    }
    if track.is_album:                         # 1.2.1 (C09) : une ligne par album, s'ouvre au double-clic
        values.update(artist=" · ".join(x for x in (track.artist, track.album or "") if x), views="", duration="",
                      lib="", dl="›")
    if checked is not None:
        values["chk"] = CHECKED if checked else UNCHECKED
    return Row(track.video_id, values, ("dup",) if track.is_duplicate else (), track)


def ask_and_download(parent: Any, ctrl: Any, tracks: Sequence[TrackResult], new_name: str = "") -> None:
    """Popup « playlists de destination » puis mise en file des téléchargements."""
    if not tracks:
        return
    if not ctrl.has_library:
        ctrl.message("error", t("msg.no_drive"))
        return
    dups = sum(1 for x in tracks if x.is_duplicate)
    sub = plural("dl.to_download_one", "dl.to_download_many", len(tracks))
    if dups:
        sub += " " + plural("dl.already_one", "dl.already_many", dups)
    PlaylistPicker(
        parent, ctrl, t("dl.picker_title"), t("dl.picker_ok", n=len(tracks)),
        on_ok=lambda ids: ctrl.enqueue(list(tracks), ids), multi=True,
        preselect=ctrl.last_playlist_ids, new_name=new_name, allow_empty=True, subtitle=sub,
    )
