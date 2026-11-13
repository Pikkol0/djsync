"""Écriture (et relecture de contrôle) des fichiers d'analyse Pioneer ANLZ0000.DAT / .EXT.

Structure recopiée de VRAIS fichiers exportés par Rekordbox (constantes vérifiées octet par octet) :
  en-tête   « PMAI », 0x1C, taille totale, 1, 0x10000, 0x10000, 0 (entiers big-endian) ;
  .DAT      PPTH, PVBR, PQTZ, PWAV, PWV2, PCOB (hot cues), PCOB (mémoires)
  .EXT      PPTH, PWV3, PCOB, PCOB, PCO2, PCO2, PWV5, PWV4
  .2EX      PPTH, PWV7, PWV6, PWVC (formes d'onde 3 bandes, V0.3.0)
Chaque balise : code 4 lettres, longueur d'en-tête, longueur totale, puis contenu.

Non écrits (facultatifs) : PQT2 (grille étendue) et PSSI (phrases, nécessite l'analyse « phrase » de
Rekordbox). Le .2EX est écrit depuis la V0.3.0 : sans lui, Rekordbox 6/7 réglé sur « 3Band » montrait un
aperçu bleu (liste, aperçu du morceau entier) au lieu de l'aperçu 3 bandes des sons qu'il a analysés.
"""
from __future__ import annotations

import os
import re
import struct
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .waveform import Waveforms

ANLZ_ROOT = "PIONEER/USBANLZ"


# ------------------------------------------------------------------------ balises
def _tag(code: bytes, header_rest: bytes, body: bytes) -> bytes:
    len_header = 12 + len(header_rest)
    return code + struct.pack(">II", len_header, len_header + len(body)) + header_rest + body


def _ppth(track_path: str) -> bytes:
    raw = track_path.encode("utf-16-be") + b"\x00\x00"
    return _tag(b"PPTH", struct.pack(">I", len(raw)), raw)


def _pvbr(total_samples: int) -> bytes:
    # 400 entrées d'index à 0 (comme les fichiers réels) + nombre total d'échantillons (mp3 ; 0 sinon)
    return _tag(b"PVBR", struct.pack(">I", 0), b"\x00" * 1600 + struct.pack(">I", total_samples & 0xFFFFFFFF))


def _pqtz(beats: Sequence[Tuple[int, int, int]]) -> bytes:
    body = b"".join(struct.pack(">HHI", n, tempo, ms) for n, tempo, ms in beats)
    return _tag(b"PQTZ", struct.pack(">III", 0, 0x00080000, len(beats)), body)


def _pwav(code: bytes, data: bytes) -> bytes:
    return _tag(code, struct.pack(">II", len(data), 0x00010000), data)


def _pwv(code: bytes, entry_bytes: int, count: int, unknown: int, data: bytes) -> bytes:
    return _tag(code, struct.pack(">III", entry_bytes, count, unknown), data)


def build_2ex(track_path: str, wf: Waveforms) -> bytes:
    n = len(wf.band_detail) // 3
    return _file([
        _ppth(track_path),
        _pwv(b"PWV7", 3, n, 0x00960000, wf.band_detail),
        _tag(b"PWV6", struct.pack(">II", 3, len(wf.band_preview) // 3), wf.band_preview),
        _tag(b"PWVC", b"\x00\x00", struct.pack(">HHH", *wf.band_norm)),
    ])


def _file(tags: List[bytes]) -> bytes:
    body = b"".join(tags)
    return b"PMAI" + struct.pack(">IIIIII", 0x1C, 0x1C + len(body), 1, 0x00010000, 0x00010000, 0) + body


def _as_cues(memory_cues: Sequence[int], cues: Optional[Sequence] = None) -> list:
    from .cues import Cue

    return list(cues) if cues is not None else [Cue(0, int(ms)) for ms in memory_cues]


def build_dat(track_path: str, beats: Sequence[Tuple[int, int, int]], wf: Waveforms, total_samples: int = 0,
              memory_cues: Sequence[int] = (), cues: Optional[Sequence] = None) -> bytes:
    from .cues import dat_tags

    hot, mem = dat_tags(_as_cues(memory_cues, cues))         # 1.3.0 : listes écrites comme Rekordbox
    return _file([_ppth(track_path), _pvbr(total_samples), _pqtz(beats), _pwav(b"PWAV", wf.preview),
                  _pwav(b"PWV2", wf.tiny_preview), hot, mem])


def build_ext(track_path: str, wf: Waveforms, memory_cues: Sequence[int] = (), cues: Optional[Sequence] = None) -> bytes:
    from .cues import ext_tags

    n = wf.detail_count
    return _file([
        _ppth(track_path),
        _pwv(b"PWV3", 1, n, 0x00960000, wf.detail),
        *ext_tags(_as_cues(memory_cues, cues)),
        _pwv(b"PWV5", 2, n, 0x00960305, wf.color_detail),
        _pwv(b"PWV4", 6, len(wf.color_preview) // 6, 0, wf.color_preview),
    ])


# ------------------------------------------------------------------- relecture
def parse(data: bytes) -> Dict[str, List[Tuple[bytes, bytes]]]:
    """{code: [(en-tête après les 12 octets communs, contenu)]}. Lève ValueError si incohérent."""
    if data[:4] != b"PMAI":
        raise ValueError("not an ANLZ file (PMAI expected)")
    len_header, len_file = struct.unpack(">II", data[4:12])
    if len_file != len(data):
        raise ValueError("inconsistent declared size")
    out: Dict[str, List[Tuple[bytes, bytes]]] = {}
    i = len_header
    while i < len(data):
        code = data[i:i + 4].decode("ascii")
        lh, lt = struct.unpack(">II", data[i + 4:i + 12])
        if lh < 12 or lt < lh or i + lt > len(data):
            raise ValueError(f"tag {code}: inconsistent lengths")
        out.setdefault(code, []).append((data[i + 12:i + lh], data[i + lh:i + lt]))
        i += lt
    return out


def read_path(data: bytes) -> str:
    tags = parse(data)
    if "PPTH" not in tags:
        return ""
    return tags["PPTH"][0][1].decode("utf-16-be").rstrip("\x00")


# -------------------------------------------------------------------- emplacement
ANLZ_NAME = re.compile(r"^ANLZ(\d{4})\.DAT$", re.IGNORECASE)


def rekordbox_anlz_dir(track_path: str) -> str:
    """1.3.0-rc.6 (B27) : dossier « /PIONEER/USBANLZ/Pxxx/xxxxxxxx » calculé comme Rekordbox.

    Hachage du chemin du son sur la clé (« /Contents/… », unités UTF-16), repris de rkbdb2xml
    (licence MIT, voir THIRD_PARTY_NOTICES) et vérifié sur les 213 pistes d'un vrai export
    (tests/data/real_export.pdb). Les platines lisent le chemin écrit dans la base ; avoir le même
    dossier que Rekordbox évite toute différence si un lecteur ou un logiciel le recalcule.
    """
    v = 0
    raw = track_path.encode("utf-16-le")
    for i in range(0, len(raw), 2):
        c = raw[i] | (raw[i + 1] << 8)
        t = (v * 0x5BC9 + c) & 0xFFFFFFFF
        v = (t * 0x93B5 + c) & 0xFFFFFFFF
    r = v % 200003
    p = ((r & 1) | ((r >> 1) & 2) | ((r >> 4) & 4) | ((r >> 4) & 8) | ((r >> 5) & 0x10)
         | ((r >> 8) & 0x20) | ((r >> 10) & 0x40))
    return f"/{ANLZ_ROOT}/P{p:03X}/{r:08X}"


def anlz_dir_for(track_path: str, salt: int = 0) -> str:
    """Ancien emplacement (jusqu'à la 1.3.0-rc.5, hachage propre à DJSync) : sert à reconnaître les
    analyses à déplacer. Ne plus l'utiliser pour écrire."""
    h = zlib.crc32(f"{salt}:{track_path.casefold()}".encode("utf-8"))
    return f"/{ANLZ_ROOT}/P{h & 0x3FF:03X}/{(h >> 10) & 0x3FFFFF:08X}"


def choose_anlz_base(drive_root: Path, track_path: str) -> str:
    """« /PIONEER/USBANLZ/Pxxx/xxxxxxxx/ANLZnnnn » : le dossier de Rekordbox, et le premier jeu de
    fichiers libre ou déjà à CE son. Deux sons dont le chemin donne le même dossier (rare) : comme
    Rekordbox, le second prend ANLZ0001.*. Jamais l'analyse d'un autre son écrasée."""
    rel_dir = rekordbox_anlz_dir(track_path)
    folder = Path(drive_root) / rel_dir.lstrip("/")
    for n in range(10000):
        dat = folder / f"ANLZ{n:04d}.DAT"
        if not dat.exists():
            return f"{rel_dir}/ANLZ{n:04d}"
        try:
            if read_path(dat.read_bytes()).casefold() == track_path.casefold():
                return f"{rel_dir}/ANLZ{n:04d}"
        except (OSError, ValueError, UnicodeDecodeError):
            continue
    raise OSError("no free analysis folder found")


def choose_anlz_dir(drive_root: Path, track_path: str) -> str:
    """Compatibilité : dossier seul (le nom des fichiers peut être ANLZ0001 : préférer choose_anlz_base)."""
    return choose_anlz_base(drive_root, track_path).rsplit("/", 1)[0]


def is_anlz_dat(name: str) -> bool:
    return bool(ANLZ_NAME.match(name))


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".djsync-tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


class CuesUnreadable(ValueError):
    """1.4.1 (B96) : les cues de l'analyse existante ne se relisent pas ; rien n'est réécrit."""


def write_files(drive_root: Path, track_path: str, beats: Sequence[Tuple[int, int, int]], wf: Waveforms,
                total_samples: int = 0, rel_dir: Optional[str] = None, memory_cues: Sequence[int] = (),
                previous: Optional[str] = None) -> str:
    """Écrit ANLZnnnn.DAT, .EXT et .2EX ; renvoie le chemin à inscrire (…/ANLZ0000.DAT, ou ANLZ0001…).
    `memory_cues` : mémoires (ms) lues par les platines (V0.5.0 : premier temps fort).
    `rel_dir` imposé (bibliothèque de l'ordinateur) : fichiers ANLZ0000.* dans ce dossier.
    `previous` : ancien « …/ANLZnnnn.DAT » de ce son (1.3.0-rc.6 : emplacement changé), dont les cues
    sont reprises si le nouvel emplacement n'en a pas encore."""
    base = f"{rel_dir}/ANLZ0000" if rel_dir else choose_anlz_base(drive_root, track_path)
    target = Path(drive_root) / base.lstrip("/")
    cues = None
    sources = [target.with_name(target.name + ".DAT")]
    if previous:
        sources.append(Path(drive_root) / previous.lstrip("/"))
    for old_dat in sources:                     # 1.3.0 : une réanalyse garde les cues déjà posées
        if not old_dat.is_file():
            continue
        old_ext = old_dat.with_suffix(".EXT")
        try:
            from .cues import read_cues

            kept = read_cues(old_dat.read_bytes(), old_ext.read_bytes() if old_ext.is_file() else None)
            cues = kept or None
        except (OSError, ValueError, struct.error, IndexError) as exc:
            # 1.4.1 (B96) : avant, les cues étaient perdus sans message ; le son n'est plus réécrit
            raise CuesUnreadable(f"cues of the existing analysis could not be read ({old_dat.name}: {exc}); "
                                 "track left untouched") from exc
        break
    dat = build_dat(track_path, beats, wf, total_samples, memory_cues, cues)
    ext = build_ext(track_path, wf, memory_cues, cues)
    two = build_2ex(track_path, wf) if wf.band_detail else b""
    for blob in (dat, ext) + ((two,) if two else ()):    # contrôle avant écriture : relisible
        parse(blob)
    _write_atomic(target.with_name(target.name + ".DAT"), dat)
    _write_atomic(target.with_name(target.name + ".EXT"), ext)
    if two:
        _write_atomic(target.with_name(target.name + ".2EX"), two)
    return f"{base}.DAT"


def read_memory_cues(data: bytes) -> List[int]:
    """Positions (ms) des mémoires d'un .DAT/.EXT (liste PCOB de type 0)."""
    out: List[int] = []
    for code, raw in iter_tags(data):
        if code != "PCOB" or struct.unpack(">I", raw[12:16])[0] != 0:
            continue
        i = struct.unpack(">I", raw[4:8])[0]
        while i + 12 <= len(raw) and raw[i:i + 4] == b"PCPT":
            entry = struct.unpack(">I", raw[i + 8:i + 12])[0]
            out.append(struct.unpack(">I", raw[i + 32:i + 36])[0])
            i += entry
    return out


# ---------------------------------------------------------- V0.2.0 : grille et aperçus
def iter_tags(data: bytes) -> List[Tuple[str, bytes]]:
    """[(code, octets bruts de la balise)] dans l'ordre du fichier (pour réécrire sans rien perdre)."""
    parse(data)                                  # validation
    len_header = struct.unpack(">I", data[4:8])[0]
    out, i = [], len_header
    while i < len(data):
        lt = struct.unpack(">I", data[i + 8:i + 12])[0]
        out.append((data[i:i + 4].decode("ascii"), data[i:i + lt]))
        i += lt
    return out


def rebuild(data: bytes, replace: Dict[str, Optional[bytes]]) -> bytes:
    """Réécrit un fichier ANLZ : chaque balise listée dans `replace` est remplacée (octets complets
    de la nouvelle balise) ou retirée (None) ; les autres sont recopiées à l'octet près, en-tête PMAI
    compris (seule la longueur totale change)."""
    len_header = struct.unpack(">I", data[4:8])[0]
    body = b"".join(replace.get(code, raw) or b"" if code in replace else raw for code, raw in iter_tags(data))
    head = bytearray(data[:len_header])
    struct.pack_into(">I", head, 8, len_header + len(body))
    out = bytes(head) + body
    parse(out)
    return out


def retarget(data: bytes, track_path: str) -> bytes:
    """Même analyse, autre fichier audio : seul le chemin PPTH change (copie d'une bibliothèque à l'autre)."""
    return rebuild(data, {"PPTH": _ppth(track_path)})


def read_beats(data: bytes) -> List[Tuple[int, int, int]]:
    """Grille PQTZ d'un .DAT : [(n° du temps dans la mesure 1-4, tempo x100, position ms)]."""
    tags = parse(data)
    if "PQTZ" not in tags:
        return []
    head, body = tags["PQTZ"][0]
    count = struct.unpack(">I", head[8:12])[0] if len(head) >= 12 else len(body) // 8
    count = min(count, len(body) // 8)
    return [struct.unpack(">HHI", body[k * 8:k * 8 + 8]) for k in range(count)]


def replace_beats(data: bytes, beats: Sequence[Tuple[int, int, int]]) -> bytes:
    """.DAT avec une nouvelle grille (en-tête PQTZ d'origine conservé, sauf le nombre de temps)."""
    tags = parse(data)
    if "PQTZ" not in tags:
        raise ValueError("no beat grid (PQTZ) in this file")
    head = bytearray(tags["PQTZ"][0][0])
    if len(head) < 12:
        head = bytearray(struct.pack(">III", 0, 0x00080000, 0))
    struct.pack_into(">I", head, 8, len(beats))
    body = b"".join(struct.pack(">HHI", n, tempo, ms) for n, tempo, ms in beats)
    return rebuild(data, {"PQTZ": _tag(b"PQTZ", bytes(head), body)})


def drop_extended_grid(data: bytes) -> bytes:
    """Retire PQT2 (grille étendue, .EXT/.2EX) : sinon les platines récentes garderaient l'ancienne."""
    return rebuild(data, {"PQT2": None}) if "PQT2" in parse(data) else data


# ------------------------------------------- 1.4.1 (C131, D20) : greffe dans une analyse de Rekordbox
CUE_TAGS = ("PCOB", "PCO2")
GRID_EXTRAS = ("PQT2", "PSSI")           # grille étendue et phrases : calées sur l'ancienne grille, retirées


def cue_tags(data: bytes) -> List[bytes]:
    """Balises de cues (octets bruts, dans l'ordre du fichier)."""
    return [raw for code, raw in iter_tags(data) if code in CUE_TAGS]


def _wave_tags(suffix: str, wf: Waveforms) -> Dict[str, Optional[bytes]]:
    if suffix == ".DAT":
        return {"PWAV": _pwav(b"PWAV", wf.preview), "PWV2": _pwav(b"PWV2", wf.tiny_preview)}
    if suffix == ".EXT":
        n = wf.detail_count
        return {"PWV3": _pwv(b"PWV3", 1, n, 0x00960000, wf.detail),
                "PWV5": _pwv(b"PWV5", 2, n, 0x00960305, wf.color_detail),
                "PWV4": _pwv(b"PWV4", 6, len(wf.color_preview) // 6, 0, wf.color_preview)}
    if suffix == ".2EX" and wf.band_detail:
        return {"PWV7": _pwv(b"PWV7", 3, len(wf.band_detail) // 3, 0x00960000, wf.band_detail),
                "PWV6": _tag(b"PWV6", struct.pack(">II", 3, len(wf.band_preview) // 3), wf.band_preview),
                "PWVC": _tag(b"PWVC", b"\x00\x00", struct.pack(">HHH", *wf.band_norm))}
    return {}


def graft(files: Dict[str, bytes], beats: Optional[Sequence[Tuple[int, int, int]]] = None,
          wf: Optional[Waveforms] = None) -> Dict[str, bytes]:
    """Greffe dans les fichiers d'analyse d'un son ({".DAT": …, ".EXT": …, ".2EX": …}) sans les
    reconstruire : `beats` remplace PQTZ (PQT2 et PSSI retirés), `wf` remplace les balises de forme
    d'onde déjà présentes. Tout le reste (PPTH, PVBR, cues…) est recopié à l'octet près. Renvoie
    seulement les fichiers qui changent. ValueError si un fichier est illisible, si le .DAT manque
    ou si les cues ne ressortent pas identiques (rien n'est alors à écrire)."""
    from .cues import read_cues

    if ".DAT" not in files:
        raise ValueError("no .DAT analysis file")
    try:
        read_cues(files[".DAT"], files.get(".EXT"))          # cues relisibles, sinon on ne touche à rien
    except (struct.error, IndexError) as exc:
        raise ValueError(f"unreadable cues: {exc}") from exc
    out: Dict[str, bytes] = {}
    for suffix, data in files.items():
        new = data
        if beats is not None:
            if suffix == ".DAT":
                new = replace_beats(new, beats)
            present = {code for code, _raw in iter_tags(new)}
            drop = {code: None for code in GRID_EXTRAS if code in present}
            if drop:
                new = rebuild(new, drop)
        if wf is not None:
            present = {code for code, _raw in iter_tags(new)}
            swap = {code: raw for code, raw in _wave_tags(suffix, wf).items() if code in present}
            if swap:
                new = rebuild(new, swap)
        if cue_tags(new) != cue_tags(data):
            raise ValueError(f"cues would change in {suffix}")
        if new != data:
            out[suffix] = new
    return out


def with_cues_of(original: bytes, current: bytes) -> bytes:
    """`original` avec les cues de `current` (« Rétablir l'analyse de Rekordbox » : les cues posés
    depuis sont gardés). Cues identiques : `original` rendu à l'octet près."""
    now: Dict[str, List[bytes]] = {}
    for code, raw in iter_tags(current):
        if code in CUE_TAGS:
            now.setdefault(code, []).append(raw)
    if cue_tags(original) == cue_tags(current):
        return original
    len_header = struct.unpack(">I", original[4:8])[0]
    body, seen = [], set()
    for code, raw in iter_tags(original):
        if code not in CUE_TAGS:
            body.append(raw)
        elif code not in seen:
            seen.add(code)
            body += now.get(code, [])
    for code in CUE_TAGS:                                 # listes absentes de l'original : à la fin
        if code not in seen:
            body += now.get(code, [])
    blob = b"".join(body)
    head = bytearray(original[:len_header])
    struct.pack_into(">I", head, 8, len_header + len(blob))
    out = bytes(head) + blob
    parse(out)
    return out


WAVE_STYLES = ("blue", "rgb", "3band")    # 1.4.1 (C77) : réglage « Type de forme d'onde », comme Rekordbox
BAND_RGB = ((0x1F, 0x6F, 0xE5), (0xF0, 0x98, 0x2C), (0xF6, 0xEA, 0xD2))   # basses, médiums, aigus (3 bandes)


def blue_colour(whiteness: int) -> str:
    """Couleur de la forme d'onde « Bleu » de Rekordbox : bleu profond (0) vers bleu très clair (7)."""
    k = max(0, min(7, int(whiteness))) / 7.0
    r = int(0x10 + (0xC8 - 0x10) * k)
    g = int(0x5A + (0xE6 - 0x5A) * k)
    b = int(0xE6 + (0xFF - 0xE6) * k)
    return f"#{r:02X}{g:02X}{b:02X}"


def _bands_colour(low: int, mid: int, high: int) -> str:
    """Une colonne en 3 bandes réduite à une couleur : celle de la bande la plus forte (aperçus étroits)."""
    k = max(range(3), key=lambda i: (low, mid, high)[i])
    return "#%02X%02X%02X" % BAND_RGB[k]


def read_overview(dat: Optional[bytes] = None, ext: Optional[bytes] = None, style: str = "rgb",
                  two_ex: Optional[bytes] = None) -> List[Tuple[float, str]]:
    """Aperçu de forme d'onde pour le lecteur : [(hauteur 0-1, couleur #RRGGBB)].

    1.4.1 (C77) : selon le type choisi, lu dans les fichiers d'analyse comme Rekordbox : « rgb » PWV4 (.EXT),
    « 3band » PWV6 (.2EX), « blue » PWAV (.DAT) ; sinon le premier qui existe."""
    def pwv4() -> List[Tuple[float, str]]:
        try:
            tags = parse(ext) if ext else {}
        except ValueError:
            tags = {}
        if "PWV4" not in tags:
            return []
        b = tags["PWV4"][0][1]
        out = []
        for k in range(len(b) // 6):
            _d0, _d1, low, mid, high, _d5 = b[k * 6:k * 6 + 6]
            h = max(low, mid, high) / 127.0
            tot = (low + mid + high) or 1
            r = int(min(255, 70 + 185 * low / tot)); g = int(min(255, 70 + 185 * mid / tot))
            bl = int(min(255, 70 + 185 * high / tot))
            out.append((min(1.0, h), f"#{r:02X}{g:02X}{bl:02X}"))
        return out

    def pwv6() -> List[Tuple[float, str]]:
        try:
            tags = parse(two_ex) if two_ex else {}
        except ValueError:
            tags = {}
        if "PWV6" not in tags:
            return []
        b = tags["PWV6"][0][1]
        return [(min(1.0, max(b[k * 3:k * 3 + 3]) / 127.0), _bands_colour(*b[k * 3:k * 3 + 3]))
                for k in range(len(b) // 3)]

    def pwav() -> List[Tuple[float, str]]:
        try:
            tags = parse(dat) if dat else {}
        except ValueError:
            tags = {}
        if "PWAV" not in tags:
            return []
        return [((v & 0x1F) / 31.0, blue_colour(v >> 5)) for v in tags["PWAV"][0][1]]

    order = {"rgb": (pwv4, pwv6, pwav), "3band": (pwv6, pwv4, pwav), "blue": (pwav, pwv4, pwv6)}
    for fn in order.get(style, order["rgb"]):
        out = fn()
        if out:
            return out
    return []


def read_band_detail(two_ex: bytes) -> Any:
    """1.3.0-rc.3 (B21) : forme d'onde 3 bandes PWV7 du .2EX (150 colonnes/s, 3 octets : basses, médiums,
    aigus, 0-127), en BandWave, pour l'éditeur de grille quand le fichier audio est introuvable. None si absente."""
    import numpy as np

    from .waveform import BandWave

    tags = parse(two_ex)
    if "PWV7" not in tags:
        return None
    b = tags["PWV7"][0][1]
    n = len(b) // 3
    if not n:
        return None
    a = np.frombuffer(b[: n * 3], dtype=np.uint8).reshape(n, 3)
    return BandWave(rate=150, low=a[:, 0].copy(), mid=a[:, 1].copy(), high=a[:, 2].copy())


def band_from_detail(detail: List[Tuple[float, str]]) -> Any:
    """B21 : dernier recours (ni fichier audio ni .2EX) : la forme d'onde des fichiers d'analyse dessinée
    dans les couleurs 3 bandes (basses pleine hauteur, médiums et aigus en retrait), pas en RGB."""
    import numpy as np

    from .waveform import BandWave

    if not detail:
        return None
    h = np.array([d[0] for d in detail], dtype=np.float64) * 127.0
    return BandWave(rate=150, low=h.astype(np.uint8), mid=(h * 0.75).astype(np.uint8),
                    high=(h * 0.4).astype(np.uint8))


def read_detail(ext: bytes, style: str = "rgb") -> List[Tuple[float, str]]:
    """Forme d'onde détaillée (150 colonnes/s) : « rgb » PWV5 couleur, « blue » PWV3 (hauteur et blancheur,
    1.4.1, C77) ; à défaut l'autre."""
    tags = parse(ext)

    def pwv5() -> List[Tuple[float, str]]:
        if "PWV5" not in tags:
            return []
        b = tags["PWV5"][0][1]
        out = []
        for k in range(len(b) // 2):
            v = struct.unpack(">H", b[k * 2:k * 2 + 2])[0]
            r, g, bl, h = (v >> 13) & 7, (v >> 10) & 7, (v >> 7) & 7, (v >> 2) & 31
            out.append((h / 31.0, f"#{r * 36:02X}{g * 36:02X}{bl * 36:02X}"))
        return out

    def pwv3() -> List[Tuple[float, str]]:
        if "PWV3" not in tags:
            return []
        return [((v & 0x1F) / 31.0, blue_colour(v >> 5)) for v in tags["PWV3"][0][1]]

    for fn in ((pwv3, pwv5) if style == "blue" else (pwv5, pwv3)):
        out = fn()
        if out:
            return out
    return []
