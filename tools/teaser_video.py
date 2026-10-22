"""OUTIL DE DÉVELOPPEMENT : vidéo verticale (1080 x 1920, ~75 s) du workflow principal, pour Reels /
TikTok / Shorts.

    python tools/teaser_video.py teaser.mp4 [--fps 30]

Vraie interface hors écran (artistes fictifs, aucun réseau), filmée par tools/video_kit.Studio : le
pointeur clique les vrais boutons, un panneau de texte annonce chaque partie, la caméra recadre la zone
utile, un projecteur montre l'élément dont on parle. Rien d'important dans les 350 px du bas (zone de la
légende et des boutons des plateformes).
"""
from __future__ import annotations

import argparse
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_video as dv  # noqa: E402
import video_kit as vk  # noqa: E402

CANVAS = (1080, 1920)
APP = (1240, 1440)                      # fenêtre de l'appli (interface à 120 %, la fenêtre Diagnostic y tient)
DISPLAY = (40, 250, 1000, 1000 * APP[1] / APP[0])
CTA = "DJSync.exe — github.com/Pikkol0/djsync"


def prepare() -> None:
    """Faux système / réseau pour le tournage : éjection réussie, moteur à jour."""
    import djsync.core.engine as engine
    import djsync.ui.controller as controller

    controller.eject_volume = lambda root: True
    engine.latest = lambda fetch=None: engine.Release(engine.current_version(), {})


def row_rect(table: Any, title: str, key: str = "") -> Any:
    """Rectangle (dans le viewport) de la ligne `title` (ou de sa cellule `key`)."""
    from PySide6.QtCore import QRect

    row = next(r for r in table.all_rows() if getattr(r.data, "title", None) == title)
    i = table._index_of(row.iid)
    title_col = table.column_index("title")
    table.scrollTo(table._model.index(i, title_col))      # ligne visible avant d'y pointer
    if key:
        return table.visualRect(table._model.index(i, table.column_index(key)))
    first = table.visualRect(table._model.index(i, title_col))
    return QRect(0, first.y(), table.viewport().width(), first.height())


def header_rect(table: Any, key: str) -> Any:
    from PySide6.QtCore import QRect

    h = table.horizontalHeader()
    c = table.column_index(key)
    return h, QRect(h.sectionViewportPosition(c), 0, h.sectionSize(c), h.height())


def nav_rect(lib: Any, iid: str) -> Any:
    return lib.nav.visualItemRect(lib._items[iid])


def fake_analysis(s: vk.Studio, ctrl: Any, seconds: float) -> None:
    """La file d'analyse avance (barre de progression) sans attendre le calcul réel des faux sons."""
    gate = threading.Event()
    real = ctrl.library.analyze_tracks
    ctrl.library.analyze_tracks = lambda ids, **kw: (gate.wait(60), real(ids, **kw))[1]
    q = ctrl.analysis
    total = max(2, getattr(q, "total", 10) or 10)
    steps = 8
    for k in range(1, steps + 1):
        q.done = min(total - 1, int(total * k / (steps + 1)))
        q.current = f"{dv.DEMO[k % len(dv.DEMO)][1]} - {dv.DEMO[k % len(dv.DEMO)][0]}"
        ctrl._emit("analysis")
        s.hold(seconds / steps)
    ctrl.stop_analysis()
    gate.set()
    s.pump(2.5)
    ctrl.library.analyze_tracks = real


def warm_grid(app: Any, s: vk.Studio) -> None:
    """Calcule d'avance la forme d'onde de l'éditeur de grille (mise en cache) : pas d'attente à l'image."""
    done = []
    track = next(x for x in app.ctrl.library.list_tracks() if x.title == "Grid Test")
    app.ctrl.load_grid_wave(track, lambda w: done.append(w))
    end = time.time() + 30
    while not done and time.time() < end:
        s.pump(0.05)


def frame_dialog(s: vk.Studio, dlg: Any, width: float = 720) -> None:
    """Caméra sur une fenêtre (un peu de marge autour)."""
    s.pump(0.05)
    s.frame()
    r = s.rect_of(dlg)
    width = max(width, (r.height() + 140) / s.aspect, r.width() + 80)
    s.zoom(r.center().x() - width / 2, r.center().y() - width * s.aspect / 2, width)


def press_enter(widget: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.keyClick(widget, Qt.Key_Return)


def scenario(app: Any, s: vk.Studio) -> None:
    from djsync.ui.diagnostic_dialog import ALT, DiagnosticDialog
    from djsync.ui.dialogs import PlaylistPicker
    from djsync.ui.views.library_view import ALL, TODO

    ctrl = app.ctrl
    nav = app._nav
    home, search, lib = app.views["home"], app.views["search"], app.views["library"]

    s.card(["Your DJ app", "lives on your USB."], 2.6)

    # ================================================================ 1. Nomade
    s.cut()
    s.panel("1/5", "Nomad", "Plug your USB into any Windows PC. Nothing to install.")
    s.cut()
    s.plug(3.8, "DJ KEY", "DJSync.exe", ("Plug. Launch. Mix.", "any Windows PC · Windows 10 / 11"))
    app.show_view("home")
    s.pump(0.6)
    s.chapter("1/5 · Nomad")
    s.zoom(180, 60, 860, now=True)
    s.cut()
    cards = [home.cards_lay.itemAt(i).widget() for i in range(home.cards_lay.count())]
    s.caption("Your USB drive, detected automatically")
    s.spot(cards[0])
    s.hold(2.0)
    if len(cards) > 1:
        s.caption("…and this PC's Rekordbox library")
        s.spot(cards[1])
        s.hold(2.0)
    s.unspot()

    # ================================================================ 2. Télécharger
    s.cut()
    s.panel("2/5", "Download", "Search YouTube Music, or paste a Spotify link.")
    s.chapter("2/5 · Download")
    s.full(now=True)
    s.cut()
    s.caption("Open Search")
    s.click(nav["search"], after=0.4)
    s.zoom(170, 0, 900)
    s.caption("Type an artist or a title")
    s.click(search.entry, after=0.2)
    s.type(search.entry, "nova lane")
    press_enter(search.entry)
    s.wait_until(lambda: len(search.table.displayed_iids()) >= 5)
    s.caption("Songs and videos, from YouTube Music")
    s.hold(1.6)
    s.cut()
    s.panel("2/5", "Into your playlists", "Create a playlist on the fly, or pick existing ones.")
    s.cut()
    s.caption("Click the download arrow")
    s.spot(search.table.viewport(), row_rect(search.table, "Afterglow"))
    s.hold(0.8)
    s.click(search.table.viewport(), row_rect(search.table, "Afterglow", "dl"), after=0.6)
    picker = s.dialog(PlaylistPicker)
    s.unspot()
    frame_dialog(s, picker)
    s.caption("New playlist: type a name, then Create")
    s.click(picker._new, after=0.1)
    s.type(picker._new, "Saturday night")
    s.click(s.button(picker, "Create"), after=0.6)
    house = next(p.playlist_id for p in ctrl.playlists if p.name == "House")
    s.caption("A track can go into several playlists")
    s.click(picker._vars[house], after=0.6)
    s.caption("Download")
    s.expect(lambda: picker._vars[house].isChecked(), "House checked")
    s.click(picker._ok_btn, after=0.4)
    s.expect(lambda: s.dialog(PlaylistPicker) is None, "download picker closed")
    s.expect(lambda: any(p.name == "Saturday night" for p in ctrl.playlists), "playlist created")
    pid = next(p.playlist_id for p in ctrl.playlists if p.name == "Saturday night")
    s.caption("Downloading, tagged and filed on the drive")
    s.click(nav["downloads"], after=0.2)
    s.zoom(170, 0, 900)
    s.wait_until(lambda: bool(ctrl.jobs) and all(j.is_finished for j in ctrl.jobs), timeout=10)
    s.hold(1.4)
    s.caption("Your new playlist, in the library")
    s.click(nav["library"], after=0.5)
    s.zoom(0, 0, 900)
    s.click(lib.nav.viewport(), nav_rect(lib, f"p{pid}"), after=1.6)
    s.caption("Add any track to a playlist")
    s.click(lib.nav.viewport(), nav_rect(lib, ALL), after=0.6)
    s.click(lib.table.viewport(), row_rect(lib.table, "Golden Hour"), after=0.3)
    s.click(lib.add_btn, after=0.6)
    s.expect(lambda: s.dialog(PlaylistPicker) is not None, "add-to picker open")
    picker = s.dialog(PlaylistPicker)
    frame_dialog(s, picker)
    s.expect(lambda: pid in picker._vars, "playlists listed")
    s.click(picker._vars[pid], after=0.4)
    s.expect(lambda: picker._vars[pid].isChecked(), "Saturday night checked")
    s.click(picker._ok_btn, after=1.0)
    s.expect(lambda: s.dialog(PlaylistPicker) is None, "add-to picker closed")

    # ================================================================ 3. Analyser
    s.cut()
    s.panel("3/5", "Analyse", "BPM, key, beat grid and waveforms. Like Rekordbox.")
    s.chapter("3/5 · Analyse")
    s.zoom(0, 0, 900, now=True)
    s.cut()
    s.caption("Tracks not analysed yet")
    s.click(lib.nav.viewport(), nav_rect(lib, TODO), after=0.6)
    s.caption("Analyse them all, in the background")
    s.click(lib.analyse_btn, after=0.2)
    fake_analysis(s, ctrl, 3.0)
    s.click(lib.nav.viewport(), nav_rect(lib, ALL), after=0.4)
    s.expect(lambda: any(r.data.title == "Grid Test" for r in lib.table.all_rows()), "all tracks shown")
    s.caption("Right-click a track ▸ Edit beat grid")
    rr = row_rect(lib.table, "Grid Test")
    s.click(lib.table.viewport(), rr, after=0.1)
    s.click(lib.table.viewport(), rr, action=lambda: lib.table._context(rr.center()), after=0.3)
    s.choose("Edit beat grid", after=0.2)
    s.wait_until(lambda: app.grid_editor is not None and app.grid_editor.isVisible()
                 and getattr(app.grid_editor, "_wave_state", "ready") != "loading", timeout=8)
    ge = app.grid_editor
    s.expect(lambda: ge.track.title == "Grid Test", "grid editor opened on Grid Test")
    s.zoom(120, 0, 1000)
    s.caption("Rekordbox-style waveform and beat grid")
    s.hold(1.6)
    s.caption("Nudge the grid, set the first beat of the bar")
    s.click(s.button(ge, "+10"), after=0.5)
    s.click(s.button(ge, "Bar starts here"), after=0.6)
    s.caption("Save: written for Rekordbox and the decks")
    s.click(ge.save_btn, after=1.2)
    if app.grid_editor is not None and app.grid_editor.isVisible():
        app.grid_editor.close()
    s.pump(0.3)

    # ================================================================ 4. Organiser
    s.cut()
    s.panel("4/5", "Organise", "Camelot keys, harmonic mixing, clean-up.")
    s.chapter("4/5 · Organise")
    app.show_view("library")
    lib.nav.setCurrentItem(lib._items[ALL])
    s.pump(0.6)
    s.zoom(180, 0, 880, now=True)
    s.cut()
    head, hr = header_rect(lib.table, "key")
    s.caption("Every key in Camelot notation")
    s.spot(head, hr, pad=4)
    s.hold(1.6)
    s.unspot()
    s.caption("Pick a track, then Harmonic")
    s.click(lib.table.viewport(), row_rect(lib.table, "Midnight Drive"), after=0.3)
    s.click(lib.harm_btn, after=0.3)
    s.caption("Only the tracks that mix well together")
    s.hold(1.8)
    s.click(lib.harm_btn, after=0.3)
    s.caption("Diagnostic: duplicates, music videos, low bitrate")
    s.click(nav["home"], after=0.4)
    s.zoom(180, 60, 860)
    s.click(s.button(home.cards, "Diagnostic"), after=0.2)
    dlg = s.dialog(DiagnosticDialog)
    s.full()
    s.wait_until(lambda: not dlg._loading and dlg._choice.button(ALT) is not None, timeout=8)
    s.spot(dlg.list)
    s.hold(1.6)
    s.unspot()
    r, rd = s.rect_of(dlg.detail), s.rect_of(dlg)
    s.zoom(rd.right() - 790, r.y() - 70, 800)
    s.caption("Re-download a clean version…")
    s.click(dlg._choice.button(ALT), after=0.5)
    s.caption("…it replaces the old one in every playlist")
    s.spot(dlg.apply_btn)
    s.hold(1.8)
    s.unspot()
    s.click(s.button(dlg, "Close"), after=0.4)

    # ================================================================ 5. Rekordbox
    s.cut()
    s.panel("5/5", "100% Rekordbox", "Everything stays readable by Rekordbox and the decks.")
    s.chapter("")
    s.caption("")
    s.cut()
    s.checklist("Written the Rekordbox way", "on your USB and on your PC", [
        ("Rekordbox library", "exportLibrary.db (OneLibrary)"),
        ("Older players", "export.pdb kept in sync"),
        ("Analysis files", "beat grids, waveforms, cues (ANLZ)"),
        ("Your computer", "Rekordbox collection (master.db)")], 4.5)
    s.cut()
    s.card(["One file.", "Any PC. Any gig."], 4.0, cta=CTA)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--dry", action="store_true", help="rehearsal: run the scenario without rendering")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        print("FFmpeg is required.")
        return 1
    vk.install_menu_patch()
    prepare()
    dv.W, dv.H = APP
    app, usb, _frames, accent = dv.build_app("en", APP, zoom=120)
    s = vk.Studio(app, str(args.out), args.fps, accent, CANVAS, DISPLAY, APP, portrait=True, dry=args.dry)
    dv.settle(app, s, usb)
    warm_grid(app, s)
    try:
        scenario(app, s)
    finally:
        s.close()
        app.close()
    print(f"video: {args.out}  ({s.n / args.fps:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
