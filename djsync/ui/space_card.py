"""Carte « Espace » des Paramètres (1.3.1, C27) : barre empilée des postes, détail, actions sans risque.

Le calcul (parcours des dossiers) tourne en arrière-plan quand la carte s'affiche, pas au branchement
de la clé ; le résultat est gardé quelques minutes (`core.space.UsageCache`).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QGridLayout, QWidget

from ..core import space
from ..i18n import num, plural, t
from . import theme
from .views.common import human_size
from .widgets import button, hbox, label

log = logging.getLogger(__name__)

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
        # 1.4.3 (C200) : place totale de DJSync sur cet ordinateur, en tête de la carte, avec le détail
        self.footprint = label("", "", wrap=True)
        self.footprint.setObjectName("djsync_footprint")
        self.footprint.hide()
        layout.addWidget(self.footprint)
        self.footprint_detail = label("", "dim", wrap=True)
        self.footprint_detail.hide()
        layout.addWidget(self.footprint_detail)
        self.footprint_music = label("", "", wrap=True)          # 1.4.3-rc.2 (C228) : sons téléchargés, à part
        self.footprint_music.setObjectName("djsync_music")
        self.footprint_music.hide()
        layout.addWidget(self.footprint_music)
        self.footprint_data: Optional[Dict[str, int]] = None
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
        from .widgets import FlowLayout

        self.actions_flow = FlowLayout(spacing=theme.px(6))   # 1.4.2 (A2-1) : actions sous la liste, à la ligne
        layout.addLayout(self.actions_flow)
        self.result = label("", "accent", wrap=True)
        layout.addWidget(self.result)
        self._rows: List[Any] = []
        # 1.4.4 (C222) : une barre par autre disque concerné (disques de l'ordinateur, clés branchées)
        from .widgets import vbox

        self.disks_box = vbox(spacing=theme.px(6))
        layout.addLayout(self.disks_box)
        self.disk_bars: List[Any] = []
        self._disk_widgets: List[Any] = []

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
        self._compute_footprint(force)
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
            self._compute_disks(target, usage, token)
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

    def _compute_disks(self, target: Dict[str, Any], usage: space.Usage, token: int) -> None:
        """1.4.4 (C222) : autres disques de l'ordinateur et autres clés, mesurés en arrière-plan."""
        local = getattr(self.ctrl, "local", None)
        music_dir = getattr(local, "music_dir", None) if local is not None else None
        drives = list(getattr(self.ctrl, "drives", []) or [])

        def work() -> list:
            if target["local"]:
                where = {"analysis": target.get("share"), "databases": target.get("db"),
                         "backups": target["backup"], "caches": Path(target["data"]) / "cache"}
                sizes = {k: usage.parts.get(k, 0) for k in where}
                main = usage.disk or space.drive_of(target["music"])          # déjà montré par la barre du haut
                bars = space.computer_disks(where, usage.music_elsewhere, skip=[main], sizes=sizes)
                skip_usb: list = []
            else:
                bars = space.computer_disks({"music": music_dir, "caches": Path(target["data"]) / "cache"})
                skip_usb = [str(target["root"])]
            return bars + space.usb_disks(drives, getattr(self.ctrl.settings, "contents_dir", "Contents"),
                                          skip=skip_usb)

        def ok(bars: list) -> None:
            if token == self._token:
                self._show_disks(bars)

        self.ctrl.dispatcher.submit(work, ok, lambda exc: log.info("Other disks not measured: %s", exc),
                                    pool="tools")

    def _show_disks(self, bars: list) -> None:
        for w in self._disk_widgets:
            self.disks_box.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._disk_widgets = []
        self.disk_bars = bars
        try:
            if bars:
                head = label(t("space.other_disks"), "section")
                self.disks_box.addWidget(head)
                self._disk_widgets.append(head)
            for b in bars:
                u = b.usage
                kind = t("space.disk_usb") if b.kind == "usb" else t("space.disk_computer")
                text = t("space.disk_title", name=b.title, kind=kind, free=human_size(u.free),
                         total=human_size(u.total))
                title = label(text, "dim", wrap=True)
                bar = SpaceBar()
                bar.set_parts(u.parts)
                bar.setToolTip(" · ".join(f"{t('space.' + k)} {human_size(v)}" for k, v in u.parts.items() if v))
                self.disks_box.addWidget(title)
                self.disks_box.addWidget(bar)
                self._disk_widgets += [title, bar]
                warns = [t(f"space.warn_{w}") for w in u.warnings()]
                if warns:
                    w = label("  ".join(warns), "warn", wrap=True)
                    self.disks_box.addWidget(w)
                    self._disk_widgets.append(w)
        except RuntimeError:                       # carte détruite entre-temps
            log.debug("Space card gone", exc_info=True)

    def _compute_footprint(self, force: bool = False) -> None:
        """1.4.3 (C200) : application, caches, sauvegardes, réglages et sons téléchargés sur l'ordinateur."""
        if self.footprint_data is not None and not force:
            self._show_footprint(self.footprint_data)
            return
        from ..settings import settings_dir

        local = getattr(self.ctrl, "local", None)
        music = getattr(local, "music_dir", None) if local is not None else None
        data = settings_dir()

        def ok(fp: Dict[str, int]) -> None:
            self.footprint_data = fp
            self._show_footprint(fp)

        self.ctrl.dispatcher.submit(lambda: space.djsync_footprint(data, music), ok,
                                    lambda exc: log.info("DJSync footprint not measured: %s", exc), pool="tools")

    def _show_footprint(self, fp: Dict[str, int]) -> None:
        try:
            self.footprint.setText(t("space.footprint", size=human_size(fp.get("total", 0))))
            parts = [t(f"space.fp_{k}", size=human_size(fp.get(k, 0))) for k in space.FOOTPRINT_PARTS]
            self.footprint_detail.setText(" · ".join(parts))
            self.footprint.setToolTip(t("space.footprint_tip"))
            self.footprint.show()
            self.footprint_detail.show()
            music = fp.get("music", 0)
            self.footprint_music.setText(t("space.fp_music_apart", size=human_size(music)))
            self.footprint_music.setToolTip(t("space.fp_music_apart_tip"))
            self.footprint_music.setVisible(bool(music))
        except RuntimeError:                          # carte détruite entre-temps
            log.debug("Footprint label gone", exc_info=True)

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
                     pct=num(100.0 * usage.library / usage.total, ".1f"), other=human_size(usage.parts.get("other", 0)),
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
            self.actions_flow.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._rows = []
        if not usage:
            return
        for row, (key, value) in enumerate(usage.parts.items()):
            dot = label("●", "")
            dot.setStyleSheet(f"color: {PART_COLORS.get(key) or theme.FAINT};")
            name = label(t(f"space.{key}"), "", wrap=True)   # 1.4.4 (C225, A2-1) : à la ligne si étroit (Windows)
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
                b = button("", lambda _c=False, f=folder: self._open(f), kind="flat", icon="folder",
                           tooltip=t("space.open"))                # 1.4.4 (C219, A2-1) : icône seule
                self.grid.addWidget(b, row, col)
                cells.append(b)
            col += 1
            if key in actions:
                text, fn = actions[key]
                b = button(text, fn, kind="flat", icon="trash")
                self.actions_flow.addWidget(b)                  # 1.4.2 (A2-1) : plus dans la grille (trop large)
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
        """1.4.2 (A2-13) : confirmation avec le nombre de points et la place libérée avant de supprimer."""
        def preview(res: Any) -> None:
            n, size = res
            if n <= 0:
                self.result.setText(t("space.trim_none", n=TRIM_KEEP))
                return
            from .dialogs import ConfirmDialog

            ConfirmDialog(self.result.window(), t("space.trim_confirm_title"),
                          plural("space.trim_confirm_one", "space.trim_confirm_many", n, size=human_size(size),
                                 keep=TRIM_KEEP),
                          lambda: self._do_trim(target), confirm_text=t("space.trim_confirm_ok"), danger=True,
                          detail=t("space.trim_confirm_detail"))

        self.ctrl.dispatcher.submit(lambda: space.trim_preview(target["backup"], TRIM_KEEP), preview, self._failed,
                                    pool="tools")

    def _do_trim(self, target: Dict[str, Any]) -> None:
        def done(res: Any) -> None:
            n, freed = res
            self.compute(force=True)
            self.result.setText(t("space.trimmed", n=n, size=human_size(freed)))

        self.ctrl.dispatcher.submit(lambda: space.trim_points(target["backup"], TRIM_KEEP), done, self._failed,
                                    pool="tools")

    def _failed(self, exc: Any) -> None:
        self.result.setText(t("space.failed") + f" ({exc})")
