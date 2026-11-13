"""1.4.1 (C145) : tâches longues dans le volet gauche (`TaskStrip`).

Une carte par tâche en cours du registre `ctrl.tasks` (ui/tasks.py), dans l'ordre du registre (analyse,
téléchargements, puis les autres). Volet déplié : pour chaque tâche, la carte de l'analyse d'avant (titre,
→ ⏸ ⏹ selon ce que la tâche permet, « 12 / 40  ·  détail », barre). Volet replié : la même carte réduite à
son anneau (B73). La carte disparaît dès que la tâche est finie ; une tâche en échec reste en rouge jusqu'au
clic. Au-delà de 3 cartes, la zone défile."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QProgressBar, QScrollArea, QWidget

from ..i18n import t
from . import theme
from .icons import qicon
from .mini_ring import MiniRing
from .tasks import FAILED, PAUSED, STOPPING, Task, TaskRegistry
from .widgets import ElidedLabel, clickable, hbox, icon_button, label, restyle, vbox

MAX_CARDS = 3                    # au-delà, la zone des cartes défile
DEFAULT_PAGE = "downloads"       # page ouverte par une carte quand la tâche n'en donne pas


def _counts(task: Task) -> str:
    return f"{task.done} / {task.total}" if task.total > 0 else ""


def card_text(task: Task) -> str:
    """Texte sous le titre : « 3 / 10  ·  son » (analyse), « Téléchargements 1 / 2 » (`show_title="always"`,
    comme la carte d'avant), « En pause » ajouté pendant une pause."""
    if task.state == FAILED:
        return task.error or t("task.failed")
    prefix = t(task.title) + " " if task.show_title == "always" else ""
    head = (prefix + _counts(task)).strip()
    parts = [p for p in (head, t("task.paused") if task.state == PAUSED else "", task.detail) if p]
    return "  ·  ".join(parts)


def ring_tip(task: Task) -> str:
    if task.state == FAILED:
        return t(task.title) + (f" — {task.error}" if task.error else "")
    paused = f" · {t('task.paused')}" if task.state == PAUSED else ""
    return (t(task.title) + " " + _counts(task)).strip() + paused


def line_text(task: Task, title: str) -> str:
    """1.4.1 (C140) : carte en une ligne : « 12 / 40  ANALYSE » (le chiffre d'abord : c'est lui qui bouge, et il
    reste lisible quand le titre est coupé), « · En pause », ou l'erreur."""
    if task.state == FAILED:
        return f"{title.upper()}  ·  {task.error or t('task.failed')}"
    paused = f"  ·  {t('task.paused')}" if task.state == PAUSED else ""
    return f"{_counts(task)}  {title.upper()}".strip() + paused


class TaskCard(QFrame):
    """Carte d'une tâche (rôle « panel », comme la carte de l'analyse d'avant)."""

    def __init__(self, strip: "TaskStrip", key: str) -> None:
        super().__init__()
        self.setProperty("role", "panel")
        self.strip, self.key = strip, key
        self.task: Optional[Task] = None
        lay = vbox(self, margins=theme.px(10), spacing=theme.px(4))
        head = hbox(spacing=theme.px(4))
        self.title = label("", "section", wrap=True)                    # titre long : à la ligne, jamais coupé
        head.addWidget(self.title, 1)
        # 1.4.1 (C140, socle du volet) : carte en une ligne quand la hauteur manque (« ANALYSE  12 / 40 »),
        # détail dans la bulle, → ⏸ ⏹ gardés
        self.line = ElidedLabel("", "section")
        head.addWidget(self.line, 1)
        self.line.hide()
        self.open = icon_button("go", lambda: strip.open_task(self.task), t("task.open"), size=12)
        self.pause = icon_button("pause", self._pause, t("task.pause"), size=12)
        self.stop = icon_button("stop", self._stop, t("task.stop"), size=12)
        for b in (self.open, self.pause, self.stop):
            head.addWidget(b)
            b.hide()
        lay.addLayout(head)
        self.label = label("", "dim", wrap=True)
        lay.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.ring = MiniRing("wave", lambda: strip.open_task(self.task))      # volet replié (B73)
        lay.addWidget(self.ring, 0, Qt.AlignHCenter)
        self.ring.hide()
        self._role = "dim"
        self._paused_icon: Optional[bool] = None
        clickable(self, self._clicked)
        self.hide()

    # ------------------------------------------------------------------ commandes
    def _pause(self) -> None:
        task, reg = self.task, self.strip.registry
        if task is not None:
            reg.resume(task.key) if task.state == PAUSED else reg.pause(task.key)

    def _stop(self) -> None:
        if self.task is not None:
            self.strip.registry.stop(self.task.key)

    def _clicked(self) -> None:
        task = self.task
        if task is not None and task.state == FAILED:
            self.strip.registry.dismiss(task.key)
        else:
            self.strip.open_task(task)

    # ------------------------------------------------------------------ affichage
    def update(self, task: Task, compact: bool, margin: int, line: bool = False) -> None:
        self.task = task
        line = line and not compact
        vm = max(1, margin * 6 // 10) if line else margin
        self.layout().setContentsMargins(margin, vm, margin, vm)
        failed = task.state == FAILED
        full = not compact
        self.title.setVisible(full and not line)
        self.label.setVisible(full and not line)
        self.line.setVisible(line)
        self.ring.setVisible(compact)
        title = t(task.stopping_title) if task.state == STOPPING else t(task.title)
        self.title.setText("" if compact else title.upper())
        self.label.setText("" if compact else card_text(task))
        if line:
            self.line.setText(line_text(task, title))
        role = "err" if failed else "dim"
        if role != self._role:
            self._role = role
            self.label.setProperty("role", role)
            restyle(self.label)
        if task.active and task.total <= 0 and task.fraction_override is None:
            self.bar.setRange(0, 0)                       # durée inconnue : barre sans fin
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * task.fraction))
        self.bar.setVisible(full and not failed and not line)
        active = task.active and full
        self.open.setVisible(active and bool(task.open))
        self.pause.setVisible(active and task.can_pause)
        self.stop.setVisible(active and task.can_stop)
        self.open.setToolTip(t(task.open_tip))
        self.stop.setToolTip(t(task.stop_tip))
        self.stop.setEnabled(task.stoppable)
        paused = task.state == PAUSED
        if paused != self._paused_icon:
            self._paused_icon = paused
            self.pause.setIcon(qicon("play" if paused else "pause", 12, theme.TEXT))
        self.pause.setToolTip(t("task.resume") if paused else t("task.pause"))
        tip = t("task.failed_tip") if failed else t(task.open_tip if task.open else "nav.open_activity")
        if line:                                          # le détail caché passe dans la bulle
            tip = f"{title}\n{card_text(task)}\n{tip}"
        self.setToolTip(tip)
        if compact:
            self.ring.set(task.fraction, task.icon, ring_tip(task), theme.ERR if failed else theme.ACCENT)


class TaskStrip(QWidget):
    """Les cartes des tâches, l'une sous l'autre (zone qui défile au-delà de 3)."""

    def __init__(self, registry: TaskRegistry, opener: Callable[[str], None], parent: Any = None) -> None:
        super().__init__(parent)
        self.registry = registry
        self._opener = opener
        self.compact = False
        self.line = False                    # 1.4.1 (C140) : cartes en une ligne (hauteur du volet trop juste)
        self.margin = theme.px(10)
        lay = vbox(self, spacing=0)
        self.inner = QWidget()
        self.cards_lay = vbox(self.inner, spacing=theme.px(6))
        lay.addWidget(self.inner)
        self.area = QScrollArea()
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.area)
        self.area.hide()
        self._scrolling = False
        self.cards: Dict[str, TaskCard] = {}
        self._order: List[str] = []
        self.hide()

    # ------------------------------------------------------------------ cartes
    def card(self, key: str) -> TaskCard:
        """Carte d'une tâche (créée cachée au besoin, gardée ensuite : une relance reprend la même carte)."""
        c = self.cards.get(key)
        if c is None:
            c = self.cards[key] = TaskCard(self, key)
            self.cards_lay.addWidget(c)
        return c

    def open_task(self, task: Optional[Task]) -> None:
        self._opener((task.open if task is not None else None) or DEFAULT_PAGE)

    def _reorder(self, keys: List[str]) -> None:
        if keys == self._order:
            return
        self._order = list(keys)
        for i, k in enumerate(keys):
            c = self.cards[k]
            self.cards_lay.removeWidget(c)
            self.cards_lay.insertWidget(i, c)

    # ------------------------------------------------------------------ affichage
    def refresh(self, compact: Optional[bool] = None, margin: Optional[int] = None,
                line: Optional[bool] = None) -> None:
        if compact is not None:
            self.compact = bool(compact)
        if line is not None:
            self.line = bool(line)
        if margin is not None:
            self.margin = margin
        tasks = self.registry.tasks()
        shown = {x.key for x in tasks}
        for k, c in self.cards.items():
            if k not in shown:
                c.hide()
        if not tasks:
            self.hide()
            return
        for x in tasks:
            self.card(x.key)
        self._reorder([x.key for x in tasks])
        for x in tasks:
            c = self.cards[x.key]
            c.update(x, self.compact, self.margin, self.line)
            c.show()
        self._set_scrolling(len(tasks) > MAX_CARDS)
        # volet replié : pas de barre de défilement (elle couperait les anneaux) ; molette seulement
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff if self.compact else Qt.ScrollBarAsNeeded)
        self.show()
        self._fit_area()

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
        """Zone qui défile : haute de 3 cartes."""
        if not self._scrolling:
            return
        bar = 0 if self.compact else self.area.verticalScrollBar().sizeHint().width()
        w = max(1, self.width() - bar)
        cards = [c for c in (self.cards[k] for k in self._order) if not c.isHidden()][:MAX_CARDS]
        hs = []
        for c in cards:
            h = c.heightForWidth(w) if c.hasHeightForWidth() else -1
            hs.append(h if h >= 0 else c.sizeHint().height())
        self.area.setFixedHeight(sum(hs) + self.cards_lay.spacing() * max(0, len(hs) - 1))

    def resizeEvent(self, e: Any) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(e)
        self._fit_area()

    def rescale(self) -> None:
        for c in self.cards.values():
            c.ring.rescale()
