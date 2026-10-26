"""Hot cues, boucles et mémoires dans les fichiers ANLZ (1.3.0, C22).

Format relevé octet par octet sur une clé exportée par Rekordbox (wav, m4a et mp3 ; voir le document
du projet « cues-reference-rekordbox ») :

- Rekordbox n'écrit les cues QUE dans les fichiers d'analyse (la table `cue` de exportLibrary.db reste
  vide) ; positions en millisecondes, quel que soit le format audio.
- .DAT : PCOB hot cues A–C (anciennes platines à 3 pads) + PCOB toutes les mémoires.
- .EXT : PCOB hot cues D–H + PCOB mémoires vide + PCO2 toutes les hot cues (noms, couleurs, longueur
  des boucles) + PCO2 toutes les mémoires.
- Numéros : mémoire 0, A=1 … H=8. Entrées triées par position décroissante.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .anlz import iter_tags, parse

SLOTS = "ABCDEFGH"
NO_LOOP = 0xFFFFFFFF
# Couleur par défaut de chaque pad (color_code 0) telle que Rekordbox l'écrit dans le .EXT.
DEFAULT_RGB = {1: (0xFF, 0x00, 0x17), 2: (0x00, 0xC4, 0xFF), 3: (0x33, 0xFF, 0x00), 4: (0x4D, 0x00, 0xFF),
               5: (0x00, 0xFF, 0x30), 6: (0xFF, 0x5E, 0x00), 7: (0x00, 0x00, 0xFF), 8: (0xFF, 0xE8, 0x00)}
LOOP_RGB = (0xFF, 0x8C, 0x00)
# Palette des hot cues de Rekordbox (16 couleurs) : color_code -> RGB, relevée sur un export réel ;
# l'ordre des codes suit le cercle des couleurs (bleu -> cyan -> vert -> jaune -> rouge -> violet).
PALETTE = {1: (0x00, 0x00, 0xFF), 8: (0x00, 0xC4, 0xFF), 9: (0x00, 0xE0, 0xFF), 18: (0x00, 0xFF, 0x47),
           19: (0x00, 0xFF, 0x30), 23: (0x33, 0xFF, 0x00), 26: (0x80, 0xFF, 0x00), 30: (0xE6, 0xFF, 0x00),
           32: (0xFF, 0xE8, 0x00), 38: (0xFF, 0x5E, 0x00), 42: (0xFF, 0x00, 0x00), 43: (0xFF, 0x00, 0x17),
           49: (0xFF, 0x00, 0xA1), 56: (0xB3, 0x00, 0xFF), 60: (0x4D, 0x00, 0xFF), 62: (0x1A, 0x00, 0xFF)}


@dataclass
class Cue:
    slot: int                       # 0 = mémoire, 1..8 = hot cue A..H
    ms: int
    loop_ms: Optional[int] = None   # fin de boucle (ms) ; None = simple point
    loop_beats: int = 0             # longueur de la boucle en temps (affichage platine), 0 si inconnue
    name: str = ""
    color_code: int = 0             # 0 = couleur par défaut du pad
    rgb: Tuple[int, int, int] = (0, 0, 0)

    @property
    def is_hot(self) -> bool:
        return self.slot > 0

    @property
    def is_loop(self) -> bool:
        return self.loop_ms is not None and self.loop_ms > self.ms

    @property
    def label(self) -> str:
        return SLOTS[self.slot - 1] if 1 <= self.slot <= 8 else ""

    def colour(self) -> Tuple[int, int, int]:
        """Couleur à afficher : celle de la palette, sinon celle du pad (orange pour une boucle)."""
        if self.color_code and self.rgb != (0, 0, 0):
            return self.rgb
        if not self.is_hot:
            return (0xFF, 0x30, 0x30)
        return LOOP_RGB if self.is_loop else DEFAULT_RGB.get(self.slot, (0x80, 0x80, 0x80))


def _order(cues: Sequence[Cue]) -> List[Cue]:
    return sorted(cues, key=lambda c: (-c.ms, not c.is_loop, c.slot))


# ------------------------------------------------------------------------ écriture
def pcpt(c: Cue, order_first: int = 0xFFFF, order_last: int = 0xFFFF) -> bytes:
    body = struct.pack(">IIIHHBBHII", c.slot, 0, 0x00010000, order_first, order_last, 2 if c.is_loop else 1, 0,
                       1000, c.ms & 0xFFFFFFFF, (c.loop_ms if c.is_loop else NO_LOOP) & 0xFFFFFFFF) + b"\x00" * 16
    return b"PCPT" + struct.pack(">II", 28, 12 + len(body)) + body


def pcob(kind: int, cues: Sequence[Cue]) -> bytes:
    """Liste PCOB (kind 1 : hot cues, 0 : mémoires). Mémoires chaînées comme Rekordbox."""
    cues = _order(cues)
    n = len(cues)
    if kind == 0:
        entries = b"".join(pcpt(c, 0xFFFF if k == 0 else k - 1, 0xFFFF if k == n - 1 else k + 1)
                           for k, c in enumerate(cues))
        last = n - 1 if n else -1
    else:
        entries = b"".join(pcpt(c) for c in cues)
        last = -1
    head = struct.pack(">IHHi", kind, 0, n, last)
    return b"PCOB" + struct.pack(">II", 24, 24 + len(entries)) + head + entries


def pcp2(c: Cue) -> bytes:
    name = (c.name.encode("utf-16-be") + b"\x00\x00") if c.name else b""
    if c.is_hot:
        rgb = c.rgb if c.color_code else (LOOP_RGB if c.is_loop else DEFAULT_RGB.get(c.slot, (0, 0, 0)))
    else:
        rgb = c.rgb if c.color_code else (0, 0, 0)
    body = (struct.pack(">IB", c.slot, 2 if c.is_loop else 1) + b"\x00\x03\xe8"
            + struct.pack(">II", c.ms & 0xFFFFFFFF, (c.loop_ms if c.is_loop else NO_LOOP) & 0xFFFFFFFF)
            + b"\x00\x01" + b"\x00" * 6
            + struct.pack(">HHI", c.loop_beats if c.is_loop else 0, 1 if c.is_loop else 0, len(name)) + name
            + struct.pack(">BBBB", c.color_code & 0xFF, *rgb))
    body += b"\x00" * (88 - 12 + len(name) - len(body))
    return b"PCP2" + struct.pack(">II", 16, 12 + len(body)) + body


def pco2(kind: int, cues: Sequence[Cue]) -> bytes:
    cues = _order(cues)
    entries = b"".join(pcp2(c) for c in cues)
    head = struct.pack(">IHH", kind, len(cues), 0)
    return b"PCO2" + struct.pack(">II", 20, 20 + len(entries)) + head + entries


def dat_tags(cues: Sequence[Cue]) -> Tuple[bytes, bytes]:
    hot = [c for c in cues if 1 <= c.slot <= 3]
    mem = [c for c in cues if c.slot == 0]
    return pcob(1, hot), pcob(0, mem)


def ext_tags(cues: Sequence[Cue]) -> Tuple[bytes, bytes, bytes, bytes]:
    hot_late = [c for c in cues if 4 <= c.slot <= 8]
    hot = [c for c in cues if c.slot > 0]
    mem = [c for c in cues if c.slot == 0]
    return pcob(1, hot_late), pcob(0, []), pco2(1, hot), pco2(0, mem)


def _rewrite(data: bytes, wanted: Dict[Tuple[str, int], bytes], insert_after: str) -> bytes:
    """Remplace les listes de cues (code, type) ; ajoute celles qui manquent après la dernière balise
    `insert_after` (ou à la fin). Les autres balises sont recopiées à l'octet près."""
    head_len = struct.unpack(">I", data[4:8])[0]
    out: List[bytes] = []
    done = set()
    last_anchor = -1
    for code, raw in iter_tags(data):
        if code in ("PCOB", "PCO2"):
            kind = struct.unpack(">I", raw[12:16])[0]
            key = (code, kind)
            if key in wanted and key not in done:
                out.append(wanted[key])
                done.add(key)
                last_anchor = len(out) - 1
                continue
            if key in wanted:                       # liste en double : on n'en garde qu'une
                continue
        out.append(raw)
        if code in (insert_after, "PCOB", "PCO2"):
            last_anchor = len(out) - 1
    missing = [wanted[k] for k in (("PCOB", 1), ("PCOB", 0), ("PCO2", 1), ("PCO2", 0)) if k in wanted and k not in done]
    pos = last_anchor + 1 if last_anchor >= 0 else len(out)
    out[pos:pos] = missing
    body = b"".join(out)
    head = bytearray(data[:head_len])
    struct.pack_into(">I", head, 8, head_len + len(body))
    result = bytes(head) + body
    parse(result)
    return result


def write_cues(dat: bytes, ext: Optional[bytes], cues: Sequence[Cue]) -> Tuple[bytes, Optional[bytes]]:
    """Nouveaux .DAT / .EXT avec ces cues (tout le reste inchangé)."""
    cues = [c for c in cues if 0 <= c.slot <= 8 and c.ms >= 0]
    slots = [c.slot for c in cues if c.slot]
    if len(slots) != len(set(slots)):
        raise ValueError("two hot cues on the same pad")
    d_hot, d_mem = dat_tags(cues)
    new_dat = _rewrite(dat, {("PCOB", 1): d_hot, ("PCOB", 0): d_mem}, "PWV2")
    new_ext = None
    if ext is not None:
        e_hot, e_mem, e2_hot, e2_mem = ext_tags(cues)
        new_ext = _rewrite(ext, {("PCOB", 1): e_hot, ("PCOB", 0): e_mem, ("PCO2", 1): e2_hot, ("PCO2", 0): e2_mem},
                           "PWV3")
    return new_dat, new_ext


# ------------------------------------------------------------------------ lecture
def _read_pcob(raw: bytes) -> List[Cue]:
    out = []
    lh = struct.unpack(">I", raw[4:8])[0]
    i = lh
    while i + 12 <= len(raw) and raw[i:i + 4] == b"PCPT":
        ln = struct.unpack(">I", raw[i + 8:i + 12])[0]
        slot = struct.unpack(">I", raw[i + 12:i + 16])[0]
        kind = raw[i + 28]
        ms, loop = struct.unpack(">II", raw[i + 32:i + 40])
        out.append(Cue(slot, ms, loop if kind == 2 and loop != NO_LOOP else None))
        i += max(ln, 12)
    return out


def _read_pco2(raw: bytes) -> List[Cue]:
    out = []
    lh = struct.unpack(">I", raw[4:8])[0]
    i = lh
    while i + 16 <= len(raw) and raw[i:i + 4] == b"PCP2":
        ln = struct.unpack(">I", raw[i + 8:i + 12])[0]
        e = raw[i:i + ln]
        slot = struct.unpack(">I", e[12:16])[0]
        kind = e[16]
        ms, loop = struct.unpack(">II", e[20:28])
        num, _den, n_name = struct.unpack(">HHI", e[36:44])
        name = e[44:44 + n_name].decode("utf-16-be", errors="replace").rstrip("\x00") if n_name else ""
        code, r, g, b = e[44 + n_name:48 + n_name] if len(e) >= 48 + n_name else (0, 0, 0, 0)
        out.append(Cue(slot, ms, loop if kind == 2 and loop != NO_LOOP else None, num if kind == 2 else 0, name,
                       code, (r, g, b)))
        i += max(ln, 16)
    return out


def _key(c: Cue) -> Tuple[int, int]:
    return (c.slot, 0) if c.slot else (0, c.ms * 10 + (1 if c.is_loop else 0))


def read_cues(dat: Optional[bytes], ext: Optional[bytes] = None) -> List[Cue]:
    """Toutes les cues d'un son : liste étendue PCO2 du .EXT si elle existe (noms, couleurs), sinon les
    listes PCOB du .DAT et du .EXT. Triées : hot cues A→H, puis mémoires par position."""
    found: Dict[Tuple[int, int], Cue] = {}
    have_ext2 = {0: False, 1: False}
    if ext:
        for code, raw in iter_tags(ext):
            if code == "PCO2":
                kind = struct.unpack(">I", raw[12:16])[0]
                have_ext2[kind] = True
                for c in _read_pco2(raw):
                    found[_key(c)] = c
    for blob in (dat, ext):
        if not blob:
            continue
        for code, raw in iter_tags(blob):
            if code != "PCOB":
                continue
            kind = struct.unpack(">I", raw[12:16])[0]
            if have_ext2.get(kind):
                continue
            for c in _read_pcob(raw):
                found.setdefault(_key(c), c)
    hot = sorted((c for c in found.values() if c.slot), key=lambda c: c.slot)
    mem = sorted((c for c in found.values() if not c.slot), key=lambda c: (c.ms, c.is_loop))
    return hot + mem


def loop_beats_for(start_ms: int, end_ms: int, bpm: float) -> int:
    """Longueur d'une boucle en temps, arrondie (affichée par la platine)."""
    if bpm <= 0 or end_ms <= start_ms:
        return 0
    return max(1, int(round((end_ms - start_ms) / 60000.0 * bpm)))


# ------------------------------------------------------------- master.db (ordinateur)
# djmdCue.Kind : 0 = mémoire, A-C = 1-3, D-H = 5-9 (4 n'est pas utilisé par Rekordbox).
KIND_FOR_SLOT = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9}
SLOT_FOR_KIND = {v: k for k, v in KIND_FOR_SLOT.items()}


# --------------------------------------------------------- édition (page Grille et cues)
def nearest_beat_ms(beats: Sequence[Tuple[int, int, int]], ms: float) -> int:
    """Position du temps de la grille le plus proche (calage des cues)."""
    if not beats:
        return int(round(ms))
    return int(min(beats, key=lambda b: abs(b[2] - ms))[2])


def loop_end_ms(beats: Sequence[Tuple[int, int, int]], start_ms: int, n_beats: int) -> int:
    """Fin d'une boucle de `n_beats` temps qui commence à `start_ms`, calée sur la grille ; au-delà du
    dernier temps, on prolonge au tempo du dernier temps."""
    n_beats = max(1, int(n_beats))
    if not beats:
        return start_ms + n_beats * 500
    i = min(range(len(beats)), key=lambda k: abs(beats[k][2] - start_ms))
    j = i + n_beats
    if j < len(beats):
        return int(beats[j][2] - beats[i][2] + start_ms)
    tempo = beats[-1][1] / 100.0 or 120.0
    return int(round(start_ms + n_beats * 60000.0 / tempo))


def suggest_cues(beats: Sequence[Tuple[int, int, int]], existing: Sequence[Cue], every_bars: int = 32,
                 limit: int = 8) -> List[Cue]:
    """« Proposer des cues » : A au premier temps fort, puis un pad toutes les `every_bars` mesures, sur
    les pads encore libres seulement (les cues existants ne sont jamais déplacés)."""
    bars = [b[2] for b in beats if b[0] == 1]
    if not bars:
        return []
    taken = {c.slot for c in existing if c.slot}
    used_ms = {c.ms for c in existing if c.slot}
    free = [s for s in range(1, limit + 1) if s not in taken]
    out: List[Cue] = []
    for ms in bars[::max(1, every_bars)]:
        if not free:
            break
        if ms in used_ms:
            continue
        out.append(Cue(free.pop(0), int(ms)))
    return out


__all__ = ["Cue", "SLOTS", "PALETTE", "read_cues", "write_cues", "pcob", "pco2", "loop_beats_for",
           "nearest_beat_ms", "loop_end_ms", "suggest_cues", "KIND_FOR_SLOT", "SLOT_FOR_KIND"]


def save_to_files(dat_path, cues: Sequence[Cue], backup_dir) -> None:
    """Réécrit le .DAT et le .EXT d'un son avec ces cues. Copie d'origine dans `backup_dir` avant toute
    écriture ; en cas d'échec, les fichiers d'origine sont remis."""
    import logging
    from pathlib import Path

    from .anlz import _write_atomic

    dat_path = Path(dat_path)
    ext_path = dat_path.with_suffix(".EXT")
    originals = {dat_path: dat_path.read_bytes()}
    if ext_path.is_file():
        originals[ext_path] = ext_path.read_bytes()
    backup = Path(backup_dir)
    backup.mkdir(parents=True, exist_ok=True)
    for f, data in originals.items():
        (backup / f.name).write_bytes(data)
    new_dat, new_ext = write_cues(originals[dat_path], originals.get(ext_path), cues)
    try:
        _write_atomic(dat_path, new_dat)
        if new_ext is not None:
            _write_atomic(ext_path, new_ext)
    except BaseException:
        for f, data in originals.items():
            try:
                _write_atomic(f, data)
            except OSError:
                logging.getLogger(__name__).error("Could not restore %s (copy in %s)", f, backup)
        raise
