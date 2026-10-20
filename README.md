<p align="center">
  <img src="docs/logos/djsync-violet_light.png" width="96" alt="DJSync logo">
</p>

<h1 align="center">DJSync</h1>

<p align="center">
  Find music, put it on your Rekordbox USB drive, ready for Pioneer CDJs — without going through Rekordbox.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.3.0-B79CFF">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-555">
</p>

---

## What DJSync does

DJSync is a **portable** desktop app (it can run straight from the USB drive) that works on a drive
exported by Rekordbox:

- **Search and download** from YouTube Music (results as you type, preview before downloading), or
  **import a link** from Spotify, YouTube or SoundCloud (single track or playlist).
- **Write directly into the drive's library**: `exportLibrary.db` (OneLibrary, recent players) **and**
  `export.pdb` (older players), with date added and artwork.
- **Analyse tracks** without Rekordbox: BPM, beat grid, key (shown in Camelot notation), Pioneer waveforms
  (ANLZ files), in the background (Library ▸ *Not analysed*). Tracks already analysed by Rekordbox are never
  changed.
- **Manage the library** like a mini Rekordbox: playlists and folders, drag and drop, track order,
  harmonic filter, built-in player with waveform.
- **Fix** a shifted beat grid (also straight from the player), **find and merge duplicates**, edit title / artist.
- **Back up before every change**: a copy of the database goes to `DJSync_Backups/` on the drive.

English interface (French available in Settings; other languages can be added — see below), 20 colour
themes, zoom from 80 to 200 %. Plain, fast Qt interface (PySide6): no animations, nothing redrawn for nothing.

> ⚠️ Personal project, not affiliated with Pioneer DJ / AlphaTheta. The drive formats are reverse-engineered:
> **keep a copy of your drive** and close Rekordbox while DJSync writes to it.

## Screenshots

| Library | Beat grid editor |
|---|---|
| ![Library](docs/captures/library.png) | ![Grid](docs/captures/grid.png) |

## Installation

### Requirements
- **Python 3.10+** (developed and tested with 3.12)
- **FFmpeg** (`ffmpeg` + `ffprobe`): download, m4a playback, analysis. In the `PATH`, or the folder set in
  *Settings ▸ FFmpeg*.
- **Deno** (or Node): needed by yt-dlp for some YouTube downloads — <https://deno.com>

### Run from source
```bash
git clone https://github.com/Pikkol0/djsync.git
cd djsync
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```
On Linux, Tkinter comes from the system (`sudo apt install python3-tk`).

### Portable Windows executable
```bash
pip install pyinstaller
pyinstaller packaging/DJSync.spec
```
Builds `dist/DJSync.exe` (with a splash screen shown while it starts). Copy it to the drive with `ffmpeg.exe`, `ffprobe.exe` and `deno.exe` next to it:
DJSync then recognises the drive it runs from and connects to it automatically.
*(Build not yet validated on a Windows machine.)*

## Quick use

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Search a track or paste a link, from anywhere |
| `Ctrl+1` … `Ctrl+6` | Home, Search, Library, Downloads, Import URL, Settings |
| `Ctrl+F` | Search / filter field of the page |
| `Space` | Play / pause |
| `Ctrl+→` / `Ctrl+←` | Next / previous track |
| `F1` | Help |

The in-app **Shortcuts & help** button has a short guide.

## Command-line tools (read-only)
```bash
python -m djsync.db.diagnose E:            # check a drive's database
python -m djsync.db.pdb.check E:           # check export.pdb
python -m djsync.analysis track.m4a        # analyse a file (BPM, key, grid) without writing anything
python -m djsync.analysis --compare E:     # compare DJSync's analysis with Rekordbox's on a drive
```

## Languages
Everything (interface, error messages, logs, command-line output) is written in **English**. Other languages
only translate the interface: `djsync/i18n/fr.py` is a dictionary `key -> text`; **a missing key simply falls
back to English**, so a translation can be partial. To add a language, copy `fr.py`, translate what you want
and register it in `djsync/i18n/__init__.py`.

## Code layout

```
app.py                  entry point (python app.py)
djsync/
  core/                 YouTube Music search, download (yt-dlp), Spotify import, duplicates, Camelot
  db/                   USB drive: exportLibrary.db (SQLCipher) in library/, export.pdb in pdb/, artwork
  analysis/             BPM, grid, key, waveforms, ANLZ files (numpy + FFmpeg only)
  audio/                built-in player, artwork
  ui/                   Qt interface (PySide6): app, controller (ctrl/), views (views/), table, dialogs
  i18n/                 English (en.py, reference) and French (fr.py) texts
tests/                  pytest tests (fake drive, synthetic tracks)
tools/                  development tools: screenshots, logo export
packaging/              PyInstaller spec + icon
docs/                   technical notes (in French for now)
```

## Tests

```bash
pip install pytest
python -m pytest -q                 # everything, UI included (Qt "offscreen": no display needed)
```
Tests use neither the network nor a real drive: generated Rekordbox database, synthetic tracks.
A test also checks that no French text is hard-coded outside the translation file.
Screenshot tool (no display needed): `python tools/ui_screenshots.py shots --sizes 860x560,1280x800 --lang en --dialogs`.

## Technical notes (French)
- [Audio analysis, artwork, date added](docs/analyse_audio.md) — calibration on a real drive
- [export.pdb (older players)](docs/export_pdb.md)
- [V0.2.0 interface, beat grid, duplicates](docs/interface_v020.md)

## Version history

| Version | Changes |
|---|---|
| **0.3.0** | New Qt interface (PySide6) replacing customtkinter: native widgets, much smoother scrolling, resizing and table updates. Zoom and theme colour apply instantly without rebuilding the window; the zoom no longer follows the window size. Plainer look: flat dark theme, square corners, no shadows or animations, no per-row artwork or placeholder rows. Same features as 0.2.4; UI tests run without a display. |
| 0.2.4 | Background analysis: Library ▸ *Not analysed* section with "Analyse all" / "Stop", progress card in the sidebar, the rest of the app stays usable. Player: beat grid button and track options (title/artist, analyse again, compatible keys, show in library). export.pdb: track updates no longer eat the free space (in-place rewrite, deleted rows reclaimed), clearer "export.pdb is full" message. Fixes: dialogs sized for the zoom and kept on screen (beat grid editor could look frozen), key pill now shown right after analysis. |
| 0.2.3 | Windows start-up fix: the main window stayed invisible after the splash screen, and the splash shrank to a corner (DPI awareness set too late). |
| 0.2.2 | Window always opens inside the screen (saved size/position clamped, maximised state remembered); lightweight splash screen at launch (also a native splash for the Windows executable). |
| 0.2.1 | Fully English software: error messages, logs and command-line tools included; French kept as an optional interface translation (partial translations fall back to English). English README, obsolete console demos removed. |
| 0.2.0 | New interface: Home + omnibar, search as you type, "All tracks", Camelot pills, drag and drop onto playlists, harmonic filter, player previous/next + waveform, zoom and small windows, English by default, logo per colour. On-demand analysis, beat grid editor, duplicates tool, help and shortcuts. Code split (library, controller). |
| 0.1.6 | Local BPM / key / ANLZ waveform analysis, date added and artwork in both databases, calibration on a real drive (MP3 encoder delay). |
| 0.1.x | YouTube Music search and download, Spotify/YouTube/SoundCloud import, writing to exportLibrary.db then export.pdb, library and playlists, player, portable mode. |

## Roadmap
- [ ] Measure and fix the beat grid offset of m4a (AAC) files
- [ ] Validate the executable and the display on Windows (125–150 % DPI)
- [ ] Test on real players (recent CDJ and an older model reading export.pdb), then enable adding
      export.pdb pages by default

## Credits
- [pyrekordbox](https://github.com/dylanljones/pyrekordbox) and the community documentation
  [Deep Symmetry / crate-digger](https://djl-analysis.deepsymmetry.org/) for the Rekordbox formats.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp), [ytmusicapi](https://github.com/sigma67/ytmusicapi),
  [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/), [SQLCipher](https://www.zetetic.net/sqlcipher/).

Only download content you have the right to use.
