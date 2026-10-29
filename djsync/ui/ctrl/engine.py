"""Moteur de téléchargement (yt-dlp) : proposition de mise à jour quand il échoue, outil manuel.

Aucune vérification au démarrage. Si un téléchargement ou un import échoue d'une façon qui
ressemble à un yt-dlp périmé, DJSync interroge PyPI (une seule fois par session) et, si une version
plus récente existe, propose de l'installer (évènement « engine_offer »). Après installation, les
téléchargements tombés pour cette raison sont relancés tout seuls.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ...core import engine
from ...i18n import t

log = logging.getLogger(__name__)


class EngineMixin:
    _engine_checked = False            # vérification « sur échec » déjà faite cette session
    _engine_busy = False

    # ------------------------------------------------- nouvelle version de DJSync (V1.2.0)
    def app_update_check(self, manual: bool = False, force: bool = False,
                         result: Optional[Callable[[Any, Optional[BaseException]], None]] = None) -> None:
        """Au démarrage (au plus une fois par jour, si activé) ou à la demande : évènement
        « app_update » (Update) si une version plus récente de DJSync est publiée. 1.2.0-rc.4 : la
        version complète de l'exécutable (« 1.2.0-rc.4 ») et le canal choisi dans les Réglages."""
        import time

        from ... import full_version
        from ...core import updates

        s = self.settings
        if not manual and not force and (not s.check_updates or time.time() - (s.last_update_check or 0) < 20 * 3600):
            return
        current = full_version()
        channel = {"stable": False, "test": True}.get(s.update_channel)

        def done(update: Optional[updates.Update]) -> None:
            s.last_update_check = time.time()
            try:
                s.save()
            except OSError:
                pass
            self.available_update = update
            self._emit("app_update_state")
            if update is not None and result is None:      # « Tout vérifier » : ligne d'état, pas de fenêtre
                self._emit("app_update", update, current)
            elif manual:
                self.message("ok", t("update.none", version=current))
            if result is not None:                  # 1.3.1 (C89) : « Tout vérifier », sans message
                result(update, None)

        def failed(exc: BaseException) -> None:
            log.info("DJSync update check failed: %s", exc)
            if result is not None:
                result(None, exc)
            if manual:
                from ..controller import is_offline_error

                self.message("error", t("error.offline") if is_offline_error(exc) else t("update.failed"))

        self.dispatcher.submit(lambda: updates.check(current, include_prerelease=channel), done, failed, pool="net")

    # ------------------------------------------- installation depuis l'application (1.2.0-rc.4)
    available_update: Any = None
    update_progress: Any = None        # (octets, total) pendant le téléchargement, sinon None
    update_ready: Any = None           # (Plan, chemin préparé, version) : il ne reste qu'à redémarrer
    _update_cancel = False

    def app_versions(self, include_prerelease: bool, ok: Callable[[Any], None],
                     failed: Optional[Callable[[BaseException], None]] = None) -> None:
        """1.3.2 (C96) : versions publiées installables sur ce système (plus anciennes comprises), en
        arrière-plan ; `ok(liste d'Update)`, la plus récente d'abord."""
        from ...core import updates

        def bad(exc: BaseException) -> None:
            log.info("DJSync versions list failed: %s", exc)
            if failed is not None:
                failed(exc)

        self.dispatcher.submit(lambda: updates.list_versions(include_prerelease=include_prerelease), ok, bad,
                               pool="net")

    def can_self_update(self) -> bool:
        from ...core import selfupdate

        return selfupdate.plan() is not None

    def app_update_install(self, update: Any) -> None:
        """Télécharge, vérifie et prépare `update` en arrière-plan ; évènement « app_update_state » à
        chaque étape. Depuis les sources (pas d'exécutable à remplacer) : ouvre la page de la release."""
        from ...core import selfupdate

        p = selfupdate.plan()
        if p is None or not update.asset:
            self._emit("open_url", update.url)
            return
        if self.update_progress is not None:
            return
        self._update_cancel = False
        self.update_progress = (0, 0)
        self._emit("app_update_state")

        last = [-1]

        def progress(done: int, total: int) -> None:
            self.update_progress = (done, total)
            step = int(100 * done / total) if total else done // (1 << 20)
            if step != last[0]:                # au plus ~100 rafraîchissements
                last[0] = step
                self.dispatcher.post(self._emit, "app_update_state")

        def work() -> Any:
            f = selfupdate.download(update, selfupdate.download_dir(), progress, lambda: self._update_cancel)
            try:
                return selfupdate.prepare(p, f)
            finally:
                f.unlink(missing_ok=True)

        def ok(staged: Any) -> None:
            self.update_progress = None
            self.update_ready = (p, staged, update.version)
            self._emit("app_update_state")
            self._emit("app_update_ready", update.version)

        def failed(exc: BaseException) -> None:
            self.update_progress = None
            self._emit("app_update_state")
            reason = str(exc) if isinstance(exc, selfupdate.UpdateError) else ""
            if reason == "cancelled":
                return
            log.warning("DJSync update %s failed: %s", update.version, exc)
            from ..controller import is_offline_error

            key = {"bad_checksum": "update.err_checksum", "no_checksum": "update.err_checksum",
                   "prepare_failed": "update.err_prepare", "no_asset": "update.err_asset"}.get(reason)
            self.message("error", t("error.offline") if is_offline_error(exc) else t(key or "update.err_download"))

        self.dispatcher.submit(work, ok, failed, pool="net")

    def app_update_cancel(self) -> None:
        self._update_cancel = True

    def app_update_restart(self) -> None:
        """Échange les versions après la fermeture de DJSync, puis la relance."""
        import os

        from ...core import selfupdate

        if self.update_ready is None:
            return
        p, staged, version = self.update_ready
        pids = [os.getpid()]
        if p.kind == "windows":
            pids.append(os.getppid())          # le lanceur DJSync.exe attend la fin de l'application
        try:
            selfupdate.schedule_swap(p, staged, pids)
        except OSError as exc:
            log.warning("Cannot schedule the update: %s", exc)
            self.message("error", t("update.err_prepare"))
            return
        log.info("Restarting into DJSync %s", version)
        self.player.stop()
        self._emit("quit")

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
