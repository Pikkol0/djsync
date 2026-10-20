"""Fausse clé USB de démonstration (10 sons, tonalités, playlists, un dossier) : tests d'interface
et captures d'écran (tools/ui_screenshots.py). Aucun réseau, aucun FFmpeg."""
from __future__ import annotations

import struct
import wave
from pathlib import Path

DEMO = [  # titre, artiste, album, bpm, tonalité, playlists
    ("One More Time", "Daft Punk", "Discovery", 122.88, "F#m", ["House", "Classiques"]),
    ("One More Time (Clip Officiel)", "Daft Punk", None, 122.88, "F#m", ["House"]),
    ("Music Sounds Better With You", "Stardust", None, 124.21, "Bbm", ["House"]),
    ("Mon Survet", "Jok'Air", None, 74.99, "Bbm", ["Rap FR"]),
    ("Désaccordé", "Vald", "Agartha", 75.0, "Abm", ["Rap FR"]),
    ("Pump It Up", "Endor", None, 128.99, "C#m", ["Club"]),
    ("Kalash Hyperpop", "Kalash", None, 138.0, "E", ["Club", "Rap FR"]),
    ("Umbrella", "Rihanna", "Good Girl Gone Bad", 87.01, "Db", ["Classiques"]),
    ("Freestyle Funk", "Tsonpa", None, 130.06, "C", ["Club"]),
    ("Sans analyse", "Inconnu", None, 0, None, []),
]


def make_demo_usb(base: Path, analysed_song: bool = False) -> Path:
    """analysed_song : ajoute un son synthétique ANALYSÉ (FFmpeg requis) : forme d'onde, grille."""
    from sqlcipher3 import dbapi2 as sqlcipher

    from djsync.db._key import get_default_key
    from tests.test_usb_library import DDL

    usb = base / "DEMO_USB"
    (usb / "PIONEER" / "rekordbox").mkdir(parents=True)
    (usb / "Contents").mkdir()
    conn = sqlcipher.connect(str(usb / "PIONEER" / "rekordbox" / "exportLibrary.db"))
    conn.execute("PRAGMA key = '%s'" % get_default_key())
    conn.execute("PRAGMA journal_mode = WAL")
    for ddl in DDL:
        conn.execute(ddl)
    conn.execute("INSERT INTO property VALUES ('', '1000', 0, '2026-01-01', 0, 1)")
    conn.commit()
    conn.close()

    from djsync.db import RekordboxUsbLibrary, drive_from_letter

    with RekordboxUsbLibrary(drive_from_letter(str(usb)), analyze=False, artwork=False) as lib:
        folder = lib.create_folder("Soirées") if hasattr(lib, "create_folder") else None
        names = {}
        for title, artist, album, bpm, key, pls in DEMO:
            for name in pls:
                if name not in names:
                    names[name] = lib.create_playlist(name, folder.playlist_id if (folder and name == "Club") else 0).playlist_id
            d = lib.default_download_dir(artist, album)
            d.mkdir(parents=True, exist_ok=True)
            f = d / f"{artist} - {title}.wav"
            with wave.open(str(f), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
                w.writeframes(struct.pack("<h", 0) * 8000 * 3)
            t = lib.add_track(f, title, artist, album, None, [names[p] for p in pls])
            with lib._write() as conn:
                kid = None
                if key:
                    row = conn.execute("SELECT key_id FROM key WHERE name = ?", (key,)).fetchone()
                    kid = row[0] if row else conn.execute("INSERT INTO key (name) VALUES (?)", (key,)).lastrowid
                conn.execute("UPDATE content SET bpmx100 = ?, key_id = ?, length = ? WHERE content_id = ?",
                             (int(bpm * 100), kid, 180 + len(title) * 3, t.content_id))
        if analysed_song:
            from tests.audio_fixture import song, write_wav

            d = lib.default_download_dir("DJSync Demo")
            d.mkdir(parents=True, exist_ok=True)
            f = write_wav(d / "Grid Test.wav", song(124.0, 0.42, 40, ("A", "F", "C", "G"), (1, 0, 0, 0)))
            lib.analyze = True
            lib.add_track(f, "Grid Test", "DJSync Demo", None, None, [names["House"]])
    return usb


