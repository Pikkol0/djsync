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
