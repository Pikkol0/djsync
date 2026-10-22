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

## 2. On the players (CDJ / XDJ) — the most valuable test
Not a controller: real players reading the USB drive. Prepare the drive with DJSync (step 1), plug it
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

## 3. Send your feedback
- **[Open a "Test on players" report](https://github.com/Pikkol0/djsync/issues/new?template=deck_test.yml)**
  for the players, a **[bug report](https://github.com/Pikkol0/djsync/issues/new?template=bug.yml)**
  for anything else, or an **[idea](https://github.com/Pikkol0/djsync/issues/new?template=idea.yml)**.
- **Attach the log**: `djsync.log` in the hidden `.djsync/data` folder next to DJSync
  (Windows: type `E:\.djsync\data` in the File Explorer address bar, with your drive letter;
  macOS: Cmd+Shift+. shows hidden files; Linux: Ctrl+H).
- No GitHub account? Send the same information and the log to the person who invited you.
