"""Hot cues, boucles et mémoires de la page « Grille et cues » (1.3.0, C22).

Une rangée de 8 pads A à H aux couleurs Rekordbox, sous la forme d'onde :
  * pad vide : clic (ou touche 1 à 8) = poser un cue au temps de la grille le plus proche du curseur
    (Maj : exactement au curseur) ;
  * pad posé : clic = écouter depuis ce point (une boucle tourne jusqu'au clic suivant sur la forme
    d'onde) ; clic droit = boucle de 1 à 16 temps, renommer, couleur, déplacer au curseur, supprimer ;
  * mémoires : ajouter au curseur, liste simple (clic = y aller, clic droit = supprimer).
Rien n'est posé tout seul : « Proposer des cues » ne remplit que les pads libres, et seulement après un
clic. Rien n'est écrit avant « Enregistrer » (page Grille et cues).
"""
from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from ..analysis.cues import PALETTE, SLOTS, Cue, loop_beats_for, loop_end_ms, nearest_beat_ms, suggest_cues
from ..i18n import t
from . import theme
from .widgets import button, hbox, label, vbox

LOOP_CHOICES = (1, 2, 4, 8, 16)


def rgb_hex(rgb: Any) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def fmt_ms(ms: float) -> str:
    s = max(0.0, ms / 1000.0)
    return f"{int(s // 60)}:{s % 60:04.1f}"


def _text_on(color: str) -> str:
    c = QColor(color)
    return "#101010" if (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) > 150 else "#ffffff"


class Pad(QPushButton):
    def __init__(self, panel: "CuePanel", slot: int) -> None:
        super().__init__()
        self.panel, self.slot = panel, slot
        self._fit_height()
        self.setMinimumWidth(theme.px(60))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.clicked.connect(lambda: panel.pad_clicked(slot))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: panel.pad_menu(slot, self.mapToGlobal(pos)))

    def _fit_height(self) -> None:
        """1.3.0-rc.3 (B16) : deux lignes (lettre + temps / boucle) d'après la police réelle (qui suit
        l'échelle d'affichage de Windows, contrairement aux marges), avec une marge haute et basse."""
        f = QFont(self.font())
        f.setBold(True)
        self.setMinimumHeight(max(theme.px(46), 2 * QFontMetrics(f).lineSpacing() + max(12, theme.px(12))))

    def changeEvent(self, e: Any) -> None:          # noqa: N802
        from PySide6.QtCore import QEvent

        if e.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._fit_height()
        super().changeEvent(e)

    def show_cue(self, cue: Optional[Cue]) -> None:
        self._fit_height()
        letter = SLOTS[self.slot - 1]
        r = theme.px(8)
        if cue is None:
            self.setText(letter)
            self.setToolTip(t("cue.pad_empty_tip", pad=letter))
            self.setStyleSheet(f"QPushButton {{ background: {theme.SURFACE}; color: {theme.FAINT}; "
                               f"border: 1px dashed {theme.BORDER}; border-radius: {r}px; font-weight: 600; }}"
                               f"QPushButton:hover {{ border-color: {theme.ACCENT}; color: {theme.TEXT}; }}")
            return
        color = rgb_hex(cue.colour())
        sub = cue.name or fmt_ms(cue.ms)
        if cue.is_loop:
            sub = f"⟳ {cue.loop_beats or '?'}  " + sub
        self.setText(f"{letter}\n{sub}")
        self.setToolTip(t("cue.pad_set_tip", pad=letter, time=fmt_ms(cue.ms)))
        self.setStyleSheet(f"QPushButton {{ background: {color}; color: {_text_on(color)}; border: 0; "
                           f"border-radius: {r}px; font-weight: 600; padding: 2px 6px; }}"
                           f"QPushButton:hover {{ border: 2px solid {theme.TEXT}; }}")


class CuePanel(QWidget):
    """Pads et mémoires ; `editor` est la page GridEditor (curseur, grille, lecture, redessin)."""

    def __init__(self, editor: Any) -> None:
        super().__init__()
        self.ed = editor
        lay = vbox(self, spacing=theme.px(6))
        head = hbox()
        title = label(t("cue.hot_cues"), "section")
        title.setToolTip(t("cue.hint"))
        head.addWidget(title)
        short = label(t("cue.hint_short"), "dim")
        short.setToolTip(t("cue.hint"))
        head.addWidget(short, 1)
        self.suggest_btn = button(t("cue.suggest"), self.suggest, icon="grid", tooltip=t("cue.suggest_tip"))
        head.addWidget(self.suggest_btn)
        self.clear_btn = button(t("cue.clear_all"), self.clear_all, icon="trash")
        head.addWidget(self.clear_btn)
        lay.addLayout(head)
        pads = hbox(spacing=theme.px(6))
        self.pads = [Pad(self, s) for s in range(1, 9)]
        for p in self.pads:
            pads.addWidget(p, 1)
        lay.addLayout(pads)
        mem = hbox(spacing=theme.px(6))
        mem.addWidget(label(t("cue.memories"), "dim"))
        self.mem_row = hbox(spacing=theme.px(4))
        mem.addLayout(self.mem_row)
        mem.addStretch(1)
        mem.addWidget(button(t("cue.add_memory"), self.add_memory, icon="plus", tooltip=t("cue.add_memory_tip")))
        # 1.3.1 (C75) : mémoire de boucle au curseur (longueur au choix, calée sur la grille)
        mem.addWidget(button(t("cue.add_memory_loop"), self._memory_loop_menu, icon="plus",
                             tooltip=t("cue.add_memory_loop_tip")))
        lay.addLayout(mem)
        self.refresh()

    # ------------------------------------------------------------------ état
    @property
    def cues(self) -> List[Cue]:
        return self.ed.cues

    def cue(self, slot: int) -> Optional[Cue]:
        return next((c for c in self.cues if c.slot == slot), None)

    def refresh(self) -> None:
        for p in self.pads:
            p.show_cue(self.cue(p.slot))
        while self.mem_row.count():
            item = self.mem_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in sorted((c for c in self.cues if not c.slot), key=lambda c: c.ms):
            b = QPushButton((f"⟳ {c.loop_beats or '?'}  " if c.is_loop else "▼ ") + fmt_ms(c.ms))
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton {{ color: {theme.ERR}; background: {theme.SURFACE}; border: 1px solid "
                            f"{theme.BORDER}; border-radius: {theme.px(6)}px; padding: 2px 8px; }}")
            b.setToolTip(t("cue.memory_tip"))
            b.clicked.connect(lambda _=False, m=c: self.ed.go_to(m.ms))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, m=c, w=b: self._memory_menu(m, w.mapToGlobal(pos)))
            self.mem_row.addWidget(b)
        self.clear_btn.setEnabled(bool(self.cues))

    def _changed(self) -> None:
        self.refresh()
        self.ed.cues_changed()

    def _position(self, exact: bool = False) -> int:
        """Position d'un nouveau cue : temps le plus proche du curseur (Maj : exactement au curseur)."""
        exact = exact or bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
        ms = self.ed.cursor_ms
        return int(round(ms)) if exact or not self.ed.beats else nearest_beat_ms(self.ed.beats, ms)

    # ----------------------------------------------------------------- pads
    def pad_clicked(self, slot: int) -> None:
        c = self.cue(slot)
        if c is None:
            self.place(slot)
        else:
            self.ed.play_from(c.ms, (c.ms, c.loop_ms) if c.is_loop else None)

    def place(self, slot: int, exact: bool = False) -> None:
        old = self.cue(slot)
        ms = self._position(exact)
        if old is not None:
            if old.is_loop:
                length = old.loop_ms - old.ms
                old.loop_ms = ms + length
            old.ms = ms
        else:
            self.cues.append(Cue(slot, ms))
        self._changed()

    def pad_menu(self, slot: int, pos: Any) -> None:
        from .table import popup_menu

        c = self.cue(slot)
        letter = SLOTS[slot - 1]
        entries: List[Any] = [(t("cue.place_here", pad=letter), lambda: self.place(slot), "grid")]
        if c is not None:
            entries.append(None)
            for n in LOOP_CHOICES:
                entries.append((t("cue.loop_n", n=n), lambda n=n: self.set_loop(slot, n)))
            if c.is_loop:
                entries.append((t("cue.no_loop"), lambda: self.set_loop(slot, 0)))
            entries.append(None)
            entries.append((t("cue.rename"), lambda: self.rename(slot), "edit"))
            entries.append((t("cue.colour"), lambda: self.choose_colour(slot, pos), "tag"))
            entries.append((t("cue.delete"), lambda: self.delete(slot), "trash"))
        popup_menu(self, entries, pos)

    def set_loop(self, slot: int, n_beats: int) -> None:
        c = self.cue(slot)
        if c is None:
            return
        playing = self._is_active_loop(c)
        if n_beats <= 0:
            c.loop_ms, c.loop_beats = None, 0
        else:
            c.loop_ms = loop_end_ms(self.ed.beats, c.ms, n_beats)
            c.loop_beats = n_beats
        if playing:                                   # 1.3.0 (B35) : la boucle en cours suit le pad
            if c.loop_ms:
                self.ed.active_loop = (int(c.ms), int(c.loop_ms))
                self.ed.draw()
            else:
                self.ed.exit_loop()
        self._changed()

    def _is_active_loop(self, c: Cue) -> bool:
        """1.3.0 (B35) : cette cue est-elle la boucle en train de tourner dans la page ?"""
        loop = getattr(self.ed, "active_loop", None)
        return bool(loop and c.loop_ms and loop == (int(c.ms), int(c.loop_ms)))

    def rename(self, slot: int) -> None:
        from .dialogs import TextInputDialog

        c = self.cue(slot)
        if c is None:
            return

        def done(text: str) -> None:
            c.name = text[:40]
            self._changed()

        TextInputDialog(self.window(), t("cue.rename"), t("cue.rename_prompt", pad=SLOTS[slot - 1]), done,
                        initial=c.name, allow_empty=True)

    def choose_colour(self, slot: int, pos: Any) -> None:
        from PySide6.QtWidgets import QMenu

        from .icons import swatch_icon

        c = self.cue(slot)
        if c is None:
            return
        menu = QMenu(self)
        menu.addAction(t("cue.colour_default"), lambda: self._set_colour(c, 0))
        for code, rgb in PALETTE.items():
            menu.addAction(swatch_icon(rgb_hex(rgb)), "", lambda k=code: self._set_colour(c, k))
        menu.exec(pos)

    def _set_colour(self, c: Cue, code: int) -> None:
        c.color_code = code
        c.rgb = PALETTE.get(code, (0, 0, 0))
        self._changed()

    def delete(self, slot: int) -> None:
        # 1.3.0 (B35) : supprimer le pad de la boucle en cours en sort aussitôt (sans coupure). Avant, le
        # son continuait de boucler alors que la boucle orange avait disparu.
        if any(c.slot == slot and self._is_active_loop(c) for c in self.cues):
            self.ed.exit_loop()
        self.ed.cues = [c for c in self.cues if c.slot != slot]
        self._changed()

    # -------------------------------------------------------------- mémoires
    def add_memory(self) -> None:
        ms = self._position()
        if any(not c.slot and c.ms == ms for c in self.cues):
            return
        self.cues.append(Cue(0, ms))
        self._changed()

    def _memory_menu(self, m: Cue, pos: Any) -> None:
        from .table import popup_menu

        entries: List[Any] = [(t("cue.go_memory"), lambda: self.ed.go_to(m.ms), "play"), None]
        for n in LOOP_CHOICES:                         # 1.3.1 (C75) : mémoire de boucle
            entries.append((t("cue.loop_n", n=n), lambda n=n: self.set_memory_loop(m, n)))
        if m.is_loop:
            entries.append((t("cue.no_loop"), lambda: self.set_memory_loop(m, 0)))
        entries += [None, (t("cue.delete"), lambda: self._delete_memory(m), "trash")]
        popup_menu(self, entries, pos)

    def set_memory_loop(self, m: Cue, n_beats: int) -> None:
        """1.3.1 (C75) : une mémoire devient une boucle de `n_beats` temps (0 : redevient un point)."""
        if n_beats <= 0:
            m.loop_ms, m.loop_beats = None, 0
        else:
            m.loop_ms = loop_end_ms(self.ed.beats, m.ms, n_beats)
            m.loop_beats = n_beats
        self._changed()

    def add_memory_loop(self, n_beats: int) -> None:
        ms = self._position()
        if any(not c.slot and c.ms == ms and c.is_loop for c in self.cues):
            return
        c = Cue(0, ms)
        self.cues.append(c)
        self.set_memory_loop(c, n_beats)

    def _memory_loop_menu(self) -> None:
        from PySide6.QtGui import QCursor

        from .table import popup_menu

        popup_menu(self, [(t("cue.loop_n", n=n), lambda n=n: self.add_memory_loop(n)) for n in LOOP_CHOICES],
                   QCursor.pos())

    def _delete_memory(self, m: Cue) -> None:
        self.ed.cues = [c for c in self.cues if c is not m]
        self._changed()

    # ------------------------------------------------------------ lot
    def suggest(self) -> None:
        new = suggest_cues(self.ed.beats, self.cues)
        if not new:
            self.ed.ctrl.message("info", t("cue.suggest_none"))
            return
        self.cues.extend(new)
        self._changed()
        self.ed.ctrl.message("ok", t("cue.suggested", n=len(new)))

    def clear_all(self) -> None:
        from .dialogs import ConfirmDialog

        def go() -> None:
            self.ed.cues = []
            self._changed()

        ConfirmDialog(self.window(), t("cue.clear_all"), t("cue.clear_all_msg"), go, confirm_text=t("cue.clear_all"),
                      danger=True)

    def loop_label(self, c: Cue) -> str:
        bpm = 0.0
        if self.ed.beats:
            tempos = sorted(b[1] for b in self.ed.beats)
            bpm = tempos[len(tempos) // 2] / 100.0
        return str(c.loop_beats or loop_beats_for(c.ms, c.loop_ms or c.ms, bpm))
