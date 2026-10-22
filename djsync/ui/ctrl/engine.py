"""Moteur de téléchargement (yt-dlp) : proposition de mise à jour quand il échoue, outil manuel.

Aucune vérification au démarrage. Si un téléchargement ou un import échoue d'une façon qui
ressemble à un yt-dlp périmé, DJSync interroge PyPI (une seule fois par session) et, si une version
plus récente existe, propose de l'installer (évènement « engine_offer »). Après installation, les
téléchargements tombés pour cette raison sont relancés tout seuls.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from ...core import engine
from ...i18n import t

log = logging.getLogger(__name__)


class EngineMixin:
    _engine_checked = False            # vérification « sur échec » déjà faite cette session
    _engine_busy = False

    # ------------------------------------------------- nouvelle version de DJSync (V1.1.0)
    def app_update_check(self, manual: bool = False) -> None:
        """Au démarrage (au plus une fois par jour, si activé) ou à la demande : évènement
        « app_update » (Update) si une version plus récente de DJSync est publiée."""
        import time

        from ... import __version__
        from ...core import updates

        s = self.settings
        if not manual and (not s.check_updates or time.time() - (s.last_update_check or 0) < 20 * 3600):
            return

        def done(update: Optional[updates.Update]) -> None:
            s.last_update_check = time.time()
            try:
                s.save()
            except OSError:
                pass
            if update is not None:
                self._emit("app_update", update, __version__)
            elif manual:
                self.message("ok", t("update.none", version=__version__))

        def failed(exc: BaseException) -> None:
            log.info("DJSync update check failed: %s", exc)
            if manual:
                from ..controller import is_offline_error

                self.message("error", t("error.offline") if is_offline_error(exc) else t("update.failed"))

        self.dispatcher.submit(lambda: updates.check(__version__), done, failed, pool="net")

    def engine_failure(self, message: str) -> None:
        """Appelé (thread UI) quand une fonction essentielle échoue."""
        if self._engine_checked or self._engine_busy or not engine.looks_outdated(message):
            return
        self._engine_checked = True
        current = engine.current_version()

        def done(release: engine.Release) -> None:
            if release.newer_than(current):
                self._emit("engine_offer", release, current)

        self.dispatcher.submit(engine.latest, done, lambda exc: log.info("Update check failed: %s", exc), pool="net")

    def engine_check(self, on_result: Callable[[Optional[engine.Release], str, Optional[str]], None]) -> None:
        """Réglages > Rechercher une mise à jour : on_result(release|None, version actuelle, erreur|None)."""
        current = engine.current_version()
        self.dispatcher.submit(
            engine.latest,
            lambda rel: on_result(rel, current, None),
            lambda exc: on_result(None, current, str(exc)),
            pool="net",
        )

    def engine_install(self, release: engine.Release, on_done: Optional[Callable[[bool, str], None]] = None) -> None:
        if self._engine_busy:
            return
        self._engine_busy = True
        self.message("info", t("engine.installing", version=release.version))

        def ok(version: str) -> None:
            self._engine_busy = False
            self.message("ok", t("engine.installed", version=version))
            if on_done:
                on_done(True, version)
            self._retry_engine_failures()

        def failed(exc: BaseException) -> None:
            self._engine_busy = False
            self.message("error", t("engine.install_failed", error=str(exc)[:200]))
            if on_done:
                on_done(False, str(exc))

        self.dispatcher.submit(lambda: engine.install(release), ok, failed, pool="net")

    def engine_rollback(self) -> str:
        version = engine.rollback()
        self.message("info", t("engine.rolled_back", version=version))
        return version

    def _retry_engine_failures(self) -> None:
        for job in list(self.jobs):
            if job.status == "error" and engine.looks_outdated(job.message):
                self.retry(job)
