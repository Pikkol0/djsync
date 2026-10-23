"""Contrôleur 1.2.2 : modifier les infos d'un son, Uniformiser (C14), playlists par genre (C07)."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...i18n import t
from ...models import LibraryTrack

log = logging.getLogger(__name__)
Callback = Callable[..., None]


class CurationMixin:
    _genre_sync_pending = False

    # ------------------------------------------------------------ identité de la bibliothèque
    def library_key(self) -> str:
        """Identifiant stable de la bibliothèque active (réglages par bibliothèque : genres, revue)."""
        lib, drive = self.library, self.drive
        if lib is None or drive is None:
            return ""
        if self.is_local:
            return "local:" + str(getattr(lib, "db_path", ""))
        created = ""
        try:
            rows = lib._read("SELECT COALESCE(createdDate,''), COALESCE(deviceName,'') FROM property LIMIT 1")
            created = "|".join(str(x) for x in rows[0]) if rows else ""
        except Exception:  # noqa: BLE001
            pass
        return "usb:" + (getattr(drive, "label", "") or "") + ":" + created

    # ------------------------------------------------------------ infos d'un son (S04)
    def track_details(self, content_id: int, ok: Callback) -> None:
        lib = self.library
        if lib is None:
            return
        self.dispatcher.submit(lambda: lib.track_details(content_id), ok, self._on_error, pool="db")

    def edit_track(self, content_id: int, values: Dict[str, Any], ok: Optional[Callback] = None) -> None:
        """values : title, artist, album, year, genre, artwork (KEEP / None / octets / URL)."""
        def fn(lib: Any) -> Any:
            vals = dict(values)
            art = vals.get("artwork")
            if isinstance(art, str):                       # URL Deezer : téléchargée ici, hors thread UI
                from ...core.metadata import download_image

                vals["artwork"] = download_image(art)
            result = lib.edit_track_metadata(content_id, **vals)
            self._genre_after_change(lib)
            return result

        self._write(fn, ok, t("msg.metadata_saved"))

    def cover_candidates(self, track: LibraryTrack, ok: Callback) -> None:
        from ...core.metadata import cover_candidates

        self.dispatcher.submit(lambda: cover_candidates(track.title, track.artist or ""), ok,
                               lambda exc: ok([]), pool="net")

    def fetch_image(self, url: str, ok: Callback) -> None:
        from ...core.metadata import download_image

        self.dispatcher.submit(lambda: download_image(url), ok, lambda exc: ok(b""), pool="net")

    # ------------------------------------------------------------ Uniformiser (C14)
    def review_store(self) -> Any:
        from ...core.uniformize import ReviewStore
        from ...settings import settings_dir

        key = hashlib.sha1(self.library_key().encode("utf-8")).hexdigest()[:16]
        return ReviewStore(settings_dir() / "uniformize" / f"{key}.json")

    def uniformize_scan(self, tracks: Sequence[LibraryTrack], on_item: Callback, on_done: Callback,
                        cancelled: Callable[[], bool]) -> None:
        """Propositions son par son (Deezer + règles), en arrière-plan ; on_item(track, details,
        proposal) dans le thread UI à chaque son, on_done() à la fin."""
        lib = self.library
        if lib is None:
            return
        owned_check = getattr(lib, "is_owned", None)
        tracks = list(tracks)

        def work() -> None:
            import time

            from ...core import metadata, uniformize

            for track in tracks:
                if cancelled():
                    break
                try:
                    details = lib.track_details(track.content_id)
                except Exception as exc:  # noqa: BLE001
                    log.info("Uniformize: %s: %s", track.title, exc)
                    continue
                title, feats, head = uniformize.clean_title(track.title, track.artist or "")
                artist = head or uniformize.clean_artist(track.artist or "")
                found: Dict[str, Any] = {}
                try:
                    found = metadata.match(title, artist, track.duration_seconds, cleaned=True)
                except Exception as exc:  # noqa: BLE001 - hors ligne : règles seules
                    log.info("Deezer lookup failed for %s: %s", track.title, exc)
                    time.sleep(0.5)
                owned = bool(track.source_url) if owned_check is None else bool(owned_check(track.content_id))
                prop = uniformize.propose(track, details, found, owned=owned)
                self.dispatcher.post(on_item, track, details, prop)
                time.sleep(0.12)                           # Deezer : ~50 requêtes / 5 s
            self.dispatcher.post(on_done)

        self.dispatcher.submit(work, None, self._on_error, pool="net")

    def uniformize_apply(self, items: Sequence[Any], ok: Optional[Callback] = None) -> None:
        """items : [(track, values)] validés -> écrits en une fois (une sauvegarde)."""
        items = list(items)

        def fn(lib: Any) -> List[LibraryTrack]:
            from ...core.metadata import download_image

            done: List[LibraryTrack] = []
            with lib.batch():
                for track, values in items:
                    vals = {k: v for k, v in values.items() if k in ("title", "artist", "album", "year", "genre", "artwork")}
                    if isinstance(vals.get("artwork"), str):
                        try:
                            vals["artwork"] = download_image(vals["artwork"])
                        except Exception as exc:  # noqa: BLE001 - pochette indisponible : le reste est écrit
                            log.info("Cover download failed: %s", exc)
                            vals.pop("artwork")
                    done.append(lib.edit_track_metadata(track.content_id, **vals))
            self._genre_after_change(lib)
            return done

        self._write(fn, ok, t("uni.saved", n=len(items)))

    # ------------------------------------------------------------ playlists par genre (C07)
    def genre_config(self) -> Dict[str, Any]:
        from ...core.genre_playlists import default_config

        key = self.library_key()
        store = self.settings.genre_playlists
        if key not in store:
            store[key] = default_config()
        return store[key]

    def save_settings_quiet(self) -> None:
        try:
            self.settings.save()
        except OSError:
            pass

    def track_genres(self, ok: Callback) -> None:
        lib = self.library
        if lib is None:
            ok({})
            return
        self.dispatcher.submit(lambda: lib.track_genres() if hasattr(lib, "track_genres") else {}, ok,
                               lambda exc: ok({}), pool="db")

    def genre_apply(self, config: Dict[str, Any], removed: Sequence[str] = (), turn_off: bool = False,
                    ok: Optional[Callback] = None) -> None:
        """Enregistre la configuration et synchronise (ou supprime les playlists si on désactive)."""
        from ...core import genre_playlists as gp

        key = self.library_key()

        def fn(lib: Any) -> Any:
            if turn_off:
                gp.disable(lib, config)
                config["enabled"] = False
                return None
            if removed:
                gp.disable(lib, config, removed)
            return gp.sync(lib, config)

        def done(report: Any) -> None:
            self.settings.genre_playlists[key] = config
            self.save_settings_quiet()
            if report is not None and report.disabled:
                self.message("info", t("genre.disabled_deleted", names=", ".join(report.disabled)))
            elif report is not None:
                self.message("ok", t("genre.synced", created=report.created, added=report.added))
            self._emit("playlists_changed")
            if ok:
                ok(report)

        self._write(fn, done)

    def _genre_after_change(self, lib: Any) -> None:
        """Après un téléchargement ou une modification d'infos (thread DB) : mise à jour automatique."""
        try:
            config = self.settings.genre_playlists.get(self.library_key())
            if not config or not config.get("enabled") or not config.get("auto"):
                return
            from ...core.genre_playlists import sync

            report = sync(lib, config)
            if report.added or report.removed or report.created or report.disabled:
                log.info("Genre playlists: +%d -%d, %d created", report.added, report.removed, report.created)
                self.dispatcher.post(self.save_settings_quiet)
        except Exception as exc:  # noqa: BLE001 - Rekordbox ouvert, etc. : réessayé au prochain changement
            log.info("Genre playlists not updated: %s", exc)
