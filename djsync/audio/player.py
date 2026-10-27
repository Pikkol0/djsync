"""Lecteur audio minimal : Lecture / Pause / Stop / Seek / Volume, via miniaudio (~1 Mo, sans SDL).

Principe : UN périphérique de sortie miniaudio, ouvert au premier son, qui réclame des trames à un
générateur Python (thread audio de miniaudio). Ces trames sortent d'un tampon rempli d'avance
(≈ 2 s) par un thread « lecteur de flux » :
  * MP3 / WAV / FLAC / OGG : décodés par miniaudio lui-même (stream_file, seek natif) ;
  * m4a/AAC, AIFF… : FFmpeg décode en PCM vers un tube (`-ss` pour le seek), sans fichier temporaire.

Rien n'est jamais décodé en entier en mémoire (un mix d'1 h ne coûte que le tampon) et le thread
audio ne bloque jamais : si le tampon est vide (disque USB lent), il joue du silence sans avancer.
`post` renvoie un appel dans le thread de l'interface (UiDispatcher.post) ; tous les événements
(`on_event`) y sont émis.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

RATE = 44100
CHANNELS = 2
FRAME_BYTES = 2 * CHANNELS                 # s16 stéréo
_AHEAD = RATE * 2                          # trames décodées d'avance
# 1.2.3 : réserve de la carte son. À 60 ms, ouvrir une fenêtre (interface occupée, le fil audio
# Python attend) la vidait : macOS rejouait alors le dernier bloc (« rollback » entendu en préécoute).
BUFFER_MS = 200
_NATIVE = {".mp3", ".wav", ".flac", ".ogg"}  # décodés par miniaudio

STOPPED, LOADING, PLAYING, PAUSED = "stopped", "loading", "playing", "paused"


@dataclass(frozen=True)
class NowPlaying:
    title: str
    artist: str
    path: str                              # fichier audio
    cover_url: Optional[str] = None        # vignette distante (préécoute)
    cover_path: Optional[str] = None       # image locale (pochette Rekordbox de la clé)


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class _Stream:
    """Flux décodé d'un fichier à partir de `start` secondes, lu par un thread vers un tampon."""

    def __init__(self, path: Path, start: float, ffmpeg: Optional[str]) -> None:
        self.path, self.start, self.ffmpeg = path, start, ffmpeg
        self.buf: deque = deque()
        self.buffered = 0                  # octets dans buf
        self.done = False                  # plus rien à lire
        self.error: Optional[str] = None
        self.started = threading.Event()   # première donnée (ou erreur) disponible
        self._cv = threading.Condition()
        self._closed = False
        self._proc: Optional[subprocess.Popen] = None
        threading.Thread(target=self._run, daemon=True, name="djsync-audio-reader").start()

    # ---------------------------------------------------------------- thread lecteur
    def _push(self, data: bytes) -> bool:
        with self._cv:
            while self.buffered >= _AHEAD * FRAME_BYTES and not self._closed:
                self._cv.wait(0.2)
            if self._closed:
                return False
            if data:
                self.buf.append(data)
                self.buffered += len(data)
        self.started.set()
        return True

    def _run(self) -> None:
        try:
            if self.path.suffix.lower() in _NATIVE:
                self._run_native()
            else:
                self._run_ffmpeg()
        except Exception as exc:  # noqa: BLE001 - signalé à l'interface
            self.error = str(exc) or exc.__class__.__name__
        finally:
            self.done = True
            self.started.set()

    def _run_native(self) -> None:
        import miniaudio

        gen = miniaudio.stream_file(str(self.path), miniaudio.SampleFormat.SIGNED16, CHANNELS, RATE,
                                    frames_to_read=4096, seek_frame=int(self.start * RATE))
        for chunk in gen:
            if not self._push(chunk.tobytes()):
                return

    def _run_ffmpeg(self) -> None:
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg is required to play this format (set its folder in Settings).")
        cmd = [self.ffmpeg, "-v", "error", "-nostdin"]
        if self.start > 0:
            cmd += ["-ss", f"{self.start:.3f}"]
        cmd += ["-i", str(self.path), "-map", "0:a:0", "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
                "-ar", str(RATE), "-ac", str(CHANNELS), "-"]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      stdin=subprocess.DEVNULL, creationflags=_no_window())
        got = 0
        while True:
            data = self._proc.stdout.read(16384)
            if not data:
                break
            got += len(data)
            if not self._push(data):
                return
        err = self._proc.stderr.read().decode("utf-8", "replace").strip()
        if self._proc.wait() != 0 and not got:
            raise RuntimeError(f"Cannot decode: {err[-200:] or 'FFmpeg error'}")

    # ------------------------------------------------------------- thread audio
    def read(self, nbytes: int) -> bytes:
        out = bytearray()
        with self._cv:
            while self.buf and len(out) < nbytes:
                chunk = self.buf.popleft()
                take = nbytes - len(out)
                if len(chunk) > take:
                    self.buf.appendleft(chunk[take:])
                    chunk = chunk[:take]
                out += chunk
                self.buffered -= len(chunk)
            self._cv.notify_all()
        return bytes(out)

    @property
    def exhausted(self) -> bool:
        return self.done and not self.buf

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self.buf.clear()
            self._cv.notify_all()
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass


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
        self._volume = 0.8
        self._gen = 0                      # annule les chargements devenus obsolètes
        self._device = None
        self._lock = threading.Lock()
        self._stream: Optional[_Stream] = None
        self._path: Optional[Path] = None
        self._frames = 0                   # trames ENVOYÉES à la carte son depuis le début du morceau
        # 1.3.0-rc.3 (C39) : position « entendue », interpolée entre deux appels de la carte son
        self._cb_time: Optional[float] = None      # instant du dernier envoi
        self._cb_frames = 0                        # trames envoyées à cet instant
        self._cb_period = 0.0                      # durée du dernier paquet (s)
        self._base = 0                             # trames au dernier seek / pause : jamais en dessous
        self._prev: Optional[tuple] = None         # avant un seek : (instant, trames, paquet, envoyées) de l'ancien flux
        self.latency_offset_ms = 0                 # réglage : retard supplémentaire (Bluetooth…), en ms
        self._paused = False

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

    @staticmethod
    def probe_duration(path: str) -> float:
        try:
            import mutagen

            audio = mutagen.File(path)
            if audio and audio.info and audio.info.length:
                return float(audio.info.length)
        except Exception:  # noqa: BLE001
            pass
        try:
            import miniaudio

            return float(miniaudio.get_file_info(path).duration)
        except Exception:  # noqa: BLE001
            return 0.0

    # -------------------------------------------------------------- sortie audio
    def _pump(self):
        """Générateur appelé par le thread audio de miniaudio : renvoie `n` trames à chaque fois."""
        n = yield b""
        while True:
            n = yield self._fill(n)

    def _fill(self, n: int) -> bytes:
        silence = b"\0" * (n * FRAME_BYTES)
        with self._lock:
            stream = self._stream
            if stream is None or self._paused:
                return silence
            data = stream.read(n * FRAME_BYTES)
            data = data[: len(data) - len(data) % FRAME_BYTES]
            self._frames += len(data) // FRAME_BYTES
            if data:
                self._cb_time, self._cb_frames, self._cb_period = time.monotonic(), self._frames, n / RATE
        if not data:
            return silence
        if self._volume < 0.999:
            import numpy as np

            pcm = np.frombuffer(data, dtype="<i2").astype(np.float32) * (self._volume ** 2)
            data = pcm.astype("<i2").tobytes()
        return data + silence[len(data):]

    def _ensure_device(self) -> bool:
        if self._device is not None:
            return True
        try:
            import miniaudio

            backends = [miniaudio.Backend.NULL] if os.environ.get("DJSYNC_AUDIO_NULL") else None
            device = miniaudio.PlaybackDevice(miniaudio.SampleFormat.SIGNED16, CHANNELS, RATE,
                                              buffersize_msec=BUFFER_MS, backends=backends, app_name="DJSync")
            pump = self._pump()
            next(pump)
            device.start(pump)
        except Exception as exc:  # noqa: BLE001 - pas de carte son, pilote absent...
            self._emit("error", f"Audio output unavailable: {exc}")
            return False
        self._device = device
        return True

    def _open(self, start: float) -> _Stream:
        assert self._path is not None
        return _Stream(self._path, start, self._ffmpeg())

    def _swap(self, stream: Optional[_Stream], frames: int = 0) -> None:
        with self._lock:
            # seek en pleine lecture : la carte son joue encore la fin de l'ancien flux (sa réserve) ;
            # on garde de quoi afficher cette fin avant de passer au nouveau point
            playing = self._stream is not None and stream is not None and self._cb_time is not None and not self._paused
            self._prev = (self._cb_time, self._cb_frames, self._cb_period, self._frames) if playing else None
            old, self._stream, self._frames = self._stream, stream, frames
            self._base, self._cb_time = frames, None
        if old is not None:
            old.close()

    # ------------------------------------------------------------------- chargement
    def _prepare(self, gen: int, path: Path, meta: NowPlaying) -> None:
        """Thread : ouvre le flux, attend les premières trames et mesure la durée."""
        stream = _Stream(path, 0.0, self._ffmpeg())
        stream.started.wait(30)
        if stream.error and not stream.buf:
            stream.close()
            message = stream.error if stream.error.startswith(("FFmpeg", "Cannot")) else f"Cannot play: {stream.error}"
            self._post(lambda: self._failed(gen, message))
            return
        duration = self.probe_duration(str(path))
        self._post(lambda: self._start(gen, stream, meta, duration))

    def _failed(self, gen: int, message: str) -> None:
        if gen != self._gen:
            return
        self.state = STOPPED
        self._emit("error", message)
        self._emit("state", STOPPED)

    # ---------------------------------------------------------------- commandes (UI)
    def play(self, path: str | Path, meta: NowPlaying) -> None:
        """Charge puis lit. L'ouverture se fait en arrière-plan (état LOADING)."""
        path = Path(path)
        if not path.is_file():
            self._emit("missing", str(path))         # 1.3.0-rc.3 (B20) : message adapté par l'interface
            return
        self.stop(keep_meta=False)
        self._gen += 1
        self.meta = meta
        self._path = path
        self._set_state(LOADING)
        threading.Thread(target=self._prepare, args=(self._gen, path, meta), daemon=True).start()

    def _start(self, gen: int, stream: _Stream, meta: NowPlaying, duration: float) -> None:
        if gen != self._gen or not self._ensure_device():
            stream.close()
            if gen == self._gen:
                self._set_state(STOPPED)
            return
        self._paused = False
        self._swap(stream)
        self.duration = duration
        self._emit("loaded", (meta, duration))
        self._set_state(PLAYING)

    def toggle_pause(self) -> None:
        if self.state == PLAYING:
            with self._lock:
                self._paused = True
                # ce qui est déjà dans la carte son finit d'être joué : position = tout ce qui a été envoyé
                self._base, self._cb_time = self._frames, None
            self._set_state(PAUSED)
        elif self.state == PAUSED:
            self._paused = False
            self._set_state(PLAYING)

    def stop(self, keep_meta: bool = True) -> None:
        self._gen += 1
        self._swap(None)
        if not keep_meta:
            return
        if self.state != STOPPED:
            self._set_state(STOPPED)

    def seek(self, seconds: float) -> None:
        if self.state not in (PLAYING, PAUSED) or self.duration <= 0 or self._path is None:
            return
        seconds = max(0.0, min(seconds, max(0.0, self.duration - 0.5)))
        self._swap(self._open(seconds), int(seconds * RATE))

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))

    @property
    def volume(self) -> float:
        return self._volume

    def position(self) -> float:
        """Position ENTENDUE (s). 1.3.0-rc.3 (C39) : avant, nombre de trames envoyées à la carte son,
        qui avançait par paquets et en avance d'environ la taille de sa réserve (jusqu'à 200 ms). On
        part du dernier envoi, on retire le retard de la carte son et on avance avec l'horloge (au plus
        d'un paquet, pour ne jamais dépasser ce qui a été envoyé) ; jamais en dessous du dernier seek."""
        if self.state not in (PLAYING, PAUSED):
            return 0.0
        with self._lock:
            frames, cb_time, cb_frames, period, base = (self._frames, self._cb_time, self._cb_frames,
                                                        self._cb_period, self._base)
            paused, prev = self._paused, self._prev
        if paused:
            return max(base, frames) / RATE
        latency = BUFFER_MS / 1000.0 + self.latency_offset_ms / 1000.0
        now = time.monotonic()
        if cb_time is not None:
            elapsed = min(max(0.0, now - cb_time), max(period, 0.001) * 1.5)
            heard = cb_frames / RATE - latency + elapsed
            if heard >= base / RATE:
                return min(heard, frames / RATE)
        if prev is not None:                     # la fin de l'ancien flux s'entend encore
            p_time, p_frames, p_period, p_sent = prev
            old = p_frames / RATE - latency + min(max(0.0, now - p_time), latency + max(p_period, 0.001))
            if old < p_sent / RATE:
                return old
        return base / RATE

    def sent_position(self) -> float:
        """Position de ce qui a été ENVOYÉ à la carte son (en avance sur ce qu'on entend) : pour décider
        d'un saut (fin de boucle) assez tôt pour qu'il soit entendu au bon moment."""
        if self.state not in (PLAYING, PAUSED):
            return 0.0
        return self._frames / RATE

    def poll(self) -> None:
        """À appeler régulièrement (timer UI) : détecte la fin du morceau (ou une erreur de flux)."""
        stream = self._stream
        if self.state == PLAYING and stream is not None and stream.exhausted:
            played = self._frames
            self._swap(None)
            self.state = STOPPED
            if stream.error and played == 0:
                self._emit("error", stream.error)
            self._emit("ended", None)
            self._emit("state", STOPPED)

    def close(self) -> None:
        self._gen += 1
        self._swap(None)
        if self._device is not None:
            try:
                self._device.close()
            except Exception:  # noqa: BLE001
                pass
            self._device = None
