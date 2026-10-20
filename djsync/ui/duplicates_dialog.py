"""Outil « Doublons » : retrouve les sons présents plusieurs fois sur la clé, laisse choisir lequel
garder, corriger son titre / artiste, et supprime les autres.

Exemple : « Daft Punk - One More Time (Clip Officiel) » (artiste vide) et « One More Time »
(Daft Punk). Le son gardé prend la place des doublons dans toutes leurs playlists (même
position) ; la base est sauvegardée avant la modification.
"""
from __future__ import annotations

from typing import Any, List, Optional

import customtkinter as ctk

from ..core.duplicates import best_keeper, split_display
from ..i18n import plural, t
from ..models import LibraryTrack, format_duration
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .icons import ctk_icon
from .widgets import CamelotPill

_FORMATS = {1: "MP3", 4: "AAC", 5: "FLAC", 11: "WAV", 12: "AIFF"}


class DuplicatesDialog(BaseDialog):
    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("dup.title"), 860, 580)
        self.ctrl = controller
        self.groups: List[List[LibraryTrack]] = []
        self.index = -1
        self._keep = ctk.IntVar(value=0)
        self._busy = False

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=18, pady=(0, 16))
        theme.button(bar, t("action.close"), self.close, kind="ghost", width=90).pack(side="right")
        self.apply_btn = theme.button(bar, t("dup.apply"), self._apply, kind="primary", width=230)
        self.apply_btn.pack(side="right", padx=(0, 8))
        self.skip_btn = theme.button(bar, t("dup.skip"), self._skip, kind="ghost", width=150)
        self.skip_btn.pack(side="right", padx=(0, 8))

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 6))
        ctk.CTkLabel(head, text="", image=ctk_icon("duplicates", 22, theme.ACCENT)).pack(side="left")
        theme.label(head, t("dup.title"), 16, theme.TEXT, "bold").pack(side="left", padx=(10, 0))
        self.count = theme.label(head, t("dup.searching"), 11, theme.DIM)
        self.count.pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.list = ctk.CTkScrollableFrame(body, fg_color=theme.SURFACE, corner_radius=8, width=230)
        self.list.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self.detail = ctk.CTkFrame(body, fg_color=theme.SURFACE, corner_radius=8)
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail.grid_columnconfigure(0, weight=1)
        theme.label(self.detail, t("dup.searching"), 12, theme.FAINT).grid(row=0, column=0, pady=40)
        self._buttons: List[ctk.CTkButton] = []
        self._refresh_actions()
        controller.find_duplicates(self._loaded)

    # ------------------------------------------------------------------ liste
    def _loaded(self, groups: List[List[LibraryTrack]]) -> None:
        if not self.winfo_exists():
            return
        self.groups = groups
        self._fill_list()
        self._select(0 if groups else -1)

    def _fill_list(self) -> None:
        for w in self.list.winfo_children():
            w.destroy()
        self._buttons = []
        self.count.configure(text=plural("dup.groups_one", "dup.groups_many", len(self.groups)))
        for i, g in enumerate(self.groups):
            title, artist = split_display(best_keeper(g).title, best_keeper(g).artist)
            b = ctk.CTkButton(self.list, text=f"{title}\n{artist or '—'}  ·  ×{len(g)}", anchor="w", height=44,
                              corner_radius=6, fg_color="transparent", hover_color=theme.ELEV,
                              text_color=theme.TEXT, font=theme.font(11), command=lambda k=i: self._select(k))
            b.pack(fill="x", padx=4, pady=2)
            self._buttons.append(b)

    def _select(self, i: int) -> None:
        self.index = i
        for k, b in enumerate(self._buttons):
            b.configure(fg_color=theme.ACCENT_DIM if k == i else "transparent")
        for w in self.detail.winfo_children():
            w.destroy()
        if not (0 <= i < len(self.groups)):
            box = ctk.CTkFrame(self.detail, fg_color="transparent")
            box.grid(row=0, column=0, pady=60)
            ctk.CTkLabel(box, text="", image=ctk_icon("check", 40, theme.ACCENT)).pack()
            theme.label(box, t("dup.none_title"), 14, theme.DIM, "bold").pack(pady=(8, 2))
            theme.label(box, t("dup.none_sub"), 11, theme.FAINT, wraplength=420, justify="center").pack()
            self._refresh_actions()
            return
        group = self.groups[i]
        keeper = best_keeper(group)
        self._keep.set(group.index(keeper))
        theme.label(self.detail, t("dup.choose"), 12, theme.DIM, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        for k, x in enumerate(group):
            self._version_row(k, x).grid(row=k + 1, column=0, sticky="ew", padx=10, pady=3)
        form = ctk.CTkFrame(self.detail, fg_color="transparent")
        form.grid(row=len(group) + 2, column=0, sticky="ew", padx=14, pady=(14, 12))
        form.grid_columnconfigure(1, weight=1)
        title, artist = split_display(keeper.title, keeper.artist)
        theme.label(form, t("dup.fix_metadata"), 12, theme.TEXT, "bold", anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        theme.label(form, t("track.title"), 11, theme.DIM, width=70, anchor="w").grid(row=1, column=0, sticky="w")
        self.title_entry = theme.entry(form)
        self.title_entry.grid(row=1, column=1, sticky="ew", pady=2)
        self.title_entry.insert(0, title)
        theme.label(form, t("track.artist"), 11, theme.DIM, width=70, anchor="w").grid(row=2, column=0, sticky="w")
        self.artist_entry = theme.entry(form)
        self.artist_entry.grid(row=2, column=1, sticky="ew", pady=2)
        self.artist_entry.insert(0, artist)
        theme.label(form, t("dup.metadata_hint"), 10, theme.FAINT, anchor="w", justify="left", wraplength=480).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._refresh_actions()

    def _version_row(self, k: int, x: LibraryTrack) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.detail, fg_color=theme.ELEV, corner_radius=8)
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkRadioButton(row, text="", variable=self._keep, value=k, width=24, fg_color=theme.ACCENT,
                           hover_color=theme.ACCENT_HOVER, border_color=theme.FAINT,
                           command=lambda: self._keeper_changed()).grid(row=0, column=0, rowspan=2, padx=(10, 4))
        theme.label(row, x.title, 12, theme.TEXT, "bold", anchor="w").grid(row=0, column=1, sticky="ew", pady=(6, 0))
        fmt = _FORMATS.get(x.file_type, "")
        info = [x.artist or t("dup.no_artist"), format_duration(x.duration_seconds), fmt,
                f"{x.bpm:.0f} BPM" if x.bpm else t("dup.not_analysed"), (x.date_added or "")[:10]]
        theme.label(row, "  ·  ".join(i for i in info if i), 10, theme.DIM, anchor="w").grid(
            row=1, column=1, sticky="ew", pady=(0, 6))
        if x.camelot:
            CamelotPill(row, x.camelot).grid(row=0, column=2, rowspan=2, padx=6)
        ctk.CTkButton(row, text="", image=ctk_icon("play", 14, theme.TEXT), width=30, height=30, corner_radius=7,
                      fg_color="transparent", hover_color=theme.BORDER,
                      command=lambda: self.ctrl.play_queue(self.groups[self.index], k)).grid(
            row=0, column=3, rowspan=2, padx=(0, 8))
        return row

    def _keeper_changed(self) -> None:
        group = self.groups[self.index]
        x = group[self._keep.get()]
        title, artist = split_display(x.title, x.artist)
        if not any(split_display(g.title, g.artist) == (self.title_entry.get().strip(), self.artist_entry.get().strip())
                   for g in group) and self.title_entry.get().strip():
            return                                  # l'utilisateur a déjà corrigé à la main : on garde
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, title)
        self.artist_entry.delete(0, "end")
        self.artist_entry.insert(0, artist)

    def _refresh_actions(self) -> None:
        ok = 0 <= self.index < len(self.groups) and not self._busy
        self.apply_btn.configure(state="normal" if ok else "disabled")
        self.skip_btn.configure(state="normal" if ok else "disabled")

    # ------------------------------------------------------------------ actions
    def _skip(self) -> None:
        if 0 <= self.index < len(self.groups):
            self.groups.pop(self.index)
            self._fill_list()
            self._select(min(self.index, len(self.groups) - 1))

    def _apply(self) -> None:
        if not (0 <= self.index < len(self.groups)):
            return
        group = self.groups[self.index]
        keep = group[self._keep.get()]
        others = [x for x in group if x is not keep]
        title = self.title_entry.get().strip() or keep.title
        artist = self.artist_entry.get().strip()
        new_title = title if title != keep.title else None
        new_artist = artist if artist != keep.artist else None
        names = ", ".join(t("fmt.quoted", text=x.title) for x in others[:3])

        def go() -> None:
            self._busy = True
            self._refresh_actions()

            def done(_r: Any) -> None:
                self._busy = False
                if self.winfo_exists():
                    self._skip()

            def failed(_e: BaseException) -> None:
                self._busy = False
                if self.winfo_exists():
                    self._refresh_actions()

            self.ctrl.resolve_duplicates(keep.content_id, [x.content_id for x in others], new_title, new_artist,
                                         ok=done, err=failed)

        ConfirmDialog(self, t("dup.confirm_title"), t("dup.confirm_msg", n=len(others), names=names, keep=keep.title),
                      go, confirm_text=t("dup.apply_short"), danger=True, detail=t("dup.confirm_detail"))

    def close(self) -> None:
        super().close()

    @property
    def current_group(self) -> Optional[List[LibraryTrack]]:
        return self.groups[self.index] if 0 <= self.index < len(self.groups) else None
