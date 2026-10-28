"""Lecture : file d'écoute (précédent / suivant / enchaînement automatique), préécoute, formes d'onde.

La file vit dans le contrôleur (pas dans la barre de lecture) : n'importe quelle vue la remplit
(`play_queue`), les raccourcis clavier et la barre la pilotent.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from ...audio.player import LOADING, PAUSED, PLAYING, STOPPED, NowPlaying
from ...i18n import t
from ...models import DownloadJob, LibraryTrack, TrackResult

RESTART_AFTER = 3.0   # « Précédent » après 3 s de lecture : revient au début du son


@dataclass
class QueueItem:
    """Un élément de la file : son de la clé, résultat à préécouter, ou téléchargement terminé."""

    kind: str          # "library" | "result" | "job"
    item: Any

    @property
    def title(self) -> str:
        return self.item.track.title if self.kind == "job" else self.item.title

    @property
    def library_track(self) -> Optional[LibraryTrack]:
        return self.item if self.kind == "library" else None


def queue_of(items: Sequence[Any]) -> List[QueueItem]:
    out = []
    for it in items:
        if isinstance(it, LibraryTrack):
            out.append(QueueItem("library", it))
        elif isinstance(it, TrackResult):
            out.append(QueueItem("result", it))
        elif isinstance(it, DownloadJob):
            if it.status == "done" and it.file_path:
                out.append(QueueItem("job", it))
    return out


class PlaybackMixin:
    queue: List[QueueItem]
    queue_index: int

    def _init_playback(self) -> None:
        self.queue, self.queue_index = [], -1
        self._started_at = 0.0
        self.grid_editor: Any = None                       # page Grille et cues ouverte (B20)
        from ...audio.nowplaying import MediaKeys         # 1.2.3 : touches multimédia sur macOS

        self.now_playing = MediaKeys(self.toggle_play, self.play_next, self.play_previous, self.dispatcher.post,
                                      on_seek=lambda s: self.player.seek(s))

    # ----------------------------------------------------------------- évènements du lecteur
    def missing_file_text(self, path: Any) -> str:
        """1.3.0-rc.3 (B20) : fichier introuvable, dit selon la bibliothèque ouverte (recalculé à chaque fois)."""
        from pathlib import Path

        p = Path(str(path))
        if getattr(self, "is_local", False):
            return t("msg.file_missing_local", name=p.name, folder=str(p.parent))
        drive = getattr(self, "drive", None)
        root = str(getattr(drive, "root", "") or drive or p.anchor)
        return t("msg.file_missing_drive", name=p.name, drive=root)

    def file_missing(self, track: Any) -> bool:
        """B20 : le fichier du son existe-t-il encore ? (False si on ne sait pas)"""
        lib = getattr(self, "library", None)
        if lib is None or track is None:
            return False
        try:
            return not lib.absolute_path(track).is_file()
        except Exception:  # noqa: BLE001
            return False

    def _player_event(self, kind: str, payload: Any) -> None:
        if kind == "missing":                           # B20
            self.message("error", self.missing_file_text(payload))
            return
        self._emit("player", kind, payload)
        if kind in ("state", "loaded"):
            self._update_now_playing()
        if kind == "ended":
            self.play_next(auto=True)

    def _update_now_playing(self) -> None:
        np_ = getattr(self, "now_playing", None)
        if np_ is None or not np_.enabled:
            return
        meta = self.player.meta
        if meta is None or self.player.state == STOPPED:
            np_.clear()
            return
        np_.update(meta.title, meta.artist, self.player.duration, self.player.position(),
                   self.player.state == PLAYING)

    @property
    def current_item(self) -> Optional[QueueItem]:
        return self.queue[self.queue_index] if 0 <= self.queue_index < len(self.queue) else None

    @property
    def has_next(self) -> bool:
        return self.queue_index + 1 < len(self.queue)

    @property
    def has_previous(self) -> bool:
        return self.queue_index > 0

    # ----------------------------------------------------------------------- file
    def play_queue(self, items: Sequence[Any], index: int = 0) -> None:
        """Remplace la file (sons de la liste affichée) et lit l'élément `index`."""
        queue = queue_of(items)
        if not queue:
            return
        target = items[index] if 0 <= index < len(items) else None
        pos = next((i for i, q in enumerate(queue) if q.item is target), 0)
        self.queue, self.queue_index = queue, pos
        self._play_current()
        self._emit("queue")

    def play_next(self, auto: bool = False) -> None:
        if not self.has_next:
            if not auto:
                self.message("info", t("player.queue_end"))
            self._emit("queue")
            return
        self.queue_index += 1
        self._play_current()
        self._emit("queue")

    def play_previous(self) -> None:
        if self.player.state in (PLAYING, PAUSED) and self.player.position() > RESTART_AFTER:
            self.player.seek(0)
            return
        if not self.has_previous:
            if self.current_item is not None:
                self.player.seek(0) if self.player.state in (PLAYING, PAUSED) else self._play_current()
            return
        self.queue_index -= 1
        self._play_current()
        self._emit("queue")

    def toggle_play(self) -> None:
        # 1.3.0-rc.4 (B20) : page Grille et cues ouverte -> Lecture / Pause (barre du bas, Espace, touches
        # multimédia) joue le son de la page, à la position de son curseur, comme son propre bouton
        editor = getattr(self, "grid_editor", None)
        if editor is not None:
            try:
                alive = editor.winfo_exists()
            except RuntimeError:
                alive = False
            if alive and editor.isVisible():
                editor._play()
                return
            # 1.3.0-rc.8 (B31) : page cachée (autre onglet, autre son lancé) -> Lecture / Pause agissent
            # sur le son en cours, plus sur celui de la page restée ouverte en arrière-plan
            if not alive:
                self.grid_editor = None
        state = self.player.state
        if state in (PLAYING, PAUSED):
            self.player.toggle_pause()
        elif state == STOPPED:
            if self.current_item is not None:
                self._play_current()
            elif self.player.meta is not None:
                self.player.play(self.player.meta.path, self.player.meta)
        # LOADING : rien (le son arrive)

    def _play_current(self) -> None:
        item = self.current_item
        if item is None:
            return
        self._started_at = time.time()
        if item.kind == "library":
            self._play_library(item.item)
        elif item.kind == "result":
            self._preview(item.item)
        else:
            job = item.item
            tr = job.track
            self.player.play(job.file_path, NowPlaying(tr.title, tr.artist, job.file_path, cover_url=tr.thumbnail_url))

    # -------------------------------------------------------------- compatibilité
    def preview(self, track: TrackResult) -> None:
        """Préécoute d'un seul résultat (file d'un élément)."""
        self.play_queue([track], 0)

    def play_library_track(self, track: LibraryTrack) -> None:
        self.play_queue([track], 0)

    def play_job(self, job: DownloadJob) -> None:
        self.play_queue([job], 0)

    # ------------------------------------------------------------------ lecture réelle
    def _play_library(self, track: LibraryTrack) -> None:
        lib = self.library
        if lib is None:
            return
        path = lib.absolute_path(track)
        art = lib.artwork_file(track)
        self.player.play(path, NowPlaying(track.title, track.artist, str(path), cover_path=str(art) if art else None))

    def _preview(self, track: TrackResult) -> None:
        """Préécoute AVANT téléchargement sur la clé : fichier temporaire, lu dans le lecteur."""
        self.message("info", t("player.fetching", title=track.title))
        cached = self._preview_files.get(track.video_id)
        index = self.queue_index

        def work() -> str:
            if cached and Path(cached).is_file():
                return cached
            return self.service.download(track, self.preview_dir, tag=False).file_path

        def ok(path: str) -> None:
            self._preview_files[track.video_id] = path
            if index != self.queue_index:          # l'utilisateur est passé à un autre son entre-temps
                return
            self.player.play(path, NowPlaying(track.title, track.artist, path, cover_url=track.thumbnail_url))

        def err(exc: BaseException) -> None:
            self._on_error(exc)
            self.engine_failure(str(exc))

        self.dispatcher.submit(work, ok, err, pool="net")

    # ---------------------------------------------------------------- formes d'onde
    def load_overview(self, track: LibraryTrack, ok: Callable[[list], None]) -> None:
        """Aperçu de forme d'onde (ANLZ) pour la barre de lecture : [(hauteur, couleur)]."""
        lib = self.library
        if lib is None or not track.analysis_path:
            ok([])
            return

        def work() -> list:
            from ...analysis.anlz import read_overview

            dat, ext = lib.analysis_files(track)
            return read_overview(dat.read_bytes() if dat else None, ext.read_bytes() if ext else None)

        self.dispatcher.submit(work, ok, lambda _e: ok([]), pool="cover")

    def load_detail(self, track: LibraryTrack, ok: Callable[[Any], None]) -> None:
        """1.2.3 : forme d'onde détaillée (150 colonnes/s) et grille, pour la forme d'onde défilante."""
        lib = self.library
        if lib is None or not track.analysis_path:
            ok(None)
            return

        def work() -> Any:
            from ...analysis.anlz import read_beats, read_detail

            dat, ext = lib.analysis_files(track)
            if ext is None:
                return None
            detail = read_detail(ext.read_bytes())
            beats = read_beats(dat.read_bytes()) if dat else []
            return (detail, beats) if detail else None

        self.dispatcher.submit(work, ok, lambda _e: ok(None), pool="cover")

    @staticmethod
    def player_busy(state: str) -> bool:
        return state in (PLAYING, PAUSED, LOADING)
