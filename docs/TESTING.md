# Testing DJSync — tester guide

*Version française : [TESTING.fr.md](TESTING.fr.md)*

Thanks for testing! The goal of this beta: make sure DJSync **never breaks a drive**, and that what
it writes looks right **in Rekordbox and on real players**. 30–60 minutes is plenty.

## Before you start
1. **Copy your whole USB drive** to your computer (or use a spare drive). DJSync backs up its
   database before every change, but a full copy is the real safety net.
2. Download DJSync for your computer from the
   [latest pre-release](https://github.com/Pikkol0/djsync/releases) and follow the
   [installation guide](INSTALL.md).
3. **Close Rekordbox** while DJSync writes to a drive or to the computer's library.

## 1. On the computer (everyone)
Tick what works, note what doesn't:

- [ ] DJSync starts from the drive and opens it by itself
- [ ] **Search** a track, **download** it into a **new playlist** and into an existing one
- [ ] **Import** a Spotify playlist link: are the right tracks found?
- [ ] **Library ▸ Not analysed ▸ Analyse all**: BPM and key look right?
- [ ] **Play** a track: the waveform scrolls in the player bar
- [ ] **Edit the beat grid** of a track (right-click ▸ Edit beat grid): shift, *Bar starts here*, Save
- [ ] Reorder a playlist, rename a track, add a track to another playlist
- [ ] **Home ▸ Diagnostic**: duplicates / low quality / music videos found? Try *Download and replace*
- [ ] **Eject** (bottom of the sidebar), unplug, plug back in: everything is still there
- [ ] Optional: open the drive in **Rekordbox** (Devices): playlists, BPM, keys, waveforms are there

## 2. In Rekordbox — checking DJSync's changes

Goal: make sure **everything DJSync changes** shows up identically in Rekordbox, in **both libraries
of the drive** (the one read by recent players and the older "Device Library").

### 2a. Prepare the drive in DJSync (write down each value in the report table)
Create a playlist **"DJSync test"** and make these changes, each on a different track:

| ID | Action in DJSync | Write down |
|---|---|---|
| P1 | Download 3 tracks into "DJSync test", then *Analyse all* | BPM and key shown |
| P2 | Track A: beat grid ▸ **Shift** +10 ms five times (+50 ms), Save | first beat position before / after |
| P3 | Track B: beat grid ▸ put the cursor on another kick ▸ **Bar starts here**, Save | new first beat of the bar |
| P4 | Track C: beat grid ▸ **BPM × 2** (or **Set BPM** with an exact value), Save | new BPM |
| P5 | Track D: **Edit title / artist** | new title |
| P6 | Reorder "DJSync test", add a track to a 2nd playlist, remove another one | final order |
| P7 | **Diagnostic**: replace a duplicate with a clean version | playlist and position of the replaced track |
| P8 | **Delete from drive** one test track | deleted track |
| P9 | Fix the grid of a track **analysed by Rekordbox** (if any) | BPM / first beat |

Then **Eject**, unplug.

### 2b. Check in Rekordbox
Plug the drive into a computer with Rekordbox, open it (*Devices*), and check **in both libraries of
the drive**:

| ID | Check | Expected |
|---|---|---|
| R1 | Tracks and playlists | Same tracks and playlists in **both** libraries; "DJSync test" is there |
| R2 | BPM | Each track has the BPM written down in DJSync (P1, P4) |
| R3 | Beat grid / first beat | Beat markers on the kicks; the bar's "1" at the same place as in DJSync (P2, P3) — zoom in on the start |
| R4 | Detailed waveform | Present, in colour, aligned with the grid |
| R5 | Waveform overview | The overview (top / in the list) is present **and up to date** after a grid fix |
| R6 | Key | Same key as in DJSync |
| R7 | Title, artist, artwork | The edited title (P5) is updated; artwork present |
| R8 | Playlists | Order (P6), added / removed track, replaced track at the same place (P7), deleted track gone (P8) |
| R9 | Memory cue | On the first downbeat (if enabled in Settings) |
| R10 | Original tracks | Tracks exported by Rekordbox (grids, cues, hot cues) are **unchanged**, except P9 |
| R11 | Round trip | Export a new track from Rekordbox to the drive, then reopen the drive in DJSync: everything is still there, on both sides |
| R12 | Computer library (optional) | If you test the computer's collection: same checks R2–R8 in Rekordbox's Collection (Rekordbox closed while DJSync writes) |

Then, if you have players: repeat R1–R9 on the players (part 3).

## 3. On the players (CDJ / XDJ) — the most valuable test
Not a controller: real players reading the USB drive. Prepare the drive with DJSync (part 2a), plug it
into the player, and check **tracks added or edited with DJSync** next to tracks exported by Rekordbox:

| Check | What "good" looks like |
|---|---|
| Library | The drive is recognised; playlists and folders are there, in the right order |
| Track info | Title, artist, artwork, BPM, key |
| Waveforms | Overview (whole track) and scrolling waveform, in colour on recent players |
| Beat grid | Beat markers on the kicks; **Sync** and **Quantize** behave like with Rekordbox tracks |
| Memory cue | A cue on the first downbeat (if enabled in Settings) |
| Fixed grid | A grid corrected in DJSync is correct on the player |
| Rekordbox tracks | Tracks exported by Rekordbox still work exactly as before |

Recent players (CDJ-3000, XDJ-AZ, OPUS-QUAD…) read the newer library format (`exportLibrary.db`);
older ones (CDJ-2000NXS2, XDJ-1000MK2, XDJ-RX2…) read `export.pdb`. DJSync writes both: **tell us
which model you used**. Photos of the player screen are very welcome.

## 4. Send your feedback
- **[Open a "Test in Rekordbox" report](https://github.com/Pikkol0/djsync/issues/new?template=rekordbox_test.yml)**
  for part 2 (results table already filled with the test IDs), a
  **["Test on players" report](https://github.com/Pikkol0/djsync/issues/new?template=deck_test.yml)**
  for the players, a **[bug report](https://github.com/Pikkol0/djsync/issues/new?template=bug.yml)**
  for anything else, or an **[idea](https://github.com/Pikkol0/djsync/issues/new?template=idea.yml)**.
- **Attach the log**: `djsync.log` in the hidden `.djsync/data` folder next to DJSync
  (Windows: type `E:\.djsync\data` in the File Explorer address bar, with your drive letter;
  macOS: Cmd+Shift+. shows hidden files; Linux: Ctrl+H).
- No GitHub account? Send the same information and the log to the person who invited you.
