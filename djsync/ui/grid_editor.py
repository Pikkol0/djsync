"""Éditeur de grille de temps (comme le mode GRID de Rekordbox).

Pour corriger un décalage observé sur les platines : la forme d'onde détaillée du son (ANLZ) avec
ses temps (1ers temps de mesure plus épais, à la couleur d'accent). On peut :
  * décaler toute la grille (±1 ms, ±10 ms) ;
  * choisir le 1er temps de mesure (« le temps sélectionné devient le 1 ») ;
  * imposer un BPM (grille constante ancrée sur le temps sélectionné) ;
  * écouter à partir d'un endroit (clic sur la forme d'onde puis Lecture) ;
puis Enregistrer : le .DAT est réécrit (copie d'origine dans DJSync_Backups/anlz), le BPM mis à
jour dans exportLibrary.db et export.pdb.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, List, Optional, Tuple

import customtkinter as ctk

from ..analysis import grid as G
from ..audio.player import PAUSED, PLAYING
from ..i18n import t
from ..models import LibraryTrack, format_duration
from . import theme
from .dialogs import BaseDialog, ConfirmDialog
from .icons import ctk_icon
from .widgets import Tooltip

COLS_PER_S = 150.0          # forme d'onde détaillée ANLZ : 150 colonnes par seconde
VIEW_CHOICES = (4, 8, 16, 32)


class GridEditor(BaseDialog):
    modal = False           # V0.2.4 : le lecteur et la bibliothèque restent utilisables pendant l'édition

    def __init__(self, parent: Any, controller: Any, track: LibraryTrack) -> None:
        super().__init__(parent, t("grid.title"), 940, 560)
        self.resizable(True, True)
        self.ctrl, self.track = controller, track
        self.original: List[Tuple[int, int, int]] = []
        self.beats: List[Tuple[int, int, int]] = []
        self.detail: List[Tuple[float, str]] = []
        self.duration_ms = max(1, track.duration_seconds * 1000)
        self.view_s = 8
        self.start_ms = 0.0
        self.cursor_ms = 0.0
        self.selected = 0
        self._drag_x: Optional[int] = None
        self._native = False

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=18, pady=(0, 16))
        theme.button(bar, t("action.cancel"), self.close, kind="ghost", width=90).pack(side="right")
        self.save_btn = theme.button(bar, t("action.save"), self._save, kind="primary", width=130)
        self.save_btn.pack(side="right", padx=(0, 8))
        self.reset_btn = theme.button(bar, t("grid.reset"), self._reset, kind="ghost", width=110)
        self.reset_btn.pack(side="left")
        self.state_lbl = theme.label(bar, "", 11, theme.DIM)
        self.state_lbl.pack(side="left", padx=12)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(head, text="", image=ctk_icon("grid", 22, theme.ACCENT)).pack(side="left")
        box = ctk.CTkFrame(head, fg_color="transparent")
        box.pack(side="left", padx=(10, 0))
        theme.label(box, track.display_name, 14, theme.TEXT, "bold", anchor="w").pack(anchor="w")
        self.info = theme.label(box, t("grid.loading"), 11, theme.DIM, anchor="w")
        self.info.pack(anchor="w")
        zoom = ctk.CTkFrame(head, fg_color="transparent")
        zoom.pack(side="right")
        theme.label(zoom, t("grid.view"), 11, theme.DIM).pack(side="left", padx=(0, 6))
        self.view_menu = theme.option_menu(zoom, [f"{v} s" for v in VIEW_CHOICES], self._view_changed, width=80)
        self.view_menu.set(f"{self.view_s} s")
        self.view_menu.pack(side="left")

        self.canvas = tk.Canvas(self, bg=theme.SURFACE, highlightthickness=0, height=theme.tkpx(190), cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=20, pady=(6, 0))
        self.scroll = ctk.CTkSlider(self, from_=0, to=1, number_of_steps=1000, height=14, fg_color=theme.BORDER,
                                    progress_color=theme.BORDER, button_color=theme.DIM,
                                    button_hover_color=theme.TEXT, command=self._scrolled)
        self.scroll.set(0)
        self.scroll.pack(fill="x", padx=20, pady=(4, 6))

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=20, pady=(2, 6))

        def tool(text: str, cmd: Any, tip: str, width: int = 64) -> ctk.CTkButton:
            b = theme.button(tools, text, cmd, kind="ghost", width=width)
            b.pack(side="left", padx=(0, 6))
            Tooltip(b, tip)
            return b

        self.play_btn = ctk.CTkButton(tools, text="", image=ctk_icon("play", 16, theme.ON_ACCENT), width=40, height=32,
                                      corner_radius=8, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                      command=self._play)
        self.play_btn.pack(side="left", padx=(0, 12))
        Tooltip(self.play_btn, t("grid.play_tip"))
        theme.label(tools, t("grid.shift"), 11, theme.DIM).pack(side="left", padx=(0, 6))
        tool("−10", lambda: self._shift(-10), t("grid.shift_tip", ms=-10), 48)
        tool("−1", lambda: self._shift(-1), t("grid.shift_tip", ms=-1), 40)
        tool("+1", lambda: self._shift(1), t("grid.shift_tip", ms=1), 40)
        tool("+10", lambda: self._shift(10), t("grid.shift_tip", ms=10), 48)
        tool(t("grid.downbeat"), self._downbeat, t("grid.downbeat_tip"), 150)
        right = ctk.CTkFrame(tools, fg_color="transparent")
        right.pack(side="right")
        theme.label(right, "BPM", 11, theme.DIM).pack(side="left", padx=(0, 6))
        self.bpm_entry = theme.entry(right, "", width=80)
        self.bpm_entry.pack(side="left")
        self.bpm_entry.bind("<Return>", lambda _e: self._apply_bpm())
        b = theme.button(right, t("grid.apply_bpm"), self._apply_bpm, kind="ghost", width=110)
        b.pack(side="left", padx=(6, 0))
        Tooltip(b, t("grid.apply_bpm_tip"))
        theme.label(self, t("grid.hint"), 10, theme.FAINT, anchor="w", justify="left", wraplength=880).pack(
            fill="x", padx=20, pady=(0, 6))

        self.canvas.bind("<Configure>", lambda _e: self.draw())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag_x", None))
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _e: self._pan(-0.15))
        self.canvas.bind("<Button-5>", lambda _e: self._pan(0.15))
        self.bind("<Left>", lambda _e: self._shift(-1))
        self.bind("<Right>", lambda _e: self._shift(1))
        self.save_btn.configure(state="disabled")
        controller.load_grid(track.content_id, self._loaded, self._load_failed)
        self._tick()

    # ------------------------------------------------------------------ chargement
    def _loaded(self, data: Any) -> None:
        if not self.winfo_exists():
            return
        g = data["grid"]
        self.original = list(g.beats)
        self.beats = list(g.beats)
        self.detail = data["detail"]
        self.duration_ms = max(g.duration_ms, g.beats[-1][2] + 1000, int(len(self.detail) / COLS_PER_S * 1000))
        self._native = g.native
        self.selected = next((i for i, b in enumerate(self.beats) if b[0] == 1), 0)
        self.cursor_ms = self.beats[self.selected][2]
        self.start_ms = max(0.0, self.cursor_ms - 1000)
        self._refresh_info()
        self.draw()

    def _load_failed(self, exc: BaseException) -> None:
        if self.winfo_exists():
            self.info.configure(text=self.ctrl.error_text(exc), text_color=theme.ERR)

    # ---------------------------------------------------------------- géométrie
    @property
    def px_per_ms(self) -> float:
        return max(1, self.canvas.winfo_width()) / (self.view_s * 1000.0)

    def _x(self, ms: float) -> float:
        return (ms - self.start_ms) * self.px_per_ms

    def _ms(self, x: float) -> float:
        return self.start_ms + x / self.px_per_ms

    def _clamp_view(self) -> None:
        span = self.view_s * 1000.0
        self.start_ms = max(0.0, min(self.start_ms, max(0.0, self.duration_ms - span)))
        total = max(1.0, self.duration_ms - span)
        self.scroll.set(self.start_ms / total if total > 0 else 0)

    # ------------------------------------------------------------------- dessin
    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10 or not self.beats:
            return
        self._clamp_view()
        mid = h * 0.55
        # forme d'onde détaillée (une colonne par pixel, max des colonnes ANLZ couvertes)
        if self.detail:
            n = len(self.detail)
            for x in range(0, w, max(1, theme.tkpx(1))):
                a = int(self._ms(x) / 1000.0 * COLS_PER_S)
                b = max(a + 1, int(self._ms(x + 1) / 1000.0 * COLS_PER_S))
                if a >= n or b <= 0:
                    continue
                seg = self.detail[max(0, a):min(n, b)]
                if not seg:
                    continue
                v, color = max(seg, key=lambda s: s[0])
                half = max(1.0, v * (h * 0.42))
                if color in ("#000000", "#000"):
                    color = theme.DIM
                c.create_line(x, mid - half, x, mid + half, fill=color)
        # grille
        lo, hi = self._ms(-2), self._ms(w + 2)
        bar_no = 0
        for i, (n, _tempo, ms) in enumerate(self.beats):
            if n == 1:
                bar_no += 1
            if ms < lo or ms > hi:
                continue
            x = self._x(ms)
            down = n == 1
            color = theme.ACCENT if down else theme.mix(theme.SURFACE, theme.TEXT, 0.55)
            c.create_line(x, 14, x, h, fill=color, width=theme.tkpx(2.5 if down else 1))
            if down:
                c.create_text(x + 4, 3, text=str(bar_no), anchor="nw", fill=theme.ACCENT, font=theme.tk_font(9, "bold"))
            if i == self.selected:
                c.create_polygon(x - 6, h, x + 6, h, x, h - 10, fill=theme.WARN, outline="")
        # curseur (position d'écoute)
        xc = self._x(self.cursor_ms)
        if 0 <= xc <= w:
            c.create_line(xc, 0, xc, h, fill=theme.TEXT, width=theme.tkpx(1.5), dash=(3, 3))
        c.create_text(w - 6, 3, text=format_duration(int(self.start_ms / 1000)), anchor="ne", fill=theme.FAINT,
                      font=theme.tk_font(9))

    def _refresh_info(self) -> None:
        if not self.beats:
            return
        tempos = sorted(b[1] for b in self.beats)
        bpm = tempos[len(tempos) // 2] / 100.0
        kind = t("grid.constant") if len(set(tempos)) <= 1 else t("grid.variable")
        delta = self.beats[self.selected][2] - self._original_at(self.selected)
        parts = [f"{bpm:.2f} BPM", kind, plural_beats(len(self.beats))]
        if self._native:
            parts.append(t("grid.native"))
        self.info.configure(text="  ·  ".join(parts), text_color=theme.DIM)
        self.bpm_entry.delete(0, "end")
        self.bpm_entry.insert(0, f"{bpm:.2f}")
        changed = self.beats != self.original
        self.save_btn.configure(state="normal" if changed else "disabled")
        self.state_lbl.configure(text=(t("grid.modified", ms=f"{delta:+d}") if changed else ""))

    def _original_at(self, index: int) -> int:
        """Position d'origine du temps le plus proche (pour afficher le décalage appliqué)."""
        if not self.original:
            return 0
        j = G.nearest(self.original, self.beats[index][2])
        return self.original[j][2]

    # ---------------------------------------------------------------- édition
    def _shift(self, ms: int) -> None:
        if not self.beats:
            return
        anchor = self.beats[self.selected][2]
        self.beats = G.shift(self.beats, ms, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor + ms)
        self._refresh_info()
        self.draw()

    def _downbeat(self) -> None:
        if self.beats:
            self.beats = G.set_downbeat(self.beats, self.selected)
            self._refresh_info()
            self.draw()

    def _apply_bpm(self) -> None:
        try:
            bpm = float(self.bpm_entry.get().replace(",", "."))
        except ValueError:
            return
        if not 40 <= bpm <= 300 or not self.beats:
            self.ctrl.message("warn", t("grid.bpm_range"))
            return
        anchor = self.beats[self.selected][2]
        self.beats = G.set_bpm(self.beats, bpm, self.selected, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _reset(self) -> None:
        self.beats = list(self.original)
        self.selected = min(self.selected, len(self.beats) - 1)
        self._refresh_info()
        self.draw()

    # --------------------------------------------------------------- navigation
    def _view_changed(self, label: str) -> None:
        center = self.start_ms + self.view_s * 500
        self.view_s = int(label.split()[0])
        self.start_ms = center - self.view_s * 500
        self.draw()

    def _scrolled(self, value: float) -> None:
        self.start_ms = float(value) * max(0.0, self.duration_ms - self.view_s * 1000.0)
        self.draw()

    def _pan(self, fraction: float) -> None:
        self.start_ms += fraction * self.view_s * 1000
        self.draw()

    def _wheel(self, e: Any) -> None:
        self._pan(-0.15 if e.delta > 0 else 0.15)

    def _press(self, e: Any) -> None:
        self._drag_x = e.x
        self._drag_start = self.start_ms
        self._moved = False
        self.cursor_ms = max(0.0, self._ms(e.x))
        if self.beats:
            self.selected = G.nearest(self.beats, self.cursor_ms)
            self._refresh_info()
        self.draw()
        if self.ctrl.player.state in (PLAYING, PAUSED) and self._is_playing_this():
            self.ctrl.player.seek(self.cursor_ms / 1000.0)

    def _drag(self, e: Any) -> None:
        if self._drag_x is None:
            return
        self.start_ms = self._drag_start - (e.x - self._drag_x) / self.px_per_ms
        self.draw()

    # ------------------------------------------------------------------- écoute
    def _is_playing_this(self) -> bool:
        item = self.ctrl.current_item
        return item is not None and item.kind == "library" and item.item.content_id == self.track.content_id

    def _play(self) -> None:
        player = self.ctrl.player
        if self._is_playing_this() and player.state in (PLAYING, PAUSED):
            player.toggle_pause()
            return
        self.ctrl.play_queue([self.track], 0)
        start = self.cursor_ms / 1000.0

        def seek_when_ready(tries: int = 0) -> None:
            if player.state == PLAYING and player.duration > 0:
                player.seek(start)
            elif tries < 40 and self.winfo_exists():
                self.after(100, lambda: seek_when_ready(tries + 1))

        self.after(100, seek_when_ready)

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        player = self.ctrl.player
        playing = self._is_playing_this() and player.state == PLAYING
        self.play_btn.configure(image=ctk_icon("pause" if playing else "play", 16, theme.ON_ACCENT))
        if playing:
            self.cursor_ms = player.position() * 1000.0
            span = self.view_s * 1000.0
            if not (self.start_ms <= self.cursor_ms <= self.start_ms + span * 0.85):
                self.start_ms = self.cursor_ms - span * 0.15
            self.draw()
        self.after(60 if playing else 300, self._tick)

    # -------------------------------------------------------------- enregistrer
    def _save(self) -> None:
        def go() -> None:
            self.save_btn.configure(state="disabled", text=t("grid.saving"))

            def done(_r: Any) -> None:
                if self.winfo_exists():
                    self.close()

            def failed(_e: BaseException) -> None:
                if self.winfo_exists():
                    self.save_btn.configure(state="normal", text=t("action.save"))

            self.ctrl.save_grid(self.track.content_id, self.beats, ok=done, err=failed)

        if self._native:
            ConfirmDialog(self, t("grid.native_title"), t("grid.native_msg"), go, confirm_text=t("action.save"),
                          detail=t("grid.native_detail"))
        else:
            go()

    def close(self) -> None:
        if self._is_playing_this() and self.ctrl.player.state == PLAYING:
            self.ctrl.player.toggle_pause()
        super().close()


def plural_beats(n: int) -> str:
    from ..i18n import plural

    return plural("grid.beats_one", "grid.beats_many", n)
