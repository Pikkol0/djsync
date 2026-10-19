"""Barre de lecture fixée en bas : pochette, titre/artiste, Play-Pause/Stop, progression, volume."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from ..audio.covers import icon, placeholder
from ..audio.player import LOADING, PAUSED, PLAYING, STOPPED, NowPlaying
from ..models import format_duration
from . import theme
from .covers import CoverLoader, CoverRef, file_cover, url_cover

BAR_HEIGHT = 88
COVER_PX = 60


def _ctk_image(img: Any, size: int) -> ctk.CTkImage:
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


class PlayerBar(ctk.CTkFrame):
    def __init__(self, parent: Any, controller: Any, loader: CoverLoader) -> None:
        super().__init__(parent, fg_color=theme.SURFACE, corner_radius=0, height=theme.px(BAR_HEIGHT))
        self.ctrl, self.loader = controller, loader
        self.player = controller.player
        self._dragging = False
        self._cover_token = 0
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=3, uniform="bar")
        self.grid_columnconfigure(1, weight=4, uniform="bar")
        self.grid_columnconfigure(2, weight=3, uniform="bar")
        self.grid_rowconfigure(0, weight=1)

        cover_px = theme.px(COVER_PX)
        self._ph = _ctk_image(placeholder(cover_px), cover_px)
        self._img_ref: Any = self._ph

        # ---- gauche : pochette + titre
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(theme.px(14), 8))
        left.grid_columnconfigure(1, weight=1)
        left.grid_rowconfigure(0, weight=1)
        self.cover = ctk.CTkLabel(left, text="", image=self._ph, width=cover_px, height=cover_px)
        self.cover.grid(row=0, column=0, padx=(0, 12))
        text = ctk.CTkFrame(left, fg_color="transparent")
        text.grid(row=0, column=1, sticky="w")
        self.title = theme.label(text, "Aucune lecture", 13, theme.TEXT, "bold", anchor="w")
        self.title.pack(anchor="w")
        self.artist = theme.label(text, "Double-clic sur un son pour l'écouter", 11, theme.DIM, anchor="w")
        self.artist.pack(anchor="w")

        # ---- centre : boutons + progression
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="nsew")
        mid.grid_columnconfigure(0, weight=1)
        buttons = ctk.CTkFrame(mid, fg_color="transparent")
        buttons.grid(row=0, column=0, pady=(theme.px(10), 0))
        isz = theme.px(18)
        self._icons = {
            "play": _ctk_image(icon("play", isz * 2, theme.ON_ACCENT), isz),
            "pause": _ctk_image(icon("pause", isz * 2, theme.ON_ACCENT), isz),
            "stop": _ctk_image(icon("stop", isz * 2, theme.TEXT), isz),
            "volume": _ctk_image(icon("volume", isz * 2, theme.DIM), isz),
        }
        self.stop_btn = ctk.CTkButton(
            buttons, text="", image=self._icons["stop"], width=theme.px(34), height=theme.px(34), corner_radius=17,
            fg_color="transparent", hover_color=theme.ELEV, border_width=1, border_color=theme.BORDER,
            command=self.player.stop,
        )
        self.stop_btn.pack(side="left", padx=6)
        self.play_btn = ctk.CTkButton(
            buttons, text="", image=self._icons["play"], width=theme.px(40), height=theme.px(40), corner_radius=20,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, command=self._play_pause,
        )
        self.play_btn.pack(side="left", padx=6)

        prog = ctk.CTkFrame(mid, fg_color="transparent")
        prog.grid(row=1, column=0, sticky="ew", padx=theme.px(8))
        prog.grid_columnconfigure(1, weight=1)
        self.elapsed = theme.label(prog, "0:00", 10, theme.DIM, width=theme.px(40))
        self.elapsed.grid(row=0, column=0)
        self.seek = theme.slider(prog, from_=0, to=1, number_of_steps=1000)
        self.seek.set(0)
        self.seek.grid(row=0, column=1, sticky="ew", padx=6)
        self.total = theme.label(prog, "0:00", 10, theme.DIM, width=theme.px(40))
        self.total.grid(row=0, column=2)
        self.seek.bind("<ButtonPress-1>", lambda _e: setattr(self, "_dragging", True), add="+")
        self.seek.bind("<ButtonRelease-1>", self._seek_release, add="+")
        self.seek.configure(command=self._seek_moved)

        # ---- droite : volume
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=(8, theme.px(18)))
        ctk.CTkLabel(right, text="", image=self._icons["volume"]).pack(side="left", padx=(0, 8))
        self.volume = theme.slider(right, from_=0, to=1, width=theme.px(110), command=self._volume_changed)
        self.volume.set(self.player.volume)
        self.volume.pack(side="left")

        controller.on("player", self._on_player)
        self._tick()

    # ---------------------------------------------------------------- actions
    def _play_pause(self) -> None:
        if self.player.state in (PLAYING, PAUSED):
            self.player.toggle_pause()
        elif self.player.state == STOPPED and self.player.meta is not None:
            meta = self.player.meta
            self.player.play(meta.path, meta)  # rejoue le dernier son

    def _volume_changed(self, value: float) -> None:
        self.player.set_volume(float(value))

    def _seek_moved(self, value: float) -> None:
        if self._dragging and self.player.duration > 0:
            self.elapsed.configure(text=format_duration(int(float(value) * self.player.duration)))

    def _seek_release(self, _e: Any) -> None:
        if self._dragging and self.player.duration > 0:
            self.player.seek(float(self.seek.get()) * self.player.duration)
        self._dragging = False

    # ---------------------------------------------------------------- évènements
    def _on_player(self, kind: str, payload: Any) -> None:
        if kind == "state":
            self._refresh_state(payload)
        elif kind == "loaded":
            meta, duration = payload if isinstance(payload, tuple) else (payload, self.player.duration)
            self._show_meta(meta, float(duration or 0))
        elif kind == "error":
            self.ctrl.message("error", str(payload))
        elif kind == "ended":
            self.seek.set(0)
            self.elapsed.configure(text="0:00")

    def _refresh_state(self, state: str) -> None:
        playing = state == PLAYING
        self.play_btn.configure(image=self._icons["pause" if playing else "play"])
        if state == LOADING and self.player.meta:
            self._show_meta(self.player.meta, 0.0)
            self.artist.configure(text=f"{self.player.meta.artist}  ·  chargement…")
        elif state == STOPPED:
            self.seek.set(0)
            self.elapsed.configure(text="0:00")
            if self.player.meta:
                self.artist.configure(text=self.player.meta.artist)

    def _show_meta(self, meta: NowPlaying, duration: float) -> None:
        self.title.configure(text=meta.title or "Sans titre")
        self.artist.configure(text=meta.artist or "")
        self.total.configure(text=format_duration(int(duration)))
        self._set_cover(self._cover_ref(meta))

    @staticmethod
    def _cover_ref(meta: NowPlaying) -> Optional[CoverRef]:
        if meta.cover_url:
            return url_cover(meta.cover_url)
        return file_cover(Path(meta.cover_path) if meta.cover_path else None, Path(meta.path), f"bar:{meta.path}")

    def _set_cover(self, ref: Optional[CoverRef]) -> None:
        """Pochette chargée/décodée en arrière-plan ; un jeton ignore les réponses périmées."""
        self._cover_token += 1
        token = self._cover_token
        size = theme.px(COVER_PX)
        self.cover.configure(image=self._ph)

        def show(img: Any) -> None:
            if token != self._cover_token or not self.winfo_exists():
                return
            self._img_ref = _ctk_image(img, size)
            self.cover.configure(image=self._img_ref)

        self.loader.load_pil(ref, size * 2, show)

    # ---------------------------------------------------------------- timer
    def _tick(self) -> None:
        try:
            self.player.poll()
            if self.player.state in (PLAYING, PAUSED) and self.player.duration > 0 and not self._dragging:
                pos = min(self.player.position(), self.player.duration)
                self.seek.set(pos / self.player.duration)
                self.elapsed.configure(text=format_duration(int(pos)))
        finally:
            self.after(250, self._tick)
