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

## Install (2 minutes)
1. Download **`DJSync-<version>-windows.zip`** from the
   [latest release](https://github.com/Pikkol0/djsync/releases/latest).
2. Right-click the zip ▸ **Extract All…** ▸ choose **the root of the drive** (for example `E:\`).
3. Open the drive and double-click **`DJSync.exe`**.
   - Windows says "Windows protected your PC"? Click **More info** ▸ **Run anyway** (unsigned app, once
     per computer).
4. Done: DJSync recognises the drive it runs from and opens it automatically.

> Next to `DJSync.exe` there is a `.djsync` folder, hidden at first launch: it holds the program and your
> settings. **Never separate `DJSync.exe` from that folder** (always copy both).

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

## Updating DJSync
Download the new zip and extract it **to the same place**, replacing the files: your settings are kept.

## Troubleshooting
| Problem | Fix |
|---|---|
| YouTube downloads fail | DJSync offers the engine update itself; otherwise *Settings* ▸ **Download engine** ▸ *Check for an update*. |
| "The database is locked: close Rekordbox…" | Quit Rekordbox (check it is not still running in the taskbar). |
| The drive is not detected | *Settings* ▸ *Rekordbox USB drive* ▸ **Drive letter** (e.g. `E`) ▸ *Save*. |
| See the hidden `.djsync` folder | Type `E:\.djsync` in File Explorer's address bar (the folder is protected like a system file). |
| The antivirus blocks `DJSync.exe` | Allow it: unsigned app (the zip's SHA-256 is published with the release). |
| Anything else | Attach the log `.djsync\data\djsync.log` to your report (type `E:\.djsync\data` in File Explorer's address bar, with your drive's letter). |
