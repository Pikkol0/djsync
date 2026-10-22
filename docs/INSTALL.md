# DJSync — quick installation guide (Windows, macOS, Linux)

*Version française : [INSTALL.fr.md](INSTALL.fr.md)*

Nothing to install on the computer: DJSync runs straight from the USB drive and brings everything it
needs (FFmpeg and the JavaScript runtime for YouTube are included).

## What you need
- A computer: **Windows 10 or 11** (64-bit), **macOS 11 or later** on Apple silicon (M1, M2, M3…) or
  **Linux** (x86-64) — macOS and Linux are in *beta* — and an internet connection (search, downloads).
- **A USB drive exported by Rekordbox**: it must contain `PIONEER\rekordbox\exportLibrary.db`.
  If it doesn't, export one playlist to the drive from Rekordbox once.
  *Or* Rekordbox installed on the computer, to update its collection.
- About **300 MB** free on the drive for DJSync and its backups (plus room for your tracks).

## Install (1 minute)
Pick the file for your computer on the **[download page](https://github.com/Pikkol0/djsync/releases/latest)**.

### Windows
1. **[Download DJSync.exe](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync.exe)**: one
   file, nothing to unzip.
2. Copy it **to the root of your USB drive** (for example `E:\`).
3. **Double-click it.**
   - Windows says "Windows protected your PC"? Click **More info** ▸ **Run anyway** (unsigned app, once
     per computer).
   - The first launch takes a moment: DJSync prepares its files on the drive (once).

### macOS (beta)
1. **[Download DJSync-macOS.dmg](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync-macOS.dmg)**
   and open it.
2. **Drag DJSync onto your USB drive** (in the Finder sidebar, under *Locations*).
3. Open your drive and **double-click DJSync**.
   - **First time only**, macOS says it cannot check the app (it is not signed by Apple): open
     *System Settings* ▸ *Privacy & Security*, scroll down, click **Open Anyway**, confirm.
   - DJSync then sets itself up on the drive and restarts once by itself. Next times: just double-click.

### Linux (beta)
1. **[Download DJSync-Linux-x86_64.tar.gz](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync-Linux-x86_64.tar.gz)**
   and extract the **DJSync** folder **to your USB drive**.
2. Run `DJSync/DJSync` (double-click in most file managers, or from a terminal). If Qt complains about
   `xcb`, install `libxcb-cursor0` (Debian/Ubuntu) or `xcb-util-cursor` (Fedora, Arch).

Then: DJSync recognises the drive it runs from and opens it automatically.

> DJSync keeps its files and your settings in a hidden folder next to itself (`.djsync`). If you copy it elsewhere or
> delete that folder, it rebuilds it at the next launch (settings then start from scratch).

## First steps
- **Find a track**: `Ctrl+K` (or paste a Spotify / YouTube / SoundCloud link), then **Download** and pick
  the playlist.
- **Analyse** (BPM, key, beat grid, waveforms): *Library* ▸ **Not analysed** ▸ *Analyse all*.
- **Before unplugging the drive**: **Eject** button (bottom of the sidebar) — the library is closed safely.
- **Shortcuts & help**: button at the bottom of the sidebar, or `F1`.
- French interface: *Settings* ▸ *Appearance* ▸ *Language*.

## Good to know
- **Close Rekordbox** while DJSync changes a library (drive or computer).
- DJSync **backs up the drive's library** (`DJSync_Backups` folder): the original state (before DJSync)
  is kept forever, plus your manual backups, those from the start of the year, month and week, and the
  last 5. *Settings* ▸ *Drive backups* ▸ **Backups and restore**: go back to one in one click, or create
  one ("Before the gig"). Still keep a copy of your drive.
- **Quit DJSync before unplugging the drive** it runs from.
- Running from a drive, DJSync **asks first** before opening a computer's Rekordbox library.
- **Without internet**, DJSync still works: playlists, player, analysis, beat grid, duplicates, copying
  between libraries. Only search, downloads and online artwork need it.

## Updating DJSync
DJSync tells you when a new version is out (*Settings* ▸ *Download engine* to turn it off). Replace
DJSync (`DJSync.exe`, `DJSync.app` or the `DJSync` folder) with the new one: your settings are kept.

## Uninstalling DJSync
- **From the drive**: *Settings* ▸ *Drive backups* ▸ **Remove DJSync from this drive**. DJSync closes and
  deletes its program, settings and log. Your music and Rekordbox library stay. Options: put back the
  original library (before DJSync), delete the backups.
- **By hand**: delete `DJSync.exe` (or `DJSync.app`, or the `DJSync` folder on Linux), the hidden
  `.djsync` folder next to it and, if you no longer want them, `DJSync_Backups`. Run from the computer,
  settings are in `%APPDATA%\DJSync` (Windows) or `~/.config/djsync` (macOS, Linux).
- **Back to the drive as it was before DJSync, without uninstalling**: *Backups and restore* ▸
  "Original (before DJSync)" ▸ **Restore**.

## Troubleshooting
| Problem | Fix |
|---|---|
| YouTube downloads fail | DJSync offers the engine update itself; otherwise *Settings* ▸ **Download engine** ▸ *Check for an update*. |
| "The database is locked: close Rekordbox…" | Quit Rekordbox (check it is not still running in the taskbar). |
| The drive is not detected | *Settings* ▸ *Rekordbox USB drive* ▸ **Drive letter** (e.g. `E`; on macOS/Linux the drive's folder, e.g. `/Volumes/DJ KEY`) ▸ *Save*. |
| macOS: "cannot be opened" every time, or a message about a temporary copy | *System Settings* ▸ *Privacy & Security* ▸ **Open Anyway**. If it persists: in Terminal, `xattr -dr com.apple.quarantine ` then drag DJSync from the drive into the window, Enter. |
| See the hidden `.djsync` folder | Type `E:\.djsync` in File Explorer's address bar (the folder is protected like a system file). |
| The antivirus blocks `DJSync.exe` | Allow it: unsigned app (its SHA-256 is published with the release). |
| The players no longer read the drive, or a playlist is missing | *Backups and restore* ▸ restore the **Original** (or a backup from before the problem), then report it with the log. |
| Anything else | Attach the log `djsync.log` to your report: *Settings* ▸ *Drive backups* ▸ **Open the log folder**. |
