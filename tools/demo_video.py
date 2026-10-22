"""OUTIL DE DÉVELOPPEMENT (pas livré dans l'exécutable) : vidéo de présentation de DJSync.

    python tools/demo_video.py sortie.mp4 [--lang fr|en] [--fps 25]

Filme la VRAIE interface (plateforme Qt « offscreen », pas besoin d'écran) sur une fausse clé de
démonstration aux artistes fictifs, sans réseau : recherche, téléchargement, bibliothèque, analyse,
lecteur, grille, import Spotify, diagnostic, copie, réglages. Un pointeur de souris simulé montre les
clics ; les légendes sont incrustées. FFmpeg assemble les images en MP4 (H.264).
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DJSYNC_AUDIO_NULL", "1")

W, H = 1280, 720

# Artistes et titres FICTIFS (aucune marque réelle dans la vidéo)
DEMO = [  # titre, artiste, album, bpm, tonalité, playlists
    ("Midnight Drive", "Nova Lane", "Neon Hours", 122.0, "F#m", ["House", "Warm-up"]),
    ("Midnight Drive (Clip Officiel)", "Nova Lane", None, 122.0, "F#m", ["House"]),
    ("Golden Hour", "Solé", None, 124.0, "Bbm", ["House"]),
    ("Rue des Lilas", "K-Lyon", None, 75.0, "Bbm", ["Rap FR"]),
    ("Béton", "Oscar Vale", "Gris", 75.0, "Abm", ["Rap FR"]),
    ("Pressure (Official Video)", "Endo Kid", None, 129.0, "C#m", ["Club"]),
    ("Lights Out", "Mara Ko", None, 138.0, "E", ["Club", "Rap FR"]),
    ("Summer Rain", "Lia Sun", "Weather", 87.0, "Db", ["Warm-up"]),
    ("Funk Machine", "Groove Unit", None, 130.0, "C", ["Club"]),
    ("Late Night Talk", "Inconnu", None, 0, None, []),
]

TEXT = {
    "fr": {
        "intro": ("DJSync", "Vos sons, votre clé Rekordbox. Sans Rekordbox."),
        "home": ("Un seul fichier sur la clé", "DJSync reconnaît la clé USB… et la bibliothèque Rekordbox du PC"),
        "search": ("Chercher", "YouTube Music, en un instant — ou collez un lien Spotify, YouTube, SoundCloud"),
        "download": ("Télécharger", "Directement dans vos playlists Rekordbox"),
        "downloads": ("Téléchargements", "Format, tags, pochette : tout est rangé sur la clé"),
        "library": ("Bibliothèque", "Playlists, BPM, tonalités Camelot, filtre harmonique, copie vers une autre bibliothèque"),
        "analysis": ("Analyse", "BPM, tonalité, grille et formes d'onde, lisibles par les platines"),
        "player": ("Lecteur", "Préécoute avec la forme d'onde, comme sur la platine"),
        "grid": ("Grille de temps", "Corrigez le premier temps et le tempo, au battement près"),
        "import": ("Import de playlist", "Une playlist Spotify → les bons sons trouvés automatiquement"),
        "diag": ("Diagnostic", "Doublons, faible débit, clips officiels → remplacés par une version propre"),
        "settings": ("Réglages", "Format m4a ou MP3, normalisation, moteur de téléchargement à jour"),
        "help": ("Partout, tout le temps", "Fonctionne hors ligne · éjection propre · sauvegarde avant chaque modification"),
        "outro": ("DJSync", "Téléchargez DJSync.exe — github.com/Pikkol0/djsync"),
        "query": "nova lane",
        "spotify": "https://open.spotify.com/playlist/demo",
        "playlist": "Soirée de samedi",
    },
    "en": {
        "intro": ("DJSync", "Your tracks, your Rekordbox USB drive. No Rekordbox needed."),
        "home": ("One file on the drive", "DJSync finds the USB drive… and this computer's Rekordbox library"),
        "search": ("Search", "YouTube Music in an instant — or paste a Spotify, YouTube, SoundCloud link"),
        "download": ("Download", "Straight into your Rekordbox playlists"),
        "downloads": ("Downloads", "Format, tags, artwork: everything filed on the drive"),
        "library": ("Library", "Playlists, BPM, Camelot keys, harmonic filter, copy to another library"),
        "analysis": ("Analysis", "BPM, key, beat grid and waveforms, readable by the players"),
        "player": ("Player", "Preview with the waveform, like on the deck"),
        "grid": ("Beat grid", "Fix the first beat and the tempo, to the beat"),
        "import": ("Playlist import", "A Spotify playlist → the right tracks found automatically"),
        "diag": ("Diagnostic", "Duplicates, low bitrate, music videos → replaced by a clean version"),
        "settings": ("Settings", "m4a or MP3, volume normalisation, up-to-date download engine"),
        "help": ("Anywhere, anytime", "Works offline · safe eject · backup before every change"),
        "outro": ("DJSync", "Download DJSync.exe — github.com/Pikkol0/djsync"),
        "query": "nova lane",
        "spotify": "https://open.spotify.com/playlist/demo",
        "playlist": "Saturday night",
    },
}


# ============================================================================ données fictives
def fake_results(query: str) -> list:
    from djsync.models import TrackResult

    base = [("Nova Lane", "Midnight Drive", 214, "song"), ("Nova Lane", "Afterglow", 198, "song"),
            ("Nova Lane", "City Lights (Extended Mix)", 362, "song"), ("Nova Lane", "Afterglow (Live Session)", 251, "video"),
            ("Nova Lane & Solé", "Golden Coast", 189, "song"), ("Nova Lane", "Parallel", 227, "song")]
    return [TrackResult(video_id=f"vid{i:08d}", title=title, artist=artist, album="Neon Hours" if i < 3 else None,
                        duration_seconds=d, result_type=kind, views=None if kind == "song" else 182_000 * (i + 1))
            for i, (artist, title, d, kind) in enumerate(base)]


SPOTIFY = [("Afterglow", "Nova Lane", 198), ("Paper Planes", "Lia Sun", 205), ("Concrete", "Oscar Vale", 176),
           ("Saturday", "Mara Ko", 221), ("Low Tide", "Endo Kid", 243), ("Velvet", "Solé", 190),
           ("Slow Motion", "K-Lyon", 168), ("Bassline Theory", "Groove Unit", 287)]


def make_service():
    import wave

    from djsync.models import Candidate, DownloadedTrack, DownloadProgress, SearchMode, SpotifyPlaylist, SpotifyTrack, TrackResult
    from tests.test_ui_smoke import FakeService

    class VideoService(FakeService):
        def search(self, query, limit=20, mode=SearchMode.ALL, exclude=None):
            time.sleep(0.6)
            return self.annotate(fake_results(query))

        def fetch_views(self, video_id):
            return 1_250_000

        def fetch_spotify(self, url):
            time.sleep(0.5)
            return SpotifyPlaylist(name="Saturday Night", tracks=[SpotifyTrack(t, (a,), None, d) for t, a, d in SPOTIFY])

        def match_spotify(self, source, per_type=5):
            time.sleep(0.25)
            title = source.title
            vid = "sp" + "".join(c for c in title if c.isalnum())[:9].ljust(9, "x")
            song = TrackResult(video_id=vid, title=title, artist=source.artist, duration_seconds=source.duration_seconds + 1)
            video = TrackResult(video_id=vid[:-1] + "v", title=f"{title} (Official Video)", artist=source.artist,
                                duration_seconds=source.duration_seconds + 14, result_type="video")
            score = 64.0 if title == "Slow Motion" else 93.0
            return [Candidate(song, score), Candidate(video, 71.0)]

        def download(self, track, dest_dir, on_progress=None, tag=True):
            for p in range(0, 101, 7):
                if on_progress:
                    on_progress(DownloadProgress("downloading", float(p), ""))
                time.sleep(0.09)
            if on_progress:
                on_progress(DownloadProgress("tagging", 100.0, ""))
            time.sleep(0.3)
            dest = Path(dest_dir)
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"{track.artist} - {track.title}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
                w.writeframes(b"\0\0" * 8000)
            return DownloadedTrack(track, str(path))

    return VideoService


# ============================================================================ enregistreur
class Recorder:
    def __init__(self, app: Any, frames: Path, fps: int, accent: str) -> None:
        self.app, self.dir, self.fps, self.accent = app, frames, fps, accent
        self.n = 0
        self.cursor: Tuple[float, float] = (W * 0.62, H * 0.55)
        self.click_at: Optional[Tuple[float, float, float]] = None     # x, y, instant du clic
        self.caption: Optional[Tuple[str, str]] = None
        self.caption_since = 0.0
        self.t = 0.0
        self.last = None
        self.fade_left = 0

    # ---------------------------------------------------------------- images
    def pump(self, seconds: float) -> None:
        from PySide6.QtWidgets import QApplication

        from PySide6.QtCore import QEvent

        end = time.time() + seconds
        while time.time() < end:
            QApplication.instance().processEvents()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)    # comme la vraie boucle d'événements
            time.sleep(0.005)

    def compose(self) -> Any:
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtWidgets import QApplication, QDialog

        img = QImage(W, H, QImage.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(0, 0, self.app.grab())
        dialogs = [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()]
        for d in dialogs:
            p.fillRect(0, 0, W, H, QColor(0, 0, 0, 110))
            pm = d.grab()
            x, y = (W - pm.width()) // 2, max(10, (H - pm.height()) // 2 - 20)
            d._video_pos = (x, y)
            p.setPen(Qt.NoPen)
            for k in range(6):                                   # ombre douce
                p.setBrush(QColor(0, 0, 0, 22))
                p.drawRoundedRect(QRectF(x - k * 2, y - k * 2 + 6, pm.width() + k * 4, pm.height() + k * 4), 12, 12)
            p.drawPixmap(x, y, pm)
        self._draw_caption(p)
        self._draw_cursor(p, QPointF(*self.cursor))
        p.end()
        return img

    def _draw_caption(self, p: Any) -> None:
        if not self.caption:
            return
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont

        age = self.t - self.caption_since
        alpha = min(1.0, age / 0.35)
        slide = (1 - alpha) * 18
        title, sub = self.caption
        ft, fs = QFont(), QFont()
        ft.setPixelSize(26)
        ft.setBold(True)
        fs.setPixelSize(18)
        from PySide6.QtGui import QFontMetrics

        w = max(QFontMetrics(ft).horizontalAdvance(title), QFontMetrics(fs).horizontalAdvance(sub)) + 56
        box = QRectF(40, H - 132 + slide, w, 92)
        p.setOpacity(alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(12, 12, 16, 230))
        p.drawRoundedRect(box, 14, 14)
        p.setBrush(QColor(self.accent))
        p.drawRoundedRect(QRectF(box.x(), box.y(), 6, box.height()), 3, 3)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(ft)
        p.drawText(QRectF(box.x() + 28, box.y() + 14, w, 34), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QColor("#C9C9D2"))
        p.setFont(fs)
        p.drawText(QRectF(box.x() + 28, box.y() + 50, w, 28), Qt.AlignLeft | Qt.AlignVCenter, sub)
        p.setOpacity(1.0)

    def _draw_cursor(self, p: Any, at: Any) -> None:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QPainterPath, QPen

        if self.click_at is not None:
            cx, cy, t0 = self.click_at
            age = self.t - t0
            if age < 0.5:
                r = 8 + age * 60
                p.setPen(QPen(QColor(self.accent), 3))
                p.setOpacity(max(0.0, 1 - age / 0.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r, r)
                p.setOpacity(1.0)
        path = QPainterPath()
        x, y = at.x(), at.y()
        pts = [(0, 0), (0, 22), (6, 16.5), (10.5, 26), (14, 24.5), (9.5, 15), (17, 15)]
        path.moveTo(x, y)
        for dx, dy in pts[1:]:
            path.lineTo(x + dx, y + dy)
        path.closeSubpath()
        p.setPen(QPen(QColor("#111111"), 1.6))
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(path)

    def frame(self) -> None:
        from PySide6.QtGui import QPainter

        img = self.compose()
        if self.fade_left and self.last is not None:          # fondu enchaîné entre deux plans
            k = self.fade_left / self.fade_total
            blend = img.copy()
            p = QPainter(blend)
            p.setOpacity(k)
            p.drawImage(0, 0, self.last)
            p.end()
            img = blend
            self.fade_left -= 1
        img.save(str(self.dir / f"f{self.n:05d}.png"))
        self.n += 1
        self.t += 1 / self.fps
        self._current = img

    def hold(self, seconds: float) -> None:
        for _ in range(max(1, int(seconds * self.fps))):
            self.pump(1 / self.fps * 0.6)
            self.frame()

    def cut(self, caption_key: Optional[str] = None, text: Optional[dict] = None, fade: float = 0.4) -> None:
        """Nouveau plan : fondu depuis la dernière image, nouvelle légende."""
        self.last = getattr(self, "_current", None)
        self.fade_total = self.fade_left = int(fade * self.fps)
        if caption_key and text:
            self.caption = text[caption_key]
            self.caption_since = self.t
        else:
            self.caption = None

    # ---------------------------------------------------------------- souris
    def pos_of(self, widget: Any) -> Tuple[float, float]:
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QDialog

        win = widget.window()
        c = widget.rect().center()
        if isinstance(win, QDialog):
            pt = widget.mapTo(win, c)
            ox, oy = getattr(win, "_video_pos", ((W - win.width()) // 2, (H - win.height()) // 2))
            return ox + pt.x(), oy + pt.y()
        pt = widget.mapTo(self.app, QPoint(c.x(), c.y()))
        return float(pt.x()), float(pt.y())

    def move(self, target: Tuple[float, float], seconds: float = 0.7) -> None:
        x0, y0 = self.cursor
        x1, y1 = target
        steps = max(2, int(seconds * self.fps))
        for i in range(1, steps + 1):
            k = i / steps
            e = 0.5 - 0.5 * math.cos(math.pi * k)              # accélère puis freine
            arc = math.sin(math.pi * k) * 30
            self.cursor = (x0 + (x1 - x0) * e, y0 + (y1 - y0) * e - arc)
            self.pump(0.01)
            self.frame()

    def click(self, widget: Any, action: Any = None, seconds: float = 0.7) -> None:
        self.frame()
        self.move(self.pos_of(widget), seconds)
        self.click_at = (*self.cursor, self.t)
        self.hold(0.15)
        if action is not None:
            action()
        elif hasattr(widget, "click"):
            widget.click()
        self.hold(0.25)

    def type_into(self, widget: Any, text: str, cps: float = 14) -> None:
        widget.setFocus()
        for i in range(1, len(text) + 1):
            widget.setText(text[:i])
            self.pump(0.01)
            for _ in range(max(1, int(self.fps / cps))):
                self.frame()

    def card(self, title: str, sub: str, seconds: float, logo: bool = True) -> None:
        """Carton titre (intro / fin)."""
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

        from djsync.ui.logo import logo_pixmap

        n = int(seconds * self.fps)
        for i in range(n):
            k = min(1.0, i / (0.6 * self.fps))
            img = QImage(W, H, QImage.Format_RGB32)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            g = QLinearGradient(0, 0, W, H)
            g.setColorAt(0, QColor("#141419"))
            g.setColorAt(1, QColor("#1E1A2B"))
            p.fillRect(0, 0, W, H, g)
            p.setOpacity(k)
            size = 120
            if logo:
                p.drawPixmap(int(W / 2 - size / 2), int(H / 2 - 150 + (1 - k) * 20), logo_pixmap(size, self.accent))
            f = QFont()
            f.setPixelSize(64)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(0, H / 2 - 10, W, 80), Qt.AlignCenter, title)
            f.setPixelSize(26)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor("#C9C9D2"))
            p.drawText(QRectF(0, H / 2 + 72, W, 40), Qt.AlignCenter, sub)
            p.end()
            if self.fade_left and getattr(self, "_current", None) is not None:
                pass
            img.save(str(self.dir / f"f{self.n:05d}.png"))
            self.n += 1
            self.t += 1 / self.fps
            self._current = img


# ============================================================================ scénario
def scenario(app: Any, rec: Recorder, text: dict, usb: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from djsync.ui.dialogs import PlaylistPicker

    ctrl = app.ctrl
    rec.card(*text["intro"], seconds=3.2)

    # ---- Accueil
    app.show_view("home")
    home = app.views["home"]
    rec.pump(1.5)
    rec.cut("home", text, fade=0.6)
    rec.hold(3.2)

    # ---- Recherche
    rec.click(home.omnibar, lambda: home.omnibar.setFocus())
    rec.type_into(home.omnibar, text["query"])
    rec.hold(0.3)
    rec.click(home.go_btn)
    rec.cut("search", text, fade=0.3)
    search = app.views["search"]
    rec.hold(1.6)
    rows = search.table.displayed_iids()
    rec.hold(1.4)

    # ---- Télécharger dans une playlist
    rec.cut("download", text, fade=0.0)
    first = rows[1] if len(rows) > 1 else rows[0]
    search.table.select([first])
    rec.hold(0.6)
    from djsync.ui.widgets import button as _b  # noqa: F401  (même style que l'appli)

    rec.click(search.table, lambda: search._download())
    rec.hold(0.8)
    picker = next((w for w in QApplication.topLevelWidgets() if isinstance(w, PlaylistPicker) and w.isVisible()), None)
    if picker is not None:
        rec.frame()
        rec.click(picker._new, lambda: picker._new.setFocus())
        rec.type_into(picker._new, text["playlist"], cps=18)
        rec.click(picker._new, lambda: picker._create())
        rec.hold(0.7)
        rec.click(picker._ok_btn)
    rec.hold(0.4)
    pid = next((p.playlist_id for p in ctrl.playlists if p.name == text["playlist"]), None)
    picks = [rows[i] for i in (2, 4) if i < len(rows)]
    search.table.select(picks)
    ctrl.enqueue([search._tracks[i] for i in picks], [pid] if pid else [])
    app.show_view("downloads")
    rec.cut("downloads", text, fade=0.3)
    rec.hold(3.6)

    # ---- Bibliothèque
    app.show_view("library")
    lib = app.views["library"]
    rec.pump(1.0)
    rec.cut("library", text, fade=0.4)
    rec.hold(1.5)
    items = getattr(lib, "_items", {})
    house = next((k for k, it in items.items() if it.text(0).startswith("House")), None)
    if house is not None:
        tree = items[house].treeWidget()
        rect = tree.visualItemRect(items[house])
        target = tree.viewport()
        pos = target.mapTo(app, rect.center())
        rec.move((pos.x(), pos.y()))
        rec.click_at = (*rec.cursor, rec.t)
        tree.setCurrentItem(items[house])
        rec.hold(2.2)

    # ---- Analyse (carte de progression, sans attendre la vraie analyse de tous les sons)
    gate = threading.Event()
    real = ctrl.library.analyze_tracks
    ctrl.library.analyze_tracks = lambda ids, **kw: (gate.wait(30), real(ids, **kw))[1]
    lib.show_unanalysed()
    rec.pump(0.8)
    rec.cut("analysis", text, fade=0.3)
    rec.hold(0.8)
    lib._analyse_all()
    q = ctrl.analysis
    for k in range(1, 9):
        q.done, q.current = k, f"{DEMO[k][1]} - {DEMO[k][0]}"
        ctrl._emit("analysis")
        rec.hold(0.4)
    ctrl.stop_analysis()
    gate.set()
    rec.pump(3)
    ctrl.library.analyze_tracks = real

    # ---- Lecteur + grille
    from djsync.ui.views.library_view import ALL

    lib.nav.setCurrentItem(lib._items[ALL])
    rec.pump(1.5)
    target = next((r.data for r in lib.table.all_rows() if r.data.title == "Grid Test"), None)
    if target is not None:
        lib.table.select([str(target.content_id)])
        lib._play(str(target.content_id))
        rec.pump(2.0)
        rec.cut("player", text, fade=0.3)
        rec.move((W * 0.5, H - 40), 0.8)
        rec.hold(2.6)
        ctrl.player.stop()
        app.open_grid_editor(target)
        rec.pump(2.5)
        rec.cut("grid", text, fade=0.4)
        rec.hold(3.4)
        app.grid_editor.close()
        rec.pump(0.3)

    # ---- Import Spotify
    app.show_view("import")
    imp = app.views["import"]
    rec.pump(0.6)
    rec.cut("import", text, fade=0.4)
    rec.click(imp.url, lambda: imp.url.setFocus())
    rec.type_into(imp.url, text["spotify"], cps=30)
    rec.click(imp.go)
    rec.hold(4.2)

    # ---- Diagnostic
    from djsync.ui.diagnostic_dialog import DiagnosticDialog

    app.show_view("home")
    rec.pump(1.0)
    rec.cut("diag", text, fade=0.4)
    rec.hold(0.6)
    diag_btn = next((b for b in home.cards.findChildren(type(home.go_btn)) if b.text() == "Diagnostic"), None)
    if diag_btn is not None:
        rec.click(diag_btn)
    else:
        home._open_diagnostic()
    rec.hold(2.6)
    dlg = next((w for w in QApplication.topLevelWidgets() if isinstance(w, DiagnosticDialog) and w.isVisible()), None)
    if dlg is not None:
        b = dlg._choice.button(100)
        if b is not None:
            rec.click(b, lambda: b.setChecked(True))
            rec.hold(1.6)
        dlg._select(1) if len(dlg.items) > 1 else None
        rec.hold(2.4)
        dlg.close()
        rec.pump(0.3)

    # ---- Réglages
    app.show_view("settings")
    sv = app.views["settings"]
    from PySide6.QtWidgets import QScrollArea

    area = next(iter(sv.findChildren(QScrollArea)), None)
    if area is not None:
        area.ensureWidgetVisible(sv.format_menu, 0, 260)
    rec.pump(0.8)
    rec.cut("settings", text, fade=0.4)
    rec.hold(3.0)

    # ---- Transverse : aide, hors ligne, éjection
    app.open_help()
    rec.pump(1.0)
    rec.cut("help", text, fade=0.4)
    rec.hold(3.4)
    for w in QApplication.topLevelWidgets():
        if w.isVisible() and w is not app:
            w.close()
    rec.pump(0.3)
    rec.cut(None, fade=0.6)
    rec.card(*text["outro"], seconds=3.4)


def build_app(lang: str, size: Tuple[int, int] = (0, 0), zoom: int = 100) -> Tuple[Any, Path, Path, str]:
    """Fausse clé (artistes fictifs) + bibliothèque du PC de démonstration + DJSyncApp hors écran, sans réseau.
    Renvoie (fenêtre, clé, dossier des images, couleur d'accent)."""
    tmp = Path(tempfile.mkdtemp(prefix="djsync_video_"))
    frames = tmp / "frames"
    frames.mkdir()
    os.environ["DJSYNC_HOME"] = str(tmp / "home")

    import tests.demo_fixture as demo_fixture

    demo_fixture.DEMO = DEMO
    usb = demo_fixture.make_demo_usb(tmp, analysed_song=True)

    import djsync.core.quality as quality
    import djsync.db.local_library as local_library
    import djsync.ui.controller as controller
    import djsync.ui.ctrl.diagnostic as diagnostic
    from djsync.db import UsbDrive
    from djsync.settings import Settings

    controller.find_usb_drives = lambda: [UsbDrive(root=usb, label="DJ KEY")]
    controller.MusicService = make_service()
    real_probe = quality.probe
    quality.probe = lambda p: quality.AudioInfo("mp3", 160, 44100) if p.name.startswith("Lia Sun") else real_probe(p)
    diagnostic.soundcloud_search = lambda q, limit=3: []
    db_dir = tmp / "Pioneer" / "rekordbox"                  # bibliothèque du PC (base de démonstration)
    db_dir.mkdir(parents=True)
    for f in (ROOT / "tests" / "data" / "rekordbox6").glob("*"):
        if f.suffix != ".md":
            shutil.copy(f, db_dir / f.name)
    local_library.rekordbox_running = lambda: False

    from djsync.ui.app import DJSyncApp
    from djsync.ui import theme

    settings = Settings()
    settings.language = lang
    settings.zoom = zoom
    settings.local_db_dir, settings.local_music_dir = str(db_dir), str(tmp / "Music")
    settings.active_drive = str(usb)
    app = DJSyncApp(settings)
    app.resize(*(size if size[0] else (W, H)))
    app.reveal()
    return app, usb, frames, getattr(theme, "ACCENT", "#B388FF")


def settle(app: Any, rec: "Recorder", usb: Path) -> None:
    """Attend l'ouverture de la clé (et pas celle du PC)."""
    from djsync.db import UsbDrive

    rec.pump(4)
    deadline = time.time() + 10
    while not app.ctrl.has_library and time.time() < deadline:
        rec.pump(0.2)
    if app.ctrl.is_local:
        app.ctrl.connect(UsbDrive(root=usb, label="DJ KEY"))
        rec.pump(3)


def encode(ffmpeg: str, frames: Path, fps: int, out: Path, speed: float = 1.0) -> None:
    """speed < 1 ralentit la vidéo (0.5 = deux fois plus lente, même nombre d'images par seconde)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    slow = ["-vf", f"setpts={1 / speed:g}*PTS,fps={fps}"] if speed != 1.0 else []
    cmd = [ffmpeg, "-y", "-v", "error", "-framerate", str(fps), "-i", str(frames / "f%05d.png"), *slow,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
           "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--lang", default="fr")
    ap.add_argument("--fps", type=int, default=25)
    args = ap.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("FFmpeg is required.")
        return 1
    text = TEXT[args.lang]
    app, usb, frames, accent = build_app(args.lang)
    rec = Recorder(app, frames, args.fps, accent)
    settle(app, rec, usb)
    scenario(app, rec, text, usb)
    app.close()

    encode(ffmpeg, frames, args.fps, args.out)
    print(f"video: {args.out}  ({rec.n / args.fps:.0f} s, {rec.n} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
