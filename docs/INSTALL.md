# DJSync — quick installation guide (Windows)

*Version française : [INSTALL.fr.md](INSTALL.fr.md)*

Nothing to install on the computer: DJSync runs straight from the USB drive and brings everything it
needs (FFmpeg and the JavaScript runtime for YouTube are included).

## What you need
- **Windows 10 or 11** (64-bit) and an internet connection (search, downloads).
- **A USB drive exported by Rekordbox**: it must contain `PIONEER\rekordbox\exportLibrary.db`.
  If it doesn't, export one playlist to the drive from Rekordbox once.
  *Or* Rekordbox installed on the computer, to update its collection.
- About **250 MB** free on the drive for DJSync (plus room for your tracks).

## Install (1 minute)
1. **[Download DJSync.exe](https://github.com/Pikkol0/djsync/releases/latest/download/DJSync.exe)**: one
   file, nothing to unzip.
2. Copy it **to the root of your USB drive** (for example `E:\`).
3. **Double-click it.**
   - Windows says "Windows protected your PC"? Click **More info** ▸ **Run anyway** (unsigned app, once
     per computer).
   - The first launch takes a moment: DJSync prepares its files on the drive (once).
4. Done: DJSync recognises the drive it runs from and opens it automatically.

> DJSync keeps its files and your settings in a hidden folder next to itself. If you copy it elsewhere or
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
- DJSync **backs up the database before every change** (`DJSync_Backups` folder on the drive). Still keep
  a copy of your drive.
- Running from a drive, DJSync **asks first** before opening a computer's Rekordbox library.
- **Without internet**, DJSync still works: playlists, player, analysis, beat grid, duplicates, copying
  between libraries. Only search, downloads and online artwork need it.

## Updating DJSync
Replace `DJSync.exe` with the new one: at the next launch it updates itself and keeps your settings.

## Troubleshooting
| Problem | Fix |
|---|---|
| YouTube downloads fail | DJSync offers the engine update itself; otherwise *Settings* ▸ **Download engine** ▸ *Check for an update*. |
| "The database is locked: close Rekordbox…" | Quit Rekordbox (check it is not still running in the taskbar). |
| The drive is not detected | *Settings* ▸ *Rekordbox USB drive* ▸ **Drive letter** (e.g. `E`) ▸ *Save*. |
| See the hidden `.djsync` folder | Type `E:\.djsync` in File Explorer's address bar (the folder is protected like a system file). |
| The antivirus blocks `DJSync.exe` | Allow it: unsigned app (its SHA-256 is published with the release). |
| Anything else | Attach the log `.djsync\data\djsync.log` to your report (type `E:\.djsync\data` in File Explorer's address bar, with your drive's letter). |
