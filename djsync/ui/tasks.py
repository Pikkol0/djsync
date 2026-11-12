"""1.4.1 (C145) : registre des tâches longues.

Un registre par contrôleur (`ctrl.tasks`). Un outil s'y inscrit (`task = ctrl.tasks.start(...)`), publie son
avancement (`task.progress(i, n)`) puis sa fin (`task.finish()` ou `task.fail(...)`). Le volet gauche
(`TaskStrip`) n'affiche que ce registre.

Le registre ne lance rien et ne connaît aucun outil : il garde l'état affiché et relaie pause, reprise et
arrêt aux fonctions fournies par l'outil. Pause = l'outil ne commence pas l'élément suivant ; arrêt = même
chose, puis fin propre (c'est l'outil qui appelle `finish`). Une écriture (export.pdb, master.db,
remplacement de fichier) s'inscrit sans `stop` : progression seule.

Aucune dépendance à Qt : les appels venus d'un fil de travail passent par `post` (UiDispatcher.post), le
retrait différé d'une tâche finie par `later` (UiDispatcher.call_later)."""
from __future__ import annotations

import itertools
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

RUNNING, PAUSED, STOPPING, DONE, FAILED = "running", "paused", "stopping", "done", "failed"
ACTIVE = (RUNNING, PAUSED, STOPPING)

DONE_LINGER_S = 4.0          # « ✓ fini » reste affiché 4 s, puis la ligne disparaît


class Task:
    """Une tâche longue affichée dans le volet. Champs en lecture pour l'affichage ; l'outil n'appelle que
    `progress`, `finish` et `fail` (depuis n'importe quel fil)."""

    def __init__(self, registry: "TaskRegistry", key: str, seq: int) -> None:
        self._registry = registry
        self.key = key
        self.seq = seq                     # ordre d'inscription (à rang égal)
        self.title = ""                    # clé i18n
        self.icon = "wave"
        self.order = 10                    # rang dans le volet (analyse 0, téléchargements 1, le reste après)
        self.done = 0
        self.total = 0                     # 0 = durée inconnue (barre sans fin)
        self.fraction_override: Optional[float] = None
        self.detail = ""                   # son en cours, etc. (texte déjà traduit)
        self.state = RUNNING
        self.error = ""
        self.can_pause = False
        self.can_stop = False
        self.open: Optional[str] = None    # page à ouvrir (clé de vue ou outil du Diagnostic)
        self.linger = DONE_LINGER_S
        self.show_title = "auto"           # "auto" : nom dans la ligne s'il y a plusieurs tâches ; "always"
        self.stopping_title = "task.stopping"
        self.open_tip = "task.open"        # bulles des boutons → et ⏹ (clés i18n)
        self.stop_tip = "task.stop"
        self._pause: Optional[Callable[[], None]] = None
        self._resume: Optional[Callable[[], None]] = None
        self._stop: Optional[Callable[[], None]] = None
        self._token = 0                    # change à chaque relance : un retrait différé ancien est ignoré

    # ------------------------------------------------------------------ état
    @property
    def active(self) -> bool:
        return self.state in ACTIVE

    @property
    def fraction(self) -> float:
        """Avancement 0..1 (0 si la durée est inconnue)."""
        if self.state == DONE:
            return 1.0
        if self.fraction_override is not None:
            return max(0.0, min(1.0, self.fraction_override))
        if self.total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.done / self.total))

    @property
    def pausable(self) -> bool:
        return self.can_pause and self.state in (RUNNING, PAUSED)

    @property
    def stoppable(self) -> bool:
        return self.can_stop and self.state in (RUNNING, PAUSED)

    # ------------------------------------------------------------------ appels de l'outil (tout fil)
    def progress(self, done: int, total: Optional[int] = None, detail: Optional[str] = None,
                 fraction: Optional[float] = None) -> None:
        self._registry._call(self._progress, done, total, detail, fraction)

    def finish(self) -> None:
        self._registry._call(self._registry._finish, self, False, "")

    def fail(self, message: str = "") -> None:
        self._registry._call(self._registry._finish, self, True, message)

    def _progress(self, done: int, total: Optional[int], detail: Optional[str], fraction: Optional[float]) -> None:
        if not self.active:
            return
        before = (self.done, self.total, self.detail, self.fraction_override)
        self.done = max(0, int(done))
        if total is not None:
            self.total = max(0, int(total))
        if detail is not None:
            self.detail = detail
        self.fraction_override = fraction
        if (self.done, self.total, self.detail, self.fraction_override) != before:
            self._registry._changed()

    def __repr__(self) -> str:  # pragma: no cover - débogage
        return f"<Task {self.key} {self.state} {self.done}/{self.total}>"


class TaskRegistry:
    def __init__(self, post: Optional[Callable[..., None]] = None,
                 later: Optional[Callable[[int, Callable[[], None]], None]] = None,
                 notify: Optional[Callable[[], None]] = None) -> None:
        self._post = post
        self._later = later
        self._listeners: List[Callable[[], None]] = []
        if notify is not None:
            self._listeners.append(notify)
        self._tasks: Dict[str, Task] = {}
        self._seq = itertools.count(1)
        self._ui_thread = threading.current_thread()

    # ------------------------------------------------------------------ lecture
    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def get(self, key: str) -> Optional[Task]:
        return self._tasks.get(key)

    def tasks(self) -> List[Task]:
        """Tâches affichées (en cours, finies depuis peu, en échec), dans l'ordre du volet."""
        return sorted(self._tasks.values(), key=lambda x: (x.order, x.seq))

    def active(self) -> List[Task]:
        return [x for x in self.tasks() if x.active]

    # ------------------------------------------------------------------ inscription
    def start(self, key: str, title: str, *, total: int = 0, done: int = 0, detail: str = "",
              can_pause: bool = False, can_stop: bool = False, open: Optional[str] = None,  # noqa: A002
              pause: Optional[Callable[[], None]] = None, resume: Optional[Callable[[], None]] = None,
              stop: Optional[Callable[[], None]] = None, icon: str = "wave", order: int = 10,
              linger: float = DONE_LINGER_S, show_title: str = "auto",
              stopping_title: str = "task.stopping", open_tip: str = "task.open",
              stop_tip: str = "task.stop") -> Task:
        """Inscrit une tâche (à appeler dans le fil de l'interface). Une seule tâche par `key` : relancer une
        tâche reprend la même ligne (remise en route si elle était finie ou en échec)."""
        task = self._tasks.get(key)
        if task is None:
            task = Task(self, key, next(self._seq))
            self._tasks[key] = task
        elif not task.active:
            task.done, task.detail, task.error, task.fraction_override = 0, "", "", None
        task._token += 1
        task.title, task.icon, task.order = title, icon, order
        task.total, task.done = max(0, int(total)), max(task.done, int(done))
        if detail:
            task.detail = detail
        task.can_pause, task.can_stop = bool(can_pause and pause and resume), bool(can_stop and stop)
        task._pause, task._resume, task._stop = pause, resume, stop
        task.open, task.linger, task.show_title, task.stopping_title = open, linger, show_title, stopping_title
        task.open_tip, task.stop_tip = open_tip, stop_tip
        if task.state not in ACTIVE:
            task.state = RUNNING
        self._changed()
        return task

    # ------------------------------------------------------------------ commandes du volet
    def pause(self, key: str) -> bool:
        task = self._tasks.get(key)
        if task is None or not task.can_pause or task.state != RUNNING:
            return False
        task.state = PAUSED
        self._relay(task._pause)
        self._changed()
        return True

    def resume(self, key: str) -> bool:
        task = self._tasks.get(key)
        if task is None or task.state != PAUSED:
            return False
        task.state = RUNNING
        self._relay(task._resume)
        self._changed()
        return True

    def stop(self, key: str) -> bool:
        """Demande d'arrêt : la tâche passe « en arrêt » ; l'outil finit l'élément en cours puis appelle
        `finish`. Sans effet sur une tâche sans arrêt (écriture)."""
        task = self._tasks.get(key)
        if task is None or not task.stoppable:
            return False
        task.state = STOPPING
        self._relay(task._stop)
        self._changed()
        return True

    def mark_stopping(self, key: str) -> None:
        """L'outil a été arrêté par un autre bouton que celui du volet (même affichage « Arrêt… »)."""
        task = self._tasks.get(key)
        if task is not None and task.state in (RUNNING, PAUSED):
            task.state = STOPPING
            self._changed()

    def dismiss(self, key: str) -> bool:
        """Retire une tâche finie ou en échec (clic sur une ligne rouge)."""
        task = self._tasks.get(key)
        if task is None or task.active:
            return False
        del self._tasks[key]
        self._changed()
        return True

    # ------------------------------------------------------------------ interne
    def _finish(self, task: Task, failed: bool, error: str) -> None:
        if self._tasks.get(task.key) is not task or not task.active:
            return
        task.error = error.strip()
        task.state = FAILED if failed else DONE
        task._token += 1
        if task.state == DONE:
            if task.linger <= 0 or self._later is None:
                del self._tasks[task.key]
            else:
                token = task._token
                self._later(int(task.linger * 1000), lambda: self._expire(task, token))
        self._changed()

    def _expire(self, task: Task, token: int) -> None:
        if self._tasks.get(task.key) is task and task._token == token and task.state == DONE:
            del self._tasks[task.key]
            self._changed()

    def _relay(self, fn: Optional[Callable[[], None]]) -> None:
        if fn is None:
            return
        try:
            fn()
        except Exception:  # noqa: BLE001 - un outil en erreur ne doit pas casser le volet
            log.exception("Task command")

    def _call(self, fn: Callable[..., None], *args: Any) -> None:
        if self._post is not None and threading.current_thread() is not self._ui_thread:
            self._post(fn, *args)
        else:
            fn(*args)

    def _changed(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("Task listener")
