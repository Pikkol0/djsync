"""Touches multimédia et widget « À l'écoute » de macOS (1.2.3).

Sur macOS, les touches lecture / suivant / précédent (F7-F9, casque, Touch Bar) ne sont PAS envoyées
aux applications comme des touches : le système les donne à l'application déclarée « en cours de
lecture » via MPRemoteCommandCenter / MPNowPlayingInfoCenter (framework MediaPlayer). DJSync s'y
déclare : titre, artiste, durée, position, lecture/pause. Ailleurs (Windows, Linux) : rien à faire,
les touches arrivent déjà comme des touches Qt.

Tout est facultatif : sans pyobjc (lancement depuis les sources) ou en cas d'erreur, rien ne change.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


class MediaKeys:
    def __init__(self, on_toggle: Callable[[], None], on_next: Callable[[], None], on_previous: Callable[[], None],
                 post: Callable[[Callable[[], None]], None], on_seek: Optional[Callable[[float], None]] = None) -> None:
        self.enabled = False
        self._handlers: list = []                       # références gardées (sinon libérées par ObjC)
        if sys.platform != "darwin":
            return
        try:
            import MediaPlayer as mp  # pyobjc-framework-MediaPlayer
        except Exception as exc:  # noqa: BLE001
            log.info("Media keys unavailable (MediaPlayer framework): %s", exc)
            return
        self._mp = mp
        try:
            center = mp.MPRemoteCommandCenter.sharedCommandCenter()
            ok = 0                                       # MPRemoteCommandHandlerStatusSuccess

            def handler(fn: Callable[[], None]) -> Any:
                def h(_event: Any) -> int:
                    post(fn)
                    return ok
                self._handlers.append(h)
                return h

            for cmd, fn in ((center.togglePlayPauseCommand(), on_toggle), (center.playCommand(), on_toggle),
                            (center.pauseCommand(), on_toggle), (center.nextTrackCommand(), on_next),
                            (center.previousTrackCommand(), on_previous)):
                cmd.setEnabled_(True)
                cmd.addTargetWithHandler_(handler(fn))
            if on_seek is not None:
                def seek(event: Any) -> int:
                    pos = float(event.positionTime())
                    post(lambda: on_seek(pos))
                    return ok
                self._handlers.append(seek)
                cmd = center.changePlaybackPositionCommand()
                cmd.setEnabled_(True)
                cmd.addTargetWithHandler_(seek)
            self.enabled = True
            log.info("macOS media keys enabled (Now Playing)")
        except Exception as exc:  # noqa: BLE001
            log.info("Media keys unavailable: %s", exc)

    def update(self, title: str, artist: str, duration: float, position: float, playing: bool) -> None:
        """Infos affichées par macOS ; `playing` décide à qui le système envoie les touches."""
        if not self.enabled:
            return
        mp = self._mp
        try:
            info = {mp.MPMediaItemPropertyTitle: title or "", mp.MPMediaItemPropertyArtist: artist or "",
                    mp.MPMediaItemPropertyPlaybackDuration: float(duration or 0),
                    mp.MPNowPlayingInfoPropertyElapsedPlaybackTime: float(position or 0),
                    mp.MPNowPlayingInfoPropertyPlaybackRate: 1.0 if playing else 0.0}
            center = mp.MPNowPlayingInfoCenter.defaultCenter()
            center.setNowPlayingInfo_(info)
            center.setPlaybackState_(1 if playing else 2)     # MPNowPlayingPlaybackStatePlaying / Paused
        except Exception as exc:  # noqa: BLE001
            log.debug("Now Playing update failed: %s", exc)

    def clear(self) -> None:
        if not self.enabled:
            return
        try:
            center = self._mp.MPNowPlayingInfoCenter.defaultCenter()
            center.setNowPlayingInfo_(None)
            center.setPlaybackState_(3)                              # Stopped
        except Exception:  # noqa: BLE001
            pass
