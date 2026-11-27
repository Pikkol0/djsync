"""Éditeur « Grille et cues » : grille de temps (comme le mode GRID de Rekordbox) et, depuis la 1.3.0
(C22), hot cues A à H, boucles et mémoires (voir `cue_pads.py`).

Pour corriger un décalage observé sur les platines : la forme d'onde détaillée du son (ANLZ) avec
ses temps (1ers temps de mesure plus épais, à la couleur d'accent). On peut :
  * décaler toute la grille (±1, ±10, ±100 ms) ;
  * placer un début de mesure exactement sur le curseur, ou faire du temps sélectionné le 1 ;
  * imposer un BPM, le doubler ou le diviser par 2 (grille constante ancrée sur le temps sélectionné) ;
  * écouter à partir d'un endroit (clic ou glisser sur la forme d'onde : le curseur suit ; en lecture,
    la lecture saute à cet endroit) ;
puis Enregistrer : le .DAT est réécrit (copie d'origine dans DJSync_Backups/anlz), le BPM mis à
jour dans exportLibrary.db et export.pdb.

C'est une PAGE de la fenêtre principale (comme un onglet), ouverte par `DJSyncApp.open_grid_editor` :
changer d'onglet la cache sans perdre les modifications ; « Retour » ou Échap la ferme.
"""
from __future__ import annotations

import logging
import copy
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QLineEdit, QPushButton, QScrollBar, QSizePolicy, QWidget,
)

from ..analysis import grid as G
from ..analysis.cues import Cue, nearest_grid_ms
from ..audio.player import PAUSED, PLAYING
from ..i18n import plural, t
from ..models import LibraryTrack, format_duration
from . import stall, theme
from .cursor import draw_cursor
from .dialogs import ConfirmDialog
from .icons import qicon
from .widgets import button, hbox, icon_button, label, panel, restyle, vbox

log = logging.getLogger(__name__)

COLS_PER_S = 150.0          # forme d'onde détaillée ANLZ : 150 colonnes par seconde
VIEW_CHOICES = (0.5, 1, 2, 4, 8, 16, 32, 64, 120)   # 1.3.2 (B53) : 0,5 s à 2 min (avant 2 à 32 s)
WHEEL_STEP = 120          # 1.3.2 (B53) : un palier de zoom par cran de molette (pavé tactile : par cumul)


# 1.4.1 (C177) : numéro affiché de la première mesure. 0 et non 1 : les débuts de phrase tombent sur les
# multiples de 8 (0, 8, 16…). Affichage seulement : rien de ce qui est écrit (grille, cues) n'en dépend.
FIRST_BAR = 0
MAGNET_DIVISIONS = (0, 1, 4)          # 1.4.1 (C92) : coupé, au temps, au quart de temps


def bar_label(downbeats: int) -> str:
    """Numéro affiché de la mesure dont le premier temps est le `downbeats`-ième de la grille (1 = le premier)."""
    return str(FIRST_BAR + downbeats - 1)



class _SegmentButton(QPushButton):
    """1.4.2 (A2-2) : bouton du décalage (−100 … +100) : au moins 40 px, mais jamais plus étroit que son texte
    (une largeur minimale fixe laissait la mise en page l'écraser : « -10C », « +10C »), à tout zoom."""

    def sizeHint(self) -> Any:  # noqa: N802
        hint = super().sizeHint()
        lines = self.text().count("\n") + 1                  # 1.4.4 (B136) : flèche au-dessus de la valeur
        h = max(hint.height(), self.fontMetrics().lineSpacing() * lines + theme.px(12))
        return QSize(max(hint.width(), theme.px(40)), h)

    def minimumSizeHint(self) -> Any:  # noqa: N802
        return self.sizeHint()

class Zones(QWidget):
    """1.4.1 (C59) : cartes côte à côte, l'une sous l'autre quand la place manque (fenêtre étroite, gros zoom)."""

    def __init__(self, cards: List[QWidget], spacing: int = 8) -> None:
        super().__init__()
        from PySide6.QtWidgets import QBoxLayout

        self.cards = list(cards)
        self.box = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(spacing)
        for c in self.cards:
            self.box.addWidget(c, 1)

    def resizeEvent(self, e: Any) -> None:          # noqa: N802
        from PySide6.QtWidgets import QBoxLayout

        need = sum(c.minimumSizeHint().width() for c in self.cards) + self.box.spacing() * (len(self.cards) - 1)
        want = QBoxLayout.LeftToRight if self.width() >= need else QBoxLayout.TopToBottom
        if self.box.direction() != want:
            self.box.setDirection(want)
        super().resizeEvent(e)


def view_label(v: float) -> str:
    return f"{v:g} s"
# Couleurs de la forme d'onde 3 bandes de Rekordbox (basses, médiums, aigus), quel que soit le thème
BAND_COLORS = ("#1f6fe5", "#f0982c", "#f6ead2")


def band_image(wave: Any, start_ms: float, px_per_ms: float, w: int, h: int, mid: float, scale: float) -> Any:
    """1.3.2-rc.6 (B50) : image (QImage, w × h pixels) de la forme d'onde 3 bandes, calculée en bloc.
    Chaque colonne = maximum des points couverts ; bandes empilées basses, médiums puis aigus devant."""
    import numpy as np
    from PySide6.QtGui import QImage

    if w <= 0 or h <= 0:
        return None
    n = wave.low.size
    xs = np.arange(w + 1, dtype=np.float64)
    pos = (start_ms + xs / px_per_ms) / 1000.0 * wave.rate
    a = np.clip(np.floor(pos[:-1]).astype(np.int64), 0, n - 1)
    b = np.clip(np.maximum(a + 1, np.floor(pos[1:]).astype(np.int64)), 1, n)
    inside = (pos[:-1] < n) & (pos[1:] > 0)
    img = np.zeros((h, w), dtype=np.uint32)              # ARGB32 prémultiplié (opaque ou transparent)
    dy = np.abs(np.arange(h, dtype=np.float32) + 0.5 - np.float32(mid))[:, None]
    for band, color in zip((wave.low, wave.mid, wave.high), BAND_COLORS):
        vals = np.maximum.reduceat(np.append(band, 0), np.append(a, b[-1]))[:-1]
        vals = np.where(inside, vals, 0).astype(np.float32) * np.float32(scale)
        argb = np.uint32(0xFF000000 | int(color[1:], 16))
        img[dy <= vals[None, :]] = argb
    q = QImage(img.data, w, h, w * 4, QImage.Format_ARGB32_Premultiplied)
    return q.copy()                                      # l'image garde ses propres données


_DETAIL_ARRAYS: Dict[Tuple[int, str], Any] = {}


def _detail_arrays(detail: Any, dim: str) -> Any:
    """(hauteurs 0..1, couleurs 0xRRGGBB) de la forme d'onde ANLZ, une fois par forme d'onde (noir -> `dim`)."""
    import numpy as np

    key = (id(detail), dim)
    hit = _DETAIL_ARRAYS.get(key)
    if hit is not None and hit[0] is detail:
        return hit[1], hit[2]
    vals = np.fromiter((float(v) for v, _c in detail), dtype=np.float32, count=len(detail))
    dim_rgb = int(dim[1:7], 16) if dim.startswith("#") and len(dim) >= 7 else 0x808080

    def rgb(c: str) -> int:
        try:
            x = int(str(c)[1:7], 16)
        except ValueError:
            return dim_rgb
        return dim_rgb if x == 0 else x

    cols = np.fromiter((rgb(c) for _v, c in detail), dtype=np.uint32, count=len(detail))
    _DETAIL_ARRAYS.clear()                    # une seule forme d'onde ouverte à la fois
    _DETAIL_ARRAYS[key] = (detail, vals, cols)
    return vals, cols


def detail_image(detail: Any, start_ms: float, px_per_ms: float, w: int, h: int, mid: float, amp: float,
                 dim: str) -> Any:
    """1.4.3-rc.2 (B117) : image (QImage, w × h pixels réels) des formes d'onde Bleu et RGB, comme les 3 bandes.

    Avant : une marche par colonne ANLZ (150 par seconde), sans lissage : au zoom, l'escalier se voyait. Ici,
    zoomé (colonne plus large qu'un pixel), hauteur et couleur interpolées entre les colonnes (contour continu) ;
    dézoomé, le maximum des colonnes couvertes (et sa couleur) ; bords haut et bas antialiasés."""
    import numpy as np
    from PySide6.QtGui import QImage

    if w <= 0 or h <= 0 or not detail:
        return None
    vals, cols = _detail_arrays(detail, dim)
    n = vals.size
    xs = np.arange(w + 1, dtype=np.float64)
    pos = (start_ms + xs / px_per_ms) / 1000.0 * COLS_PER_S          # bords des pixels, en colonnes ANLZ
    per_px = (pos[-1] - pos[0]) / max(1, w)
    r, g, b = ((cols >> 16) & 0xFF).astype(np.float32), ((cols >> 8) & 0xFF).astype(np.float32), \
        (cols & 0xFF).astype(np.float32)
    if per_px < 1.0:                                                   # zoomé : interpolation linéaire
        centre = (pos[:-1] + pos[1:]) / 2.0 - 0.5
        i0 = np.clip(np.floor(centre).astype(np.int64), 0, n - 1)
        i1 = np.clip(i0 + 1, 0, n - 1)
        f = np.clip(centre - np.floor(centre), 0.0, 1.0).astype(np.float32)
        hv = vals[i0] * (1 - f) + vals[i1] * f
        rr, gg, bb = (c[i0] * (1 - f) + c[i1] * f for c in (r, g, b))
        inside = (centre > -1.0) & (centre < n)
    else:                                                              # dézoomé : maximum des colonnes couvertes
        a = np.clip(np.floor(pos[:-1]).astype(np.int64), 0, n - 1)
        e = np.clip(np.maximum(a + 1, np.floor(pos[1:]).astype(np.int64)), 1, n)
        q = (np.clip(vals, 0, 1) * 65535).astype(np.uint64) << np.uint64(24) | cols.astype(np.uint64)
        best = np.maximum.reduceat(np.append(q, np.uint64(0)), np.append(a, e[-1]))[:-1]
        hv = (best >> np.uint64(24)).astype(np.float32) / 65535.0
        c = (best & np.uint64(0xFFFFFF)).astype(np.uint32)
        rr, gg, bb = (((c >> s) & 0xFF).astype(np.float32) for s in (16, 8, 0))
        inside = (pos[:-1] < n) & (pos[1:] > 0)
    half = np.where(inside, np.maximum(1.0, hv * np.float32(amp)), 0.0).astype(np.float32)
    dy = np.abs(np.arange(h, dtype=np.float32) + 0.5 - np.float32(mid))[:, None]
    cover = np.clip(half[None, :] - dy + 0.5, 0.0, 1.0)              # 0..1 : bord antialiasé
    alpha = (cover * 255.0 + 0.5).astype(np.uint32)
    img = (alpha << 24) | ((rr[None, :] * cover + 0.5).astype(np.uint32) << 16) \
        | ((gg[None, :] * cover + 0.5).astype(np.uint32) << 8) | (bb[None, :] * cover + 0.5).astype(np.uint32)
    img = np.ascontiguousarray(img, dtype=np.uint32)
    out = QImage(img.data, w, h, w * 4, QImage.Format_ARGB32_Premultiplied)
    return out.copy()


SCROLL_STEPS = 1000


class GridCanvas(QWidget):
    def __init__(self, editor: "GridEditor") -> None:
        super().__init__()
        self.ed = editor
        self.setMinimumHeight(theme.px(110))        # 1.3.0-rc.3 (B16) : rétrécit avant les pads
        self.setCursor(Qt.CrossCursor)
        self._drag_x: Optional[float] = None
        self._drag_start = 0.0

    paint_ms = 0.0                                  # 1.3.2 (C52) : durée moyenne d'un dessin (cadence adaptée)

    def paintEvent(self, _e: Any) -> None:          # noqa: N802
        import time

        t0 = time.perf_counter()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.SURFACE))
        self.ed.paint(p, self.width(), self.height())
        p.end()
        self.paint_ms = 0.8 * self.paint_ms + 0.2 * (time.perf_counter() - t0) * 1000.0

    def mousePressEvent(self, e: Any) -> None:      # noqa: N802
        """Clic gauche : curseur d'écoute ; clic droit / milieu : faire défiler en glissant."""
        self.setFocus()
        x = e.position().x()
        if e.button() == Qt.LeftButton:
            if self.ed.seg_tools.grab(x, e.position().y(), self.height()):    # 1.4.4 (C221) : poignée d'un repère
                return
            if not self.ed.grab_cue(x, e.position().y()):
                if self.ed.fixed_cursor:              # 1.3.0-rc.3 (B17) : on fait glisser le son sous le curseur
                    self.ed.begin_scrub(x)
                else:
                    self.ed.press(x)
        elif self.ed.fixed_cursor:
            self.ed.begin_scrub(x)
        else:
            self._drag_x, self._drag_start = x, self.ed.start_ms

    def mouseMoveEvent(self, e: Any) -> None:       # noqa: N802
        x = e.position().x()
        if not e.buttons():                           # 1.4.4 (C221) : BPM sous la souris
            self.ed.seg_tools.hover(self.ed._ms(x))
        elif e.buttons() & Qt.LeftButton and self.ed.seg_tools.dragging():
            self.ed.seg_tools.drag(x)
        elif e.buttons() & Qt.LeftButton and self.ed.dragging_cue():
            self.ed.drag_cue(x, bool(e.modifiers() & Qt.ShiftModifier))
        elif self.ed.scrubbing_fixed():
            self.ed.scrub_to(x)
        elif e.buttons() & Qt.LeftButton:
            self.ed.press(x, dragging=True)
        elif self._drag_x is not None and e.buttons() & (Qt.RightButton | Qt.MiddleButton):
            self.ed.start_ms = self._drag_start - (x - self._drag_x) / self.ed.px_per_ms
            self.ed.draw()

    def mouseReleaseEvent(self, e: Any) -> None:    # noqa: N802
        if self.ed.seg_tools.dragging():              # 1.4.4 (C221)
            self.ed.seg_tools.drop()
        elif self.ed.scrubbing_fixed():
            self.ed.end_scrub(e.position().x())
        elif e.button() == Qt.LeftButton:
            if self.ed.dragging_cue():
                self.ed.drop_cue()
            else:
                self.ed.release()
        self._drag_x = None

    def contextMenuEvent(self, e: Any) -> None:     # noqa: N802
        e.accept()                                  # clic droit = défilement, pas de menu

    def leaveEvent(self, _e: Any) -> None:          # noqa: N802
        self.ed.seg_tools.hover(None)               # 1.4.4 (C221)

    def wheelEvent(self, e: Any) -> None:           # noqa: N802
        """1.3.2 (B53) : molette ou glissement vertical du pavé tactile = zoomer (Ctrl / ⌘ + molette aussi) ;
        glissement horizontal ou Maj + molette = défiler dans le son. Avant (C03, 1.2.1) : l'inverse."""
        dx, dy = e.angleDelta().x(), e.angleDelta().y()
        if e.modifiers() & Qt.ShiftModifier:          # Maj + molette : Qt donne parfois le pas en x
            dx, dy = dx or dy, 0
        if dx and abs(dx) > abs(dy):
            self.ed.pan(-0.15 * dx / WHEEL_STEP if abs(dx) < WHEEL_STEP else (-0.15 if dx > 0 else 0.15))
            return
        if not dy:
            return
        self._wheel = getattr(self, "_wheel", 0) + dy
        while abs(self._wheel) >= WHEEL_STEP:          # un palier par cran ; le pavé tactile cumule ses petits pas
            step = -1 if self._wheel > 0 else 1
            self._wheel -= WHEEL_STEP if self._wheel > 0 else -WHEEL_STEP
            self.ed.zoom(step)

    def event(self, e: Any) -> bool:                 # noqa: D401
        from PySide6.QtCore import QEvent

        if e.type() == QEvent.NativeGesture:         # pincement (Mac, pavés tactiles)
            from PySide6.QtCore import Qt as _Qt

            if e.gestureType() == _Qt.ZoomNativeGesture and abs(e.value()) > 0.02:
                self.ed.zoom(-1 if e.value() > 0 else 1)
                return True
        return super().event(e)


COVER_PX = 96                  # 1.4.4 (C215) : pochette de Grille et cues


class WaveStyleBar(QWidget):
    """1.4.4 (C234) : trois petits boutons (3 bandes, Bleu, RGB) posés dans le coin haut droit de la forme d'onde."""

    STYLES = ("3band", "blue", "rgb")

    def __init__(self, canvas: QWidget, current: str, on_pick: Any) -> None:
        super().__init__(canvas)
        self._on_pick = on_pick
        lay = hbox(self, margins=0, spacing=theme.px(2))
        self.buttons = {}
        for st in self.STYLES:
            b = QPushButton(t(f"settings.waveform_{st}"))
            b.setCheckable(True)
            b.setProperty("kind", "flat")
            b.setToolTip(t("grid.wave_style_tip", name=t(f"settings.waveform_{st}")))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            f = b.font()
            f.setPointSizeF(max(6.0, f.pointSizeF() * 0.8))
            b.setFont(f)
            b.clicked.connect(lambda _c=False, x=st: self._pick(x))
            lay.addWidget(b)
            self.buttons[st] = b
        self.setStyleSheet("QPushButton { padding: 1px 6px; border-radius: 4px; background: rgba(0,0,0,110); }"
                           f"QPushButton:checked {{ color: {theme.ON_ACCENT}; background: {theme.ACCENT}; }}")
        self.set_style(current)
        canvas.installEventFilter(self)
        self._place()

    def set_style(self, style: str) -> None:
        for st, b in self.buttons.items():
            b.setChecked(st == style)

    def _pick(self, style: str) -> None:
        self.set_style(style)
        self._on_pick(style)

    def _place(self) -> None:
        self.adjustSize()
        p = self.parentWidget()
        if p is not None:
            self.move(max(0, p.width() - self.width() - theme.px(6)), theme.px(4))
            self.raise_()

    def eventFilter(self, obj: Any, ev: Any) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent

        if ev.type() in (QEvent.Resize, QEvent.Show):
            self._place()
        return False


class HeightGrip(QWidget):
    """1.4.4 (C233) : poignée horizontale sous la forme d'onde ; glisser change sa hauteur, double-clic la remet
    en automatique (place restante)."""

    def __init__(self, editor: "GridEditor") -> None:
        super().__init__()
        self.ed = editor
        self.setFixedHeight(theme.px(8))
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip(t("grid.height_tip"))
        self._y0: Optional[float] = None
        self._h0 = 0

    def paintEvent(self, _e: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = theme.px(36)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.FAINT))
        p.drawRoundedRect((self.width() - w) // 2, (self.height() - theme.px(3)) // 2, w, theme.px(3), 2, 2)
        p.end()

    def mousePressEvent(self, e: Any) -> None:  # noqa: N802
        self._y0 = e.globalPosition().y()
        self._h0 = self.ed.canvas.height()

    def mouseMoveEvent(self, e: Any) -> None:  # noqa: N802
        if self._y0 is None:
            return
        h = self._h0 + (e.globalPosition().y() - self._y0)
        self.ed.set_wave_height(int(round(h / theme.zoom())), save=False)

    def mouseReleaseEvent(self, _e: Any) -> None:  # noqa: N802
        if self._y0 is not None:
            self._y0 = None
            self.ed.set_wave_height(self.ed._wave_height)

    def mouseDoubleClickEvent(self, _e: Any) -> None:  # noqa: N802
        self.ed.set_wave_height(0)


class GridEditor(QWidget):
    """Page « Grille de temps » (dans la zone de contenu de la fenêtre principale)."""

    def __init__(self, parent: Any, controller: Any, track: LibraryTrack, on_close: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.ctrl, self.track = controller, track
        self._on_close = on_close
        self._closed = False
        self.original: List[Tuple[int, int, int]] = []
        self.beats: List[Tuple[int, int, int]] = []
        self.detail: List[Tuple[float, str]] = []
        self.wave: Any = None                  # BandWave fine (calculée depuis l'audio), sinon ANLZ
        self._wave_state = "loading"           # loading | ready | failed (ANLZ affichée seulement si échec)
        self.duration_ms = max(1, track.duration_seconds * 1000)
        self.view_s = 8
        self.start_ms = 0.0
        self.cursor_ms = 0.0
        self.selected = 0
        self.cues: List[Cue] = []              # 1.3.0 (C22) : hot cues, boucles, mémoires
        self.original_cues: List[Cue] = []
        self.active_loop: Optional[Tuple[int, int]] = None
        self._drag_cue: Optional[Cue] = None
        self._native = False
        self._scrubbing = False
        self._scrub: Optional[Tuple[float, float, bool]] = None    # (x de départ, curseur de départ, a bougé)
        # 1.3.0-rc.3 (B17) : curseur volant par défaut (il suit la souris sur une vue fixe) ; case « Curseur
        # fixe au centre » : le son défile sous un curseur immobile, comme Rekordbox. Choix gardé.
        self.fixed_cursor = bool(getattr(controller.settings, "grid_fixed_cursor", False))
        magnet = int(getattr(controller.settings, "grid_magnet", 0) or 0)   # 1.4.1 (C92)
        self.magnet = magnet if magnet in MAGNET_DIVISIONS else 0
        self._label_top, self._label_bottom = 14, 32               # bande des étiquettes (B16, recalculée au dessin)
        self._lead_ms = self._timeline_lead(track)
        self._kick1: Optional[float] = None     # 1.4.2 (C194) : 1er kick posé, en attente du second
        # 1.4.2 (C212) : page dans une zone qui défile (1.4.3-rc.2 : aussi à l'horizontale, fenêtre étroite).
        # Fenêtre trop basse (ou zoom fort) : la page garde la hauteur minimale de chaque bloc et une barre de défilement apparaît, au lieu de tasser les
        # blocs les uns sur les autres (boutons de la grille, du tempo et des mémoires superposés).
        from PySide6.QtWidgets import QFrame, QScrollArea

        outer = vbox(self)
        self.page_area = QScrollArea()
        self.page_area.setWidgetResizable(True)
        self.page_area.setFrameShape(QFrame.NoFrame)
        self.page_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)     # 1.4.3-rc.2 (C212) : aussi en largeur
        inner = QWidget()
        inner.setObjectName("grid_inner")
        self.body = vbox(inner, margins=theme.px(18), spacing=theme.px(8))
        self.page_area.setWidget(inner)
        outer.addWidget(self.page_area)

        head = hbox()
        head.addWidget(button(t("grid.back"), self.close, kind="flat", icon="back"))
        # 1.4.4 (C215) : pochette du son, en grand, à côté du titre
        from PySide6.QtWidgets import QLabel

        self.cover = QLabel()
        self.cover.setFixedSize(theme.px(COVER_PX), theme.px(COVER_PX))
        self.cover.setScaledContents(True)
        head.addWidget(self.cover)
        self._load_cover(track)
        titles = vbox(spacing=0)
        titles.addWidget(label(track.display_name, "title"))
        self.info = label(t("grid.loading"), "dim")
        titles.addWidget(self.info)
        head.addLayout(titles, 1)
        head.addWidget(label(t("grid.view"), "dim"))
        self.view_menu = QComboBox()
        self.view_menu.addItems([view_label(v) for v in VIEW_CHOICES])
        self.view_menu.setCurrentText(view_label(self.view_s))
        self.view_menu.currentTextChanged.connect(self._view_changed)
        head.addWidget(self.view_menu)
        head.addWidget(icon_button("minus", lambda: self.zoom(1), t("grid.zoom_out")))
        head.addWidget(icon_button("plus", lambda: self.zoom(-1), t("grid.zoom_in")))
        self.body.addLayout(head)

        # 1.3.0-rc.3 (B20) : son dont le fichier audio est introuvable
        self.missing = label(t("grid.file_missing"), "err", wrap=True)
        self.missing.setVisible(bool(controller.file_missing(track)))
        self.missing.setProperty("role", "err")
        self.body.addWidget(self.missing)
        # 1.4.3 (C16) : son au tempo qui change : à vérifier passage par passage, puis valider (« Grille juste »)
        self.tempo_banner = label("", "chip_warn", wrap=True)
        self.tempo_banner.hide()
        self.body.addWidget(self.tempo_banner)
        # 1.4.4 (B125) : 1er temps de la mesure à vérifier : choix entre les 4 temps d'une mesure, d'un clic, avec
        # écoute depuis chaque temps (lecteur de la page) ; seul le numéro des temps change, jamais leur position
        self._db_pending = self._downbeat_service_call("downbeat_pending", False)
        self._db_picked = False
        self._db_base = 0
        self._build_downbeat_box()
        self.canvas = GridCanvas(self)
        self.canvas.setFocusPolicy(Qt.ClickFocus)
        self.canvas.setMouseTracking(True)                       # 1.4.4 (C221) : BPM sous la souris
        self.body.addWidget(self.canvas, 1)
        # 1.4.4 (C221) : passages et repères (bande sous la forme d'onde, carte « Changements de tempo »)
        from .tempo_segments import SegmentTools

        self.seg_tools = SegmentTools(self)
        # 1.4.4 (C234) : type de forme d'onde changé d'ici (3 bandes, bleu, RGB), discret, coin haut droit
        self.style_bar = WaveStyleBar(self.canvas, self.wave_style, self.set_wave_style)
        # 1.4.4 (C219) : l'aide de la forme d'onde derrière un ⓘ (plus de bulle à chaque survol de la forme d'onde)
        from .widgets import InfoDot

        self.canvas_help = InfoDot(t("grid.hint"))
        self.style_bar.layout().insertWidget(0, self.canvas_help)
        self.style_bar._place()
        # 1.4.4 (C233) : barre à faire glisser sous la forme d'onde (hauteur gardée ; double-clic : automatique)
        self.height_grip = HeightGrip(self)
        self.body.addWidget(self.height_grip)
        self._apply_wave_height(int(getattr(controller.settings, "grid_wave_height", 0) or 0))
        self.scroll = QScrollBar(Qt.Horizontal)
        self.scroll.setRange(0, SCROLL_STEPS)
        self.scroll.valueChanged.connect(self._scrolled)
        from .cursor import FrameMeter, Monotonic

        self._mono = Monotonic()                    # 1.3.2 (C52)
        self._meter = FrameMeter("beat grid")
        self.scroll.hide()            # 1.3.2 (C51) : remplacée par la vue d'ensemble, qui navigue aussi
        self.body.addWidget(self.scroll)
        from .grid_overview import GridOverview

        # 1.3.2 (C51) : vue d'ensemble du son ici, entre la forme d'onde zoomée et les hot cues (elle était
        # dans la barre du lecteur) : cliquer ou glisser déplace la vue et la lecture
        self.overview = GridOverview()
        self.overview.set_editor(self)
        self.body.addWidget(self.overview)
        self.body.addWidget(self.seg_tools.band)        # 1.4.4 (B131) : bande fine sous la vue d'ensemble

        # 1.4.1 (C59) : bas de page en zones : barre de lecture (sous la forme d'onde), hot cues, puis deux cartes
        # « Grille » et « Tempo » côte à côte (l'une sous l'autre si la fenêtre est étroite), barre d'enregistrement
        play = hbox(spacing=theme.px(8))
        self.play_btn = icon_button("play", self._play, t("grid.play_tip"), color=theme.ON_ACCENT)
        self.play_btn.setProperty("kind", "primary")
        self.play_btn.setFixedSize(theme.px(40), theme.px(40))     # 1.3.2-rc.2 (B46) : rond à tout zoom
        play.addWidget(self.play_btn)
        # 1.3.0-rc.3 (C40) : sortir de la boucle sans coupure (« Loop Exit » des platines)
        self.exit_btn = button(t("grid.loop_exit"), self.exit_loop, kind="primary", icon="next",
                               tooltip=t("grid.loop_exit_tip"))
        self.exit_btn.hide()
        play.addWidget(self.exit_btn)
        self.time_lbl = label("0:00.000", "dim")
        self.time_lbl.setMinimumWidth(theme.px(64))
        play.addWidget(self.time_lbl)
        play.addWidget(self.seg_tools.live_lbl)                  # 1.4.4 (C221) : BPM au curseur et sous la souris
        play.addStretch(1)
        # 1.4.1 (C92) : aimant (comme le Quantize de Rekordbox) : curseur et cues calés sur la grille
        self.magnet_box = QCheckBox(t("grid.magnet"))
        self.magnet_box.setToolTip(t("grid.magnet_tip"))
        self.magnet_box.setChecked(bool(self.magnet))
        self.magnet_menu = QComboBox()
        self.magnet_menu.addItems([t("grid.magnet_beat"), t("grid.magnet_quarter")])
        self.magnet_menu.setCurrentIndex(1 if self.magnet == 4 else 0)
        self.magnet_menu.setEnabled(bool(self.magnet))
        self.magnet_menu.setToolTip(t("grid.magnet_tip"))
        self.magnet_box.toggled.connect(self._magnet_changed)
        self.magnet_menu.currentIndexChanged.connect(self._magnet_changed)
        play.addWidget(self.magnet_box)
        play.addWidget(self.magnet_menu)
        play.addSpacing(theme.px(12))
        self.fixed_box = QCheckBox(t("grid.fixed_cursor"))
        self.fixed_box.setToolTip(t("grid.fixed_cursor_tip"))
        self.fixed_box.setChecked(self.fixed_cursor)
        self.fixed_box.toggled.connect(self._set_fixed)
        play.addWidget(self.fixed_box)
        self._magnet_enable()
        self.body.addLayout(play)

        from .cue_pads import CuePanel

        self.cue_panel = CuePanel(self)

        # carte « Grille » : décaler (contrôle segmenté), demi-temps, premier temps
        grid_card = panel()
        gv = vbox(grid_card, margins=theme.px(10), spacing=theme.px(6))
        # 1.4.4 (C237) : dans l'ordre du travail : 1er temps (kicks, début de mesure), puis ajustement
        gv.addWidget(label(t("grid.first_beat_title"), "section"))
        # 1.4.2 (B111) : la rangée passe sur deux lignes quand la largeur manque (les boutons se chevauchaient)
        from .widgets import FlowLayout

        bar_row_box = QWidget()
        bar_row_box.setProperty("role", "row")
        bar_row = FlowLayout(bar_row_box, spacing=theme.px(6))
        bar_row.addWidget(button(t("grid.bar_here"), self._bar_here, icon="grid", tooltip=t("grid.bar_here_tip")))
        bar_row.addWidget(button(t("grid.downbeat"), self._downbeat, tooltip=t("grid.downbeat_tip")))
        gv.addWidget(bar_row_box)
        gv.addWidget(label(t("grid.adjust_title"), "section"))

        # 1.4.4 (B136) : « Décaler la grille » au-dessus, puis une seule rangée −100 … +100 et ½ temps ; une flèche
        # par pas (double, simple, fine) au-dessus de la valeur signée
        self.shift_box = QWidget()
        self.shift_box.setProperty("role", "row")
        shift = vbox(self.shift_box, spacing=theme.px(4))
        shift.addWidget(label(t("grid.shift"), "dim"))
        segments = QWidget()
        segments.setProperty("role", "row")
        seg = hbox(segments, spacing=0)
        self._shift_btns = []
        glyphs = {-100: "\u226a", -10: "\u2039", -1: "\u2190", 1: "\u2192", 10: "\u203a", 100: "\u226b"}
        for i, ms in enumerate((-100, -10, -1, 1, 10, 100)):
            b = _SegmentButton(glyphs[ms] + "\n" + f"{ms:+d}".replace("-", "−"))
            b.clicked.connect(lambda _=False, m=ms: self._shift(m))
            b.setToolTip(t("grid.shift_tip", ms=ms))
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("segment", "first" if i == 0 else "middle")
            self._shift_btns.append(b)
            seg.addWidget(b)
        self.half_btn = _SegmentButton(t("grid.half_beat_short"))
        self.half_btn.clicked.connect(lambda _=False: self._shift_half())
        self.half_btn.setToolTip(t("grid.half_beat_tip"))
        self.half_btn.setCursor(Qt.PointingHandCursor)
        self.half_btn.setProperty("segment", "last")
        seg.addWidget(self.half_btn)
        seg.addStretch(1)
        shift.addWidget(segments)
        gv.addWidget(self.shift_box)
        # carte « Tempo » : ÷ 2 [BPM] × 2, Appliquer ; × 2/3, × 3/2
        tempo_card = panel()
        tv = vbox(tempo_card, margins=theme.px(10), spacing=theme.px(6))
        tv.addWidget(label(t("grid.zone_tempo"), "section"))
        bpm_row_box = QWidget()
        bpm_row_box.setProperty("role", "row")
        bpm_row = FlowLayout(bpm_row_box, spacing=theme.px(4))
        bpm_row.addWidget(button(t("grid.half"), lambda: self._scale(0.5), tooltip=t("grid.half_tip")))
        self.bpm_entry = QLineEdit()
        self.bpm_entry.setFixedWidth(theme.px(78))
        self.bpm_entry.setAlignment(Qt.AlignCenter)
        self.bpm_entry.setToolTip(t("grid.bpm_entry_tip"))
        self.bpm_entry.returnPressed.connect(self._apply_bpm)
        bpm_row.addWidget(self.bpm_entry)
        bpm_row.addWidget(button(t("grid.double"), lambda: self._scale(2.0), tooltip=t("grid.double_tip")))
        bpm_row.addWidget(button(t("grid.apply_bpm_short"), self._apply_bpm, icon="check",
                                 tooltip=t("grid.apply_bpm_tip")))
        tv.addWidget(bpm_row_box)
        # 1.4.4 (C242) : × 2/3 et × 3/2 retirés (devenus très rares) ; deux kicks : le 1er se replace à volonté,
        # le 2e (n'importe où plus loin) donne le BPM et réécrit la grille (C194)
        kick_row_box = QWidget()
        kick_row_box.setProperty("role", "row")
        kick_row = FlowLayout(kick_row_box, spacing=theme.px(4))
        self.kick_btn = button(t("grid.kick1"), self._kick_first, icon="grid", tooltip=t("grid.kick1_tip"))
        self.kick2_btn = button(t("grid.kick2"), self._kick_second, icon="grid", tooltip=t("grid.kick2_tip"))
        self.kick2_btn.setEnabled(False)
        kick_row.addWidget(self.kick_btn)
        kick_row.addWidget(self.kick2_btn)
        tv.addWidget(kick_row_box)
        self.kick_hint = label("", "dim", wrap=True)
        self.kick_hint.hide()
        tv.addWidget(self.kick_hint)
        # 1.4.3 (C16) : grille fixe (un seul tempo) <-> grille par passage trouvée par l'analyse
        mode_row = hbox(spacing=theme.px(4))
        self.fixed_grid_btn = button(t("grid.fixed_grid"), self._fixed_grid, icon="grid")
        self.split_grid_btn = button(t("grid.split_grid"), self._split_grid, icon="wave",
                                     tooltip=t("grid.split_grid_tip"))
        mode_row.addWidget(self.fixed_grid_btn)
        mode_row.addWidget(self.split_grid_btn)
        mode_row.addStretch(1)
        tv.addLayout(mode_row)
        self.fixed_grid_btn.hide()
        self.split_grid_btn.hide()

        # 1.4.4 (C237) : onglets Grille | Tempo | Cues sous la forme d'onde, un seul visible (le dernier ouvert est
        # gardé) ; « Appliquer à » (B131) au-dessus quand le son a plusieurs passages
        self._build_tabs(grid_card, tempo_card)

        # barre d'enregistrement : à gauche l'état et « Annuler les modifications », à droite Retour et Enregistrer
        bar = hbox(spacing=theme.px(8))
        self.state_lbl = label("", "chip_warn")
        self.state_lbl.hide()
        bar.addWidget(self.state_lbl)
        self.reset_btn = button(t("grid.reset"), self._reset, kind="flat", icon="refresh")
        bar.addWidget(self.reset_btn)
        bar.addStretch(1)                       # 1.4.4 (C237) : un seul Retour (en haut)
        # 1.4.2 (C204) : marquer la grille « vérifiée » sans rien y changer
        self.checked_btn = button(t("grid.checked_btn"), self._grid_ok, icon="check", tooltip=t("grid.checked_tip"))
        self._grid_marked = bool(getattr(self.ctrl, "grid_checked", lambda _i: False)(self.track.content_id))
        bar.addWidget(self.checked_btn)
        self.save_btn = button(t("action.save"), self._save, kind="primary", icon="check")
        self.save_btn.setEnabled(False)
        bar.addWidget(self.save_btn)
        self.body.addLayout(bar)

        for seq, fn in ((Qt.Key_Left, lambda: self._shift(-1)), (Qt.Key_Right, lambda: self._shift(1)),
                        (Qt.Key_Escape, self.close)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda f=fn: f() if not self.bpm_entry.hasFocus() else None)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)           # 1.3.2-rc.3 (B50) : minuteur précis sous Windows
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)
        self._play_icon_state: Any = None
        controller.load_grid(track.content_id, self._loaded, self._load_failed)
        controller.on("waveform_style", self._style_changed)               # 1.4.1 (C77)
        controller.grid_editor = self                # 1.3.0-rc.4 (B20) : le bouton Lecture du bas joue CE son
        controller._emit("grid_page", self)          # 1.3.0-rc.3 (B17) : le lecteur passe en forme d'onde 3 bandes

    # ---------------------------------------------------------- 1.4.4 (C237) : onglets Grille | Tempo | Cues
    # 1.4.4 (B136, C242) : deux onglets, Tempo (grille, BPM et passages en trois panneaux) et Cues ; la ligne des
    # onglets ne bouge plus (« Outils appliqués à » à droite, place gardée même caché)
    TABS = ("tempo", "cues")

    def _build_tabs(self, grid_card: QWidget, tempo_card: QWidget) -> None:
        from PySide6.QtWidgets import QStackedWidget

        bar = QWidget()
        bar.setObjectName("grid_tabs")
        row = hbox(bar, spacing=theme.px(4))
        self.tab_btns: Dict[str, Any] = {}
        for key, icon in zip(self.TABS, ("wave", "key")):
            b = button(t(f"grid.tab_{key}"), lambda _c=False, k=key: self.show_tab(k), icon=icon)
            b.setCheckable(True)
            b.setProperty("kind", "tab")
            row.addWidget(b)
            self.tab_btns[key] = b
        row.addStretch(1)
        scope = self.seg_tools.scope_box
        sp = scope.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        scope.setSizePolicy(sp)
        row.addWidget(scope)
        self.tabs_bar = bar
        self.body.addWidget(bar)
        self.zones = QStackedWidget()
        self.zones.setObjectName("grid_pages")
        tempo_page = QWidget()
        tv = vbox(tempo_page, spacing=theme.px(8))
        for card in (grid_card, tempo_card):
            card.layout().addStretch(1)                    # contenu en haut, pas étiré sur la hauteur
        self.tempo_zones = Zones([grid_card, tempo_card, self.seg_tools.card], spacing=theme.px(8))
        for k, f in enumerate((10, 9, 12)):
            self.tempo_zones.box.setStretch(k, f)
        tv.addWidget(self.tempo_zones)
        tv.addStretch(1)
        cues_page = QWidget()
        cv = vbox(cues_page, spacing=0)
        cv.addWidget(self.cue_panel)
        cv.addStretch(1)
        self._tab_pages = {"tempo": tempo_page, "cues": cues_page}
        for key in self.TABS:
            self.zones.addWidget(self._tab_pages[key])
        self.body.addWidget(self.zones)
        self.show_tab(str(getattr(self.ctrl.settings, "grid_tab", "tempo") or "tempo"), remember=False)

    def show_tab(self, key: str, remember: bool = True) -> None:
        if key not in self.TABS:
            key = "tempo"                                  # ancien onglet « grid » : réuni dans Tempo
        self.current_tab = key
        for k, b in self.tab_btns.items():
            b.setChecked(k == key)
        self.zones.setCurrentWidget(self._tab_pages[key])
        # la page prend la hauteur de son contenu (un onglet court ne garde pas la hauteur du plus long)
        for k, w in self._tab_pages.items():
            w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if k == key else QSizePolicy.Ignored)
        self.zones.adjustSize()
        self.seg_tools.scope_box.setVisible(key != "cues" and self.seg_tools.multi())
        if remember and getattr(self.ctrl.settings, "grid_tab", "") != key:
            self.ctrl.settings.grid_tab = key
            save = getattr(self.ctrl, "save_settings_quiet", None)
            if save is not None:
                save()

    def _set_beats(self, new: Optional[List[Any]], at_ms: Optional[float] = None) -> bool:
        """1.4.4 (B131) : grille d'un outil, appliquée au passage sous le curseur (ou à tout le son)."""
        if not new:
            return False
        kept = self.seg_tools.apply_scoped(list(new), at_ms)
        if kept:
            self.beats = kept
        return bool(kept)

    # ---------------------------------------------------------- 1er temps à vérifier (1.4.4, B125)
    def _downbeat_service_call(self, name: str, default: Any, *args: Any) -> Any:
        svc = getattr(self.ctrl, "tempo_grids", None)
        fn = getattr(svc, name, None) if svc is not None else None
        if fn is None:
            return default
        try:
            return fn(self.track, *args)
        except Exception:  # noqa: BLE001 - simple aide au réglage
            log.debug("Handled error in %s", name, exc_info=True)
            return default

    def _build_downbeat_box(self) -> None:
        from .widgets import FlowLayout

        self.downbeat_box = QWidget()
        self.downbeat_box.setProperty("role", "row")
        dv = vbox(self.downbeat_box, spacing=theme.px(4))
        self.downbeat_banner = label(t("grid.downbeat_check"), "chip_warn", wrap=True)
        dv.addWidget(self.downbeat_banner)
        row = QWidget()
        row.setProperty("role", "row")
        flow = FlowLayout(row, spacing=theme.px(8))
        self.downbeat_picks: List[QPushButton] = []
        self.downbeat_listens: List[Any] = []
        for k in range(4):
            cell = QWidget()
            cell.setProperty("role", "row")
            h = hbox(cell, spacing=theme.px(2))
            lis = icon_button("play", lambda q=k: self._downbeat_listen(q), t("grid.downbeat_listen_tip", n=k + 1))
            pick = button(t("grid.downbeat_pick", n=k + 1), lambda q=k: self._downbeat_pick(q),
                          tooltip=t("grid.downbeat_pick_tip"))
            h.addWidget(lis)
            h.addWidget(pick)
            self.downbeat_listens.append(lis)
            self.downbeat_picks.append(pick)
            flow.addWidget(cell)
        dv.addWidget(row)
        self.downbeat_box.hide()
        self.body.addWidget(self.downbeat_box)

    def _downbeat_setup(self) -> None:
        """Les 4 temps proposés : la mesure (selon l'analyse) où entrent les basses le plus nettement."""
        if not self.beats:
            return
        at = float(self._downbeat_service_call("downbeat_at", -1.0))
        if at >= 0:
            i = G.nearest(self.beats, at * 1000.0)
        else:
            i = next((k for k, b in enumerate(self.beats) if b[0] == 1), 0)
        i -= (self.beats[i][0] - 1) % 4                       # 1er temps de cette mesure
        self._db_base = max(0, min(i, len(self.beats) - 4))

    def _downbeat_index(self, k: int) -> int:
        return max(0, min(self._db_base + k, len(self.beats) - 1))

    def _downbeat_listen(self, k: int) -> None:
        if not self.beats:
            return
        self.selected = self._downbeat_index(k)
        self.play_from(self.beats[self.selected][2])

    def _downbeat_pick(self, k: int) -> None:
        """Ce temps devient le 1er de la mesure ; la grille ne bouge pas. Choix fait : plus « à vérifier »."""
        if not self.beats:
            return
        i = self._downbeat_index(k)
        self.beats = G.set_downbeat(self.beats, i)
        self.selected = i
        self._db_picked = True
        if self.beats == self.original:                     # le choix de l'analyse : rien à enregistrer
            self._downbeat_resolved()
        self._refresh_info()
        self.draw()

    def _downbeat_resolved(self) -> None:
        if self._db_pending:
            self._downbeat_service_call("downbeat_done", False)
        self._db_pending = False

    def _refresh_downbeat(self) -> None:
        box = getattr(self, "downbeat_box", None)
        if box is None:
            return
        shown = bool(self.beats) and (self._db_pending or self._db_picked)
        box.setVisible(shown)
        if not shown:
            return
        unsaved = self._db_picked and self.beats != self.original
        if self._db_pending and not self._db_picked:
            text, role = t("grid.downbeat_check"), "chip_warn"
        elif unsaved:
            text, role = t("grid.downbeat_chosen"), "chip_ok"
        else:
            text, role = t("grid.downbeat_checked"), "chip_ok"
        self.downbeat_banner.setText(text)
        if self.downbeat_banner.property("role") != role:
            self.downbeat_banner.setProperty("role", role)
            restyle(self.downbeat_banner)
        for k, b in enumerate(self.downbeat_picks):
            kind = "primary" if self.beats[self._downbeat_index(k)][0] == 1 else ""
            if (b.property("kind") or "") != kind:
                b.setProperty("kind", kind)
                restyle(b)

    def _timeline_lead(self, track: LibraryTrack) -> float:
        """La grille est dans la base de temps de Rekordbox (silence d'amorçage MP3, décalage m4a), le
        lecteur joue le fichier sans ce silence : on en tient compte pour le curseur et la lecture."""
        try:
            from ..analysis.decode import timeline_lead_seconds

            return timeline_lead_seconds(self.ctrl.library.absolute_path(track)) * 1000.0
        except Exception:  # noqa: BLE001
            log.debug("Handled error in _timeline_lead", exc_info=True)  # 1.4.3 (A3-4)
            return 0.0

    def _player_seek(self, ms: float, flush: bool = True) -> None:
        # flush=False pour le retour au début d'une boucle : décidé en avance, il doit passer après ce
        # que la carte son a déjà en réserve (rc.5, C39)
        self._mono.reset()                         # 1.3.2 (C52) : saut voulu, la position peut reculer
        self.ctrl.player.seek(max(0.0, (ms - self._lead_ms) / 1000.0), flush=flush)

    # 1.3.0-rc.8 (B31) : la page reste ouverte quand on change d'onglet (modifications gardées) ; le
    # lecteur du bas ne la suit que lorsqu'elle est affichée (forme d'onde, bouton Lecture)
    def showEvent(self, event: Any) -> None:  # noqa: N802
        super().showEvent(event)
        self._tell_player(self)

    def hideEvent(self, event: Any) -> None:  # noqa: N802
        super().hideEvent(event)
        self._tell_player(None)

    def _tell_player(self, page: Any) -> None:
        from PySide6.QtWidgets import QApplication

        if self._closed or QApplication.closingDown() or not self.window().isVisible() and page is None:
            return                                   # fermeture de l'appli : le lecteur n'existe peut-être plus
        try:
            self.ctrl._emit("grid_page", page)
        except RuntimeError:                         # lecteur déjà détruit
            pass

    def winfo_exists(self) -> bool:
        from shiboken6 import isValid

        return not self._closed and isValid(self)

    # ------------------------------------------------------------------ chargement
    def _loaded(self, data: Any) -> None:
        if not self.winfo_exists():
            return
        g = data["grid"]
        self.original = list(g.beats)
        self.beats = list(g.beats)
        self.detail = data["detail"]
        self._band_fallback = data.get("band")      # B21 : 3 bandes de Rekordbox si le fichier est introuvable
        self.duration_ms = max(g.duration_ms, g.beats[-1][2] + 1000, int(len(self.detail) / COLS_PER_S * 1000))
        self._native = g.native
        self.cues = copy.deepcopy(list(data.get("cues") or []))
        self.original_cues = copy.deepcopy(self.cues)
        self.cue_panel.refresh()
        self.selected = next((i for i, b in enumerate(self.beats) if b[0] == 1), 0)
        self.cursor_ms = self.beats[self.selected][2]
        self.start_ms = max(0.0, self.cursor_ms - 1000)
        self._downbeat_setup()                       # 1.4.4 (B125)
        self._center()
        self._refresh_info()
        self._show_style()

    @property
    def wave_style(self) -> str:
        return getattr(self.ctrl.settings, "waveform_style", "3band") or "3band"

    def _show_style(self) -> None:
        """1.4.1 (C77) : un seul rendu dès l'ouverture, dans le type choisi (Paramètres ▸ Analyse), lu dans les
        fichiers d'analyse : Bleu (PWV3), RGB (PWV5) ou 3 bandes (PWV7 du .2EX). En 3 bandes, la forme d'onde
        fine calculée depuis le son remplace ensuite celle du fichier, mêmes couleurs (avant : RGB puis
        3 bandes, C77)."""
        if self.wave_style != "3band":
            self.wave = None
            self._wave_state = "ready"
            self.draw()
            return
        from ..analysis.anlz import band_from_detail

        self.wave = getattr(self, "_band_fallback", None) or band_from_detail(self.detail)
        self._wave_state = "loading"
        self.draw()
        self.ctrl.load_grid_wave(self.track, self._wave_loaded)

    def _load_cover(self, track: LibraryTrack) -> None:
        """1.4.4 (C215) : pochette de la bibliothèque (ou intégrée au fichier), lue en arrière-plan."""
        from pathlib import Path

        from ..audio.covers import placeholder
        from .covers import CoverLoader, file_cover
        from .icons import to_qpixmap

        size = theme.px(COVER_PX) * 2
        self.cover.setPixmap(to_qpixmap(placeholder(size)))
        lib = self.ctrl.library
        if lib is None:
            return
        try:
            art = lib.artwork_file(track)
            path = lib.absolute_path(track)
        except Exception:  # noqa: BLE001 - pas de pochette : l'image par défaut reste
            log.debug("No cover for grid editor", exc_info=True)
            return

        def show(img: Any) -> None:
            if img is not None and self.winfo_exists():
                self.cover.setPixmap(to_qpixmap(img))

        CoverLoader(self.ctrl.dispatcher).load_pil(file_cover(Path(art) if art else None, Path(path),
                                                              f"grid:{track.content_id}"), size, show)

    def set_wave_style(self, style: str) -> None:
        """1.4.4 (C234) : même réglage que Paramètres ▸ Analyse (lecteur et Paramètres suivent)."""
        if style == self.wave_style or style not in ("3band", "blue", "rgb"):
            return
        self.ctrl.settings.waveform_style = style
        self.ctrl.save_settings_quiet()
        self.ctrl._emit("waveform_style")

    # ------------------------------------------------------------ 1.4.4 (C233) : hauteur de la forme d'onde
    WAVE_MIN, WAVE_MAX = 80, 600

    def _apply_wave_height(self, h: int) -> None:
        """0 : automatique (la forme d'onde prend la place restante) ; sinon hauteur fixe (px à 100 %)."""
        if h <= 0:
            self.canvas.setMinimumHeight(theme.px(110))
            self.canvas.setMaximumHeight(16777215)
        else:
            h = max(self.WAVE_MIN, min(self.WAVE_MAX, h))
            self.canvas.setFixedHeight(theme.px(h))
        self._wave_height = h

    def set_wave_height(self, h: int, save: bool = True) -> None:
        self._apply_wave_height(h)
        if save:
            self.ctrl.settings.grid_wave_height = self._wave_height
            self.ctrl.save_settings_quiet()

    def _style_changed(self, *_a: Any) -> None:
        """Type de forme d'onde changé dans les Paramètres : relu tout de suite, sans toucher aux modifications."""
        if hasattr(self, "style_bar"):
            self.style_bar.set_style(self.wave_style)
        if not self.winfo_exists() or not self.beats:
            return

        def reloaded(data: Any) -> None:
            if not self.winfo_exists():
                return
            self.detail = data["detail"]
            self._band_fallback = data.get("band")
            self._band_cache = None
            self._show_style()

        self.ctrl.load_grid(self.track.content_id, reloaded, lambda _e: None)

    def _wave_loaded(self, wave: Any) -> None:
        if not self.winfo_exists():
            return
        if self.wave_style != "3band":               # type changé pendant le calcul
            return
        if wave is None:                             # B21 : fichier introuvable ou illisible
            from ..analysis.anlz import band_from_detail

            wave = getattr(self, "_band_fallback", None) or band_from_detail(self.detail)
        self.wave = wave
        self._wave_state = "ready" if wave is not None else "failed"
        self.draw()

    def _load_failed(self, exc: BaseException) -> None:
        if self.winfo_exists():
            self.info.setText(self.ctrl.error_text(exc))
            self.info.setProperty("role", "err")
            restyle(self.info)

    # ---------------------------------------------------------------- géométrie
    @property
    def px_per_ms(self) -> float:
        return max(1, self.canvas.width()) / (self.view_s * 1000.0)

    def _x(self, ms: float) -> float:
        return (ms - self.start_ms) * self.px_per_ms

    def _ms(self, x: float) -> float:
        return self.start_ms + x / self.px_per_ms

    def _clamp_view(self) -> None:
        span = self.view_s * 1000.0
        if self.fixed_cursor:                # le curseur reste au centre, même au début et à la fin du son
            self.cursor_ms = max(0.0, min(float(self.duration_ms), self.cursor_ms))
            self.start_ms = self.cursor_ms - span / 2
            value = self.cursor_ms / max(1.0, float(self.duration_ms))
        else:
            self.start_ms = max(0.0, min(self.start_ms, max(0.0, self.duration_ms - span)))
            value = self.start_ms / max(1.0, self.duration_ms - span)
        self.scroll.blockSignals(True)
        self.scroll.setValue(int(SCROLL_STEPS * value))
        self.scroll.blockSignals(False)

    def _center(self) -> None:
        if self.fixed_cursor:
            self.start_ms = self.cursor_ms - self.view_s * 500.0

    def _magnet_enable(self) -> None:
        """1.4.1-rc.2 (141-GRI-2) : avec le curseur fixe au centre, on fait glisser le son : l'aimant du curseur
        n'a pas de sens (et gênerait), il est grisé, avec la raison dans la bulle ; le choix reste gardé."""
        fixed = bool(self.fixed_cursor)
        self.magnet_box.setEnabled(not fixed)
        self.magnet_menu.setEnabled(not fixed and self.magnet_box.isChecked())
        tip = t("grid.magnet_fixed_tip") if fixed else t("grid.magnet_tip")
        self.magnet_box.setToolTip(tip)
        self.magnet_menu.setToolTip(tip)

    def _magnet_changed(self, *_args: Any) -> None:
        """1.4.1 (C92) : aimant coupé, au temps ou au quart de temps ; choix gardé."""
        on = self.magnet_box.isChecked()
        self.magnet_menu.setEnabled(on and not self.fixed_cursor)
        self.magnet = (4 if self.magnet_menu.currentIndex() == 1 else 1) if on else 0
        try:
            self.ctrl.settings.grid_magnet = self.magnet
            self.ctrl.settings.save()
        except Exception:  # noqa: BLE001 - réglage de confort
            log.debug("Ignored error in _magnet_changed", exc_info=True)  # 1.4.3 (A3-4)

    def snap_ms(self, ms: float, exact: bool = False, cursor: bool = False) -> float:
        """1.4.1 (C92) : position calée sur la grille. Curseur : seulement si l'aimant est mis. Cue : au temps
        (comme avant) ou au quart de temps si l'aimant est au quart. Alt ou Maj (ou `exact`) : position libre."""
        free = exact or bool(QApplication.keyboardModifiers() & (Qt.AltModifier | Qt.ShiftModifier))
        if free or not self.beats or (cursor and (not self.magnet or getattr(self, "fixed_cursor", False))):   # GRI-2
            return float(ms) if cursor else float(int(round(ms)))
        return float(nearest_grid_ms(self.beats, ms, self.magnet or 1))

    def _set_fixed(self, on: bool) -> None:
        self.fixed_cursor = bool(on)
        try:
            self.ctrl.settings.grid_fixed_cursor = bool(on)
            self.ctrl.settings.save()
        except Exception:  # noqa: BLE001 - réglage de confort
            log.debug("Ignored error in _set_fixed", exc_info=True)  # 1.4.3 (A3-4)
        self._magnet_enable()
        self._center()
        self.draw()

    # -------------------------------------------- curseur fixe : faire glisser le son (B17)
    def begin_scrub(self, x: float) -> None:
        self.active_loop = None
        self._scrub = (x, self.cursor_ms, False)
        self._scrubbing = True

    def scrubbing_fixed(self) -> bool:
        return self._scrub is not None

    def scrub_to(self, x: float) -> None:
        if self._scrub is None:
            return
        x0, c0, moved = self._scrub
        moved = moved or abs(x - x0) > 3
        self._scrub = (x0, c0, moved)
        if moved:
            self._move_cursor(c0 - (x - x0) / self.px_per_ms)

    def end_scrub(self, x: float) -> None:
        if self._scrub is None:
            return
        _x0, _c0, moved = self._scrub
        self._scrub = None
        if not moved:                        # simple clic : ce point vient sous le curseur
            self._move_cursor(self.snap_ms(self._ms(x), cursor=True))
        self.release()

    def _move_cursor(self, ms: float) -> None:
        self.cursor_ms = min(max(0.0, ms), float(self.duration_ms))
        if self.beats:
            self.selected = G.nearest(self.beats, self.cursor_ms)
            self._refresh_info()
        self._center()
        self._show_time()
        self.draw()

    # ------------------------------------------------------------------- dessin
    def draw(self) -> None:
        self.canvas.update()

    def paint(self, p: QPainter, w: int, h: int) -> None:
        if w < 10 or not self.beats:
            return
        self._clamp_view()
        mid = h * 0.55
        if self.wave is not None:
            self._paint_bands_cached(p, w, h, mid)
        elif self._wave_state == "loading":         # pas d'ancienne forme d'onde le temps du calcul
            p.setPen(QColor(theme.FAINT))
            p.drawText(self.canvas.rect(), Qt.AlignCenter, t("grid.wave_loading"))
        elif self.detail:            # 1.4.3 (A1-10) : même image en cache que les 3 bandes
            self._paint_detail_cached(p, w, h, mid)
        lo, hi = self._ms(-2), self._ms(w + 2)
        font = QFont(p.font())
        font.setBold(True)
        p.setFont(font)
        # 1.3.0-rc.3 (B16) : bande du haut à l'échelle de la police, sur deux niveaux : numéros de mesure,
        # puis étiquettes des cues (plus de « B73 ») ; temps de la vue à droite, jamais recouvert
        fm = QFontMetrics(font)
        row = fm.height() + theme.px(2)
        self._label_top, self._label_bottom = row, row + fm.height() + theme.px(4)
        time_text = format_duration(int(max(0.0, self.start_ms) / 1000))
        time_left = w - theme.px(6) - fm.horizontalAdvance(time_text) - theme.px(6)
        bar_no = 0                                             # premiers temps rencontrés
        for i, (n, _tempo, ms) in enumerate(self.beats):
            if n == 1:
                bar_no += 1
            if ms < lo or ms > hi:
                continue
            x = self._x(ms)
            down = n == 1
            color = QColor(theme.ACCENT if down else theme.mix(theme.SURFACE, theme.TEXT, 0.55))
            p.setPen(QPen(color, theme.px(2.5) if down else 1))
            p.drawLine(QPointF(x, row), QPointF(x, h))
            if down and x + 4 + fm.horizontalAdvance(bar_label(bar_no)) < time_left:
                p.drawText(QPointF(x + 4, fm.ascent() + 1), bar_label(bar_no))   # 1.4.1 (C177) : à partir de 0
            if i == self.selected:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.WARN))
                p.drawPolygon(QPolygonF([QPointF(x - 6, h), QPointF(x + 6, h), QPointF(x, h - 10)]))
                p.setBrush(Qt.NoBrush)
        self._paint_tempo_changes(p, w, h, lo, hi)
        self.seg_tools.paint(p, w, h, self._label_bottom)       # 1.4.4 (C221) : repères et poignées
        self._paint_cues(p, w, h)
        if self._kick1 is not None:                               # 1.4.2 (C194) : 1er kick posé
            xk = self._x(self._kick1)
            if -10 <= xk <= w + 10:
                p.setPen(QPen(QColor(theme.WARN), theme.px(2), Qt.DashLine))
                p.drawLine(QPointF(xk, 0), QPointF(xk, h))
                p.drawText(QPointF(xk + 4, h - theme.px(6)), t("grid.kick1_mark"))
        xc = self._x(self.cursor_ms)
        if -10 <= xc <= w + 10:                   # 1.3.2 (C52) : trait rouge vif, net au centre
            draw_cursor(p, xc, 0, h)
        p.setPen(QColor(theme.FAINT))
        p.drawText(self.canvas.rect().adjusted(0, 1, -theme.px(6), 0), Qt.AlignRight | Qt.AlignTop, time_text)

    def _paint_tempo_changes(self, p: QPainter, w: int, h: int, lo: float, hi: float) -> None:
        """1.4.3 (C16) : trait orange et « 122 → 140 » là où le tempo de la grille change (grille par passage)."""
        from .tempo_grids import changes

        if getattr(self, "_changes_of", None) is not self.beats:
            self._changes_cache = changes(self.beats) if len({b[1] for b in self.beats}) > 1 else []
            self._changes_of = self.beats
        marks = self._changes_cache
        if not marks or len(marks) > max(2, len(self.beats) // 16):     # grille variable de live : pas de traits
            return
        fm = QFontMetrics(p.font())
        for i, before, after in marks:
            ms = self.beats[i][2]
            if ms < lo or ms > hi:
                continue
            x = self._x(ms)
            p.setPen(QPen(QColor(theme.WARN), theme.px(2), Qt.DashLine))
            p.drawLine(QPointF(x, self._label_bottom), QPointF(x, h))
            text = f"{before:.1f} → {after:.1f}"
            p.drawText(QPointF(x + 4, self._label_bottom + fm.ascent()), text)

    def _paint_cues(self, p: QPainter, w: int, h: int) -> None:
        """Boucles (bande colorée), hot cues (trait + étiquette de la lettre en haut), mémoires (▼ rouge)."""
        from .cue_pads import rgb_hex

        lo, hi = self._ms(-40), self._ms(w + 2)
        font = QFont(p.font())
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        top, bottom = self._label_top, self._label_bottom
        tag_w = fm.horizontalAdvance("W") + theme.px(6)
        for c in self.cues:
            if c.is_loop and c.loop_ms >= lo and c.ms <= hi:
                col = QColor(rgb_hex(c.colour()))
                col.setAlpha(70 if self.active_loop != (c.ms, c.loop_ms) else 120)
                x0, x1 = max(0.0, self._x(c.ms)), min(float(w), self._x(c.loop_ms))
                p.fillRect(int(x0), bottom, max(1, int(x1 - x0)), h - bottom, col)
        for c in self.cues:
            if c.ms < lo or c.ms > hi:
                continue
            x = self._x(c.ms)
            col = QColor(rgb_hex(c.colour()))
            if c.slot:
                p.setPen(QPen(col, theme.px(2)))
                p.drawLine(QPointF(x, bottom), QPointF(x, h))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRect(int(x), top, tag_w, bottom - top)
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor("#101010"))
                p.drawText(int(x), top, tag_w, bottom - top, Qt.AlignCenter, c.label)
            else:
                k = theme.px(6)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.ERR))
                p.drawPolygon(QPolygonF([QPointF(x - k, top), QPointF(x + k, top), QPointF(x, top + 1.6 * k)]))
                p.setBrush(Qt.NoBrush)

    # ------------------------------------------------------------ cues : glisser
    def grab_cue(self, x: float, y: float) -> bool:
        """Clic sur l'étiquette d'une hot cue (bande du haut) : on la déplace en glissant."""
        if y > self._label_bottom:
            return False
        tag_w = QFontMetrics(self.canvas.font()).horizontalAdvance("W") + theme.px(6)
        near = [c for c in self.cues if c.slot and -3 <= x - self._x(c.ms) <= tag_w + 3]
        if not near:
            return False
        self._drag_cue = near[0]
        return True

    def dragging_cue(self) -> bool:
        return self._drag_cue is not None

    def drag_cue(self, x: float, exact: bool = False) -> None:
        c = self._drag_cue
        if c is None:
            return
        ms = max(0.0, min(float(self.duration_ms), self._ms(x)))
        ms = int(self.snap_ms(ms, exact))                                  # 1.4.1 (C92) : aimant
        if c.is_loop:
            c.loop_ms = ms + (c.loop_ms - c.ms)
        c.ms = ms
        self.cue_panel.refresh()
        self.draw()

    def drop_cue(self) -> None:
        self._drag_cue = None
        self.cues_changed()

    def cues_changed(self) -> None:
        self._refresh_info()
        self.draw()

    def cues_dirty(self) -> bool:
        def sig(cs: List[Cue]) -> List[Any]:
            return sorted((c.slot, c.ms, c.loop_ms if c.is_loop else None, c.loop_beats, c.name, c.color_code,
                           c.is_active_loop) for c in cs)
        return sig(self.cues) != sig(self.original_cues)

    def go_to(self, ms: float) -> None:
        """Curseur sur ce point (vue recentrée) ; en lecture, la lecture y saute."""
        self.active_loop = None
        self._prev_sent_ms = None                  # saut : on ne « passe » pas sur une boucle active (C75)
        self.cursor_ms = float(ms)
        span = self.view_s * 1000.0
        if self.fixed_cursor:
            self._center()
        elif not (self.start_ms <= ms <= self.start_ms + span * 0.85):
            self.start_ms = ms - span * 0.15
        self._show_time()
        if self._is_playing_this() and self.ctrl.player.state in (PLAYING, PAUSED):
            self._player_seek(ms)
        self.draw()

    def play_from(self, ms: float, loop: Optional[Tuple[int, int]] = None) -> None:
        """Pad posé : écouter depuis ce point ; une boucle tourne jusqu'au prochain clic sur la forme d'onde."""
        self.go_to(ms)
        self.active_loop = (int(loop[0]), int(loop[1])) if loop else None
        if self._is_playing_this() and self.ctrl.player.state == PLAYING:
            return
        if self._is_playing_this() and self.ctrl.player.state == PAUSED:
            self.ctrl.player.toggle_pause()
            return
        self._play()

    def exit_loop(self) -> None:
        """C40 : la boucle s'arrête de revenir au début ; la lecture continue sans coupure."""
        if self.active_loop is None:
            return
        self.active_loop = None
        self.exit_btn.hide()
        self.draw()

    def keyPressEvent(self, e: Any) -> None:         # noqa: N802
        """Touches 1 à 8 (ou la même rangée sur un clavier AZERTY) : pads A à H ; 0 (« à ») : sortir de la boucle."""
        keys = "12345678"
        azerty = "".join(map(chr, (38, 233, 34, 39, 40, 45, 232, 95)))     # même rangée en AZERTY, sans Maj
        text = e.text()
        if text in ("0", chr(224)) and self.active_loop is not None and not self.bpm_entry.hasFocus():
            self.exit_loop()
            return
        if text and not self.bpm_entry.hasFocus():
            slot = keys.find(text) + 1 or azerty.find(text) + 1
            if slot:
                self.cue_panel.pad_clicked(slot)
                return
        super().keyPressEvent(e)

    def _paint_detail_cached(self, p: QPainter, w: int, h: int, mid: float) -> None:
        """1.4.3 (A1-10) : formes d'onde Bleu et RGB dessinées une fois dans une image trois fois plus large que la
        vue, puis recopiées (avant : boucle Python par pixel à chaque image, 3,3 ms à 704 px)."""
        from PySide6.QtGui import QPixmap

        dpr = self.canvas.devicePixelRatioF()
        key = (round(self.px_per_ms, 9), w, h, id(self.detail), dpr, theme.DIM)
        span_ms = w / self.px_per_ms
        c = getattr(self, "_detail_cache", None)
        if c is None or c[0] != key or not (c[1] <= self.start_ms and self.start_ms + span_ms <= c[1] + 3 * span_ms):
            start = self.start_ms - span_ms
            pm = QPixmap(int(3 * w * dpr), int(h * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            saved = self.start_ms
            self.start_ms = start
            try:
                self._paint_detail(q, 3 * w, h, mid)
            finally:
                self.start_ms = saved
                q.end()
            c = self._detail_cache = (key, start, pm)
        p.drawPixmap(QPointF((c[1] - self.start_ms) * self.px_per_ms, 0), c[2])

    def _paint_detail(self, p: QPainter, w: int, h: int, mid: float) -> None:
        """1.4.3-rc.2 (B117) : contour continu, antialiasé, en pixels réels de l'écran (detail_image)."""
        from PySide6.QtCore import QRectF

        dev = p.device()
        dpr = float(dev.devicePixelRatioF()) if dev is not None and hasattr(dev, "devicePixelRatioF") else 1.0
        img = detail_image(self.detail, self.start_ms, self.px_per_ms * dpr, int(round(w * dpr)),
                           int(round(h * dpr)), mid * dpr, h * dpr * 0.42, theme.DIM)
        if img is not None:
            p.drawImage(QRectF(0, 0, w, h), img)

    def _paint_bands_cached(self, p: QPainter, w: int, h: int, mid: float) -> None:
        """1.3.2 (C52) : la forme d'onde est dessinée UNE fois dans une image trois fois plus large que la
        vue, puis seulement recopiée, décalée, à chaque image de la lecture (avant, toute la forme d'onde
        était recalculée 60 fois par seconde : saccades sur un écran 4K). Refaite au zoom, à la taille,
        au changement de forme d'onde, ou quand la vue sort de l'image."""
        from PySide6.QtGui import QPixmap

        dpr = self.canvas.devicePixelRatioF()
        key = (round(self.px_per_ms, 9), w, h, id(self.wave), dpr)
        span_ms = w / self.px_per_ms
        c = getattr(self, "_band_cache", None)
        if c is None or c[0] != key or not (c[1] <= self.start_ms and self.start_ms + span_ms <= c[1] + 3 * span_ms):
            start = self.start_ms - span_ms
            pm = QPixmap(int(3 * w * dpr), int(h * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing, p.testRenderHint(QPainter.Antialiasing))
            saved = self.start_ms
            self.start_ms = start                         # dessin de [start, start + 3 vues]
            try:
                self._paint_bands(q, 3 * w, h, mid)
            finally:
                self.start_ms = saved
                q.end()
            c = self._band_cache = (key, start, pm)
        p.drawPixmap(QPointF((c[1] - self.start_ms) * self.px_per_ms, 0), c[2])

    def _paint_bands(self, p: QPainter, w: int, h: int, mid: float) -> None:
        """Forme d'onde 3 bandes façon Rekordbox : basses (bleu) derrière, médiums (orange), aigus
        (blanc) devant, symétrique ; chaque pixel = maximum des points qu'il couvre.

        1.3.2-rc.6 (B50) : dessinée en bloc dans une image (numpy), en pixels réels de l'écran. Avant, un
        point Qt était créé en Python par pixel et par bande, puis un grand polygone lissé : 300 à 700 ms à
        chaque renouvellement de l'image en cache (toutes les ~8 s), qui figeaient l'image et le son."""
        from PySide6.QtCore import QRectF

        dev = p.device()
        dpr = float(dev.devicePixelRatioF()) if dev is not None and hasattr(dev, "devicePixelRatioF") else 1.0
        img = band_image(self.wave, self.start_ms, self.px_per_ms * dpr, int(round(w * dpr)),
                         int(round(h * dpr)), mid * dpr, h * dpr * 0.27 / 127.0)
        if img is not None:
            p.drawImage(QRectF(0, 0, w, h), img)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(theme.mix(theme.SURFACE, theme.TEXT, 0.25)), 1))
        p.drawLine(QPointF(0, mid), QPointF(w, mid))

    def _refresh_info(self) -> None:
        if not self.beats:
            return
        tempos = sorted(b[1] for b in self.beats)
        bpm = tempos[len(tempos) // 2] / 100.0
        from .tempo_grids import changes as tempo_changes

        kind = t("grid.constant") if len(set(tempos)) <= 1 else \
            t("grid.split") if len(tempo_changes(self.beats)) < max(2, len(self.beats) // 16) else t("grid.variable")
        delta = self.beats[self.selected][2] - self._original_at(self.selected)
        parts = [f"{bpm:.2f} BPM", kind, plural("grid.beats_one", "grid.beats_many", len(self.beats))]
        from .views.library_view import tempo_profile_of          # 1.4.3 (C69) : live, beatswitch… détecté
        p = tempo_profile_of(self.track)
        if p is not None and p.kind:
            from .tempo_grids import kind_text

            parts.insert(2, kind_text(p))                         # 1.4.4 (C221) : type corrigé à la main
        self._refresh_tempo(p)
        self._refresh_downbeat()                                  # 1.4.4 (B125)
        if self._native:
            parts.append(t("grid.native"))
        self.info.setText("  ·  ".join(parts))
        self.bpm_entry.setText(f"{bpm:.2f}")
        grid_changed = self.beats != self.original
        cues_changed = self.cues_dirty()
        self.seg_tools.refresh()                                  # 1.4.4 (C221)
        marks_changed = self.seg_tools.dirty()
        self.save_btn.setEnabled(grid_changed or cues_changed or marks_changed)
        self._refresh_checked(grid_changed or cues_changed or marks_changed)
        parts = [t("grid.modified", ms=f"{delta:+d}")] if grid_changed else []
        if cues_changed:
            parts.append(t("cue.modified"))
        if marks_changed and not grid_changed:
            parts.append(t("grid.seg_modified"))
        self.state_lbl.setText("  ·  ".join(parts))
        self.state_lbl.setVisible(bool(parts))                  # 1.4.1 (C59) : pastille seulement s'il y a à enregistrer
        self.reset_btn.setEnabled(bool(parts))

    def _refresh_tempo(self, p: Any) -> None:
        """1.4.3 (C16) : bandeau « à vérifier » et boutons Grille fixe / Grille par passage."""
        from .tempo_grids import is_constant, main_tempo

        banner = getattr(self, "tempo_banner", None)
        if banner is None:
            return
        changing = p is not None and bool(p.kind)
        if changing:
            from .tempo_grids import kind_text

            what = kind_text(p)                                   # 1.4.4 (C221)
            banner.setText(t("grid.tempo_banner_ok", kind=what) if self._grid_marked
                           else t("grid.tempo_banner", kind=what))
            role = "chip_ok" if self._grid_marked else "chip_warn"
            if banner.property("role") != role:
                banner.setProperty("role", role)
                restyle(banner)
        banner.setVisible(changing)
        constant = is_constant(self.beats)
        self.fixed_grid_btn.setVisible(not constant)
        self.fixed_grid_btn.setToolTip(t("grid.fixed_grid_tip", bpm=f"{main_tempo(self.beats):.2f}"))
        split = getattr(self.ctrl, "tempo_grids", None)
        has_split = changing and len(getattr(p, "sections", []) or []) > 1 and split is not None
        self.split_grid_btn.setVisible(has_split and constant)

    def _fixed_grid(self) -> None:
        """1.4.3 (C16) : un seul tempo pour tout le son, calé sur le temps sélectionné."""
        from .tempo_grids import TempoGridService

        if not self.beats:
            return
        anchor = self.beats[self.selected][2]
        self.beats, _bpm = TempoGridService.fixed_grid(self.beats, self.selected, self.duration_ms)
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _split_grid(self) -> None:
        """1.4.3 (C16) : retour à la grille par passage trouvée par l'analyse."""
        svc = getattr(self.ctrl, "tempo_grids", None)
        beats = svc.split_grid(self.track, self.duration_ms) if svc is not None else None
        if not beats:
            return
        anchor = self.beats[self.selected][2] if self.beats else 0
        self.beats = beats
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _original_at(self, index: int) -> int:
        """Position d'origine du temps le plus proche (pour afficher le décalage appliqué)."""
        if not self.original:
            return 0
        j = G.nearest(self.original, self.beats[index][2])
        return self.original[j][2]

    # ---------------------------------------------------------------- édition
    def _shift(self, ms: int) -> None:
        if not self.beats:
            return
        anchor = self.beats[self.selected][2]
        self._set_beats(G.shift(self.beats, ms, self.duration_ms))        # 1.4.4 (B131) : ce passage / tout
        self.selected = G.nearest(self.beats, anchor + ms)
        self._refresh_info()
        self.draw()

    def _shift_half(self) -> None:
        if not self.beats:
            return
        anchor = self.beats[self.selected][2]
        self._set_beats(G.shift_half_beat(self.beats, self.selected, self.duration_ms))
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _downbeat(self) -> None:
        if self.beats:
            self._set_beats(G.set_downbeat(self.beats, self.selected))
            self._db_picked = self._db_picked or self._db_pending       # 1.4.4 (B125) : choix fait à la main
            self._refresh_info()
            self.draw()

    def _bar_here(self) -> None:
        """Un temps exactement sur le curseur, qui devient le 1er temps d'une mesure."""
        if self.beats:
            beats, sel = G.bar_at(self.beats, self.cursor_ms, self.duration_ms)
            at = beats[sel][2] if beats else 0
            self._set_beats(beats)
            self.selected = G.nearest(self.beats, at)
            self._refresh_info()
            self.draw()

    def _kick(self) -> None:
        """1.4.2 (C194) : ancien bouton unique (1er appui : 1er kick ; 2e appui : 2e kick)."""
        if self._kick1 is None:
            self._kick_first()
        else:
            self._kick_second()

    def _kick_first(self) -> None:
        """1.4.4 (C242) : « 1er kick ici » : kick sous le curseur ; se replace à volonté ; débloque le 2e."""
        if not self.beats:
            return
        self._kick1 = float(self.cursor_ms)
        self.kick2_btn.setEnabled(True)
        self.kick_hint.setText(t("grid.kick2_hint"))
        self.kick_hint.show()
        self.draw()

    def _kick_second(self) -> None:
        """1.4.4 (C242) : « 2e kick ici », n'importe où plus loin : nombre de temps entre les deux compté sur le
        tempo actuel, BPM exact, grille réécrite depuis le 1er kick (1er temps de mesure)."""
        if self._kick1 is None or not self.beats:
            return
        tempos = sorted(b[1] for b in self.beats)
        found = G.from_two_beats(self._kick1, self.cursor_ms, tempos[len(tempos) // 2] / 100.0, self.duration_ms)
        if found is None:
            self.ctrl.message("warn", t("grid.kicks_bad"))
            return
        beats, bpm, n = found
        first = self._kick1
        self._set_beats(beats, first)                           # 1.4.4 (B131) : le passage du 1er kick
        self.selected = G.nearest(self.beats, min(first, self.cursor_ms))
        self._kick_cancel()
        case = (t("grid.kicks_bars", n=n // 4) if n % 4 == 0 and n > 4 else t("grid.kicks_bar") if n == 4
                else t("grid.kicks_beat") if n == 1 else t("grid.kicks_beats", n=n))
        self.kick_hint.setText(t("grid.kicks_done", bpm=f"{bpm:.2f}", case=case))
        self.kick_hint.show()
        self._refresh_info()

    def _kick_cancel(self) -> None:
        self._kick1 = None
        self.kick2_btn.setEnabled(False)
        self.kick_hint.setText("")
        self.kick_hint.hide()
        self.draw()

    def _scale(self, factor: float) -> None:
        if not self.beats:
            return
        tempos = sorted(b[1] for b in self.beats)
        if not 40 <= tempos[len(tempos) // 2] / 100.0 * factor <= 300:
            self.ctrl.message("warn", t("grid.bpm_range"))
            return
        anchor = self.beats[self.selected][2]
        self._set_beats(G.scale_tempo(self.beats, factor, self.selected, self.duration_ms))
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _apply_bpm(self) -> None:
        try:
            bpm = float(self.bpm_entry.text().replace(",", "."))
        except ValueError:
            return
        if not 40 <= bpm <= 300 or not self.beats:
            self.ctrl.message("warn", t("grid.bpm_range"))
            return
        anchor = self.beats[self.selected][2]
        self._set_beats(G.set_bpm(self.beats, bpm, self.selected, self.duration_ms))
        self.selected = G.nearest(self.beats, anchor)
        self._refresh_info()
        self.draw()

    def _reset(self) -> None:
        self._kick_cancel()
        self.beats = list(self.original)
        self.cues = copy.deepcopy(self.original_cues)
        self.seg_tools.reset()                                    # 1.4.4 (C221) : repères d'origine
        self.active_loop = None
        self.cue_panel.refresh()
        self.selected = min(self.selected, len(self.beats) - 1)
        self._refresh_info()
        self.draw()

    # --------------------------------------------------------------- navigation
    def _view_changed(self, text: str) -> None:
        center = self.cursor_ms if self.fixed_cursor else self.start_ms + self.view_s * 500
        self.view_s = float(text.split()[0].replace(",", "."))
        self.view_s = int(self.view_s) if self.view_s == int(self.view_s) else self.view_s
        self.start_ms = center - self.view_s * 500
        self.draw()

    def zoom(self, step: int) -> None:
        """Vue plus courte (step < 0, on zoome) ou plus longue, centrée sur le curseur s'il est visible."""
        i = VIEW_CHOICES.index(self.view_s) if self.view_s in VIEW_CHOICES else VIEW_CHOICES.index(8)
        j = max(0, min(len(VIEW_CHOICES) - 1, i + step))
        if j == i:
            return
        span = self.view_s * 1000.0
        anchor = self.cursor_ms if self.start_ms <= self.cursor_ms <= self.start_ms + span else self.start_ms + span / 2
        ratio = (anchor - self.start_ms) / span if span else 0.5
        if self.fixed_cursor:
            anchor, ratio = self.cursor_ms, 0.5
        self.view_s = VIEW_CHOICES[j]
        self.start_ms = anchor - ratio * self.view_s * 1000.0
        self.view_menu.blockSignals(True)
        self.view_menu.setCurrentText(view_label(self.view_s))
        self.view_menu.blockSignals(False)
        self.draw()

    def _scrolled(self, value: int) -> None:
        if self.fixed_cursor:
            self._move_cursor(value / SCROLL_STEPS * self.duration_ms)
            self.release()
            return
        self.start_ms = value / SCROLL_STEPS * max(0.0, self.duration_ms - self.view_s * 1000.0)
        self.draw()

    def pan(self, fraction: float) -> None:
        if self.fixed_cursor:                    # molette : le son avance sous le curseur
            self._move_cursor(self.cursor_ms + fraction * self.view_s * 1000)
            self.release()
            return
        self.start_ms += fraction * self.view_s * 1000
        self.draw()

    def press(self, x: float, dragging: bool = False) -> None:
        """Le curseur d'écoute suit la souris (clic ou glisser) ; en lecture, la lecture y saute au
        relâchement (et pendant le glisser, au plus toutes les ~60 ms)."""
        w = max(1, self.canvas.width())
        x = min(max(0.0, x), float(w))
        if not dragging:
            self.active_loop = None
        # 1.4.2 (C194) : en posant les kicks, le curseur va où l'on clique (pas d'aimant sur l'ancienne grille)
        raw = self._ms(x) if self._kick1 is not None else self.snap_ms(self._ms(x), cursor=True)
        self.cursor_ms = min(max(0.0, raw), float(self.duration_ms))
        self._scrubbing = True
        if self.beats:
            self.selected = G.nearest(self.beats, self.cursor_ms)
            self._refresh_info()
        if dragging:                         # au bord : la vue défile pour suivre
            span = self.view_s * 1000.0
            if x >= w - 4:
                self.start_ms += span * 0.05
            elif x <= 4:
                self.start_ms -= span * 0.05
        self._show_time()
        self.draw()

    def release(self) -> None:
        self._scrubbing = False
        if self.ctrl.player.state in (PLAYING, PAUSED) and self._is_playing_this():
            self._player_seek(self.cursor_ms)

    def _show_time(self) -> None:
        s_ = self.cursor_ms / 1000.0
        self.time_lbl.setText(f"{int(s_ // 60)}:{s_ % 60:06.3f}")

    # ------------------------------------------------------------------- écoute
    def _is_playing_this(self) -> bool:
        item = self.ctrl.current_item
        return item is not None and item.kind == "library" and item.item.content_id == self.track.content_id

    def _play(self) -> None:
        if not self.missing.isHidden():               # B20 : pas d'erreur à chaque clic, le bandeau le dit
            return
        player = self.ctrl.player
        if self._is_playing_this() and player.state in (PLAYING, PAUSED):
            player.toggle_pause()
            return
        self.ctrl.play_queue([self.track], 0)
        start = self.cursor_ms

        def seek_when_ready(tries: int = 0) -> None:
            if player.state == PLAYING and player.duration > 0:
                self._player_seek(start)
            elif tries < 40 and self.winfo_exists():
                QTimer.singleShot(100, lambda: seek_when_ready(tries + 1))

        QTimer.singleShot(100, seek_when_ready)

    def _frame_interval(self) -> int:
        """1.3.2 (C52) : une image par rafraîchissement de l'écran (60, 120, 144 Hz…), ralentie (jusqu'à
        30 images/s) si le PC met trop de temps à dessiner, puis réaccélérée quand il suit."""
        try:
            hz = float(self.screen().refreshRate() or 60.0)
        except Exception:  # noqa: BLE001
            log.debug("Handled error in _frame_interval", exc_info=True)  # 1.4.3 (A3-4)
            hz = 60.0
        best = max(7, int(1000.0 / min(max(hz, 30.0), 144.0)))
        cost = getattr(self.canvas, "paint_ms", 0.0)       # durée moyenne d'un dessin
        cur = getattr(self, "_interval", best)
        if cost > 0.7 * cur:
            cur = min(33, max(cur + 4, int(cost * 1.5)))
        elif cost < 0.3 * cur:
            cur = max(best, cur - 2)
        from ..core.machine import LIGHT_FRAME_MS, light_active

        if light_active(self.ctrl.settings):            # 1.4.0 (C65) : mode léger, 30 images/s au plus
            cur = max(cur, LIGHT_FRAME_MS)
        self._interval = cur
        return cur

    def _tick(self) -> None:
        import time

        t0 = time.perf_counter()
        player = self.ctrl.player
        playing = self._is_playing_this() and player.state == PLAYING
        interval = self._frame_interval() if playing else 60    # 1.3.2 (C52) : cadence de l'écran, adaptée
        show_exit = self.active_loop is not None and playing
        if self.exit_btn.isVisibleTo(self) != show_exit:
            self.exit_btn.setVisible(show_exit)
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        if self._play_icon_state != playing:                # 1.3.2-rc.3 (B50) : l'icône (dessin SVG) était
            self._play_icon_state = playing                 # refaite à chaque image (60 fois par seconde)
            self.play_btn.setIcon(qicon("pause" if playing else "play", 16, theme.ON_ACCENT))
        if playing and not self._scrubbing:
            # 1.3.2 (C52, testeur Mac) : la position affichée ne recule jamais d'un petit pas pendant la lecture
            self.cursor_ms = self._mono(player.position() * 1000.0 + self._lead_ms)
            # 1.3.0-rc.3 (C39) : la fin de boucle se décide sur ce qui est ENVOYÉ à la carte son (en avance
            # de sa réserve), pour que le retour au début s'entende pile à la fin de la boucle
            sent_ms = player.sent_position() * 1000.0 + self._lead_ms
            prev = getattr(self, "_prev_sent_ms", None)
            self._prev_sent_ms = sent_ms
            if not self.active_loop and prev is not None:
                # 1.3.1-rc.2 (C75) : boucle active : en passant sur son début, la lecture boucle toute seule
                # (comme sur platine) ; « Sortir de la boucle » (Exit) la quitte, comme une boucle de pad.
                auto = next((c for c in self.cues if c.is_active_loop and prev < c.ms <= sent_ms), None)
                if auto is not None:
                    self.active_loop = (int(auto.ms), int(auto.loop_ms))
            if self.active_loop and sent_ms >= self.active_loop[1]:
                over = sent_ms - self.active_loop[1]
                length = max(1.0, self.active_loop[1] - self.active_loop[0])
                self._player_seek(self.active_loop[0] + over % length, flush=False)
            self._show_time()
            self.seg_tools.live(tick=True)                    # 1.4.4 (C221) : BPM à la position de lecture
            span = self.view_s * 1000.0
            if self.fixed_cursor:
                self._center()
            elif not (self.start_ms <= self.cursor_ms <= self.start_ms + span * 0.85):
                self.start_ms = self.cursor_ms - span * 0.15
            self.draw()
            self.overview.update()
            self._meter.frame(getattr(self.canvas, "paint_ms", 0.0), getattr(self.overview, "paint_ms", 0.0),
                              (time.perf_counter() - t0) * 1000.0)
            stall.watch().tick()                 # 1.3.2-rc.5 (B50) : piles écrites si l'interface se fige
        else:
            self._mono.reset()
            self._meter.stop()
            stall.watch().stop()

    # -------------------------------------------------------------- enregistrer
    def _refresh_checked(self, dirty: bool = False) -> None:
        """C204 : actif seulement sans modification (sinon « Enregistrer » marque la grille) ; « ✓ » une fois fait."""
        btn = getattr(self, "checked_btn", None)
        if btn is None:
            return
        btn.setEnabled(not dirty and not self._grid_marked and bool(self.beats))
        btn.setText(t("grid.checked_already") if self._grid_marked else t("grid.checked_btn"))

    def _grid_ok(self) -> None:
        def done(_r: Any) -> None:
            self._grid_marked = True
            self._downbeat_resolved()                         # 1.4.4 (B125) : grille validée, 1er temps compris
            if self.winfo_exists():
                self._refresh_checked()
                self._refresh_info()                          # 1.4.3 (C16) : bandeau « grille vérifiée »

        self.checked_btn.setEnabled(False)
        self.ctrl.mark_grid_checked(self.track.content_id, done)

    def _save(self) -> None:
        def go() -> None:
            self.save_btn.setEnabled(False)
            self.save_btn.setText(t("grid.saving"))

            def done(_r: Any) -> None:
                if self._db_picked:                           # 1.4.4 (B125) : 1er temps choisi, enregistré
                    self._downbeat_resolved()
                if self.winfo_exists():
                    self._leaving = True
                    self.close()

            def failed(_e: BaseException) -> None:
                if self.winfo_exists():
                    self.save_btn.setEnabled(True)
                    self.save_btn.setText(t("action.save"))

            beats = self.beats if self.beats != self.original else None
            cues = self.cues if self.cues_dirty() else None
            svc = getattr(self.ctrl, "tempo_grids", None)         # 1.4.3 (C16) : grille fixe gardée à la réanalyse
            if svc is not None and beats is not None:
                svc.remember_choice(self.track, beats)
            self.seg_tools.remember()                             # 1.4.4 (C221) : repères gardés à la réanalyse
            self.ctrl.save_grid_and_cues(self.track.content_id, beats, cues, ok=done, err=failed)

        if self._native and self.beats != self.original:
            ConfirmDialog(self, t("grid.native_title"), t("grid.native_msg"), go, confirm_text=t("action.save"),
                          detail=t("grid.native_detail"))
        else:
            go()

    def is_dirty(self) -> bool:
        return bool(self.beats) and (self.beats != self.original or self.cues_dirty() or self.seg_tools.dirty())

    def close(self) -> bool:                 # noqa: D401
        """Quitte la page (sans enregistrer) ; la lecture du son continue. 1.3.0 : grille ou cues
        modifiés et pas enregistrés -> on demande avant de les perdre."""
        if self._closed:
            return True
        if self.is_dirty() and not getattr(self, "_leaving", False):
            def leave() -> None:
                self._leaving = True
                self.close()

            ConfirmDialog(self, t("grid.leave_title"), t("grid.leave_msg"), leave,
                          confirm_text=t("grid.leave_confirm"), danger=True)
            return False
        self._closed = True
        self._timer.stop()
        stall.watch().stop()                      # 1.3.2-rc.5 (B50)
        if getattr(self.ctrl, "grid_editor", None) is self:
            self.ctrl.grid_editor = None
        self.ctrl._emit("grid_page", None)
        callback, self._on_close = self._on_close, None
        self.hide()
        self.deleteLater()
        if callback:
            callback()
        return True
