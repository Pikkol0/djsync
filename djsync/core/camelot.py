"""Clés harmoniques : conversion vers la notation Camelot (1A…12B) et voisinage harmonique.

Entrées acceptées (insensibles à la casse et aux espaces) :
  * notes musicales : "Am", "A minor", "Amin", "C#", "Bbm", "F♯ minor", "Cmaj", "E major"…
  * Camelot : "8A", "08b"
  * Open Key : "1d" (majeur), "1m" (mineur)

Rekordbox stocke les tonalités sous forme de noms musicaux ("Am", "F#m"…) dans la table `key` ;
`to_camelot` les traduit pour l'affichage. Module pur (aucune dépendance), facile à tester.
"""
from __future__ import annotations

import re
from typing import List, Optional

# hauteur de note (0 = Do) -> code Camelot
_MAJOR = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B", 6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_MINOR = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A", 6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}
_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_CAMELOT = re.compile(r"^(0?[1-9]|1[0-2])\s*([AB])$", re.I)
_OPENKEY = re.compile(r"^(0?[1-9]|1[0-2])\s*([MD])$", re.I)
_MUSICAL = re.compile(r"^([A-G])\s*([#♯b♭]?)\s*(.*)$", re.I)
_MINOR_WORDS = {"m", "min", "minor", "mineur", "-"}
_MAJOR_WORDS = {"", "maj", "major", "majeur"}


def to_camelot(key: Optional[str]) -> Optional[str]:
    """'Am' -> '8A', 'F#' -> '2B', '08b' -> '8B', '1m' -> '6A'. None si non reconnu."""
    text = (key or "").strip()
    if not text:
        return None

    m = _CAMELOT.match(text)
    if m:
        return f"{int(m.group(1))}{m.group(2).upper()}"

    m = _OPENKEY.match(text)
    if m:  # Open Key = Camelot décalé de 7 crans : 1d = Do majeur = 8B ; 1m = La mineur = 8A
        number = (int(m.group(1)) - 1 + 7) % 12 + 1
        return f"{number}{'B' if m.group(2).lower() == 'd' else 'A'}"

    m = _MUSICAL.match(text)
    if not m:
        return None
    note, accidental, rest = m.group(1).upper(), m.group(2), m.group(3).strip()
    if accidental == "B":  # (re.I) "BB" : le 2e B est une altération = bémol
        accidental = "b"
    pitch = _NOTE[note] + {"#": 1, "♯": 1, "b": -1, "♭": -1, "": 0}[accidental]
    pitch %= 12
    if rest == "M":  # "CM" = Do majeur (et "Cm" = Do mineur)
        return _MAJOR[pitch]
    if rest.lower() in _MINOR_WORDS:
        return _MINOR[pitch]
    if rest.lower() in _MAJOR_WORDS:
        return _MAJOR[pitch]
    return None


def neighbors(camelot: Optional[str]) -> List[str]:
    """Clés qui s'enchaînent harmoniquement : identique, ±1 sur la roue, relative majeure/mineure."""
    code = to_camelot(camelot)
    if not code:
        return []
    number, letter = int(code[:-1]), code[-1]
    other = "B" if letter == "A" else "A"
    prev_n, next_n = (number - 2) % 12 + 1, number % 12 + 1
    return [code, f"{prev_n}{letter}", f"{next_n}{letter}", f"{number}{other}"]


def are_compatible(a: Optional[str], b: Optional[str]) -> bool:
    ca, cb = to_camelot(a), to_camelot(b)
    return bool(ca and cb and cb in neighbors(ca))


def read_file_key(path: str) -> Optional[str]:
    """Tonalité écrite dans les tags d'un fichier audio (ID3 TKEY, MP4 initialkey, Vorbis…), sinon None."""
    try:
        import mutagen

        audio = mutagen.File(path)
    except Exception:  # noqa: BLE001 - fichier illisible : pas de tonalité
        return None
    if audio is None or audio.tags is None:
        return None
    tags = audio.tags
    try:
        if "TKEY" in tags:                                   # MP3 / AIFF / WAV (ID3)
            return str(tags["TKEY"].text[0]) or None
        for name in ("----:com.apple.iTunes:initialkey", "----:com.apple.iTunes:KEY"):  # M4A
            if name in tags:
                value = tags[name][0]
                return (bytes(value).decode("utf-8", "ignore") if not isinstance(value, str) else value) or None
        for name in ("initialkey", "INITIALKEY", "key", "KEY"):  # FLAC / Vorbis
            if name in tags:
                return str(tags[name][0]) or None
    except Exception:  # noqa: BLE001
        return None
    return None
