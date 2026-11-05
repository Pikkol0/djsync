"""Soulseek (1.4.0, C10.2) : recherche « haute qualité » et téléchargement de fichiers sans perte.

Désactivé par défaut. À la première activation, un avertissement est montré et doit être accepté :
réseau pair-à-pair, adresse IP visible des autres utilisateurs (VPN fortement recommandé), et c'est à
l'utilisateur de vérifier qu'il a le droit de télécharger un fichier et que ce fichier est fiable
(faux FLAC, mauvais tags, fichier tronqué : la vraie qualité est vérifiée par le spectre, C46).

Technique : bibliothèque aioslsk (GPL-3.0 ou plus, comme DJSync), qui parle le protocole Soulseek
directement : pas de serveur ni de programme à installer. Elle tourne dans son propre fil avec sa boucle
asyncio ; ce module en expose une interface simple et BLOQUANTE (à appeler hors du fil de l'interface) :
`search`, `download`, `metrics`. Par défaut, DJSync ne partage rien.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

AUDIO_EXTS = ("flac", "wav", "aiff", "aif", "mp3", "m4a", "alac")
LOSSLESS_EXTS = ("flac", "wav", "aiff", "aif", "alac")
SEARCH_SECONDS = 8.0
HISTORY = 300                  # points du graphe des vitesses (1 par seconde : 5 minutes)


@dataclass
class SlskResult:
    username: str
    path: str                  # chemin chez le pair (séparateurs « \\ »)
    size: int
    ext: str
    bitrate: int = 0           # kbit/s annoncé (0 = inconnu ; souvent absent pour le sans perte)
    duration: int = 0          # s
    sample_rate: int = 0
    bit_depth: int = 0
    free_slot: bool = False
    speed: int = 0             # vitesse moyenne d'envoi du pair (octets/s)
    queue: int = 0             # file d'attente chez le pair

    @property
    def name(self) -> str:
        return re.split(r"[\\/]", self.path)[-1]

    @property
    def stem(self) -> str:
        return self.name.rsplit(".", 1)[0]

    @property
    def lossless(self) -> bool:
        return self.ext in LOSSLESS_EXTS

    @property
    def folder(self) -> str:
        parts = re.split(r"[\\/]", self.path)
        return parts[-2] if len(parts) > 1 else ""

    def quality_label(self) -> str:
        """« FLAC 24 bit · 96 kHz », « MP3 320 », « WAV »…"""
        parts = [self.ext.upper()]
        if self.lossless:
            if self.bit_depth:
                parts.append(f"{self.bit_depth} bit")
            if self.sample_rate:
                parts.append(f"{self.sample_rate / 1000:g} kHz")
        elif self.bitrate:
            parts.append(str(self.bitrate))
        return " · ".join(parts)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def relevance(result: SlskResult, query: str) -> float:
    """Part des mots de la recherche présents dans le nom du fichier (et son dossier), de 0 à 1."""
    words = [w for w in _plain(query).split() if len(w) > 1]
    if not words:
        return 0.0
    hay = " " + _plain(result.folder + " " + result.stem) + " "
    return sum(1 for w in words if f" {w} " in hay) / len(words)


def rank(results: Sequence[SlskResult], query: str, duration: int = 0, limit: int = 60) -> List[SlskResult]:
    """Fichiers audio pertinents, du meilleur au moins bon : pertinence, sans perte d'abord, puis 320,
    pair libre et rapide ; un fichier dont la durée s'écarte de plus de 15 s de celle attendue recule."""
    def score(r: SlskResult) -> Tuple:
        q = 3 if r.lossless else 2 if r.bitrate >= 300 else 1 if r.bitrate >= 192 else 0
        dur_ok = 1 if not duration or not r.duration or abs(r.duration - duration) <= 15 else 0
        return (round(relevance(r, query), 1), dur_ok, q, r.free_slot, -r.queue, r.speed)

    keep = [r for r in results if r.ext in AUDIO_EXTS and relevance(r, query) >= 0.6 and r.size > 500_000]
    seen, out = set(), []
    for r in sorted(keep, key=score, reverse=True):
        key = (r.username, r.path)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:limit]


def from_aioslsk(result: Any) -> List[SlskResult]:
    """Résultats d'un pair (aioslsk SearchResult) -> SlskResult (seulement ses fichiers partagés)."""
    out = []
    for item in getattr(result, "shared_items", []) or []:
        attrs: Dict[int, int] = {}
        for a in getattr(item, "attributes", []) or []:
            key = getattr(a, "key", None)
            attrs[int(getattr(key, "value", key) if key is not None else -1)] = int(getattr(a, "value", 0) or 0)
        ext = (getattr(item, "extension", "") or "").lower().lstrip(".")
        name = item.filename
        if not ext and "." in name:
            ext = name.rsplit(".", 1)[-1].lower()
        out.append(SlskResult(result.username, name, int(item.filesize or 0), ext,
                              bitrate=attrs.get(0, 0), duration=attrs.get(1, 0), sample_rate=attrs.get(4, 0),
                              bit_depth=attrs.get(5, 0), free_slot=bool(result.has_free_slots),
                              speed=int(result.avg_speed or 0), queue=int(result.queue_size or 0)))
    return out


@dataclass
class Metrics:
    """Compteurs P2P affichés dans Téléchargements (C10.2) : vitesses dans le temps, pairs, files."""
    down: Deque[float] = field(default_factory=lambda: deque(maxlen=HISTORY))   # octets/s
    up: Deque[float] = field(default_factory=lambda: deque(maxlen=HISTORY))
    connected: bool = False
    peers: int = 0
    downloads: int = 0
    uploads: int = 0
    queued: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    shared_files: int = 0
    routers: int = -1               # 1.4.0-rc.4 (B83) : routeurs UPnP trouvés (-1 = pas encore su)


class _QuietPeers(logging.Filter):
    """1.4.0-rc.4 (B83) : la bibliothèque Soulseek écrivait des centaines de lignes par minute (connexions
    aux pairs, coupures) qui chassaient les lignes de DJSync des journaux envoyés. On garde l'UPnP, les
    avertissements utiles et les erreurs."""

    def filter(self, record: logging.LogRecord) -> bool:   # noqa: A003
        name = record.name
        if name.startswith("aioslsk.network.upnp"):
            return True
        msg = str(record.msg).lower()
        if "upnp" in msg:
            return True
        if name.startswith("aioslsk.network.connection") or "connecttopeer" in msg:
            return record.levelno >= logging.ERROR
        return record.levelno >= logging.WARNING


class _RouterWatch(logging.Handler):
    """Lit « found N IGD devices » (aioslsk) pour savoir si un routeur UPnP a répondu."""

    def __init__(self, metrics: "Metrics") -> None:
        super().__init__(logging.INFO)
        self.metrics = metrics

    def emit(self, record: logging.LogRecord) -> None:
        m = re.search(r"found (\d+) (?:igd )?devices", record.getMessage().lower())
        if m:
            self.metrics.routers = max(int(m.group(1)), 0) if self.metrics.routers <= 0 else self.metrics.routers


def quiet_library_logs() -> None:
    """Filtre posé sur les sorties du journal (une seule fois par sortie)."""
    for h in logging.getLogger().handlers:
        if not any(isinstance(f, _QuietPeersFor) for f in h.filters):
            h.addFilter(_QuietPeersFor("aioslsk"))


class _QuietPeersFor(_QuietPeers):
    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:   # noqa: A003
        return not record.name.startswith(self.prefix) or super().filter(record)


class SoulseekError(RuntimeError):
    pass


class SoulseekStalled(SoulseekError):
    """1.4.0-rc.2 (B60) : téléchargement à 0 o/s trop longtemps (pair lent, file d'attente, port fermé)."""


STALL_S = 60.0
REACH_S = 20.0                      # 1.4.0-rc.3 (B72) : pas de réponse du pair en 20 s : injoignable
QUEUE_WAIT_S = 300.0                # en file chez le pair : on attend (5 min au plus, 60 s s'il y a d'autres pairs)


def alternatives(chosen: SlskResult, pool: Sequence[SlskResult], limit: int = 5) -> List[SlskResult]:
    """1.4.0-rc.2 (B60) : même fichier chez d'autres pairs (même nom et même format), place libre et
    rapides d'abord ; utilisés quand le pair choisi bloque ou refuse."""
    name, ext = _plain(chosen.stem), chosen.ext
    same = [r for r in pool if r.username != chosen.username and r.ext == ext and _plain(r.stem) == name]
    same.sort(key=lambda r: (not r.free_slot, r.queue, -r.speed))
    out, users = [], set()
    for r in same:
        if r.username not in users:
            users.add(r.username)
            out.append(r)
    return out[:limit]


class SoulseekClient:
    """Client Soulseek dans un fil à part. Toutes les méthodes publiques sont BLOQUANTES."""

    def __init__(self, username: str, password: str, download_dir: Path, share_dir: Optional[Path] = None,
                 port: int = 0) -> None:
        self.username, self.password = username, password
        self.download_dir = Path(download_dir)
        self.share_dir = Path(share_dir) if share_dir else None
        self.port = port
        self.metrics = Metrics()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client: Any = None
        self._ready = threading.Event()
        self._error: Optional[BaseException] = None
        self._sampler: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ cycle de vie
    @property
    def connected(self) -> bool:
        return self._client is not None and self.metrics.connected

    def start(self, timeout: float = 20.0) -> None:
        if self._thread is not None:
            return
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="soulseek", daemon=True)
        self._thread.start()
        try:
            self._call(self._start(), timeout)
        except BaseException:
            self.stop()
            raise

    async def _start(self) -> None:
        from aioslsk.client import SoulSeekClient
        from aioslsk.settings import CredentialsSettings, Settings, SharedDirectorySettingEntry

        settings = Settings(credentials=CredentialsSettings(username=self.username, password=self.password))
        settings.shares.download = str(self.download_dir)
        settings.shares.scan_on_start = bool(self.share_dir)
        if self.share_dir:
            settings.shares.directories = [SharedDirectorySettingEntry(path=str(self.share_dir))]
        if self.port:
            settings.network.listening.port = self.port
            settings.network.listening.obfuscated_port = self.port + 1
        quiet_library_logs()
        self.metrics.routers = -1
        upnp_log = logging.getLogger("aioslsk.network.upnp")
        for h in [h for h in upnp_log.handlers if isinstance(h, _RouterWatch)]:
            upnp_log.removeHandler(h)
        upnp_log.addHandler(_RouterWatch(self.metrics))
        if upnp_log.level == logging.NOTSET or upnp_log.level > logging.INFO:
            upnp_log.setLevel(logging.INFO)
        client = SoulSeekClient(settings)
        try:
            await client.start()
            await client.login()
        except BaseException:
            try:                                    # tâches de fond arrêtées proprement
                await client.stop()
            except Exception:  # noqa: BLE001
                pass
            raise
        self._client = client
        self.metrics.connected = True
        net = settings.network                   # 1.4.0-rc.3 (B72) : port d'écoute dans le journal
        log.info("Soulseek listening on port %s (obfuscated %s), UPnP %s, sharing %s", net.listening.port,
                 net.listening.obfuscated_port, "on" if net.upnp.enabled else "off",
                 "on" if self.share_dir else "off")
        self._sampler = asyncio.ensure_future(self._sample())

    def stop(self) -> None:
        loop, thread = self._loop, self._thread
        if loop is None:
            return
        try:
            if self._client is not None:
                self._call(self._stop(), 10)
        except Exception as exc:  # noqa: BLE001
            log.info("Soulseek stop: %s", exc)
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(5)
        self._loop = self._thread = self._client = None
        self.metrics.connected = False

    async def _stop(self) -> None:
        if self._sampler is not None:
            self._sampler.cancel()
        await self._client.stop()

    def _call(self, coro: Any, timeout: float) -> Any:
        if self._loop is None:
            raise SoulseekError("Soulseek is not started.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    # ------------------------------------------------------------------ compteurs
    async def _sample(self) -> None:
        while True:
            try:
                self._take_sample()
            except Exception as exc:  # noqa: BLE001 - un compteur manquant ne doit rien casser
                log.debug("Soulseek metrics: %s", exc)
            await asyncio.sleep(1.0)

    def _take_sample(self) -> None:
        t = self._client.transfers
        m = self.metrics
        m.down.append(float(t.get_download_speed() or 0.0))
        m.up.append(float(t.get_upload_speed() or 0.0))
        m.downloads = len(t.get_downloading())
        m.uploads = len(t.get_uploading())
        m.queued = int(t.get_queue_size() or 0)
        m.bytes_in = sum(int(x.bytes_transfered or 0) for x in t.get_downloads())
        m.bytes_out = sum(int(x.bytes_transfered or 0) for x in t.get_uploads())
        peers = getattr(self._client.network, "peer_connections", None)
        m.peers = len(peers) if peers is not None else m.peers

    # ------------------------------------------------------------------ recherche
    def search(self, query: str, seconds: float = SEARCH_SECONDS, duration: int = 0,
               on_partial: Optional[Callable[[List[SlskResult]], None]] = None) -> List[SlskResult]:
        """Résultats classés (voir `rank`) après `seconds` ; `on_partial` reçoit les résultats au fil de l'eau."""
        if self._client is None:
            raise SoulseekError("Soulseek is not connected.")
        # 1.4.0-rc.2 (B59) : juste après la connexion, le serveur ne relaie pas toujours la première
        # recherche ; sans aucune réponse, elle est renvoyée une fois au lieu d'afficher « Aucun résultat ».
        started = time.monotonic()
        for attempt in (1, 2):
            request = self._call(self._client.searches.search(query), 15)
            end = time.monotonic() + seconds
            seen = 0
            while time.monotonic() < end:
                time.sleep(0.5)
                results = list(request.results)
                if on_partial and len(results) != seen:
                    seen = len(results)
                    on_partial(rank([x for r in results for x in from_aioslsk(r)], query, duration))
            try:
                self._client.searches.remove_request(request)
            except Exception:  # noqa: BLE001
                pass
            found = list(request.results)
            log.info("Soulseek search %r: %d answers in %.1f s (attempt %d)", query, len(found),
                     time.monotonic() - started, attempt)
            if found:
                break
        return rank([x for r in found for x in from_aioslsk(r)], query, duration)

    # ------------------------------------------------------------------ téléchargement
    def download(self, result: SlskResult, progress: Optional[Callable[[float, str], None]] = None,
                 should_stop: Optional[Callable[[], bool]] = None, timeout: float = 1800.0,
                 stall: float = 0.0, reach: float = 0.0, queue_wait: float = 0.0) -> Path:
        """Télécharge et renvoie le fichier local. progress(pourcentage, état) ; lève SoulseekError."""
        if self._client is None:
            raise SoulseekError("Soulseek is not connected.")
        from aioslsk.transfer.model import TransferState

        transfer = self._call(self._client.transfers.download(result.username, result.path), 30)
        start = time.monotonic()
        moved_at, last_bytes = start, 0
        while True:
            state = transfer.state.VALUE
            size = transfer.filesize or result.size or 1
            done = transfer.bytes_transfered or 0
            if progress:
                progress(min(100.0, 100.0 * done / size), state.name.lower())
            if state == TransferState.COMPLETE and transfer.local_path:
                return Path(transfer.local_path)
            if state in (TransferState.FAILED, TransferState.ABORTED):
                raise SoulseekError(transfer.fail_reason or transfer.abort_reason or state.name.lower())
            now = time.monotonic()
            if done != last_bytes:
                moved_at, last_bytes = now, done
            # 1.4.0-rc.3 (B72) : trois cas distincts au lieu d'une seule limite de 60 s
            queued = bool(getattr(transfer, "remotely_queued", False)) and not done
            if queued and progress:                       # le pair a répondu : on est dans sa file
                place = getattr(transfer, "place_in_queue", None)
                progress(0.0, f"queued_at:{place}" if place else "queued_remote")
            reason = ""
            if reach and not done and not queued and now - start > reach:
                reason = f"no answer from the user in {int(reach)} s"         # injoignable : vite au suivant
            elif queued and queue_wait and now - start > queue_wait:
                reason = f"still queued at the user after {int(queue_wait)} s"
            elif stall and not queued and done and now - moved_at > stall:
                reason = f"no data for {int(stall)} s"                        # B60 : transfert figé
            elif stall and not queued and not reach and not done and now - moved_at > stall:
                reason = f"no data for {int(stall)} s"
            if reason:
                self._call(self._client.transfers.abort(transfer), 10)
                raise SoulseekStalled(reason)
            if (should_stop and should_stop()) or now - start > timeout:
                self._call(self._client.transfers.abort(transfer), 10)
                raise SoulseekError("cancelled")
            time.sleep(0.5)
