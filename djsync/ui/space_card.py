"""Carte « Espace » des Paramètres (1.3.1, C27) : barre empilée des postes, détail, actions sans risque.

Le calcul (parcours des dossiers) tourne en arrière-plan quand la carte s'affiche, pas au branchement
de la clé ; le résultat est gardé quelques minutes (`core.space.UsageCache`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QGridLayout, QWidget

from ..core import space
from ..i18n import t
from . import theme
from .views.common import human_size
from .widgets import button, hbox, label

# Couleur de chaque poste (le libre reste neutre)
# 1.4.0-rc.2 (C132) : caches en vert, pour ne plus les confondre avec « Autres fichiers » (gris)
PART_COLORS = {"music": "#8B7CF6", "analysis": "#3CC8D2", "databases": "#E8D23C", "backups": "#F08C2E",
               "app": "#F06EB4", "caches": "#6FCF7C", "other": "#5A5F66", "free": ""}
TRIM_KEEP = 5


class SpaceBar(QWidget):
    """Barre empilée : une couleur par poste, proportionnelle à sa taille."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.parts: Dict[str, int] = {}
        self.setMinimumHeight(theme.px(16))

    def sizeHint(self) -> QSize:          # noqa: N802
        return QSize(theme.px(400), theme.px(16))

    def set_parts(self, parts: Dict[str, int]) -> None:
        self.parts = dict(parts)
        self.setToolTip("\n".join(f"{t('space.' + k)} : {human_size(v)}" for k, v in parts.items() if v))
        self.update()

    def ordered(self) -> List[Tuple[str, int]]:
        """Ordre des segments dans la barre (C132) : autres fichiers, bibliothèque, libre."""
        return sorted(self.parts.items(), key=lambda kv: (kv[0] != "other", kv[0] == "free"))

    def paintEvent(self, _e: Any) -> None:     # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = r.height() / 2
        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)
        p.fillRect(r, QColor(theme.BORDER))
        total = sum(self.parts.values())
        x = r.left()
        if total > 0:
            # 1.4.0-rc.2 (C132) : « Autres fichiers » à gauche, puis la bibliothèque, puis le libre
            for key, value in self.ordered():
                color = PART_COLORS.get(key)
                w = r.width() * value / total
                if color and w > 0:
                    p.fillRect(QRectF(x, r.top(), w, r.height()), QColor(color))
                x += w
        p.end()


class SpaceCard:
    """Contenu de la carte (ajouté dans le layout d'une carte des Paramètres)."""

    def __init__(self, layout: Any, ctrl: Any) -> None:
        self.ctrl = ctrl
        self.cache = space.UsageCache()
        self._token = 0
        self._pending: Optional[str] = None     # mesure en cours (clé), pour ne pas la lancer deux fois
        self.usage: Optional[space.Usage] = None
        top = hbox(spacing=theme.px(8))
        self.summary = label(t("space.idle"), "dim", wrap=True)
        top.addWidget(self.summary, 1)
        self.refresh_btn = button(t("space.refresh"), lambda: self.compute(force=True), kind="flat", icon="refresh")
        top.addWidget(self.refresh_btn)
        layout.addLayout(top)
        self.bar = SpaceBar()
        from PySide6.QtWidgets import QProgressBar

        self.busy = QProgressBar()                  # 1.4.0 (C27) : indéterminée pendant la mesure
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setMaximumHeight(6)
        self.busy.setVisible(False)
        layout.addWidget(self.busy)
        layout.addWidget(self.bar)
        self.warn = label("", "warn", wrap=True)
        self.warn.hide()
        layout.addWidget(self.warn)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(theme.px(10))
        self.grid.setVerticalSpacing(theme.px(4))
        layout.addLayout(self.grid)
        self.result = label("", "accent", wrap=True)
        layout.addWidget(self.result)
        self._rows: List[Any] = []

    # ------------------------------------------------------------------ calcul
    def _target(self) -> Optional[Dict[str, Any]]:
        lib = getattr(self.ctrl, "library", None)
        if lib is None:
            return None
        from ..settings import settings_dir

        data = settings_dir()
        local = bool(getattr(lib, "is_local", False))
        try:
            backup = Path(lib.backup_dir)
            if local:
                return {"key": f"local:{lib.contents_root}", "local": True, "music": Path(lib.contents_root),
                        "backup": backup, "data": data, "lib": lib,
                        "share": Path(lib.share_dir), "db": Path(lib.db_path).parent}
            root = Path(lib.drive.root)
            return {"key": f"usb:{root}", "local": False, "root": root, "music": Path(lib.contents_root),
                    "backup": backup, "data": data}
        except (AttributeError, OSError):
            return None

    def compute(self, force: bool = False, done: Optional[Callable[[Any], None]] = None) -> None:
        """Mesure en arrière-plan (résultat gardé quelques minutes). 1.3.1 (C90) : `done(usage ou None)`
        une fois le résultat affiché (« Tout vérifier »)."""
        target = self._target()
        self.result.setText("")
        if target is None:
            if done:
                done(None)
            self.summary.setText(t("space.no_library"))
            self.bar.set_parts({})
            self._fill({}, {})
            return
        if force:
            self.cache.drop(target["key"])
        cached = self.cache.get(target["key"])
        if cached is not None:
            self._show(cached, target)
            if done:
                done(cached)
            return
        if self._pending == target["key"] and not force:
            return
        self._pending = target["key"]
        self._token += 1
        token = self._token
        self.summary.setText(t("space.computing"))
        self.busy.setVisible(True)                  # 1.4.0 (C27) : barre d'attente pendant la mesure
        self.refresh_btn.setEnabled(False)

        def work(track_bytes: Optional[int] = None) -> space.Usage:
            if target["local"]:
                return space.local_usage(target["music"], target["backup"], target["data"], track_bytes,
                                         target["share"], target["db"])
            return space.usb_usage(target["root"], target["music"], target["data"])

        def ok(usage: space.Usage) -> None:
            if token != self._token:
                return
            self._pending = None
            self.cache.put(target["key"], usage)
            self._show(usage, target)
            if done:
                done(usage)

        def failed(_exc: Any) -> None:
            if token == self._token:
                self._pending = None
                self.refresh_btn.setEnabled(True)
                self.busy.setVisible(False)
                self.summary.setText(t("space.failed"))
            if done:
                done(None)

        if not target["local"]:
            self.ctrl.dispatcher.submit(work, ok, failed, pool="tools")
            return

        # 1.3.1-rc.2 (C27) : ordinateur : taille des sons de la collection lue dans master.db (thread de la
        # base), puis le reste mesuré sur le disque (thread des outils).
        def sizes() -> Dict[str, int]:
            """1.4.0 (C129) : taille des sons de la collection, par disque."""
            out: Dict[str, int] = {}
            for x in target["lib"].list_tracks():
                n = int(getattr(x, "file_size", 0) or 0)
                if n:
                    d = space.drive_of(x.path or "")
                    out[d] = out.get(d, 0) + n
            return out

        def measured(total: Any) -> None:
            self.ctrl.dispatcher.submit(lambda: work(total), ok, failed, pool="tools")

        self.ctrl.dispatcher.submit(sizes, measured, failed, pool="db")

    # ---------------------------------------------------------------- affichage
    def _show(self, usage: space.Usage, target: Dict[str, Any]) -> None:
        if usage is getattr(self, "usage", None) and self._rows:   # 1.4.0-rc.3 (B71) : déjà affiché tel quel
            return
        self.usage = usage
        self.refresh_btn.setEnabled(True)
        self.busy.setVisible(False)
        text = t("space.summary", free=human_size(usage.free), total=human_size(usage.total))
        if usage.total:                             # 1.4.0 (C129) : part de la bibliothèque sur tout le disque
            text = t("space.summary_lib", lib=human_size(usage.library),
                     pct=f"{100.0 * usage.library / usage.total:.1f}", other=human_size(usage.parts.get("other", 0)),
                     free=human_size(usage.free), total=human_size(usage.total))
        for drive, size in sorted(getattr(usage, "music_elsewhere", {}).items()):
            text += "\n" + t("space.music_elsewhere", size=human_size(size), drive=drive)
        self.summary.setText(text)
        self.bar.set_parts(usage.parts)
        warns = usage.warnings()
        texts = [t(f"space.warn_{w}") for w in warns]
        self.warn.setText("  ".join(texts))
        self.warn.setVisible(bool(texts))
        actions: Dict[str, Any] = {}
        if "caches" in usage.folders and usage.parts.get("caches"):
            actions["caches"] = (t("space.clear_caches"), lambda: self._clear(target))
        if not target["local"] and usage.parts.get("backups"):
            actions["backups"] = (t("space.trim_points", n=TRIM_KEEP), lambda: self._trim(target))
        self._fill(usage, actions)

    def _fill(self, usage: Any, actions: Dict[str, Any]) -> None:
        for w in self._rows:            # 1.3.1 : sans setParent(None), qui en faisait des fenêtres visibles
            self.grid.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._rows = []
        if not usage:
            return
        for row, (key, value) in enumerate(usage.parts.items()):
            dot = label("●", "")
            dot.setStyleSheet(f"color: {PART_COLORS.get(key) or theme.FAINT};")
            name = label(t(f"space.{key}"), "")
            name.setToolTip(t(f"space.{key}_tip"))
            size = label(human_size(value), "dim")
            size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cells = [dot, name, size]
            self.grid.addWidget(dot, row, 0)
            self.grid.addWidget(name, row, 1)
            self.grid.addWidget(size, row, 2)
            col = 3
            folder = usage.folders.get(key)
            if folder is not None:
                b = button(t("space.open"), lambda _c=False, f=folder: self._open(f), kind="flat", icon="folder")
                self.grid.addWidget(b, row, col)
                cells.append(b)
            col += 1
            if key in actions:
                text, fn = actions[key]
                b = button(text, fn, kind="flat", icon="trash")
                self.grid.addWidget(b, row, col)
                cells.append(b)
            self._rows += cells
            self.grid.setRowMinimumHeight(row, theme.px(30))     # lignes égales, avec ou sans bouton
        self.grid.setColumnStretch(5, 1)

    # ------------------------------------------------------------------ actions
    @staticmethod
    def _open(folder: Path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _clear(self, target: Dict[str, Any]) -> None:
        def done(freed: int) -> None:
            self.compute(force=True)
            self.result.setText(t("space.cleared", size=human_size(freed)))

        self.ctrl.dispatcher.submit(lambda: space.clear_caches(target["data"]), done, self._failed, pool="tools")

    def _trim(self, target: Dict[str, Any]) -> None:
        def done(res: Any) -> None:
            n, freed = res
            self.compute(force=True)
            self.result.setText(t("space.trimmed", n=n, size=human_size(freed)))

        self.ctrl.dispatcher.submit(lambda: space.trim_points(target["backup"], TRIM_KEEP), done, self._failed,
                                    pool="tools")

    def _failed(self, exc: Any) -> None:
        self.result.setText(t("space.failed") + f" ({exc})")
