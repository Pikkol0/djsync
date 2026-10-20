"""Éléments partagés par les vues : classe de base, lignes de résultats, popup de téléchargement."""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

import customtkinter as ctk

from ...i18n import get_language, plural, t
from ...models import TrackResult
from .. import theme
from ..covers import url_cover
from ..dialogs import PlaylistPicker
from ..widgets import Column, Row, TrackTable

CHECKED, UNCHECKED = "■", "□"  # glyphes présents dans toutes les polices Windows (Segoe UI, Arial)
DOWNLOAD_GLYPH = "↓"            # colonne « télécharger ce son » (cliquable)


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


class View(ctk.CTkFrame):
    """Une page de l'application. `on_show()` est appelé à chaque affichage."""

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, fg_color=theme.BG, corner_radius=0)
        self.ctrl, self.loader = controller, loader

    def on_show(self) -> None:
        pass

    def on_scale(self) -> None:
        """Changement d'échelle (zoom, taille de fenêtre) : les tableaux Tk se recalculent."""
        for w in self.tables():
            w.on_scale()

    def tables(self) -> List[TrackTable]:
        out: List[TrackTable] = []

        def walk(widget: Any) -> None:
            for child in widget.winfo_children():
                if isinstance(child, TrackTable):
                    out.append(child)
                else:
                    walk(child)

        walk(self)
        return out

    def focus_filter(self) -> None:
        """Ctrl+F : champ de filtre/recherche de la vue, s'il existe."""
        entry = getattr(self, "filter", None) or getattr(self, "entry", None) or getattr(self, "url", None)
        if entry is not None:
            entry.focus_set()
            try:
                entry.select_range(0, "end")
            except Exception:  # noqa: BLE001
                pass

    def header(self, text: str, sub: str = "", parent: Any = None) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent or self, fg_color="transparent")
        theme.label(box, text, 20, theme.TEXT, "bold", anchor="w").pack(side="left")
        if sub:
            theme.label(box, sub, 11, theme.FAINT, anchor="w").pack(side="left", padx=(12, 0), pady=(6, 0))
        return box


def result_columns(with_check: bool = False, with_download: bool = True) -> List[Column]:
    cols: List[Column] = []
    if with_check:
        cols.append(Column("chk", "", 38, "center", sortable=False))
    cols += [
        Column("title", t("track.title"), 300, stretch=True, min_width=170),
        Column("artist", t("track.artist"), 190, priority=1),
        Column("type", t("track.type"), 70, "center", priority=4),
        Column("views", t("track.views"), 80, "e", priority=3,
               sort=lambda r: r.data.views if r.data and r.data.views is not None else None),
        Column("duration", t("track.duration"), 70, "e", priority=2,
               sort=lambda r: r.data.duration_seconds if r.data else 0),
        Column("lib", t("track.in_library"), 80, "center", priority=5),
    ]
    if with_download:
        cols.append(Column("dl", "", 44, "center", sortable=False, min_width=36))
    return cols


def result_row(track: TrackResult, checked: Optional[bool] = None) -> Row:
    values = {
        "title": track.title, "artist": track.artist, "type": track.kind_label,
        "views": track.views_str, "duration": track.duration_str,
        "lib": t("track.already") if track.is_duplicate else "", "dl": DOWNLOAD_GLYPH,
    }
    if checked is not None:
        values["chk"] = CHECKED if checked else UNCHECKED
    return Row(track.video_id, values, url_cover(track.thumbnail_url), ("dup",) if track.is_duplicate else (), track)


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
