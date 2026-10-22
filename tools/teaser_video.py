"""OUTIL DE DÉVELOPPEMENT : teaser vertical (1080 x 1920, ~20 s) pour Reels / TikTok / Shorts.

    python tools/teaser_video.py teaser.mp4 [--lang en|fr] [--fps 30] [--speed 0.5]

Même principe que tools/demo_video.py (vraie interface hors écran, artistes fictifs, aucun réseau),
mais fenêtre en hauteur, plans courts, un mot-clé par plan en très gros.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_video as dv  # noqa: E402

PW, PH = 1080, 1920
APP_W, APP_H = 960, 1180            # fenêtre de l'appli (mise en page « haute »)
APP_X, APP_Y, APP_SCALE = 40, 560, 1000 / 960

TEXT = {
    "en": {
        "hook": ("Your DJ app", "lives on your USB."),
        "plug": ("Plug. Launch. Mix.", "any Windows PC · nothing to install"),
        "nomad": ("Nomad.", "DJSync.exe runs from your USB drive"),
        "download": ("Download.", "YouTube Music · Spotify · SoundCloud"),
        "download2": ("Download.", "straight into your playlists"),
        "analyse": ("Analyse.", "BPM · key · beat grid · waveforms"),
        "manage": ("Organise.", "playlists · Camelot keys · harmonic mixing"),
        "clean": ("Clean up.", "duplicates · music videos · low bitrate"),
        "rekordbox": ("100% Rekordbox.", "ready for Rekordbox and the decks"),
        "rb_items": [("Rekordbox library", "exportLibrary.db (OneLibrary)"),
                     ("Older players", "export.pdb kept in sync"),
                     ("Analysis files", "beat grids, waveforms, cues (ANLZ)"),
                     ("Your computer", "Rekordbox collection (master.db)")],
        "outro": ("One file.", "Any PC. Any gig."),
        "cta": "DJSync.exe — github.com/Pikkol0/djsync",
        "query": "nova lane",
        "playlist": "Saturday night",
        "file": "DJSync.exe",
        "drive": "DJ KEY",
    },
}
TEXT["fr"] = dict(TEXT["en"], **{
    "hook": ("Ton app DJ", "tient sur ta clé."),
    "plug": ("Branche. Lance. Mixe.", "n'importe quel PC Windows · rien à installer"),
    "nomad": ("Nomade.", "DJSync.exe tourne depuis ta clé USB"),
    "download": ("Télécharge.", "YouTube Music · Spotify · SoundCloud"),
    "download2": ("Télécharge.", "direct dans tes playlists"),
    "analyse": ("Analyse.", "BPM · tonalité · grille · waveforms"),
    "manage": ("Organise.", "playlists · tonalités Camelot · mix harmonique"),
    "clean": ("Nettoie.", "doublons · clips officiels · faible débit"),
    "rekordbox": ("100 % Rekordbox.", "prête pour Rekordbox et les platines"),
    "rb_items": [("Bibliothèque Rekordbox", "exportLibrary.db (OneLibrary)"),
                 ("Anciennes platines", "export.pdb synchronisé"),
                 ("Fichiers d'analyse", "grilles, waveforms, cues (ANLZ)"),
                 ("Ton ordinateur", "collection Rekordbox (master.db)")],
    "outro": ("Un seul fichier.", "Tous les PC. Toutes les soirées."),
    "playlist": "Samedi soir",
})


class PortraitRecorder(dv.Recorder):
    """Compose chaque image : fond, gros titre animé en haut, fenêtre de l'appli au milieu, marque en bas."""

    headline: Optional[Tuple[str, str]] = None
    head_since = 0.0
    view = [0.0, 0.0, float(APP_W)]          # zone de la fenêtre montrée (x, y, largeur), suivie en douceur
    target = [0.0, 0.0, float(APP_W)]

    def zoom(self, x: float = 0, y: float = 0, w: float = APP_W, now: bool = False) -> None:
        """Cadre sur une zone de la fenêtre (zoom « caméra ») ; x, y, w en pixels de la fenêtre."""
        self.target = [float(x), float(y), float(w)]
        if now:
            self.view = list(self.target)

    def say(self, key: Optional[str], text: dict) -> None:
        self.headline = text[key] if key else None
        self.head_since = self.t

    def frame(self) -> None:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath

        from djsync.ui.logo import logo_pixmap

        app_img = self.compose()                          # appli + dialogues + pointeur (sans légende)
        img = QImage(PW, PH, QImage.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, PW, PH)
        g.setColorAt(0, QColor("#121217"))
        g.setColorAt(1, QColor("#221B33"))
        p.fillRect(0, 0, PW, PH, g)
        glow = QColor(self.accent)                        # halo d'accent derrière la fenêtre
        for k in range(10, 0, -1):
            glow.setAlpha(6)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(QRectF(APP_X - k * 6, APP_Y - k * 6, 1000 + k * 12, APP_H * APP_SCALE + k * 12), 40, 40)
        w, h = 1000, APP_H * APP_SCALE
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(APP_X, APP_Y, w, h), 28, 28)
        p.save()
        p.setClipPath(clip)
        self.view = [v + (t - v) * 0.18 for v, t in zip(self.view, self.target)]
        vx, vy, vw = self.view
        p.drawImage(QRectF(APP_X, APP_Y, w, h), app_img, QRectF(vx, vy, vw, vw * h / w))
        p.restore()

        if self.headline:                                 # titre : glisse et apparaît
            age = self.t - self.head_since
            a = min(1.0, age / 0.25)
            dy = (1 - a) ** 2 * 60
            big, small = QFont(), QFont()
            big.setPixelSize(118)
            big.setBold(True)
            small.setPixelSize(44)
            p.setOpacity(a)
            p.setFont(big)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(0, 200 + dy, PW, 150), Qt.AlignCenter, self.headline[0])
            p.setFont(small)
            p.setPen(QColor(self.accent))
            p.drawText(QRectF(40, 360 + dy, PW - 80, 70), Qt.AlignCenter, self.headline[1])
            p.setOpacity(1.0)

        p.drawPixmap(PW // 2 - 150, PH - 140, logo_pixmap(64, self.accent))
        f = QFont()
        f.setPixelSize(52)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(PW // 2 - 70, PH - 140, 300, 64), Qt.AlignLeft | Qt.AlignVCenter, "DJSync")
        p.end()

        if self.fade_left and self.last is not None:
            k = self.fade_left / self.fade_total
            p = QPainter(img)
            p.setOpacity(k)
            p.drawImage(0, 0, self.last)
            p.end()
            self.fade_left -= 1
        img.save(str(self.dir / f"f{self.n:05d}.png"))
        self.n += 1
        self.t += 1 / self.fps
        self._current = img

    def cut(self, fade: float = 0.25) -> None:
        self.last = getattr(self, "_current", None)
        self.fade_total = self.fade_left = int(fade * self.fps)

    def scene(self, seconds: float, draw: Any) -> None:
        """Plan dessiné à la main : draw(painter, t) sur le fond dégradé, avec fondu d'entrée."""
        from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

        for i in range(int(seconds * self.fps)):
            img = QImage(PW, PH, QImage.Format_RGB32)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            g = QLinearGradient(0, 0, PW, PH)
            g.setColorAt(0, QColor("#121217"))
            g.setColorAt(1, QColor("#2A1F44"))
            p.fillRect(0, 0, PW, PH, g)
            draw(p, i / self.fps)
            p.setOpacity(1.0)
            p.end()
            if self.fade_left and self.last is not None:
                p = QPainter(img)
                p.setOpacity(self.fade_left / self.fade_total)
                p.drawImage(0, 0, self.last)
                p.end()
                self.fade_left -= 1
            img.save(str(self.dir / f"f{self.n:05d}.png"))
            self.n += 1
            self.t += 1 / self.fps
            self._current = img

    def card(self, lines: Tuple[str, str], seconds: float, cta: str = "") -> None:
        """Carton plein écran (accroche / fin), logo qui « pulse »."""
        import math

        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

        from djsync.ui.logo import logo_pixmap

        n = int(seconds * self.fps)
        for i in range(n):
            t = i / self.fps
            img = QImage(PW, PH, QImage.Format_RGB32)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            g = QLinearGradient(0, 0, PW, PH)
            g.setColorAt(0, QColor("#121217"))
            g.setColorAt(1, QColor("#2A1F44"))
            p.fillRect(0, 0, PW, PH, g)
            size = int(260 * (1 + 0.05 * math.sin(t * 2 * math.pi * 2)))     # pulsation ~120 BPM
            p.drawPixmap(PW // 2 - size // 2, 520 - size // 2, logo_pixmap(size, self.accent))
            big = QFont()
            big.setPixelSize(104)
            big.setBold(True)
            p.setFont(big)
            for k, line in enumerate(lines):
                a = max(0.0, min(1.0, (t - 0.25 - 0.45 * k) / 0.3))
                p.setOpacity(a)
                p.setPen(QColor("#FFFFFF") if k == 0 else QColor(self.accent))
                p.drawText(QRectF(0, 820 + k * 150 + (1 - a) * 40, PW, 140), Qt.AlignCenter, line)
            if cta:
                a = max(0.0, min(1.0, (t - 1.2) / 0.3))
                p.setOpacity(a)
                f = QFont()
                f.setPixelSize(40)
                p.setFont(f)
                p.setPen(QColor("#D8D8E0"))
                p.drawText(QRectF(40, 1240, PW - 80, 80), Qt.AlignCenter, cta)
            p.setOpacity(1.0)
            p.end()
            if self.fade_left and self.last is not None:
                p = QPainter(img)
                p.setOpacity(self.fade_left / self.fade_total)
                p.drawImage(0, 0, self.last)
                p.end()
                self.fade_left -= 1
            img.save(str(self.dir / f"f{self.n:05d}.png"))
            self.n += 1
            self.t += 1 / self.fps
            self._current = img


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _titles(p: Any, accent: str, lines: Tuple[str, str], t: float, y: float = 200) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont

    big, small = QFont(), QFont()
    big.setPixelSize(104)
    big.setBold(True)
    small.setPixelSize(44)
    a = _ease(t / 0.35)
    p.setOpacity(a)
    p.setFont(big)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, y + (1 - a) * 50, PW, 140), Qt.AlignCenter, lines[0])
    a2 = _ease((t - 0.25) / 0.35)
    p.setOpacity(a2)
    p.setFont(small)
    p.setPen(QColor(accent))
    p.drawText(QRectF(40, y + 150 + (1 - a2) * 40, PW - 80, 70), Qt.AlignCenter, lines[1])
    p.setOpacity(1.0)


def draw_plug(accent: str, text: dict) -> Any:
    """Une clé USB (avec DJSync.exe) qui glisse dans un portable Windows ; l'écran s'allume sur DJSync."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPen

    from djsync.ui.logo import logo_pixmap

    def draw(p: Any, t: float) -> None:
        _titles(p, accent, text["plug"], t)
        # portable
        sx, sy, sw, sh = 150, 640, 640, 420
        p.setPen(QPen(QColor("#3A3A46"), 6))
        p.setBrush(QColor("#0C0C10"))
        p.drawRoundedRect(QRectF(sx, sy, sw, sh), 22, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2A2A34"))
        p.drawRoundedRect(QRectF(sx - 70, sy + sh + 6, sw + 140, 34), 12, 12)
        # clé USB qui arrive par la droite
        k = _ease((t - 0.3) / 0.9)
        ux = 1120 - k * 220
        uy = sy + sh + 4
        p.setBrush(QColor("#C8C8D0"))
        p.drawRoundedRect(QRectF(ux - 46, uy + 6, 46, 22), 3, 3)          # connecteur
        p.setBrush(QColor(accent))
        p.drawRoundedRect(QRectF(ux, uy - 6, 150, 46), 14, 14)
        f = QFont()
        f.setPixelSize(20)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#15121E"))
        p.drawText(QRectF(ux, uy - 6, 150, 46), Qt.AlignCenter, text["drive"])
        # écran : s'allume quand la clé est branchée, l'icône DJSync.exe apparaît puis l'appli
        on = _ease((t - 1.25) / 0.4)
        if on > 0:
            p.setOpacity(on)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#17151F"))
            p.drawRoundedRect(QRectF(sx + 16, sy + 16, sw - 32, sh - 32), 10, 10)
            icon = 150
            pulse = 1 + 0.06 * max(0.0, 1 - abs(t - 1.9) / 0.15)          # « double-clic »
            sz = int(icon * pulse)
            p.drawPixmap(int(sx + sw / 2 - sz / 2), int(sy + 110 - (sz - icon) / 2), logo_pixmap(sz, accent))
            f.setPixelSize(30)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(sx, sy + 280, sw, 50), Qt.AlignCenter, text["file"])
            if t > 1.75:                                                   # pointeur qui double-clique
                cx, cy = sx + sw / 2 + 40, sy + 200
                p.setOpacity(on)
                p.setPen(QPen(QColor("#111111"), 2))
                p.setBrush(QColor("#FFFFFF"))
                pts = [(0, 0), (0, 34), (9, 25), (16, 40), (22, 37), (15, 23), (27, 23)]
                p.drawPolygon([QPointF(cx + x, cy + y) for x, y in pts])
                for k2, t0 in enumerate((1.85, 2.05)):
                    age = t - t0
                    if 0 < age < 0.4:
                        p.setOpacity(1 - age / 0.4)
                        p.setPen(QPen(QColor(accent), 4))
                        p.setBrush(Qt.NoBrush)
                        p.drawEllipse(QPointF(cx, cy), 10 + age * 120, 10 + age * 120)
            p.setOpacity(1.0)
        # petits logos « Windows » (4 carreaux) sous le portable
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#6C6C7A"))
        for dx, dy in ((0, 0), (26, 0), (0, 26), (26, 26)):
            p.drawRect(QRectF(sx + sw / 2 - 25 + dx, sy + sh + 90 + dy, 22, 22))
        f = QFont()
        f.setPixelSize(32)
        p.setFont(f)
        p.setPen(QColor("#9A9AA8"))
        p.drawText(QRectF(sx, sy + sh + 150, sw, 50), Qt.AlignCenter, "Windows 10 · 11")

    return draw


def draw_rekordbox(accent: str, text: dict) -> Any:
    """Ce que DJSync écrit sur la clé et sur le PC, au format de Rekordbox : liste qui apparaît ligne par ligne."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPen

    def draw(p: Any, t: float) -> None:
        _titles(p, accent, text["rekordbox"], t)
        top = 660
        for i, (head, sub) in enumerate(text["rb_items"]):
            a = _ease((t - 0.45 - 0.3 * i) / 0.35)
            if a <= 0:
                continue
            y = top + i * 230 + (1 - a) * 50
            p.setOpacity(a)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(QRectF(90, y, PW - 180, 190), 28, 28)
            p.setBrush(QColor(accent))                                    # coche
            p.drawEllipse(QRectF(130, y + 55, 80, 80))
            p.setPen(QPen(QColor("#15121E"), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(150, y + 96), QPointF(165, y + 111), QPointF(192, y + 80)])
            f = QFont()
            f.setPixelSize(48)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(250, y + 30, PW - 360, 66), Qt.AlignLeft | Qt.AlignVCenter, head)
            f.setPixelSize(34)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor("#B9B9C6"))
            p.drawText(QRectF(250, y + 100, PW - 360, 56), Qt.AlignLeft | Qt.AlignVCenter, sub)
        p.setOpacity(1.0)

    return draw


def scenario(app: Any, rec: PortraitRecorder, text: dict) -> None:
    from PySide6.QtWidgets import QApplication

    from djsync.ui.diagnostic_dialog import DiagnosticDialog
    from djsync.ui.views.library_view import ALL

    ctrl = app.ctrl
    rec.card(text["hook"], 2.0)

    # ---- 1. Nomade : la clé dans n'importe quel PC, puis l'Accueil qui reconnaît la clé
    rec.cut(0.25)
    rec.scene(2.8, draw_plug(rec.accent, text))
    app.show_view("home")
    rec.pump(0.8)
    rec.zoom(190, 40, 770, now=True)
    rec.cut(0.25)
    rec.say("nomad", text)
    rec.hold(1.6)

    # ---- 2. Téléchargement
    app.show_view("search")
    search = app.views["search"]
    rec.pump(0.4)
    rec.zoom(190, 0, 770, now=True)
    rec.cut(0.2)
    rec.say("download", text)
    rec.cursor = (APP_W * 0.5, APP_H * 0.3)
    rec.click(search.entry, lambda: search.entry.setFocus(), seconds=0.3)
    rec.type_into(search.entry, text["query"], cps=24)
    search.run_search()
    rec.hold(1.1)
    rows = search.table.displayed_iids()
    ctrl.create_playlist(text["playlist"])
    rec.pump(0.4)
    pid = next((p.playlist_id for p in ctrl.playlists if p.name == text["playlist"]), None)
    picks = [rows[i] for i in (1, 2, 4) if i < len(rows)]
    search.table.select(picks)
    rec.hold(0.3)
    ctrl.enqueue([search._tracks[i] for i in picks], [pid] if pid else [])
    app.show_view("downloads")
    rec.zoom(190, 0, 770, now=True)
    rec.cut(0.2)
    rec.say("download2", text)
    rec.hold(1.9)

    # ---- 3. Analyse : éditeur de grille
    lib = app.views["library"]
    app.show_view("library")
    lib.nav.setCurrentItem(lib._items[ALL])
    rec.pump(1.0)
    target = next((r.data for r in lib.table.all_rows() if r.data.title == "Grid Test"), None)
    if target is not None:
        app.open_grid_editor(target)
        rec.pump(2.0)
        rec.zoom(150, 0, 810, now=True)
        rec.cut(0.2)
        rec.say("analyse", text)
        rec.hold(1.9)
        app.grid_editor.close()
        rec.pump(0.3)

    # ---- 4. Gestion de la bibliothèque : playlists + Camelot, puis diagnostic
    lib.nav.setCurrentItem(lib._items[ALL])
    rec.pump(0.6)
    rec.zoom(190, 0, 770, now=True)
    rec.cut(0.2)
    rec.say("manage", text)
    rec.hold(1.7)
    app.show_view("home")
    app.views["home"]._open_diagnostic()
    rec.pump(2.0)
    rec.zoom(0, 0, APP_W, now=True)
    rec.cut(0.2)
    rec.say("clean", text)
    dlg = next((w for w in QApplication.topLevelWidgets() if isinstance(w, DiagnosticDialog) and w.isVisible()), None)
    rec.hold(0.6)
    if dlg is not None:
        b = dlg._choice.button(100)
        if b is not None:
            rec.click(b, lambda: b.setChecked(True), seconds=0.4)
        rec.hold(0.9)
        dlg.close()
    rec.pump(0.3)

    # ---- 5. Compatible Rekordbox
    rec.cut(0.3)
    rec.scene(3.4, draw_rekordbox(rec.accent, text))

    # ---- Fin
    rec.cut(0.35)
    rec.card(text["outro"], 3.0, cta=text["cta"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--speed", type=float, default=1.0, help="0.5 = half speed")
    args = ap.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("FFmpeg is required.")
        return 1
    dv.W, dv.H = APP_W, APP_H                     # Recorder.compose travaille à la taille de la fenêtre
    app, usb, frames, accent = dv.build_app(args.lang, (APP_W, APP_H))
    rec = PortraitRecorder(app, frames, args.fps, accent)
    dv.settle(app, rec, usb)
    scenario(app, rec, TEXT[args.lang])
    app.close()
    dv.encode(ffmpeg, frames, args.fps, args.out, args.speed)
    print(f"video: {args.out}  ({rec.n / args.fps / args.speed:.1f} s, {rec.n} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
