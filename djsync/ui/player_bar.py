"""Barre de lecture fixée en bas : pochette, titre/artiste, pastille Camelot + BPM, Précédent /
Lecture-Pause / Suivant, progression (mini forme d'onde ANLZ cliquable si le son est analysé,
sinon curseur), volume.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, List, Optional, Tuple

import customtkinter as ctk

from ..audio.covers import placeholder
from ..audio.player import LOADING, PAUSED, PLAYING, STOPPED, NowPlaying
from ..i18n import t
from ..models import format_duration
from . import theme
from .covers import CoverLoader, CoverRef, file_cover, url_cover
from .icons import ctk_icon
from .widgets import CamelotPill, Tooltip

BAR_HEIGHT = 92
COVER_PX = 60
WAVE_H = 30


def _ctk_image(img: Any, size: int) -> ctk.CTkImage:
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


class WaveformBar(tk.Canvas):
    """Mini forme d'onde (aperçu ANLZ) : partie lue en couleur d'accent ; clic/glisser = position."""

    def __init__(self, parent: Any, on_seek: Any) -> None:
        super().__init__(parent, height=theme.tkpx(WAVE_H), bg=theme.SURFACE, highlightthickness=0, bd=0,
                         cursor="hand2")
        self._data: List[Tuple[float, str]] = []
        self._ratio = 0.0
        self._on_seek = on_seek
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<B1-Motion>", self._click)

    def set_data(self, data: List[Tuple[float, str]]) -> None:
        self._data = data
        self.configure(height=theme.tkpx(WAVE_H))
        self.draw()

    @property
    def has_data(self) -> bool:
        return bool(self._data)

    def set_ratio(self, ratio: float) -> None:
        if abs(ratio - self._ratio) * max(1, self.winfo_width()) >= 1:
            self._ratio = ratio
            self.draw()

    def draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or not self._data:
            return
        n = len(self._data)
        step = max(2, theme.tkpx(3))
        cols = max(1, w // step)
        played = self._ratio * w
        mid = h / 2
        for c in range(cols):
            a, b = c * n // cols, max(c * n // cols + 1, (c + 1) * n // cols)
            v = max(x[0] for x in self._data[a:b])
            x = c * step
            half = max(1.0, v * (h / 2 - 1))
            color = theme.ACCENT if x < played else theme.mix(theme.SURFACE, theme.DIM, 0.55)
            self.create_rectangle(x, mid - half, x + step - 1, mid + half, fill=color, outline="")
        self.create_line(played, 0, played, h, fill=theme.TEXT, width=max(1, theme.tkpx(1.5)))

    def _click(self, e: Any) -> None:
        w = max(1, self.winfo_width())
        self._on_seek(min(1.0, max(0.0, e.x / w)))


class PlayerBar(ctk.CTkFrame):
    def __init__(self, parent: Any, controller: Any, loader: CoverLoader) -> None:
        super().__init__(parent, fg_color=theme.SURFACE, corner_radius=0, height=BAR_HEIGHT)
        self.ctrl, self.loader = controller, loader
        self.player = controller.player
        self._dragging = False
        self._cover_token = 0
        self._wave_token = 0
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=3, uniform="bar")
        self.grid_columnconfigure(1, weight=4, uniform="bar")
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._ph = _ctk_image(placeholder(COVER_PX * 2), COVER_PX)
        self._img_ref: Any = self._ph

        # ---- gauche : pochette + titre + tonalité/BPM
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(14, 8))
        left.grid_columnconfigure(1, weight=1)
        left.grid_rowconfigure(0, weight=1)
        self.cover = ctk.CTkLabel(left, text="", image=self._ph, width=COVER_PX, height=COVER_PX)
        self.cover.grid(row=0, column=0, padx=(0, 12))
        text = ctk.CTkFrame(left, fg_color="transparent")
        text.grid(row=0, column=1, sticky="ew")
        self.title = theme.label(text, t("player.nothing"), 13, theme.TEXT, "bold", anchor="w")
        self.title.pack(anchor="w", fill="x")
        self.artist = theme.label(text, t("player.hint"), 11, theme.DIM, anchor="w")
        self.artist.pack(anchor="w", fill="x")
        meta = ctk.CTkFrame(text, fg_color="transparent")
        meta.pack(anchor="w", pady=(2, 0))
        self.key_pill = CamelotPill(meta)
        self.bpm = theme.label(meta, "", 10, theme.DIM)
        self._meta_box = meta

        # ---- centre : boutons + progression
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="nsew")
        mid.grid_columnconfigure(0, weight=1)
        buttons = ctk.CTkFrame(mid, fg_color="transparent")
        buttons.grid(row=0, column=0, pady=(8, 0))

        def small(icon: str, cmd: Any, tip: str) -> ctk.CTkButton:
            b = ctk.CTkButton(buttons, text="", image=ctk_icon(icon, 16, theme.TEXT), width=34, height=34,
                              corner_radius=8, fg_color="transparent", hover_color=theme.ELEV, command=cmd)
            Tooltip(b, tip)
            return b

        self.prev_btn = small("prev", self.ctrl.play_previous, t("player.previous"))
        self.prev_btn.pack(side="left", padx=4)
        self.play_btn = ctk.CTkButton(
            buttons, text="", image=ctk_icon("play", 18, theme.ON_ACCENT), width=44, height=40, corner_radius=12,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, command=self.ctrl.toggle_play,
        )
        self.play_btn.pack(side="left", padx=6)
        Tooltip(self.play_btn, t("player.play_pause"))
        self.next_btn = small("next", self.ctrl.play_next, t("player.next"))
        self.next_btn.pack(side="left", padx=4)
        self.stop_btn = small("stop", self.player.stop, t("player.stop"))
        self.stop_btn.pack(side="left", padx=(10, 0))

        prog = ctk.CTkFrame(mid, fg_color="transparent")
        prog.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 6))
        prog.grid_columnconfigure(1, weight=1)
        self.elapsed = theme.label(prog, "0:00", 10, theme.DIM, width=40)
        self.elapsed.grid(row=0, column=0)
        self.seek = theme.slider(prog, from_=0, to=1, number_of_steps=1000)
        self.seek.set(0)
        self.seek.grid(row=0, column=1, sticky="ew", padx=6)
        self.wave = WaveformBar(prog, self._wave_seek)
        self.total = theme.label(prog, "0:00", 10, theme.DIM, width=40)
        self.total.grid(row=0, column=2)
        self.seek.bind("<ButtonPress-1>", lambda _e: setattr(self, "_dragging", True), add="+")
        self.seek.bind("<ButtonRelease-1>", self._seek_release, add="+")
        self.seek.configure(command=self._seek_moved)

        # ---- droite : outils du son en cours (V0.2.3) + volume
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=(8, 18))
        self.grid_btn = ctk.CTkButton(right, text="", image=ctk_icon("grid", 17, theme.TEXT), width=34, height=34,
                                      corner_radius=8, fg_color="transparent", hover_color=theme.ELEV,
                                      command=self._edit_grid)
        self.grid_btn.pack(side="left", padx=(0, 2))
        Tooltip(self.grid_btn, t("player.edit_grid"))
        self.more_btn = ctk.CTkButton(right, text="", image=ctk_icon("menu", 17, theme.TEXT), width=34, height=34,
                                      corner_radius=8, fg_color="transparent", hover_color=theme.ELEV,
                                      command=self._track_menu)
        self.more_btn.pack(side="left", padx=(0, 14))
        Tooltip(self.more_btn, t("player.track_options"))
        ctk.CTkLabel(right, text="", image=ctk_icon("volume", 18, theme.DIM)).pack(side="left", padx=(0, 8))
        self.volume = theme.slider(right, from_=0, to=1, width=100, command=self._volume_changed)
        self.volume.set(self.player.volume)
        self.volume.pack(side="left")

        controller.on("player", self._on_player)
        controller.on("queue", self._refresh_nav)
        self._refresh_nav()
        if self.player.meta is not None:          # reconstruction de l'interface pendant une lecture
            self._show_meta(self.player.meta, self.player.duration)
            self._refresh_state(self.player.state)
        self._tick()

    # ---------------------------------------------------------------- actions
    def _volume_changed(self, value: float) -> None:
        self.player.set_volume(float(value))

    def _seek_moved(self, value: float) -> None:
        if self._dragging and self.player.duration > 0:
            self.elapsed.configure(text=format_duration(int(float(value) * self.player.duration)))

    def _seek_release(self, _e: Any) -> None:
        if self._dragging and self.player.duration > 0:
            self.player.seek(float(self.seek.get()) * self.player.duration)
        self._dragging = False

    def _wave_seek(self, ratio: float) -> None:
        if self.player.duration > 0 and self.player.state in (PLAYING, PAUSED):
            self.player.seek(ratio * self.player.duration)
            self.wave.set_ratio(ratio)

    def _refresh_nav(self) -> None:
        self.prev_btn.configure(state="normal" if self.ctrl.current_item is not None else "disabled")
        self.next_btn.configure(state="normal" if self.ctrl.has_next else "disabled")
        on_drive = self.ctrl.current_library_id() is not None
        for b in (self.grid_btn, self.more_btn):
            b.configure(state="normal" if on_drive else "disabled")

    # ------------------------------------------------- outils du son en cours (V0.2.3)
    def _with_track(self, action: Any) -> None:
        """Relit le son en cours dans la base (analyse, BPM, tonalité à jour) puis lance l'action."""
        cid = self.ctrl.current_library_id()
        if cid is None:
            self.ctrl.message("info", t("player.not_on_drive"))
            return
        self.ctrl.fresh_track(cid, lambda track: action(track) if self.winfo_exists() else None)

    def _edit_grid(self) -> None:
        def go(track: Any) -> None:
            if not track.is_analysed:
                self.ctrl.message("info", t("grid.not_analysed"))
                return
            from .grid_editor import GridEditor

            GridEditor(self.winfo_toplevel(), self.ctrl, track)

        self._with_track(go)

    def _track_menu(self) -> None:
        def show(track: Any) -> None:
            from .widgets import popup_menu

            entries: list = []
            if track.is_analysed:
                entries.append((t("lib.edit_grid"), lambda: self._edit_grid()))
            entries.append((t("action.edit_metadata"), lambda: self._edit_metadata(track)))
            entries.append((t("player.analyse_again") if track.is_analysed else t("action.analyse"),
                            lambda: self.ctrl.analyze([track.content_id], force=track.is_analysed)))
            if track.camelot:
                entries += [None, (t("lib.show_compatible", code=track.camelot), lambda: self._compatible(track))]
            entries += [None, (t("player.show_in_library"), lambda: self._show_in_library(track))]
            b = self.more_btn
            popup_menu(b, entries, b.winfo_rootx(), b.winfo_rooty())

        self._with_track(show)

    def _edit_metadata(self, track: Any) -> None:
        from .dialogs import MetadataDialog

        MetadataDialog(self.winfo_toplevel(), track.title, track.artist,
                       lambda title, artist: self.ctrl.update_metadata(track.content_id, title, artist))

    def _library_view(self) -> Any:
        self.ctrl._emit("navigate", "library")
        return getattr(self.winfo_toplevel(), "views", {}).get("library")

    def _compatible(self, track: Any) -> None:
        view = self._library_view()
        if view is not None:
            view.set_harmonic(track)

    def _show_in_library(self, track: Any) -> None:
        view = self._library_view()
        if view is not None:
            view.reveal(track.content_id)

    # ---------------------------------------------------------------- évènements
    def _on_player(self, kind: str, payload: Any) -> None:
        if not self.winfo_exists():
            return
        if kind == "state":
            self._refresh_state(payload)
        elif kind == "loaded":
            meta, duration = payload if isinstance(payload, tuple) else (payload, self.player.duration)
            self._show_meta(meta, float(duration or 0))
        elif kind == "error":
            self.ctrl.message("error", str(payload))
        elif kind == "ended":
            self.seek.set(0)
            self.wave.set_ratio(0)
            self.elapsed.configure(text="0:00")

    def _refresh_state(self, state: str) -> None:
        playing = state == PLAYING
        self.play_btn.configure(image=ctk_icon("pause" if playing else "play", 18, theme.ON_ACCENT))
        if state == LOADING and self.player.meta:
            self._show_meta(self.player.meta, 0.0)
            self.artist.configure(text=f"{self.player.meta.artist}  ·  {t('player.loading')}")
        elif state == STOPPED:
            self.seek.set(0)
            self.wave.set_ratio(0)
            self.elapsed.configure(text="0:00")
            if self.player.meta:
                self.artist.configure(text=self.player.meta.artist)
        self._refresh_nav()

    def _show_meta(self, meta: NowPlaying, duration: float) -> None:
        self.title.configure(text=meta.title or t("player.untitled"))
        self.artist.configure(text=meta.artist or "")
        self.total.configure(text=format_duration(int(duration)))
        self._set_cover(self._cover_ref(meta))
        item = self.ctrl.current_item
        track = item.library_track if item is not None else None
        if track is not None and track.path and str(meta.path).replace("\\", "/").endswith(track.path.lstrip("/")):
            self._show_track_info(track)
        else:
            self._show_track_info(None)

    def _show_track_info(self, track: Any) -> None:
        self.key_pill.pack_forget()
        self.bpm.pack_forget()
        code = track.camelot if track is not None else None
        if code:
            self.key_pill.set(code)
            self.key_pill.pack(side="left", padx=(0, 6))
        if track is not None and track.bpm:
            self.bpm.configure(text=f"{track.bpm:.1f} BPM".replace(".0 ", " "))
            self.bpm.pack(side="left")
        self._wave_token += 1
        token = self._wave_token
        if track is None or not track.analysis_path:
            self._use_wave(False)
            return

        def show(data: list) -> None:
            if token != self._wave_token or not self.winfo_exists():
                return
            self.wave.set_data(data)
            self._use_wave(bool(data))

        self.ctrl.load_overview(track, show)

    def _use_wave(self, on: bool) -> None:
        if on:
            self.seek.grid_remove()
            self.wave.grid(row=0, column=1, sticky="ew", padx=6)
        else:
            self.wave.grid_remove()
            self.seek.grid()

    @staticmethod
    def _cover_ref(meta: NowPlaying) -> Optional[CoverRef]:
        if meta.cover_url:
            return url_cover(meta.cover_url)
        return file_cover(Path(meta.cover_path) if meta.cover_path else None, Path(meta.path), f"bar:{meta.path}")

    def _set_cover(self, ref: Optional[CoverRef]) -> None:
        """Pochette chargée/décodée en arrière-plan ; un jeton ignore les réponses périmées."""
        self._cover_token += 1
        token = self._cover_token
        self.cover.configure(image=self._ph)

        def show(img: Any) -> None:
            if token != self._cover_token or not self.winfo_exists():
                return
            self._img_ref = _ctk_image(img, COVER_PX)
            self.cover.configure(image=self._img_ref)

        self.loader.load_pil(ref, COVER_PX * 2, show)

    def on_scale(self) -> None:
        self.wave.configure(height=theme.tkpx(WAVE_H))
        self.wave.draw()

    # ---------------------------------------------------------------- timer
    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        try:
            self.player.poll()
            if self.player.state in (PLAYING, PAUSED) and self.player.duration > 0 and not self._dragging:
                pos = min(self.player.position(), self.player.duration)
                self.seek.set(pos / self.player.duration)
                self.wave.set_ratio(pos / self.player.duration)
                self.elapsed.configure(text=format_duration(int(pos)))
        finally:
            self.after(250, self._tick)
