"""« Prêt pour le set ? » (1.4.2, C67) : la clé contrôlée en un clic, page de la fenêtre principale.

Contrôles (core/set_check.py) en arrière-plan et en lecture seule ; chaque ligne orange ou rouge a son bouton
(analyser, mettre à jour export.pdb, voir les fichiers introuvables…). Rien n'est modifié sans clic. Le matériel
visé est retenu (réglage `set_players`). Rapport court à copier ou enregistrer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import QComboBox, QWidget

from ..i18n import t
from . import theme
from .dialogs import BaseDialog
from .widgets import button, hbox, label, panel, restyle, vbox

ROLE = {"ok": "accent", "warn": "warn", "error": "err", "skip": "faint"}
ACTIONS = {"analyse": "set.do_analyse", "pdb": "set.do_pdb", "missing": "set.do_missing", "convert": "set.do_convert",
           "space": "set.do_space", "backup": "set.do_backup", "no_cue": "set.do_no_cue",
           "empty_playlists": "set.do_empty"}


class SetCheckDialog(BaseDialog):
    as_page = True
    modal = False

    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent, t("set.title"), 720, 560)
        self.ctrl = controller
        self.checks: List[Any] = []
        self._token = 0
        drive = controller.drive
        self.drive_name = (drive.label or str(drive.root)) if drive is not None else ""
        self.heading(t("set.title"), t("set.sub", drive=self.drive_name))
        row = hbox(spacing=theme.px(8))
        row.addWidget(label(t("set.players")))
        self.players = QComboBox()
        from ..core.set_check import PLAYERS

        self._players = list(PLAYERS)
        self.players.addItems([t(f"set.players_{k}") for k in self._players])
        cur = controller.settings.set_players
        self.players.setCurrentIndex(self._players.index(cur) if cur in self._players else 0)
        self.players.currentIndexChanged.connect(self._players_changed)
        row.addWidget(self.players, 1)
        self.body.addLayout(row)
        self.verdict = label(t("set.running"), "h2")
        self.body.addWidget(self.verdict)
        self.box = panel()
        self.rows_lay = vbox(self.box, margins=theme.px(12), spacing=theme.px(8))
        self.body.addWidget(self.box)
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.body.addStretch(1)
        foot = hbox(spacing=theme.px(6))
        self.copy_btn = button(t("set.copy"), self.copy_report, icon="copy")
        self.save_btn = button(t("set.save"), self.save_report, icon="download")
        foot.addWidget(self.copy_btn)
        foot.addWidget(self.save_btn)
        foot.addStretch(1)
        self.again_btn = button(t("set.again"), self.run, kind="primary", icon="refresh")
        foot.addWidget(self.again_btn)
        self.body.addLayout(foot)
        self.show_dialog()
        self.run()

    # ------------------------------------------------------------------ contrôles
    @property
    def players_key(self) -> str:
        return self._players[max(0, self.players.currentIndex())]

    def _players_changed(self, _i: int) -> None:
        s = self.ctrl.settings
        s.set_players = self.players_key
        self.ctrl.save_settings_quiet()
        self.run()

    def run(self) -> None:
        from ..core import set_check

        lib = self.ctrl.library
        if lib is None or getattr(self.ctrl, "is_local", False):
            self._show([])
            self.verdict.setText(t("set.no_drive"))
            return
        self._token += 1
        token = self._token
        self.verdict.setText(t("set.running"))
        self.verdict.setProperty("role", "")
        restyle(self.verdict)
        self.again_btn.setEnabled(False)
        players = self.players_key

        def work() -> List[Any]:
            from ..db.usb import drive_filesystem

            try:
                fs = drive_filesystem(lib.drive.root) or ""
            except Exception:  # noqa: BLE001 - système de fichiers inconnu : ligne « – »
                fs = ""
            return set_check.run(lib, fs, players, should_stop=lambda: self.ctrl.library is not lib)

        def ok(checks: List[Any]) -> None:
            if token == self._token and self.winfo_exists() and self.ctrl.library is lib:
                self._show(checks)

        def err(exc: BaseException) -> None:
            if token == self._token and self.winfo_exists():
                self.again_btn.setEnabled(True)
                self.verdict.setText(t("set.failed", error=str(exc)))

        self.ctrl.dispatcher.submit(work, ok, err, pool="tools")

    def _show(self, checks: List[Any]) -> None:
        from ..core.set_check import verdict

        self.checks = list(checks)
        self.again_btn.setEnabled(True)
        while self.rows_lay.count():
            item = self.rows_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows = {}
        for c in self.checks:
            self.rows_lay.addWidget(self._row(c))
        if self.checks:
            v = verdict(self.checks)
            self.verdict.setText(t(f"set.verdict_{v}"))
            self.verdict.setProperty("role", ROLE[v])
            restyle(self.verdict)

    def _row(self, c: Any) -> QWidget:
        w = QWidget()
        lay = vbox(w, spacing=theme.px(2))
        top = hbox(spacing=theme.px(8))
        mark = label(c.mark, ROLE.get(c.level, "dim"))
        mark.setFixedWidth(theme.px(18))
        top.addWidget(mark)
        name = label(t(f"set.row_{c.key}"))
        name.setFixedWidth(theme.px(170))
        top.addWidget(name)
        text = label(c.text, "dim" if c.level in ("ok", "skip") else ROLE.get(c.level, "dim"), wrap=True)
        top.addWidget(text, 1)
        act: Optional[Any] = None
        if c.action and c.level in ("warn", "error"):
            act = button(t(ACTIONS.get(c.action, "set.do_see"), n=len(c.ids)), lambda _c=False, ch=c: self.act(ch),
                         kind="flat")
            top.addWidget(act)
        lay.addLayout(top)
        self.rows[c.key] = {"widget": w, "text": text, "action": act, "check": c}
        return w

    # ------------------------------------------------------------------ actions (un clic chacune)
    def act(self, c: Any) -> None:
        win = self.window()
        if c.action == "analyse":
            self.ctrl.analyze(list(c.ids))
            self.ctrl.message("info", t("set.analysing", n=len(c.ids)))
        elif c.action == "pdb":
            self.ctrl.pdb_sync_now(ok=lambda _s=None: self.winfo_exists() and self.run(),
                                   failed=lambda *_a: self.winfo_exists() and self.run())
        elif c.action == "missing":
            if hasattr(win, "open_diagnostic"):
                win.open_diagnostic("missing")
        elif c.action == "convert":
            if hasattr(win, "_open_settings_section"):
                win._open_settings_section("libraries")
            self.ctrl.message("info", t("set.convert_hint", n=len(c.ids)))
        elif c.action == "space" and hasattr(win, "open_space"):
            win.open_space()
        elif c.action == "backup" and hasattr(win, "open_backups"):
            win.open_backups()
        elif c.action == "no_cue":
            self._open_library("nocues")
        elif c.action == "empty_playlists" and c.ids:
            self._open_library(f"p{c.ids[0]}")

    def _open_library(self, iid: Optional[str]) -> None:
        if iid is None:
            return
        win = self.window()
        self.ctrl._emit("navigate", "library")
        view = getattr(win, "views", {}).get("library")
        if view is not None:
            try:
                view._goto(iid)
            except Exception:  # noqa: BLE001 - liste pas encore lue : la Bibliothèque reste ouverte
                pass

    # ------------------------------------------------------------------ rapport
    def report_text(self) -> str:
        from ..core.set_check import report

        return report(self.checks, self.drive_name, self.players_key)

    def copy_report(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.report_text())
        self.ctrl.message("ok", t("set.copied"))

    def save_report(self) -> None:
        from datetime import datetime
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        name = f"DJSync-{datetime.now():%Y%m%d-%H%M}.txt"
        path, _f = QFileDialog.getSaveFileName(self, t("set.save"), str(Path.home() / name), "Text (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.report_text(), encoding="utf-8")
            self.ctrl.message("ok", t("set.saved", path=path))
        except OSError as exc:
            self.ctrl.message("error", str(exc))


def open_set_check(parent: Any, controller: Any) -> Optional[SetCheckDialog]:
    if controller.library is None or getattr(controller, "is_local", False):
        controller.message("error", t("msg.no_drive"))
        return None
    win = parent.window()
    if hasattr(win, "reopen_dialog_page"):
        page = win.reopen_dialog_page(SetCheckDialog)
        if page is not None:
            page.run()
            return page
    return SetCheckDialog(parent, controller)
