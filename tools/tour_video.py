"""OUTIL DE DÉVELOPPEMENT : visite détaillée en paysage (1920 x 1080, ~2 min 30) de chaque menu de DJSync,
pour YouTube.

    python tools/tour_video.py tour.mp4 [--fps 30] [--dry]

Même studio que la vidéo portrait (tools/video_kit.py) : vraie interface hors écran, artistes fictifs,
aucun réseau ; le pointeur clique les vrais boutons et ouvre les vrais menus. Huit parties, chacune
annoncée par un panneau de texte ; les horodatages des chapitres sont affichés à la fin (description
YouTube).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_video as dv  # noqa: E402
import video_kit as vk  # noqa: E402
from teaser_video import (  # noqa: E402
    CTA, fake_analysis, frame_dialog, header_rect, nav_rect, prepare, press_enter, row_rect, warm_grid,
)

CANVAS = (1920, 1080)
APP = (1600, 900)                    # fenêtre de l'appli (interface à 120 %)
DISPLAY = (160, 76, 1600, 900)        # bandes en haut (partie) et en bas (légende)
CHAPTERS: List[Tuple[float, str]] = []


def iid_rect(table: Any, iid: str, key: str = "") -> Any:
    from PySide6.QtCore import QRect

    i = table._index_of(iid)
    col = table.column_index(key or "title") if (key or "title") in [c.key for c in table.columns] else 1
    table.scrollTo(table._model.index(i, col))
    r = table.visualRect(table._model.index(i, col))
    return r if key else QRect(0, r.y(), table.viewport().width(), r.height())


def part(s: vk.Studio, num: str, title: str, sub: str) -> None:
    CHAPTERS.append((s.t, title))
    s.cut()
    s.panel(num, title, sub, 3.0)
    s.chapter(f"{num} · {title}")
    s.caption("")


def scenario(app: Any, s: vk.Studio) -> None:
    from djsync.ui.diagnostic_dialog import ALT, DiagnosticDialog
    from djsync.ui.dialogs import ConfirmDialog, FiltersPopup, MetadataDialog, PlaylistPicker
    from djsync.ui.views.library_view import ALL, TODO

    ctrl = app.ctrl
    nav = app._nav
    home, search, lib = app.views["home"], app.views["search"], app.views["library"]
    imp, sv = app.views["import"], app.views["settings"]

    CHAPTERS.append((0.0, "Intro"))
    s.card(["DJSync", "Your music, your Rekordbox USB, any computer."], 4.0)

    # ================================================================ 1. Un seul fichier
    part(s, "1/8", "On your USB, any computer", "Windows, Mac or Linux. Nothing to install.")
    s.cut()
    s.choose_os(4.0, ("Download the version for your computer", "then copy it to your USB drive"), [("Windows", "DJSync.exe"), ("macOS", "DJSync.app"), ("Linux", "DJSync folder")])
    s.cut()
    s.plug(5.0, "DJ KEY", "DJSync", ("Plug the drive in, open DJSync", "same drive, any computer"))
    app.show_view("home")
    s.pump(0.6)
    s.zoom(220, 60, 1250, now=True)
    s.cut()
    cards = [home.cards_lay.itemAt(i).widget() for i in range(home.cards_lay.count())]
    s.caption("Your USB drive: tracks, playlists, free space")
    s.spot(cards[0])
    s.hold(2.4)
    s.caption("Tracks not analysed yet, older players supported (export.pdb)")
    s.hold(2.2)
    if len(cards) > 1:
        s.caption("This PC's Rekordbox collection, one click away")
        s.spot(cards[1])
        s.hold(2.4)
    s.unspot()
    s.caption("Search, or paste a link, from Home")
    s.spot(home.omnibar)
    s.hold(2.0)
    s.unspot()

    # ================================================================ 2. Recherche
    part(s, "2/8", "Search", "Find any track on YouTube Music.")
    s.full(now=True)
    s.cut()
    s.caption("Open Search")
    s.click(nav["search"], after=0.4)
    s.zoom(230, 0, 1370)
    s.click(search.entry, after=0.2)
    s.type(search.entry, "nova lane")
    press_enter(search.entry)
    s.wait_until(lambda: len(search.table.displayed_iids()) >= 5)
    s.hold(0.8)
    head, hr = header_rect(search.table, "type")
    s.caption("Songs (official audio) or videos")
    s.spot(head, hr, pad=4)
    s.hold(2.2)
    s.caption("Already in your library? You know before downloading")
    s.spot(search.table.viewport(), row_rect(search.table, "Midnight Drive"))
    s.hold(2.4)
    s.unspot()
    s.caption("Filters: songs only, words to exclude (remix, live…)")
    s.click(search.filter_btn, after=0.8)
    fp = s.dialog(FiltersPopup)
    if fp is not None:
        frame_dialog(s, fp, 900)
        s.hold(2.2)
        s.click(s.button(fp, "Cancel"), after=0.4)
        s.zoom(230, 0, 1370)
    s.caption("Preview before downloading")
    s.click(search.table.viewport(), row_rect(search.table, "Afterglow"), after=0.3)
    s.click(search.preview_btn, after=0.4)
    s.zoom(0, 900 - 1370 * 9 / 16, 1370)
    s.spot(app.player_bar)
    s.hold(2.4)
    s.unspot()
    ctrl.player.stop()

    # ================================================================ 3. Télécharger dans les playlists
    part(s, "3/8", "Download into playlists", "Create a playlist on the fly, or pick existing ones.")
    app.show_view("search")
    s.zoom(230, 0, 1370, now=True)
    s.cut()
    s.caption("Select two tracks, then Download")
    s.click(search.table.viewport(), row_rect(search.table, "Afterglow"), after=0.2)
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    rr = row_rect(search.table, "Golden Coast")
    s.click(search.table.viewport(), rr, action=lambda: QTest.mouseClick(
        search.table.viewport(), Qt.LeftButton, Qt.ControlModifier, rr.center()), after=0.4)
    s.click(search.dl_btn, after=0.6)
    picker = s.dialog(PlaylistPicker)
    frame_dialog(s, picker, 1000)
    s.caption("New playlist: type a name, then Create")
    s.click(picker._new, after=0.1)
    s.type(picker._new, "Saturday night")
    s.click(s.button(picker, "Create"), after=0.7)
    house = next(p.playlist_id for p in ctrl.playlists if p.name == "House")
    s.caption("A track can go into several playlists")
    s.click(picker._vars[house], after=0.6)
    s.expect(lambda: picker._vars[house].isChecked(), "House checked")
    s.caption("Download")
    s.click(picker._ok_btn, after=0.4)
    s.expect(lambda: s.dialog(PlaylistPicker) is None, "picker closed")
    s.expect(lambda: any(p.name == "Saturday night" for p in ctrl.playlists), "playlist created")
    pid = next(p.playlist_id for p in ctrl.playlists if p.name == "Saturday night")
    s.caption("Downloads: progress, playlists, then tagged and filed on the drive")
    s.click(nav["downloads"], after=0.2)
    s.zoom(230, 0, 1370)
    s.wait_until(lambda: bool(ctrl.jobs) and all(j.is_finished for j in ctrl.jobs), timeout=12)
    dv_ = app.views["downloads"]
    tbl = getattr(dv_, "table", None)
    if tbl is not None and "dest" in [c.key for c in tbl.columns]:
        head, hr = header_rect(tbl, "dest")
        s.spot(head, hr, pad=4)
    s.hold(2.4)
    s.unspot()
    s.caption("Your new playlist, in the library")
    s.click(nav["library"], after=0.5)
    s.zoom(0, 0, 1370)
    s.click(lib.nav.viewport(), nav_rect(lib, f"p{pid}"), after=2.0)
    s.caption("Add any track to a playlist: Add to…")
    s.click(lib.nav.viewport(), nav_rect(lib, ALL), after=0.6)
    s.click(lib.table.viewport(), row_rect(lib.table, "Summer Rain"), after=0.3)
    s.click(lib.add_btn, after=0.6)
    s.expect(lambda: s.dialog(PlaylistPicker) is not None, "add-to picker")
    picker = s.dialog(PlaylistPicker)
    frame_dialog(s, picker, 1000)
    s.expect(lambda: pid in picker._vars, "playlists listed")
    s.click(picker._vars[pid], after=0.4)
    s.click(picker._ok_btn, after=1.0)
    s.expect(lambda: s.dialog(PlaylistPicker) is None, "add-to picker closed")

    # ================================================================ 4. Import
    part(s, "4/8", "Import a playlist", "Paste a Spotify link: the right tracks are found for you.")
    s.full(now=True)
    s.cut()
    s.caption("Import URL")
    s.click(nav["import"], after=0.4)
    s.zoom(230, 0, 1370)
    s.click(imp.url, after=0.2)
    s.type(imp.url, "https://open.spotify.com/playlist/demo", cps=28)
    s.caption("Read the link")
    s.click(imp.go, after=0.3)
    s.caption("Each track is matched on YouTube Music, with a score")
    s.wait_until(lambda: imp._handle is not None and getattr(imp._handle, "done", 0) >= len(imp.matches), timeout=10)
    s.hold(0.6)
    s.spot(imp.sp_table.viewport(), iid_rect(imp.sp_table, "0"))
    s.caption("Found: the official audio, same duration")
    s.hold(2.2)
    s.spot(imp.sp_table.viewport(), iid_rect(imp.sp_table, "6"))
    s.caption("Not sure? Marked to check: listen, or pick another match")
    s.hold(2.6)
    s.unspot()
    s.caption("Download the selection into your playlists")
    s.click(imp.dl_btn, after=0.6)
    picker = s.dialog(PlaylistPicker)
    if picker is not None:
        frame_dialog(s, picker, 1000)
        s.hold(1.2)
        s.click(s.button(picker, "Cancel"), after=0.4)

    # ================================================================ 5. Analyse
    part(s, "5/8", "Analyse like Rekordbox", "BPM, key, beat grid, waveforms. Read by the decks.")
    app.show_view("library")
    s.zoom(0, 0, 1370, now=True)
    s.cut()
    s.caption("Tracks not analysed yet")
    s.click(lib.nav.viewport(), nav_rect(lib, TODO), after=0.6)
    s.caption("Analyse all: in the background, the library stays usable")
    s.click(lib.analyse_btn, after=0.2)
    s.zoom(0, 900 - 1370 * 9 / 16, 1370)
    fake_analysis(s, ctrl, 4.0)
    s.zoom(0, 0, 1370)
    s.click(lib.nav.viewport(), nav_rect(lib, ALL), after=0.4)
    s.caption("Double-click to play: the waveform scrolls in the player")
    rr = row_rect(lib.table, "Grid Test")
    s.click(lib.table.viewport(), rr, double=True, after=0.6)
    s.zoom(0, 900 - 1370 * 9 / 16, 1370)
    s.spot(app.player_bar)
    s.hold(2.8)
    s.unspot()
    ctrl.player.stop()
    s.zoom(0, 0, 1370)
    s.caption("Tools menu ▸ Edit beat grid")
    s.click(lib.table.viewport(), row_rect(lib.table, "Grid Test"), after=0.2)
    s.click(lib.tools_btn, after=0.4)
    s.choose("Edit beat grid", after=0.2)
    s.wait_until(lambda: app.grid_editor is not None and app.grid_editor.isVisible()
                 and getattr(app.grid_editor, "_wave_state", "ready") != "loading", timeout=8)
    ge = app.grid_editor
    s.expect(lambda: ge.track.title == "Grid Test", "grid editor on Grid Test")
    s.full()
    s.caption("Rekordbox-style 3-band waveform, beats and bars")
    s.hold(2.4)
    s.caption("Shift the whole grid, to the millisecond")
    s.click(s.button(ge, "+10"), after=0.6)
    s.click(s.button(ge, "−10"), after=0.6)
    s.caption("Bar starts here: the first beat of the bar")
    s.click(s.button(ge, "Bar starts here"), after=0.8)
    s.caption("BPM × 2 / ÷ 2, or type the exact BPM")
    s.spot(s.button(ge, "BPM × 2"))
    s.hold(2.0)
    s.unspot()
    s.caption("Save: written to the analysis files read by the decks")
    s.click(ge.save_btn, after=1.4)
    if app.grid_editor is not None and app.grid_editor.isVisible():
        app.grid_editor.close()
    s.pump(0.3)

    # ================================================================ 6. Organiser
    part(s, "6/8", "Organise your library", "Playlists, order, titles, Camelot keys, clean-up.")
    app.show_view("library")
    lib.nav.setCurrentItem(lib._items[ALL])
    s.pump(0.6)
    s.zoom(0, 0, 1370, now=True)
    s.cut()
    head, hr = header_rect(lib.table, "key")
    s.caption("Keys in Camelot notation, with their colour")
    s.spot(head, hr, pad=4)
    s.hold(2.2)
    s.unspot()
    s.caption("Pick a track, then Harmonic: only compatible tracks remain")
    s.click(lib.table.viewport(), row_rect(lib.table, "Midnight Drive"), after=0.3)
    s.click(lib.harm_btn, after=2.4)
    s.click(lib.harm_btn, after=0.3)
    house = next(p.playlist_id for p in ctrl.playlists if p.name == "House")
    s.caption("Change the order of a playlist, then Save order")
    s.click(lib.nav.viewport(), nav_rect(lib, f"p{house}"), after=0.6)
    s.click(lib.table.viewport(), row_rect(lib.table, "Golden Hour"), after=0.3)
    s.click(lib.up_btn, after=0.5)
    s.click(lib.up_btn, after=0.5)
    s.click(lib.save_btn, after=1.0)
    s.caption("Right-click ▸ Edit title / artist")
    rr = row_rect(lib.table, "Midnight Drive (Clip Officiel)")
    s.click(lib.table.viewport(), rr, after=0.2)
    s.click(lib.table.viewport(), rr, action=lambda: lib.table._context(rr.center()), after=0.3)
    s.choose("Edit title / artist", after=0.4)
    md = s.dialog(MetadataDialog)
    if md is not None:
        frame_dialog(s, md, 1000)
        md._title.selectAll()
        s.type(md._title, "Midnight Drive (Video Edit)", cps=16)
        s.click(s.button(md, "Save"), after=1.0)
    s.zoom(0, 0, 1370)
    s.caption("Right-click a playlist ▸ Copy to this computer's Rekordbox")
    nr = nav_rect(lib, f"p{pid}")
    s.click(lib.nav.viewport(), nr, action=lambda: lib._nav_context(nr.center()), after=0.3)
    s.choose("Copy to", after=0.4)
    cd = s.dialog(ConfirmDialog)
    if cd is not None:
        frame_dialog(s, cd, 1000)
        s.caption("Analyses are reused, not recomputed")
        s.hold(1.4)
        s.click(s.button(cd, "Copy"), after=2.0)
    s.caption("Diagnostic: duplicates, music videos, low bitrate")
    s.click(nav["home"], after=0.4)
    s.zoom(220, 60, 1250)
    s.click(s.button(home.cards, "Diagnostic"), after=0.2)
    dlg = s.dialog(DiagnosticDialog)
    s.full()
    s.wait_until(lambda: not dlg._loading and dlg._choice.button(ALT) is not None, timeout=8)
    frame_dialog(s, dlg, 1300)
    s.spot(dlg.list)
    s.caption("Sorted by problem: duplicates, bad source, low quality")
    s.hold(2.6)
    s.unspot()
    s.caption("Keep one version… or re-download a clean one")
    s.click(dlg._choice.button(ALT), after=0.6)
    s.spot(dlg.apply_btn)
    s.caption("It replaces the old ones in every playlist, at the same position")
    s.hold(2.4)
    s.unspot()
    s.click(dlg.list.viewport(), dlg.list.visualItemRect(dlg.list.item(dlg._row_of(1))), after=0.4)
    s.caption("A music video in your library? Same thing")
    s.hold(2.4)
    s.click(s.button(dlg, "Close"), after=0.4)

    # ================================================================ 7. Rekordbox
    part(s, "7/8", "100% Rekordbox", "Everything stays readable by Rekordbox and the decks.")
    s.cut()
    s.checklist("Written the Rekordbox way", "on your USB and on your PC", [
        ("Rekordbox library", "exportLibrary.db (OneLibrary)"),
        ("Older players", "export.pdb kept in sync"),
        ("Analysis files", "beat grids, waveforms, cues (ANLZ)"),
        ("Your computer", "Rekordbox collection (master.db)")], 5.0)
    s.cut()
    s.checklist("Safe by design", "your library is never at risk", [
        ("Backup first", "the database is saved before every change"),
        ("Rekordbox open?", "DJSync warns you and waits"),
        ("Safe eject", "library closed cleanly before unplugging"),
        ("Works offline", "only search and downloads need internet")], 5.0)

    # ================================================================ 8. Partout
    part(s, "8/8", "Settings & eject", "Your format, always up to date, unplug safely.")
    s.zoom(0, 0, 800, now=True)
    s.cut()
    s.caption("Settings")
    s.click(nav["settings"], after=0.5)
    from PySide6.QtWidgets import QScrollArea

    area = next(iter(sv.findChildren(QScrollArea)), None)
    if area is not None:
        area.ensureWidgetVisible(sv.format_menu, 0, 300)
    s.pump(0.3)
    s.focus(sv.format_menu, 1100, dy=0.4)
    s.caption("M4A (original quality) or MP3 320, same volume for every track")
    s.spot(sv.format_menu)
    s.hold(2.2)
    s.spot(sv.normalize_var)
    s.hold(1.6)
    s.unspot()
    s.caption("YouTube changed? Update the download engine in one click")
    if area is not None:
        area.ensureWidgetVisible(sv.engine_check_btn, 0, 200)
    s.pump(0.2)
    s.click(sv.engine_check_btn, after=2.0)
    s.caption("Eject: the library is closed, you can unplug the drive")
    s.focus(app.eject_btn, 800, dy=0.75)
    s.click(app.eject_btn, after=2.6)

    CHAPTERS.append((s.t, "Download"))
    s.cut()
    s.card(["On your USB.", "Any computer. Any gig."], 5.0, cta=CTA)


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
    s = vk.Studio(app, str(args.out), args.fps, accent, CANVAS, DISPLAY, APP, portrait=False, dry=args.dry)
    dv.settle(app, s, usb)
    warm_grid(app, s)
    try:
        scenario(app, s)
    finally:
        s.close()
        app.close()
    print(f"video: {args.out}  ({s.n / args.fps:.1f} s)")
    print("YouTube chapters:")
    for t, name in CHAPTERS:
        print(f"{int(t // 60)}:{int(t % 60):02d} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
