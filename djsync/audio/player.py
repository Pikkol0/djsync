"""Lecteur audio minimal : Lecture / Pause / Stop / Seek / Volume, via pygame.mixer.music.

pygame lit MP3 et WAV mais PAS le m4a/AAC (ni FLAC/AIFF de façon fiable). Ces formats sont donc
décodés en WAV temporaire par FFmpeg DANS UN THREAD (l'interface ne se fige jamais), puis lus.
Les WAV décodés sont conservés dans un cache temporaire (4 derniers), supprimé à la fermeture.

Toutes les opérations `pygame.mixer` se font dans le thread de l'interface : `post` est la
fonction qui y renvoie un appel (UiDispatcher.post).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

# lus directement par pygame ; tout le reste passe par FFmpeg
_DIRECT = {".mp3", ".wav", ".ogg"}
_CACHE_KEEP = 4

STOPPED, LOADING, PLAYING, PAUSED = "stopped", "loading", "playing", "paused"


@dataclass(frozen=True)
class NowPlaying:
    title: str
    artist: str
    path: str                              # fichier audio
    cover_url: Optional[str] = None        # vignette distante (préécoute)
    cover_path: Optional[str] = None       # image locale (pochette Rekordbox de la clé)


class AudioPlayer:
    def __init__(
        self,
        post: Callable[[Callable[[], None]], None],
        on_event: Optional[Callable[[str, object], None]] = None,
        ffmpeg_location: Optional[str] = None,
    ) -> None:
        """on_event(kind, payload) est appelé dans le thread UI :
        "state" (str) · "loaded" (NowPlaying, durée s) · "error" (message) · "ended" (None)."""
        self._post = post
        self._on_event = on_event or (lambda *_: None)
        self.ffmpeg_location = ffmpeg_location or None

        self.state = STOPPED
        self.meta: Optional[NowPlaying] = None
        self.duration = 0.0
        self._offset = 0.0
        self._volume = 0.8
        self._gen = 0                      # annule les décodages devenus obsolètes
        self._mixer_ready = False
        self._tmp: Optional[Path] = None

    # ------------------------------------------------------------------ utilitaires
    def _emit(self, kind: str, payload: object = None) -> None:
        try:
            self._on_event(kind, payload)
        except Exception:  # noqa: BLE001 - un souci d'affichage ne doit jamais casser la lecture
            log.exception("Player event handler")

    def _set_state(self, state: str) -> None:
        self.state = state
        self._emit("state", state)

    def _ffmpeg(self) -> Optional[str]:
        if self.ffmpeg_location:
            for name in ("ffmpeg.exe", "ffmpeg"):
                cand = Path(self.ffmpeg_location) / name
                if cand.is_file():
                    return str(cand)
        return shutil.which("ffmpeg")

    def _cache_dir(self) -> Path:
        if self._tmp is None:
            self._tmp = Path(tempfile.mkdtemp(prefix="djsync_play_"))
        return self._tmp

    def _init_mixer(self) -> bool:
        if self._mixer_ready:
            return True
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame

            pygame.mixer.init(frequency=44100)
        except Exception as exc:  # noqa: BLE001 - pas de carte son, pilote absent...
            self._emit("error", f"Sortie audio indisponible : {exc}")
            return False
        self._mixer_ready = True
        return True

    @staticmethod
    def probe_duration(path: str) -> float:
        try:
            import mutagen

            audio = mutagen.File(path)
            return float(audio.info.length) if audio and audio.info else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    # --------------------------------------------------------------------- décodage
    def _decode(self, src: Path) -> Path:
        """WAV décodé (en cache). Appelé dans un thread d'arrière-plan."""
        key = hashlib.sha1(f"{src}|{src.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        out = self._cache_dir() / f"{key}.wav"
        if out.exists():
            return out
        ffmpeg = self._ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg is required to play this format (set its folder in Settings).")
        cmd = [ffmpeg, "-v", "error", "-y", "-i", str(src), "-vn",
               "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", str(out)]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # pas de fenêtre noire sous Windows
        )
        if proc.returncode != 0 or not out.exists():
            out.unlink(missing_ok=True)
            raise RuntimeError(f"Cannot decode: {proc.stderr.strip()[-200:] or 'FFmpeg error'}")
        old = sorted(self._cache_dir().glob("*.wav"), key=lambda p: p.stat().st_mtime)[:-_CACHE_KEEP]
        for f in old:
            if f != out:
                f.unlink(missing_ok=True)
        return out

    def _prepare(self, gen: int, path: Path, meta: NowPlaying) -> None:
        """Thread : décode si besoin, mesure la durée, puis renvoie vers le thread UI."""
        try:
            playable = path if path.suffix.lower() in _DIRECT else self._decode(path)
            duration = self.probe_duration(str(path)) or self.probe_duration(str(playable))
        except Exception as exc:  # noqa: BLE001
            message = str(exc) if isinstance(exc, RuntimeError) else f"Cannot play: {exc}"
            self._post(lambda: self._failed(gen, message))
            return
        self._post(lambda: self._start(gen, playable, meta, duration))

    def _failed(self, gen: int, message: str) -> None:
        if gen != self._gen:
            return
        self.state = STOPPED
        self._emit("error", message)
        self._emit("state", STOPPED)

    # ---------------------------------------------------------------- commandes (UI)
    def play(self, path: str | Path, meta: NowPlaying) -> None:
        """Charge puis lit. Le décodage éventuel se fait en arrière-plan (état LOADING)."""
        path = Path(path)
        if not path.is_file():
            self._emit("error", f"File not found: {path.name} (drive unplugged?)")
            return
        self.stop(keep_meta=False)
        self._gen += 1
        self.meta = meta
        self._offset = 0.0
        self._set_state(LOADING)
        threading.Thread(target=self._prepare, args=(self._gen, path, meta), daemon=True).start()

    def _start(self, gen: int, playable: Path, meta: NowPlaying, duration: float) -> None:
        if gen != self._gen or not self._init_mixer():
            if gen == self._gen:
                self._set_state(STOPPED)
            return
        import pygame

        try:
            pygame.mixer.music.load(str(playable))
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
        except Exception as exc:  # noqa: BLE001
            self.state = STOPPED
            self._emit("error", f"Cannot play: {exc}")
            self._emit("state", STOPPED)
            return
        self.duration = duration
        self._offset = 0.0
        self._emit("loaded", (meta, duration))
        self._set_state(PLAYING)

    def toggle_pause(self) -> None:
        if not self._mixer_ready:
            return
        import pygame

        if self.state == PLAYING:
            pygame.mixer.music.pause()
            self._set_state(PAUSED)
        elif self.state == PAUSED:
            pygame.mixer.music.unpause()
            self._set_state(PLAYING)

    def stop(self, keep_meta: bool = True) -> None:
        self._gen += 1
        if self._mixer_ready:
            import pygame

            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except Exception:  # noqa: BLE001 - ancienne version de pygame
                pass
        self._offset = 0.0
        if not keep_meta:
            return
        if self.state != STOPPED:
            self._set_state(STOPPED)

    def seek(self, seconds: float) -> None:
        if not self._mixer_ready or self.state not in (PLAYING, PAUSED) or self.duration <= 0:
            return
        import pygame

        seconds = max(0.0, min(seconds, max(0.0, self.duration - 0.5)))
        was_paused = self.state == PAUSED
        try:
            pygame.mixer.music.play(start=seconds)  # get_pos() repart de 0 : on garde le décalage
            self._offset = seconds
            if was_paused:
                pygame.mixer.music.pause()
        except Exception as exc:  # noqa: BLE001 - format non « seekable »
            log.warning("Seek failed: %s", exc)

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._mixer_ready:
            import pygame

            pygame.mixer.music.set_volume(self._volume)

    @property
    def volume(self) -> float:
        return self._volume

    def position(self) -> float:
        if not self._mixer_ready or self.state not in (PLAYING, PAUSED):
            return 0.0
        import pygame

        return self._offset + max(0, pygame.mixer.music.get_pos()) / 1000.0

    def poll(self) -> None:
        """À appeler régulièrement (timer UI) : détecte la fin du morceau."""
        if self.state == PLAYING and self._mixer_ready:
            import pygame

            if not pygame.mixer.music.get_busy():
                self.state = STOPPED
                self._offset = 0.0
                self._emit("ended", None)
                self._emit("state", STOPPED)

    def close(self) -> None:
        self._gen += 1
        if self._mixer_ready:
            import pygame

            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:  # noqa: BLE001
                pass
            self._mixer_ready = False
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None
