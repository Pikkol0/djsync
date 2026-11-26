"""1.4.4 (C15) : mode live (voie XML seule), service tenu par le contrôleur (`ctrl.live`, règle A3-10).

Chaîne d'un son, dans un fil à part (pool « live ») qui passe devant la file des téléchargements : téléchargement
dans `<dossier musique>/DJSync Live/AAAA-MM-JJ/` (ou son déjà là, pas retéléchargé) → analyse (BPM, grille, tempo
variable, tonalité, 1er temps, mémoire cue selon le réglage) → `djsync-live.xml` réécrit → « Prêt ». L'analyse de
fond de la bibliothèque est mise en pause pendant ce temps. Rien n'est écrit dans master.db ni sur une clé pendant
le live ; « Terminer le live » (Rekordbox fermé) range tout dans la bibliothèque de l'ordinateur.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core import live as L
from ..i18n import t

log = logging.getLogger(__name__)


class LiveService:
    def __init__(self, ctrl: Any) -> None:
        self.ctrl = ctrl
        self.session: Optional[L.LiveSession] = None
        self._lock = threading.RLock()
        self._busy = 0
        self._paused_analysis = False
        self._t0: Dict[str, float] = {}

    # ------------------------------------------------------------------ chemins
    @staticmethod
    def data_dir() -> Path:
        from ..settings import settings_dir

        return settings_dir()

    def xml_path(self) -> Path:
        return L.xml_path(self.data_dir())

    def music_dir(self, date: str) -> Path:
        from ..db.local_library import default_music_dir

        base = getattr(self.ctrl.settings, "local_music_dir", "") or ""
        return (Path(base) if base else default_music_dir()) / "DJSync Live" / date

    # ------------------------------------------------------------------ live en cours
    def ensure(self) -> L.LiveSession:
        with self._lock:
            if self.session is None or self.session.done:
                self.session = L.current(self.data_dir())
                self._write()
            return self.session

    def pending(self) -> Optional[L.LiveSession]:
        """Live pas rangé, d'un jour précédent (proposé au lancement de DJSync)."""
        s = L.open_session(self.data_dir())
        if s is not None and any(tr.ready for tr in s.tracks) and s.date != L.today():
            return s
        return None

    def _write(self) -> None:
        """Registre et XML (appelé sous le verrou)."""
        if self.session is None:
            return
        try:
            L.save(self.session, self.data_dir())
            L.write_xml(self.session, self.data_dir())
        except OSError as exc:
            log.warning("Live register / XML not written: %s", exc)

    def _changed(self, tr: Optional[L.LiveTrack] = None) -> None:
        self.ctrl.dispatcher.post(lambda: self.ctrl._emit("live", tr))

    # ------------------------------------------------------------------ ajouter un son
    def add(self, result: Any) -> Optional[L.LiveTrack]:
        """« Ajouter au live » (résultat de recherche ou lien)."""
        s = self.ensure()
        url = getattr(result, "url", "") or ""
        key = url or f"{result.artist} - {result.title}"
        with self._lock:
            old = s.find(key)
            if old is not None and old.status != "error":
                self.ctrl.message("info", t("live.already", title=old.title))
                return old
            if old is not None:
                s.tracks.remove(old)
            tr = L.LiveTrack(key, result.title, result.artist, getattr(result, "album", "") or "", url,
                             getattr(result, "source", "") or "", added_at=L.clock())
            s.tracks.append(tr)
            self._write()
        self._t0[key] = time.monotonic()
        self._start(tr, result)
        self._changed(tr)
        return tr

    def retry(self, tr: L.LiveTrack, result: Any = None) -> None:
        tr.status, tr.error = "queued", ""
        self._t0[tr.key] = time.monotonic()
        self._start(tr, result)
        self._changed(tr)

    def _start(self, tr: L.LiveTrack, result: Any) -> None:
        self._busy += 1
        self._pause_analysis(True)
        self.ctrl.dispatcher.submit(lambda: self._chain(tr, result), lambda _r: self._finished(tr),
                                    lambda exc: self._failed(tr, exc), pool="live")

    def _pause_analysis(self, pause: bool) -> None:
        """L'analyse de fond de la bibliothèque laisse la place au live (reprise ensuite si c'est nous)."""
        q = getattr(self.ctrl, "analysis", None)
        fn = getattr(self.ctrl, "pause_analysis", None)
        if q is None or fn is None:
            return
        try:
            if pause and getattr(q, "running", False) and not getattr(q, "paused", False):
                fn(True)
                self._paused_analysis = True
            elif not pause and self._paused_analysis and self._busy == 0:
                self._paused_analysis = False
                fn(False)
        except Exception:  # noqa: BLE001 - simple confort
            log.debug("Analysis pause for the live", exc_info=True)

    def _existing(self, tr: L.LiveTrack) -> Optional[str]:
        """Son déjà dans la bibliothèque de l'ordinateur (ouverte) ou dans le live du jour : son chemin."""
        s = self.session
        if s is not None:
            for other in s.tracks:
                if other is not tr and other.ready and (
                        (tr.url and L.norm_key(other.url) == L.norm_key(tr.url))
                        or L.same_track(tr.title, tr.artist, other.title, other.artist)):
                    return other.path
        lib = getattr(self.ctrl, "library", None)
        if lib is not None and getattr(self.ctrl, "is_local", False):
            try:
                found = L.find_existing(lib.list_tracks(), tr.url, tr.title, tr.artist)
            except Exception:  # noqa: BLE001 - lecture seule, simple confort
                found = None
            if found is not None and found.path and Path(found.path).is_file():
                return str(found.path)
        return None

    def _chain(self, tr: L.LiveTrack, result: Any) -> None:
        """Fil « live » : téléchargement (ou son déjà là) → analyse → XML."""
        path = self._existing(tr)
        if path:
            tr.path, tr.existing = path, True
        else:
            if result is None:
                raise RuntimeError(t("live.no_source"))
            tr.status = "downloading"
            self._changed(tr)
            folder = self.music_dir(self.session.date if self.session else L.today())
            folder.mkdir(parents=True, exist_ok=True)
            res = self.ctrl.service.download(result, folder)
            tr.path = str(res.file_path)
        tr.status = "analysing"
        self._changed(tr)
        from ..analysis import analyze_file

        a = analyze_file(tr.path, getattr(self.ctrl.settings, "ffmpeg_location", "") or None)
        tr.duration = float(a.duration)
        tr.bpm = float(a.bpm)
        tr.key_name = a.key.name or ""
        tr.beats = L.beats_of(a)
        if getattr(self.ctrl.settings, "auto_cue", False):
            first = getattr(a, "first_downbeat_ms", None)
            if first is not None:
                tr.cues = [(0, int(first), "")]
        tr.status = "ready"
        tr.ready_at = L.clock()
        tr.seconds = round(time.monotonic() - self._t0.get(tr.key, time.monotonic()), 1)
        with self._lock:
            self._write()

    def _finished(self, tr: L.LiveTrack) -> None:
        self._busy = max(0, self._busy - 1)
        self._pause_analysis(False)
        log.info("Live: %s ready in %.1f s", tr.title, tr.seconds)
        self.ctrl.message("ok", t("live.ready", title=tr.title))
        self.ctrl._emit("live", tr)

    def _failed(self, tr: L.LiveTrack, exc: BaseException) -> None:
        self._busy = max(0, self._busy - 1)
        self._pause_analysis(False)
        from .controller import is_offline_error, known_error

        key = "error.offline" if is_offline_error(exc) else known_error(exc)
        tr.status, tr.error = "error", (t(key) if key else str(exc).replace("ERROR: ", "")[:200])
        log.warning("Live: %s failed: %s", tr.title, exc)
        with self._lock:
            self._write()                      # un son en erreur n'entre pas dans le XML
        self.ctrl.message("error", t("live.failed", title=tr.title, error=tr.error))
        self.ctrl._emit("live", tr)

    # ------------------------------------------------------------------ terminer le live
    def finish(self, done: Optional[Callable[[bool], None]] = None) -> bool:
        """Range le live dans la bibliothèque de l'ordinateur. Refusé tant que Rekordbox est ouvert (DJSync ne le
        ferme jamais). Sans bibliothèque de l'ordinateur : les fichiers sont gardés, le live est clos."""
        from ..db.local_library import rekordbox_running

        s = self.session or L.open_session(self.data_dir())
        if s is None:
            return False
        if self._busy:
            self.ctrl.message("warn", t("live.busy"))
            return False
        if rekordbox_running():
            self.ctrl.message("warn", t("live.close_rekordbox"))
            self.ctrl._emit("live_blocked")
            return False
        local = self.ctrl.find_local() if hasattr(self.ctrl, "find_local") else None
        ctrl = self.ctrl

        def work() -> int:
            if local is None:
                return -1
            return self._tidy(s, local)

        def ok(n: int) -> None:
            with self._lock:
                s.done = True
                self.session = None
                try:
                    L.save(s, self.data_dir())
                    L.write_xml(None, self.data_dir())          # XML vidé
                except OSError as exc:
                    log.warning("Live register not closed: %s", exc)
            ctrl.message("ok", t("live.kept_files") if n < 0 else t("live.tidied", n=n, name=s.playlist_name))
            ctrl._emit("live", None)
            if n >= 0 and getattr(ctrl, "is_local", False) and ctrl.library is not None:
                ctrl._emit("library")
            if done:
                done(True)

        def err(exc: BaseException) -> None:
            log.warning("Live not tidied: %s", exc)
            ctrl.message("error", t("live.tidy_failed", error=str(exc)[:200]))
            if done:
                done(False)

        ctrl.dispatcher.submit(work, ok, err, pool="db")
        return True

    def _tidy(self, s: L.LiveSession, local: Any) -> int:
        """Fil « db » : playlist « Live ▸ DJSync Live – AAAA-MM-JJ » ; un son déjà dans la collection (même chemin)
        est seulement ajouté à la playlist (tonalité et formes d'onde de Rekordbox gardées) ; sinon ajouté comme un
        téléchargement. Sauvegarde de master.db avant (comme toute écriture)."""
        from ..db.local_library import LocalRekordboxLibrary

        own = getattr(self.ctrl, "is_local", False) and self.ctrl.library is not None
        lib = self.ctrl.library if own else LocalRekordboxLibrary(
            local, backup_keep=self.ctrl.settings.backup_keep, analyze=True, artwork=True,
            ffmpeg_location=self.ctrl.settings.ffmpeg_location or None,
            key_notation=self.ctrl.settings.key_notation).connect()
        try:
            plan = L.tidy_plan(s, lib.list_tracks())
            if not plan:
                return 0
            lists = lib.list_playlists()
            folder = next((p for p in lists if p.is_folder and p.name == L.FOLDER_NAME and p.parent_id == 0), None)
            if folder is None:
                folder = lib.create_folder(L.FOLDER_NAME)
            pl = next((p for p in lib.list_playlists() if not p.is_folder and p.name == s.playlist_name
                       and p.parent_id == folder.playlist_id), None)
            if pl is None:
                pl = lib.create_playlist(s.playlist_name, folder.playlist_id)
            ids: List[int] = []
            with lib.batch():
                for tr, found in plan:
                    if found is not None:
                        ids.append(found.content_id)
                        continue
                    added = lib.add_track(Path(tr.path), tr.title, tr.artist, tr.album or None, tr.url or None, ())
                    ids.append(added.content_id)
                if ids:
                    lib.add_to_playlist(pl.playlist_id, ids)
            return len(ids)
        finally:
            if not own:
                lib.close()
