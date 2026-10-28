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
# 1.3.0-rc.5 (C39) : miniaudio prend cette valeur comme taille d'UN paquet et en garde 3 d'avance par
# défaut : 200 ms donnaient ~600 ms entre ce qui est envoyé et ce qu'on entend (son « en retard » sous
# Windows, retour en arrière ou saut de cue entendus tard). Hors macOS : 2 paquets de 40 ms (~80 ms) ;
# macOS garde 200 ms (testé sans souci). La position n'utilise plus ce chiffre : le retard réel est mesuré.
BUFFER_MS = 200 if sys.platform == "darwin" else 40
PERIODS = 0 if sys.platform == "darwin" else 2      # 0 = valeur de miniaudio (3)
_NATIVE = {".mp3", ".wav", ".flac", ".ogg"}  # décodés par miniaudio

STOPPED, LOADING, PLAYING, PAUSED = "stopped", "loading", "playing", "paused"
# 1.3.0-rc.7 (C39, LEC-2) : un saut pendant la lecture rouvrait la carte son ET relançait le décodage
# (FFmpeg pour les m4a : un nouveau processus) : on entendait un trou avant le nouvel endroit. Le son
# en cours est maintenant gardé décodé en mémoire (jusqu'à 12 min, ~10 Mo par minute) : un saut y est
# immédiat ; et hors macOS la réserve de la carte son (~80 ms) est assez courte pour ne plus l'arrêter.
MEMORY_MAX_S = 12 * 60
SEEK_KEEPS_DEVICE = BUFFER_MS * max(PERIODS, 3) <= 120


@dataclass(frozen=True)
class NowPlaying:
    title: str
    artist: str
    path: str                              # fichier audio
    cover_url: Optional[str] = None        # vignette distante (préécoute)
    cover_path: Optional[str] = None       # image locale (pochette Rekordbox de la clé)


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class _PcmCache:
    """Son entier décodé en mémoire, en arrière-plan (même décodeur que la lecture)."""

    def __init__(self, path: Path, ffmpeg: Optional[str]) -> None:
        self.path, self.ffmpeg = path, ffmpeg
        self.data = bytearray()
        self.lock = threading.Lock()
        self.complete = False              # tout le son est là
        self._stop = False
        threading.Thread(target=self._run, daemon=True, name="djsync-audio-cache").start()

    def _add(self, chunk: bytes) -> bool:
        with self.lock:
            self.data += chunk
            too_long = len(self.data) > MEMORY_MAX_S * RATE * FRAME_BYTES
        return not (self._stop or too_long)

    def _run(self) -> None:
        try:
            if self.path.suffix.lower() in _NATIVE:
                import miniaudio

                for chunk in miniaudio.stream_file(str(self.path), miniaudio.SampleFormat.SIGNED16, CHANNELS, RATE,
                                                   frames_to_read=16384):
                    if not self._add(chunk.tobytes()):
                        return
            else:
                if not self.ffmpeg:
                    return
                proc = subprocess.Popen([self.ffmpeg, "-v", "error", "-nostdin", "-i", str(self.path), "-map", "0:a:0",
                                         "-vn", "-f", "s16le", "-acodec", "pcm_s16le", "-ar", str(RATE), "-ac",
                                         str(CHANNELS), "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL, creationflags=_no_window())
                try:
                    while True:
                        data = proc.stdout.read(65536)
                        if not data:
                            break
                        if not self._add(data):
                            return
                    if proc.wait() != 0:
                        return
                finally:
                    if proc.poll() is None:
                        proc.kill()
            self.complete = True
        except Exception as exc:  # noqa: BLE001 - simple accélération : la lecture normale reste
            log.info("Track not kept in memory (%s): %s", self.path.name, exc)

    def stop(self) -> None:
        self._stop = True


class _MemStream:
    """Lecture depuis le son décodé en mémoire (même interface que _Stream)."""

    def __init__(self, cache: _PcmCache, start: float) -> None:
        self.cache, self.start = cache, start
        self.pos = int(start * RATE) * FRAME_BYTES
        self.error: Optional[str] = None
        self.done = True
        self.buf = True                    # « il reste des données » tant que pos < fin
        self.started = threading.Event()
        self.started.set()

    def read(self, nbytes: int) -> bytes:
        with self.cache.lock:
            out = bytes(self.cache.data[self.pos:self.pos + nbytes])
        self.pos += len(out)
        return out

    @property
    def exhausted(self) -> bool:
        return self.pos >= len(self.cache.data)

    def close(self) -> None:
        pass


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
        # 1.3.0-rc.5 (C39) : retard réel de la carte son, mesuré : avance maximale de ce qui a été
        # demandé par la carte sur le temps écoulé depuis son premier appel (= ce qu'elle garde en réserve)
        self._dev_t0: Optional[float] = None
        self._dev_frames = 0
        self._dev_lead = 0.0
        self._cache: Optional[_PcmCache] = None     # rc.7 (C39) : son en cours, décodé en mémoire

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
        now = time.monotonic()
        if self._dev_t0 is None:
            self._dev_t0 = now
        self._dev_frames += n
        self._dev_lead = max(self._dev_lead, self._dev_frames / RATE - (now - self._dev_t0))
        with self._lock:
            stream = self._stream
            if stream is None or self._paused:
                return silence
            data = stream.read(n * FRAME_BYTES)
            data = data[: len(data) - len(data) % FRAME_BYTES]
            self._frames += len(data) // FRAME_BYTES
            if data:
                self._cb_time, self._cb_frames, self._cb_period = now, self._frames, n / RATE
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
                                              buffersize_msec=BUFFER_MS, callback_periods=PERIODS,
                                              backends=backends, app_name="DJSync")
            self._dev_t0, self._dev_frames, self._dev_lead = None, 0, 0.0
            pump = self._pump()
            next(pump)
            device.start(pump)
        except Exception as exc:  # noqa: BLE001 - pas de carte son, pilote absent...
            self._emit("error", f"Audio output unavailable: {exc}")
            return False
        self._device = device
        return True

    def _open(self, start: float):
        assert self._path is not None
        cache = self._cache
        if cache is not None and cache.complete and cache.path == self._path:
            return _MemStream(cache, start)            # rc.7 (C39) : saut immédiat
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
        if self._cache is not None and self._cache.path != path:     # rc.7 : mémoire libérée
            self._cache.stop()
            self._cache = None
        self._gen += 1
        self.meta = meta
        self._path = path
        self._set_state(LOADING)
        threading.Thread(target=self._prepare, args=(self._gen, path, meta), daemon=True).start()

    def announce(self, meta: NowPlaying) -> None:
        """1.3.2 (C74) : le son choisi s'affiche TOUT DE SUITE dans le lecteur (titre, pochette, animation de
        chargement) pendant qu'on le récupère (préécoute d'un résultat de recherche) ; `play` suivra."""
        self.stop(keep_meta=False)
        self._gen += 1
        self.meta = meta
        self._set_state(LOADING)

    def _start(self, gen: int, stream: _Stream, meta: NowPlaying, duration: float) -> None:
        if gen != self._gen or not self._ensure_device():
            stream.close()
            if gen == self._gen:
                self._set_state(STOPPED)
            return
        self._paused = False
        self._swap(stream)
        self.duration = duration
        if self._cache is not None and self._cache.path == self._path and not self._cache._stop:
            pass                                       # même son rejoué : déjà en mémoire (ou en cours)
        elif 0 < duration <= MEMORY_MAX_S and self._path is not None:
            if self._cache is not None:
                self._cache.stop()
            self._cache = _PcmCache(self._path, self._ffmpeg())
        else:
            self._cache = None
        self._emit("loaded", (meta, duration))
        self._set_state(PLAYING)

    def toggle_pause(self) -> None:
        """1.3.0-rc.4 (C39) : la pause coupe la sortie TOUT DE SUITE. Avant, on cessait seulement d'envoyer :
        la réserve de la carte son (et celle d'un casque Bluetooth, parfois près d'une seconde) continuait
        de jouer. On arrête la carte son (sa réserve est jetée) et on reprendra exactement à ce qu'on a
        entendu, flux rouvert à cet endroit."""
        if self.state == PLAYING:
            heard = self.position()
            with self._lock:
                self._paused = True
                self._cb_time = None
            self._halt_device()
            if self._path is not None and self.duration > 0:
                heard = max(0.0, min(heard, self.duration))
                self._swap(self._open(heard), int(round(heard * RATE)))
            else:
                with self._lock:
                    self._base = self._frames
            self._set_state(PAUSED)
        elif self.state == PAUSED:
            self._paused = False
            if not self._ensure_device():
                return
            self._set_state(PLAYING)

    def _halt_device(self) -> None:
        """Arrête la carte son (sa réserve est jetée) ; `_ensure_device` la relance."""
        device, self._device = self._device, None
        if device is not None:
            try:
                device.stop()
                device.close()
            except Exception as exc:  # noqa: BLE001 - pilote capricieux : la lecture reste possible
                log.info("Audio device stop: %s", exc)

    def stop(self, keep_meta: bool = True) -> None:
        if self.state == PLAYING:
            self._halt_device()                  # rc.4 (C39) : silence tout de suite
        self._gen += 1
        self._swap(None)
        if not keep_meta:
            return
        if self.state != STOPPED:
            self._set_state(STOPPED)

    def seek(self, seconds: float, flush: bool = True) -> None:
        if self.state not in (PLAYING, PAUSED) or self.duration <= 0 or self._path is None:
            return
        seconds = max(0.0, min(seconds, max(0.0, self.duration - 0.5)))
        if flush and self.state == PLAYING and self._device is not None and not SEEK_KEEPS_DEVICE:
            # 1.3.0-rc.5 (C39) : la réserve de la carte son jouerait encore l'ancien endroit ; on la
            # vide pour entendre le nouveau tout de suite (clic sur la forme d'onde, hot cue)
            self._halt_device()
            self._swap(self._open(seconds), int(seconds * RATE))
            with self._lock:
                self._prev = None
            self._ensure_device()
            return
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
            return base / RATE
        latency = max(0.0, self.output_latency() + self.latency_offset_ms / 1000.0)
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

    def output_latency(self) -> float:
        """Retard (s) entre l'envoi à la carte son et ce qu'on entend : mesuré (rc.5), sinon la réserve
        prévue (taille d'un paquet × nombre de paquets)."""
        if self._dev_lead > 0.0:
            return self._dev_lead
        return BUFFER_MS / 1000.0 * (PERIODS or 3)

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
