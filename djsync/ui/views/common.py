"""Éléments partagés par les vues : classe de base, lignes de résultats, popup de téléchargement."""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

import customtkinter as ctk

from ...models import TrackResult
from .. import theme
from ..covers import url_cover
from ..dialogs import PlaylistPicker
from ..widgets import Column, Row

CHECKED, UNCHECKED = "■", "□"  # glyphes présents dans toutes les polices Windows (Segoe UI, Arial)


class View(ctk.CTkFrame):
    """Une page de l'application. `on_show()` est appelé à chaque affichage."""

    title = ""

    def __init__(self, parent: Any, controller: Any, loader: Any) -> None:
        super().__init__(parent, fg_color=theme.BG, corner_radius=0)
        self.ctrl, self.loader = controller, loader

    def on_show(self) -> None:
        pass

    def header(self, text: str, sub: str = "") -> ctk.CTkFrame:
        box = ctk.CTkFrame(self, fg_color="transparent")
        theme.label(box, text, 20, theme.TEXT, "bold", anchor="w").pack(side="left")
        if sub:
            theme.label(box, sub, 11, theme.FAINT, anchor="w").pack(side="left", padx=(12, 0), pady=(6, 0))
        return box


def result_columns(with_check: bool = False) -> List[Column]:
    cols: List[Column] = []
    if with_check:
        cols.append(Column("chk", "", 38, "center", sortable=False))
    cols += [
        Column("title", "Titre", 300, stretch=True),
        Column("artist", "Artiste", 190),
        Column("type", "Type", 70, "center"),
        Column("views", "Vues", 80, "e", sort=lambda r: r.data.views if r.data and r.data.views is not None else None),
        Column("duration", "Durée", 70, "e", sort=lambda r: r.data.duration_seconds if r.data else 0),
        Column("lib", "Biblio", 80, "center"),
    ]
    return cols


def result_row(track: TrackResult, checked: Optional[bool] = None) -> Row:
    values = {
        "title": track.title, "artist": track.artist, "type": track.kind_label,
        "views": track.views_str, "duration": track.duration_str,
        "lib": "✓ déjà" if track.is_duplicate else "",
    }
    if checked is not None:
        values["chk"] = CHECKED if checked else UNCHECKED
    return Row(track.video_id, values, url_cover(track.thumbnail_url), ("dup",) if track.is_duplicate else (), track)


def ask_and_download(parent: Any, ctrl: Any, tracks: Sequence[TrackResult], new_name: str = "") -> None:
    """Popup « playlists de destination » puis mise en file des téléchargements."""
    if not tracks:
        return
    if not ctrl.has_library:
        ctrl.message("error", "Aucune clé connectée : branchez-la ou choisissez-la dans Paramètres.")
        return
    dups = sum(1 for t in tracks if t.is_duplicate)
    sub = f"{len(tracks)} son(s) à télécharger."
    if dups:
        sub += f" {dups} déjà présent(s) dans la bibliothèque."
    PlaylistPicker(
        parent, ctrl, "Télécharger vers…", f"Télécharger ({len(tracks)})",
        on_ok=lambda ids: ctrl.enqueue(list(tracks), ids), multi=True,
        preselect=ctrl.last_playlist_ids, new_name=new_name, allow_empty=True, subtitle=sub,
    )
