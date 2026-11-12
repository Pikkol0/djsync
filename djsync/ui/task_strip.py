"""1.4.1 (C145) : bandeau des tâches longues du volet gauche (`TaskStrip`).

Remplace la carte « Activité » (analyse, téléchargements) sans en changer l'aspect : même titre (« ANALYSE »,
« TÉLÉCHARGEMENTS », « ACTIVITÉ » à plusieurs), mêmes textes, mêmes barres, même anneau en volet replié.
Il n'affiche que le registre `ctrl.tasks` (ui/tasks.py) : une ligne fine par tâche (texte, barre), les boutons
→ ⏸ ⏹ de la première tâche dans l'en-tête (comme la flèche et l'arrêt de l'analyse aujourd'hui), ceux des
suivantes dans leur ligne ; défilement au-delà de 3 lignes ; « ✓ fini » quelques secondes ; une tâche en
échec reste en rouge jusqu'au clic. Volet replié : un anneau pour la première tâche, un second pour la
suivante (cumul des autres au-delà), comme les deux anneaux de B76."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QProgressBar, QScrollArea, QWidget

from ..i18n import t
from . import theme
from .icons import qicon
from .mini_ring import MiniRing
from .tasks import DONE, FAILED, PAUSED, STOPPING, Task, TaskRegistry
from .widgets import clickable, hbox, icon_button, label, restyle, vbox

MAX_ROWS = 3                     # au-delà, la zone des lignes défile
DEFAULT_PAGE = "downloads"       # page ouverte par la carte quand la tâche n'en donne pas


def _counts(task: Task) -> str:
    return f"{task.done} / {task.total}" if task.total > 0 else ""


def row_text(task: Task, multi: bool) -> str:
    """Texte d'une ligne. Analyse seule : « 3 / 10  ·  son » ; à plusieurs : « Analyse 3 / 10  ·  son » ;
    téléchargements (`show_title="always"`) : « Téléchargements 1 / 2 », comme la carte d'avant."""
    prefix = t(task.title) + " " if (multi or task.show_title == "always") else ""
    if task.state == FAILED:
        return (prefix + (task.error or t("task.failed"))).strip()
    if task.state == DONE:
        return (prefix + t("task.done")).strip()
    head = (prefix + _counts(task)).strip()
    parts = [p for p in (head, t("task.paused") if task.state == PAUSED else "", task.detail) if p]
    return "  ·  ".join(parts)


def ring_tip(task: Task) -> str:
    if task.state == FAILED:
        return t(task.title) + (f" — {task.error}" if task.error else "")
    if task.state == DONE:
        return t(task.title) + " " + t("task.done")
    return (t(task.title) + " " + _counts(task)).strip()


class _Buttons:
    """→ ⏸ ⏹ d'une tâche (en-tête ou ligne)."""

    def __init__(self, layout: Any, strip: "TaskStrip", at: Optional[int] = None) -> None:
        self.strip = strip
        self.task: Optional[Task] = None
        self.open = icon_button("go", lambda: strip.open_task(self.task), t("task.open"), size=12)
        self.pause = icon_button("pause", self._pause, t("task.pause"), size=12)
        self.stop = icon_button("stop", self._stop, t("task.stop"), size=12)
        for i, b in enumerate((self.open, self.pause, self.stop)):
            if at is None:
                layout.addWidget(b)
            else:
                layout.insertWidget(at + i, b)
            b.hide()
        self._paused_icon: Optional[bool] = None

    def _pause(self) -> None:
        task = self.task
        if task is None:
            return
        reg = self.strip.registry
        reg.resume(task.key) if task.state == PAUSED else reg.pause(task.key)

    def _stop(self) -> None:
        if self.task is not None:
            self.strip.registry.stop(self.task.key)

    def update(self, task: Optional[Task], shown: bool) -> None:
        self.task = task
        active = task is not None and task.active and shown
        self.open.setVisible(active and bool(task.open))
        self.pause.setVisible(active and task.can_pause)
        self.stop.setVisible(active and task.can_stop)
        if task is None:
            return
        self.open.setToolTip(t(task.open_tip))
        self.stop.setToolTip(t(task.stop_tip))
        self.stop.setEnabled(task.stoppable)
        paused = task.state == PAUSED
        if paused != self._paused_icon:
            self._paused_icon = paused
            self.pause.setIcon(qicon("play" if paused else "pause", 12, theme.TEXT))
        self.pause.setToolTip(t("task.resume") if paused else t("task.pause"))


class TaskRow(QWidget):
    """Une ligne : texte (avec ses boutons quand ce n'est pas la première tâche) et barre."""

    def __init__(self, strip: "TaskStrip", key: str) -> None:
        super().__init__()
        self.strip, self.key = strip, key
        self.task: Optional[Task] = None
        lay = vbox(self, spacing=theme.px(4))
        line = hbox(spacing=theme.px(4))
        self.label = label("", "dim", wrap=True)
        line.addWidget(self.label, 1)
        self.buttons = _Buttons(line, strip)
        lay.addLayout(line)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self._role = "dim"
        clickable(self, self._clicked)
        self.hide()

    def _clicked(self) -> None:
        task = self.task
        if task is not None and task.state == FAILED:
            self.strip.registry.dismiss(task.key)
        else:
            self.strip.open_task(task)

    def update(self, task: Task, multi: bool, inline_buttons: bool) -> None:
        self.task = task
        self.label.setText(row_text(task, multi))
        role = "err" if task.state == FAILED else "dim"
        if role != self._role:
            self._role = role
            self.label.setProperty("role", role)
            restyle(self.label)
        busy = task.active and task.total <= 0 and task.fraction_override is None
        if busy:
            self.bar.setRange(0, 0)                       # durée inconnue : barre sans fin
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * task.fraction))
        self.bar.setVisible(task.state != FAILED)
        self.setToolTip(t("task.failed_tip") if task.state == FAILED else "")
        self.buttons.update(task, inline_buttons)


class TaskStrip(QFrame):
    """Carte du volet (rôle « panel ») qui montre les tâches du registre."""

    def __init__(self, registry: TaskRegistry, opener: Callable[[str], None], parent: Any = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.registry = registry
        self._opener = opener
        self.compact = False
        lay = vbox(self, margins=theme.px(10), spacing=theme.px(4))
        head = hbox(spacing=theme.px(4))
        self.title = label("", "section")
        head.addWidget(self.title, 1)
        self.head_buttons = _Buttons(head, self)
        lay.addLayout(head)
        # lignes posées dans la carte (comme avant) ; au-delà de 3, elles passent dans une zone qui défile
        self.inner = QWidget()
        self.rows_lay = vbox(self.inner, spacing=theme.px(4))
        lay.addWidget(self.inner)
        self.area = QScrollArea()
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.area)
        self.area.hide()
        self._scrolling = False
        self.rows: Dict[str, TaskRow] = {}
        self._order: List[str] = []
        self.ring_a = MiniRing("wave", lambda: self._ring_clicked(0))
        lay.addWidget(self.ring_a, 0, Qt.AlignHCenter)
        self.ring_a.hide()
        self.ring_b = MiniRing("download", lambda: self._ring_clicked(1))
        lay.addWidget(self.ring_b, 0, Qt.AlignHCenter)
        self.ring_b.hide()
        clickable(self, lambda: self.open_task(self._head()))
        self.setToolTip(t("nav.open_activity"))
        self.hide()

    # ------------------------------------------------------------------ lignes
    def row(self, key: str) -> TaskRow:
        """Ligne d'une tâche (créée cachée au besoin, gardée ensuite : une relance reprend la même ligne)."""
        r = self.rows.get(key)
        if r is None:
            r = self.rows[key] = TaskRow(self, key)
            self.rows_lay.addWidget(r)
        return r

    def _head(self) -> Optional[Task]:
        tasks = self.registry.tasks()
        return tasks[0] if tasks else None

    def open_task(self, task: Optional[Task]) -> None:
        self._opener((task.open if task is not None else None) or DEFAULT_PAGE)

    def _ring_clicked(self, i: int) -> None:
        tasks = self.registry.tasks()
        self.open_task(tasks[i] if i < len(tasks) else (tasks[0] if tasks else None))

    def _reorder(self, keys: List[str]) -> None:
        if keys == self._order:
            return
        self._order = list(keys)
        for i, k in enumerate(keys):
            r = self.rows[k]
            self.rows_lay.removeWidget(r)
            self.rows_lay.insertWidget(i, r)

    # ------------------------------------------------------------------ affichage
    def refresh(self, compact: Optional[bool] = None) -> None:
        if compact is not None:
            self.compact = bool(compact)
        compact = self.compact
        tasks = self.registry.tasks()
        if not tasks:
            for r in self.rows.values():
                r.hide()
            self.hide()
            return
        self.show()
        multi = len(tasks) > 1
        head = tasks[0]
        shown = {x.key for x in tasks}
        for x in tasks:
            self.row(x.key)
        self._reorder([x.key for x in tasks])
        for k, r in self.rows.items():
            if k not in shown:
                r.hide()
        for i, x in enumerate(tasks):
            r = self.rows[x.key]
            r.update(x, multi, inline_buttons=i > 0 and not compact)
            r.setVisible(not compact)
        self._set_scrolling(len(tasks) > MAX_ROWS and not compact)
        self.inner.setVisible(not compact)
        self._fit_area()
        self.head_buttons.update(head, not compact)
        self.title.setVisible(not compact)
        if compact:
            title = ""
        elif multi:
            title = t("nav.activity")
        elif head.state == STOPPING:
            title = t(head.stopping_title)
        else:
            title = t(head.title)
        self.title.setText(title.upper())
        self._rings(tasks, compact)

    def _rings(self, tasks: List[Task], compact: bool) -> None:
        self.ring_a.setVisible(compact)
        self.ring_b.setVisible(compact and len(tasks) > 1)
        if not compact:
            return
        a = tasks[0]
        self.ring_a.set(a.fraction, a.icon, ring_tip(a), theme.ERR if a.state == FAILED else theme.ACCENT)
        rest = tasks[1:]
        if len(rest) == 1:
            b = rest[0]
            self.ring_b.set(b.fraction, b.icon, ring_tip(b), theme.ERR if b.state == FAILED else theme.ACCENT)
        elif rest:                                         # au-delà de deux tâches : le second anneau cumule
            done = sum(x.fraction for x in rest) / len(rest)
            failed = any(x.state == FAILED for x in rest)
            self.ring_b.set(done, "menu", "\n".join(ring_tip(x) for x in rest), theme.ERR if failed else theme.ACCENT)

    def _set_scrolling(self, on: bool) -> None:
        if on == self._scrolling:
            return
        self._scrolling = on
        lay = self.layout()
        if on:
            lay.removeWidget(self.inner)
            self.area.setWidget(self.inner)
            self.area.show()
        else:
            inner = self.area.takeWidget()
            lay.insertWidget(lay.indexOf(self.area), inner)
            self.area.hide()

    def _fit_area(self) -> None:
        """Zone qui défile : haute de 3 lignes."""
        if not self._scrolling:
            return
        m = self.layout().contentsMargins()
        w = max(1, self.width() - m.left() - m.right() - self.area.verticalScrollBar().sizeHint().width())
        rows = [r for r in (self.rows[k] for k in self._order) if not r.isHidden()][:MAX_ROWS]
        hs = []
        for r in rows:
            h = r.heightForWidth(w) if r.hasHeightForWidth() else -1
            hs.append(h if h >= 0 else r.sizeHint().height())
        self.area.setFixedHeight(sum(hs) + self.rows_lay.spacing() * max(0, len(hs) - 1))

    def resizeEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(e)
        self._fit_area()

    def rescale(self) -> None:
        self.ring_a.rescale()
        self.ring_b.rescale()
