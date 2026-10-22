"""OUTIL DE DÉVELOPPEMENT : « studio » de tournage des vidéos de présentation (portrait et paysage).

La vraie interface tourne hors écran (plateforme Qt « offscreen ») ; le studio la filme image par image
et l'incruste dans un cadre (fond, titres, légendes). Règles de lisibilité :

* le pointeur se déplace vers le VRAI widget puis le clique avec de vrais événements souris (QTest) :
  ce qu'on voit cliqué est ce qui déclenche l'action (menus, fenêtres, cases) ;
* « caméra » : recadrage doux sur la zone utile (interface agrandie) ;
* projecteur : le reste de l'interface s'assombrit autour de l'élément dont on parle ;
* panneaux de texte plein écran avant chaque partie, petit rappel de la partie, légende courte ;
* les images sont envoyées directement à FFmpeg (H.264), sans fichiers intermédiaires.
"""
from __future__ import annotations

import math
import subprocess
import time
from typing import Any, Callable, List, Optional, Sequence, Tuple

ACTIVE: Optional["Studio"] = None          # studio en cours (menus contextuels non bloquants)


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def install_menu_patch() -> None:
    """Les menus contextuels de l'appli sont modaux (QMenu.exec) : on les ouvre sans bloquer (popup),
    pour que le studio continue à filmer et que le pointeur aille cliquer une entrée."""
    import djsync.ui.player_bar as player_bar
    import djsync.ui.table as table
    import djsync.ui.views.library_view as library_view
    import djsync.ui.widgets as widgets
    from PySide6.QtWidgets import QMenu

    def popup_menu(widget: Any, entries: Sequence[Any], global_pos: Any) -> None:
        from djsync.ui import theme
        from djsync.ui.icons import qicon

        menu = QMenu(widget)
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            elif len(entry) > 2 and entry[2]:
                danger = entry[2] == "trash"
                menu.addAction(qicon(entry[2], 16, theme.ERR if danger else theme.DIM), entry[0], entry[1])
            else:
                menu.addAction(entry[0], entry[1])
        menu.popup(global_pos)
        if ACTIVE is not None:
            ACTIVE.menu, ACTIVE.menu_at = menu, global_pos

    for mod in (table, library_view, widgets, player_bar):
        mod.popup_menu = popup_menu


class Studio:
    def __init__(self, app: Any, out: str, fps: int, accent: str, canvas: Tuple[int, int],
                 display: Tuple[float, float, float, float], app_size: Tuple[int, int], portrait: bool,
                 dry: bool = False) -> None:
        global ACTIVE
        import shutil

        ACTIVE = self
        self.app, self.fps, self.accent, self.portrait = app, fps, accent, portrait
        self.W, self.H = canvas
        self.AW, self.AH = app_size
        self.disp = display                                   # x, y, w, h du cadre de l'appli
        self.aspect = display[3] / display[2]
        self.view = [0.0, 0.0, float(self.AW)]                # recadrage courant (x, y, largeur) en px appli
        self.target = list(self.view)
        self.cursor = (self.AW * 0.6, self.AH * 0.5)
        self.ripple: Optional[Tuple[float, float, float]] = None
        self.spot_rect: Optional[Any] = None
        self.spot_since = -10.0
        self.chapter_text = ""
        self.caption_text = ""
        self.caption_since = 0.0
        self.menu: Any = None
        self.menu_at: Any = None
        self.t = 0.0
        self.n = 0
        self.last: Any = None
        self._current: Any = None
        self.fade_left = self.fade_total = 0
        self.dry = dry
        self.ffmpeg = None if dry else subprocess.Popen(
            [shutil.which("ffmpeg"), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
             "-s", f"{self.W}x{self.H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "19", "-preset", "medium", "-movflags", "+faststart", out], stdin=subprocess.PIPE)

    # ================================================================ boucle Qt
    def pump(self, seconds: float = 0.0) -> None:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication

        end = time.time() + seconds
        while True:
            QApplication.instance().processEvents()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if time.time() >= end:
                break
            time.sleep(0.004)

    def visible_dialogs(self) -> List[Any]:
        from PySide6.QtWidgets import QApplication, QDialog

        return [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()]

    def dialog(self, cls: Any) -> Any:
        return next((d for d in self.visible_dialogs() if isinstance(d, cls)), None)

    # ================================================================ image de l'appli
    def _dialog_pos(self, d: Any) -> Tuple[int, int]:
        return (self.AW - d.width()) // 2, max(10, (self.AH - d.height()) // 2 - 20)

    def compose_app(self) -> Any:
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

        img = QImage(self.AW, self.AH, QImage.Format_RGB32)
        img.fill(QColor("#101014"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(0, 0, self.app.grab())
        for d in self.visible_dialogs():
            x, y = self._dialog_pos(d)
            d._video_pos = (x, y)
            p.fillRect(0, 0, self.AW, self.AH, QColor(0, 0, 0, 120))
            pm = d.grab()
            p.setPen(Qt.NoPen)
            for k in range(6):
                p.setBrush(QColor(0, 0, 0, 24))
                p.drawRoundedRect(QRectF(x - k * 2, y - k * 2 + 6, pm.width() + k * 4, pm.height() + k * 4), 12, 12)
            p.drawPixmap(x, y, pm)
        if self.menu is not None and self.menu.isVisible():
            mx, my = self._menu_pos()
            pm = self.menu.grab()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawRoundedRect(QRectF(mx + 3, my + 6, pm.width(), pm.height()), 8, 8)
            p.drawPixmap(int(mx), int(my), pm)
        # projecteur
        if self.spot_rect is not None:
            a = _ease((self.t - self.spot_since) / 0.35)
            r = self.spot_rect
            hole = QPainterPath()
            hole.addRect(QRectF(0, 0, self.AW, self.AH))
            inner = QPainterPath()
            inner.addRoundedRect(r, 10, 10)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(150 * a)))
            p.drawPath(hole.subtracted(inner))
            pen = QPen(QColor(self.accent), 3)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.setOpacity(a)
            p.drawRoundedRect(r, 10, 10)
            p.setOpacity(1.0)
        # clic + pointeur
        if self.ripple is not None:
            cx, cy, t0 = self.ripple
            age = self.t - t0
            if age < 0.55:
                p.setPen(QPen(QColor(self.accent), 3))
                p.setBrush(Qt.NoBrush)
                p.setOpacity(max(0.0, 1 - age / 0.55))
                p.drawEllipse(QPointF(cx, cy), 8 + age * 55, 8 + age * 55)
                p.setOpacity(1.0)
        x, y = self.cursor
        pts = [(0, 0), (0, 22), (6, 16.5), (10.5, 26), (14, 24.5), (9.5, 15), (17, 15)]
        path = QPainterPath()
        path.moveTo(x, y)
        for dx, dy in pts[1:]:
            path.lineTo(x + dx, y + dy)
        path.closeSubpath()
        p.setPen(QPen(QColor("#111111"), 1.6))
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(path)
        p.end()
        return img

    def _menu_pos(self) -> Tuple[float, float]:
        from PySide6.QtCore import QPoint

        origin = self.app.mapToGlobal(QPoint(0, 0))
        at = self.menu_at
        x, y = at.x() - origin.x(), at.y() - origin.y()
        w, h = self.menu.sizeHint().width(), self.menu.sizeHint().height()
        x = min(x, self.AW - w - 8)
        y = min(y, self.AH - h - 8)
        return float(x), float(y)

    # ================================================================ image finale
    def _background(self, p: Any) -> None:
        from PySide6.QtGui import QColor, QLinearGradient

        g = QLinearGradient(0, 0, self.W, self.H)
        g.setColorAt(0, QColor("#121217"))
        g.setColorAt(1, QColor("#2A1F44"))
        p.fillRect(0, 0, self.W, self.H, g)

    def _pill(self, p: Any, text: str, x: float, y: float, size: int, center: bool = False,
              alpha: float = 1.0, accent_bar: bool = False, bold: bool = True) -> None:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QFontMetrics

        f = QFont()
        f.setPixelSize(size)
        f.setBold(bold)
        w = QFontMetrics(f).horizontalAdvance(text) + size * 1.4 + (10 if accent_bar else 0)
        h = size * 2.0
        if center:
            x = (self.W - w) / 2
        p.setOpacity(alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(12, 12, 16, 225))
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2 if not accent_bar else 14, h / 2 if not accent_bar else 14)
        if accent_bar:
            p.setBrush(QColor(self.accent))
            p.drawRoundedRect(QRectF(x, y, 7, h), 3, 3)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(x + (10 if accent_bar else 0), y, w - (10 if accent_bar else 0), h), Qt.AlignCenter, text)
        p.setOpacity(1.0)

    def frame(self) -> None:
        if self.dry:                                     # répétition : pas d'image, mais le temps réel passe
            self.pump(1 / self.fps)
            self.n += 1
            self.t += 1 / self.fps
            return
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

        app_img = self.compose_app()
        img = QImage(self.W, self.H, QImage.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self._background(p)
        self.view = [v + (t - v) * 0.16 for v, t in zip(self.view, self.target)]
        vx, vy, vw = self.view
        dx, dy, dw, dh = self.disp
        framed = (dw, dh) != (self.W, self.H)
        if framed:
            glow = QColor(self.accent)
            glow.setAlpha(7)
            p.setPen(QColor(0, 0, 0, 0))
            p.setBrush(glow)
            for k in range(10, 0, -1):
                p.drawRoundedRect(QRectF(dx - k * 6, dy - k * 6, dw + k * 12, dh + k * 12), 40, 40)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(dx, dy, dw, dh), 26 if self.portrait else 18, 26 if self.portrait else 18)
            p.save()
            p.setClipPath(clip)
        p.drawImage(QRectF(dx, dy, dw, dh), app_img, QRectF(vx, vy, vw, vw * self.aspect))
        if framed:
            p.restore()
        # rappel de la partie + légende
        if self.chapter_text:
            if self.portrait:
                self._pill(p, self.chapter_text, 0, 120, 40, center=True)
            else:
                self._pill(p, self.chapter_text, dx, (dy - 52) / 2, 26)
        if self.caption_text:
            a = _ease((self.t - self.caption_since) / 0.3)
            if self.portrait:
                self._pill(p, self.caption_text, 0, dy + dh + 50 + (1 - a) * 20, 38, center=True, alpha=a,
                           bold=False)
            else:
                self._pill(p, self.caption_text, dx, dy + dh + (self.H - dy - dh - 60) / 2 + (1 - a) * 12, 30,
                           alpha=a, accent_bar=True, bold=False)
        p.end()
        self._emit(img)

    def _emit(self, img: Any) -> None:
        from PySide6.QtGui import QPainter

        if self.dry:
            self.n += 1
            self.t += 1 / self.fps
            return
        if self.fade_left and self.last is not None:
            p = QPainter(img)
            p.setOpacity(self.fade_left / self.fade_total)
            p.drawImage(0, 0, self.last)
            p.end()
            self.fade_left -= 1
        self.ffmpeg.stdin.write(bytes(img.constBits()))
        self.n += 1
        self.t += 1 / self.fps
        self._current = img

    def hold(self, seconds: float) -> None:
        for _ in range(max(1, int(round(seconds * self.fps)))):
            self.pump(0.0)
            self.frame()

    def wait_until(self, cond: Callable[[], bool], timeout: float = 8.0) -> None:
        """Filme tant que la condition n'est pas vraie (chargement, téléchargement…)."""
        end = time.time() + timeout
        t0 = self.t
        while not cond() and time.time() < end:
            self.pump(0.02)
            self.frame()
        if self.t - t0 > 2.5:
            print(f"  [studio] waited {self.t - t0:.1f} s at t={self.t:.1f}", flush=True)

    def cut(self, fade: float = 0.35) -> None:
        self.last = self._current
        self.fade_total = self.fade_left = max(1, int(fade * self.fps)) if fade else 0

    # ================================================================ textes
    def chapter(self, text: str) -> None:
        self.chapter_text = text

    def caption(self, text: str) -> None:
        if text != self.caption_text:
            self.caption_text = text
            self.caption_since = self.t

    # ================================================================ caméra
    def zoom(self, x: float = 0, y: float = 0, w: Optional[float] = None, now: bool = False) -> None:
        w = float(w or self.AW)
        w = min(w, self.AW, self.AH / self.aspect)
        h = w * self.aspect
        x = max(0.0, min(float(x), self.AW - w))
        y = max(0.0, min(float(y), self.AH - h))
        self.target = [x, y, w]
        if now:
            self.view = list(self.target)

    def full(self, now: bool = False) -> None:
        self.zoom(0, 0, None, now)

    def focus(self, widget: Any, w: float, now: bool = False, dy: float = 0.3) -> None:
        """Cadre de largeur w centré sur le widget (dy : place verticale du widget dans le cadre)."""
        r = self.rect_of(widget)
        h = w * self.aspect
        self.zoom(r.center().x() - w / 2, r.center().y() - h * dy, w, now)

    # ================================================================ géométrie
    def rect_of(self, widget: Any, local: Any = None) -> Any:
        """Rectangle (coordonnées de l'image de l'appli) d'un widget, ou d'un rectangle `local` du widget."""
        from PySide6.QtCore import QPoint, QRectF
        from PySide6.QtWidgets import QDialog, QMenu

        r = local if local is not None else widget.rect()
        win = widget.window()
        if isinstance(win, QMenu):
            mx, my = self._menu_pos()
            tl = widget.mapTo(win, r.topLeft())
            return QRectF(mx + tl.x(), my + tl.y(), r.width(), r.height())
        if isinstance(win, QDialog) and win is not self.app:
            ox, oy = self._dialog_pos(win)
            tl = widget.mapTo(win, r.topLeft())
            return QRectF(ox + tl.x(), oy + tl.y(), r.width(), r.height())
        tl = widget.mapTo(self.app, QPoint(r.x(), r.y()))
        return QRectF(tl.x(), tl.y(), r.width(), r.height())

    def spot(self, widget: Any = None, local: Any = None, pad: float = 6, rect: Any = None) -> None:
        r = rect if rect is not None else self.rect_of(widget, local)
        self.spot_rect = r.adjusted(-pad, -pad, pad, pad)
        self.spot_since = self.t

    def unspot(self) -> None:
        self.spot_rect = None

    # ================================================================ pointeur
    def move_to(self, x: float, y: float, seconds: float = 0.6) -> None:
        x0, y0 = self.cursor
        dist = math.hypot(x - x0, y - y0)
        seconds = max(0.25, min(seconds, 0.25 + dist / 900))
        steps = max(2, int(seconds * self.fps))
        for i in range(1, steps + 1):
            k = i / steps
            e = 0.5 - 0.5 * math.cos(math.pi * k)
            arc = math.sin(math.pi * k) * min(40.0, dist * 0.08)
            self.cursor = (x0 + (x - x0) * e, y0 + (y - y0) * e - arc)
            self.pump(0.0)
            self.frame()

    def follow(self, x: float, y: float, margin: float = 40) -> None:
        """La caméra suit le pointeur : si le point sort du cadre visé, le cadre glisse juste assez."""
        tx, ty, tw = self.target
        th = tw * self.aspect
        nx, ny = tx, ty
        if x < tx + margin:
            nx = x - margin - 80
        elif x > tx + tw - margin:
            nx = x + margin + 80 - tw
        if y < ty + margin:
            ny = y - margin - 80
        elif y > ty + th - margin:
            ny = y + margin + 80 - th
        if (nx, ny) != (tx, ty):
            self.zoom(nx, ny, tw)
            self.hold(0.45)

    def point(self, widget: Any, local: Any = None, seconds: float = 0.6) -> Tuple[float, float]:
        r = self.rect_of(widget, local)
        self.follow(r.center().x(), r.center().y())
        self.move_to(r.center().x() - 2, r.center().y() - 2, seconds)
        return r.center().x(), r.center().y()

    def click(self, widget: Any, local: Any = None, right: bool = False, double: bool = False,
              after: float = 0.5, action: Optional[Callable[[], None]] = None) -> None:
        """Le pointeur va sur le widget (ou sur `local` dans le widget) et clique pour de vrai."""
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QCheckBox, QRadioButton

        if local is None and isinstance(widget, (QCheckBox, QRadioButton)):
            h = widget.height()                          # la case elle-même (le reste de la ligne ne coche pas)
            local = QRect(0, 0, h, h)
        x, y = self.point(widget, local)
        self.hold(0.12)
        self.ripple = (x, y, self.t)
        pos = (local.center() if local is not None else widget.rect().center())
        if action is not None:
            action()
        elif double:
            QTest.mouseDClick(widget, Qt.LeftButton, Qt.NoModifier, pos)
        else:
            QTest.mouseClick(widget, Qt.RightButton if right else Qt.LeftButton, Qt.NoModifier, pos)
        self.pump(0.05)
        self.hold(after)

    def type(self, widget: Any, text: str, cps: float = 9.0) -> None:
        from PySide6.QtTest import QTest

        widget.setFocus()
        per = max(1, int(round(self.fps / cps)))
        for ch in text:
            QTest.keyClicks(widget, ch)
            for _ in range(per):
                self.pump(0.0)
                self.frame()

    def choose(self, text: str, after: float = 0.5) -> None:
        """Clique l'entrée `text` (début du libellé) du menu contextuel ouvert."""
        from PySide6.QtCore import QRectF

        menu = self.menu
        act = next(a for a in menu.actions() if a.text().startswith(text))
        g = menu.actionGeometry(act)
        mx, my = self._menu_pos()
        r = QRectF(mx + g.x(), my + g.y(), g.width(), g.height())
        self.hold(0.3)
        self.move_to(r.x() + min(60, r.width() / 3), r.center().y())
        self.hold(0.1)
        self.ripple = (*self.cursor, self.t)
        menu.setActiveAction(act)
        self.hold(0.15)
        menu.close()
        act.trigger()
        self.menu = None
        self.pump(0.05)
        self.hold(after)

    def button(self, root: Any, text: str) -> Any:
        """Bouton visible de `root` dont le texte commence par `text`."""
        from PySide6.QtWidgets import QAbstractButton

        return next(b for b in root.findChildren(QAbstractButton) if b.isVisible() and b.text().startswith(text))

    # ================================================================ plans dessinés
    def scene(self, seconds: float, draw: Callable[[Any, float], None]) -> None:
        from PySide6.QtGui import QImage, QPainter

        for i in range(int(round(seconds * self.fps))):
            if self.dry:
                self._emit(None)
                continue
            img = QImage(self.W, self.H, QImage.Format_RGB32)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            self._background(p)
            draw(p, i / self.fps)
            p.setOpacity(1.0)
            p.end()
            self._emit(img)
            if i % 4 == 0:
                self.pump(0.0)

    def text_block(self, p: Any, lines: Sequence[Tuple[str, int, str, bool]], t: float, cy: float,
                   gap: float = 26, stagger: float = 0.25) -> None:
        """Lignes centrées qui apparaissent l'une après l'autre : (texte, taille px, couleur, gras)."""
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QFontMetrics

        blocks = []
        for text, size, color, bold in lines:
            f = QFont()
            f.setPixelSize(size)
            f.setBold(bold)
            fm = QFontMetrics(f)
            rect = fm.boundingRect(QRectF(0, 0, self.W * 0.86, 4000).toRect(), Qt.AlignCenter | Qt.TextWordWrap, text)
            blocks.append((text, f, color, rect.height()))
        total = sum(b[3] for b in blocks) + gap * (len(blocks) - 1)
        y = cy - total / 2
        for k, (text, f, color, h) in enumerate(blocks):
            a = _ease((t - 0.1 - stagger * k) / 0.35)
            p.setOpacity(a)
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(QRectF(self.W * 0.07, y + (1 - a) * 30, self.W * 0.86, h), Qt.AlignCenter | Qt.TextWordWrap,
                       text)
            y += h + gap
        p.setOpacity(1.0)

    def panel(self, num: str, title: str, sub: str, seconds: float = 2.8) -> None:
        """Panneau plein écran, uniquement du texte, avant chaque partie."""
        print(f"  [studio] {self.t:5.1f} s  panel {num} {title}", flush=True)
        big = 112 if self.portrait else 104
        lines = [(num, 40 if self.portrait else 34, self.accent, True), (title, big, "#FFFFFF", True),
                 (sub, 50 if self.portrait else 44, "#C9C9D2", False)]
        self.scene(seconds, lambda p, t: self.text_block(p, lines, t, self.H * (0.42 if self.portrait else 0.5)))

    def card(self, lines: Sequence[str], seconds: float, cta: str = "") -> None:
        """Carton logo (accroche, fin)."""
        from djsync.ui.logo import logo_pixmap

        def draw(p: Any, t: float) -> None:
            size = int((260 if self.portrait else 200) * (1 + 0.05 * math.sin(t * 4 * math.pi)))
            cy = self.H * (0.30 if self.portrait else 0.30)
            p.drawPixmap(int(self.W / 2 - size / 2), int(cy - size / 2), logo_pixmap(size, self.accent))
            big = 104 if self.portrait else 92
            rows = [(lines[0], big, "#FFFFFF", True)] + [(x, big, self.accent, True) for x in lines[1:]]
            if cta:
                rows.append((cta, 40 if self.portrait else 36, "#D8D8E0", False))
            self.text_block(p, rows, t, self.H * (0.55 if self.portrait else 0.66), gap=18, stagger=0.35)

        self.scene(seconds, draw)

    def checklist(self, title: str, sub: str, items: Sequence[Tuple[str, str]], seconds: float) -> None:
        """Liste de coches qui apparaissent une à une (compatibilité, sécurité)."""
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QPen

        portrait = self.portrait

        def draw(p: Any, t: float) -> None:
            self.text_block(p, [(title, 100 if portrait else 84, "#FFFFFF", True),
                                (sub, 44 if portrait else 38, self.accent, False)], t,
                            self.H * (0.17 if portrait else 0.16), gap=14)
            n = len(items)
            if portrait:
                cols, w, h, x0, y0, gx, gy = 1, self.W - 180, 190, 90, self.H * 0.33, 0, 40
            else:
                cols, w, h = 2, 780, 170
                x0, y0, gx, gy = (self.W - 2 * w - 40) / 2, self.H * 0.36, 40, 40
            for i, (head, text) in enumerate(items):
                a = _ease((t - 0.5 - 0.35 * i) / 0.35)
                if a <= 0:
                    continue
                r, c = divmod(i, cols)
                x = x0 + c * (w + gx)
                y = y0 + r * (h + gy) + (1 - a) * 40
                p.setOpacity(a)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 16))
                p.drawRoundedRect(QRectF(x, y, w, h), 26, 26)
                p.setBrush(QColor(self.accent))
                d = 76
                p.drawEllipse(QRectF(x + 34, y + (h - d) / 2, d, d))
                p.setPen(QPen(QColor("#15121E"), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                cx, cy = x + 34 + d / 2, y + h / 2
                p.drawPolyline([QPointF(cx - 18, cy + 1), QPointF(cx - 4, cy + 15), QPointF(cx + 19, cy - 13)])
                f = QFont()
                f.setPixelSize(46 if portrait else 40)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor("#FFFFFF"))
                p.drawText(QRectF(x + 140, y + h * 0.16, w - 160, h * 0.4), Qt.AlignLeft | Qt.AlignVCenter, head)
                f.setPixelSize(33 if portrait else 29)
                f.setBold(False)
                p.setFont(f)
                p.setPen(QColor("#B9B9C6"))
                p.drawText(QRectF(x + 140, y + h * 0.54, w - 160, h * 0.32), Qt.AlignLeft | Qt.AlignVCenter, text)
            p.setOpacity(1.0)

        self.scene(seconds, draw)

    def plug(self, seconds: float, drive: str, file_name: str, title: Tuple[str, str]) -> None:
        """La clé USB se branche sur un portable Windows, l'écran s'allume, double-clic sur DJSync.exe."""
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QPen

        from djsync.ui.logo import logo_pixmap

        k = seconds / 4.0                                     # animation prévue pour 4 s

        def draw(p: Any, t: float) -> None:
            t = t / k
            self.text_block(p, [(title[0], 96 if self.portrait else 80, "#FFFFFF", True),
                                (title[1], 44 if self.portrait else 38, self.accent, False)], t,
                            self.H * (0.15 if self.portrait else 0.15), gap=14)
            if self.portrait:
                sx, sy, sw, sh = 150, 640, 640, 420
            else:
                sx, sy, sw, sh = self.W / 2 - 430, 300, 720, 450
            p.setPen(QPen(QColor("#3A3A46"), 6))
            p.setBrush(QColor("#0C0C10"))
            p.drawRoundedRect(QRectF(sx, sy, sw, sh), 22, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#2A2A34"))
            p.drawRoundedRect(QRectF(sx - 70, sy + sh + 6, sw + 140, 34), 12, 12)
            base_r = sx + sw + 70
            e = _ease((t - 0.4) / 1.1)
            ux = base_r + 46 + 220 * (1 - e)
            uy = sy + sh + 4
            p.setBrush(QColor("#C8C8D0"))
            p.drawRoundedRect(QRectF(ux - 46, uy + 6, 46, 22), 3, 3)
            p.setBrush(QColor(self.accent))
            p.drawRoundedRect(QRectF(ux, uy - 6, 150, 46), 14, 14)
            f = QFont()
            f.setPixelSize(20)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#15121E"))
            p.drawText(QRectF(ux, uy - 6, 150, 46), Qt.AlignCenter, drive)
            on = _ease((t - 1.6) / 0.4)
            if on > 0:
                p.setOpacity(on)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#17151F"))
                p.drawRoundedRect(QRectF(sx + 16, sy + 16, sw - 32, sh - 32), 10, 10)
                icon = 150
                pulse = 1 + 0.07 * max(0.0, 1 - abs(t - 2.75) / 0.15)
                sz = int(icon * pulse)
                p.drawPixmap(int(sx + sw / 2 - sz / 2), int(sy + 100 - (sz - icon) / 2), logo_pixmap(sz, self.accent))
                f.setPixelSize(30)
                f.setBold(False)
                p.setFont(f)
                p.setPen(QColor("#FFFFFF"))
                p.drawText(QRectF(sx, sy + 270, sw, 50), Qt.AlignCenter, file_name)
                if t > 2.2:
                    cx, cy = sx + sw / 2 + 40, sy + 190
                    p.setPen(QPen(QColor("#111111"), 2))
                    p.setBrush(QColor("#FFFFFF"))
                    pts = [(0, 0), (0, 34), (9, 25), (16, 40), (22, 37), (15, 23), (27, 23)]
                    p.drawPolygon([QPointF(cx + x, cy + y) for x, y in pts])
                    for t0 in (2.6, 2.8):
                        age = t - t0
                        if 0 < age < 0.4:
                            p.setOpacity(1 - age / 0.4)
                            p.setPen(QPen(QColor(self.accent), 4))
                            p.setBrush(Qt.NoBrush)
                            p.drawEllipse(QPointF(cx, cy), 10 + age * 120, 10 + age * 120)
                if t > 3.0:                                   # fenêtre DJSync qui s'ouvre
                    a = _ease((t - 3.0) / 0.4)
                    p.setOpacity(a)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor("#22202C"))
                    m = 40 * (1 - a)
                    p.drawRoundedRect(QRectF(sx + 40 + m, sy + 40 + m, sw - 80 - 2 * m, sh - 80 - 2 * m), 10, 10)
                    p.setBrush(QColor(self.accent))
                    p.drawRoundedRect(QRectF(sx + 60 + m, sy + 60 + m, 120, 22), 6, 6)
                    p.setBrush(QColor("#34313F"))
                    for j in range(5):
                        p.drawRoundedRect(QRectF(sx + 200 + m, sy + 110 + j * 46 + m, sw - 300, 26), 6, 6)
                p.setOpacity(1.0)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#6C6C7A"))
            for ddx, ddy in ((0, 0), (26, 0), (0, 26), (26, 26)):
                p.drawRect(QRectF(sx + sw / 2 - 25 + ddx, sy + sh + 90 + ddy, 22, 22))
            f = QFont()
            f.setPixelSize(32)
            p.setFont(f)
            p.setPen(QColor("#9A9AA8"))
            p.drawText(QRectF(sx, sy + sh + 150, sw, 50), Qt.AlignCenter, "Windows 10 · 11")

        self.scene(seconds, draw)

    def close(self) -> None:
        if self.ffmpeg is not None:
            self.ffmpeg.stdin.close()
            self.ffmpeg.wait()

    def expect(self, cond: Callable[[], bool], what: str, timeout: float = 4.0) -> None:
        """Vérifie qu'une action a eu l'effet attendu (sinon le tournage s'arrête avec un message clair)."""
        self.wait_until(cond, timeout)
        if not cond():
            raise RuntimeError(f"Video step failed: {what}")
