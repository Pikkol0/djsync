"""Mise à jour de DJSync.exe en ne téléchargeant que ce qui a changé (1.4.3, C72), sans serveur.

DJSync.exe = lanceur + application zippée (packaging/pack_single_exe.py) + bloc de fin (+ signature). Depuis la
1.4.3, chaque fichier de l'application est rangé dans le zip avec une date fixe : un fichier qui ne change pas
d'une version à l'autre (Qt, numpy, FFmpeg…) donne exactement les mêmes octets. La release publie à côté de
DJSync.exe la liste de ses morceaux, `DJSync.exe.parts.json` (début, longueur, SHA-256 de chaque morceau :
lanceur, chaque fichier du zip, fin du fichier).

L'application en cours lit les morceaux de son propre DJSync.exe, reprend ceux qui n'ont pas changé, et
télécharge les autres directement dans le fichier de la release sur GitHub (requêtes HTTP « Range »). Le fichier
reconstruit est vérifié avec la même empreinte SHA-256 que le téléchargement complet ; au moindre souci (liste
absente, version d'avant la 1.4.3, Range refusé, empreinte fausse), DJSync télécharge le fichier entier comme
avant. Windows seulement (le .dmg macOS et l'archive Linux sont compressés d'un bloc).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import struct
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger("djsync.update")

MAGIC = b"DJSYNCPK"
PARTS_SUFFIX = ".parts.json"
FULL_RATIO = 0.8           # plus de 80 % à télécharger : le fichier entier, plus simple
Part = Tuple[int, int, str]


class _Window(io.RawIOBase):
    """Vue en lecture seule sur [start, start + size) d'un fichier."""

    def __init__(self, fh, start: int, size: int):
        self.fh, self.start, self.size, self.pos = fh, start, size, 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.pos, 2: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def tell(self) -> int:
        return self.pos

    def read(self, n: int = -1) -> bytes:
        n = self.size - self.pos if n is None or n < 0 else min(n, self.size - self.pos)
        if n <= 0:
            return b""
        self.fh.seek(self.start + self.pos)
        data = self.fh.read(n)
        self.pos += len(data)
        return data

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def _trailer(fh, size: int) -> Tuple[int, int]:
    """(début, taille) du zip, d'après le bloc de fin cherché dans les 64 derniers Ko (comme le lanceur)."""
    tail_len = min(size, 65536)
    fh.seek(size - tail_len)
    tail = fh.read(tail_len)
    i = tail.rfind(MAGIC)
    if i < 0 or i + 24 > len(tail):
        raise ValueError("no DJSYNCPK block")
    start, zsize = struct.unpack_from("<QQ", tail, i + 8)
    if start + zsize > size:
        raise ValueError("bad DJSYNCPK block")
    return start, zsize


def _sha(fh, offset: int, length: int) -> str:
    h = hashlib.sha256()
    fh.seek(offset)
    left = length
    while left > 0:
        chunk = fh.read(min(left, 1 << 20))
        if not chunk:
            break
        h.update(chunk)
        left -= len(chunk)
    return h.hexdigest()


def parts_of(exe: Path) -> List[Part]:
    """Morceaux de DJSync.exe : lanceur, chaque fichier du zip (en-tête local + données), puis le reste."""
    size = exe.stat().st_size
    with open(exe, "rb") as fh:
        start, zsize = _trailer(fh, size)
        spans: List[Tuple[int, int]] = []
        with zipfile.ZipFile(_Window(fh, start, zsize)) as zf:
            for info in zf.infolist():
                fh.seek(start + info.header_offset)
                head = fh.read(30)
                if len(head) < 30 or head[:4] != b"PK\x03\x04":
                    raise ValueError("bad local header")
                n, m = struct.unpack_from("<HH", head, 26)
                length = 30 + n + m + info.compress_size + (16 if info.flag_bits & 0x08 else 0)
                spans.append((start + info.header_offset, length))
        spans.sort()
        out: List[Part] = []
        pos = 0
        for off, length in spans:
            if off < pos:
                raise ValueError("overlapping entries")
            if off > pos:
                out.append((pos, off - pos, _sha(fh, pos, off - pos)))
            out.append((off, length, _sha(fh, off, length)))
            pos = off + length
        if pos < size:
            out.append((pos, size - pos, _sha(fh, pos, size - pos)))
    return out


def manifest(exe: Path, version: str = "") -> Dict:
    """Contenu de DJSync.exe.parts.json (écrit par le workflow de build, après la signature)."""
    h = hashlib.sha256()
    with open(exe, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return {"format": 1, "version": version, "size": exe.stat().st_size, "sha256": h.hexdigest(),
            "parts": [list(p) for p in parts_of(exe)]}


def plan(remote: Dict, local: List[Part]) -> Tuple[List[Tuple[str, int, int, int]], int]:
    """Étapes de reconstruction : ("local", début local, longueur, 0) ou ("remote", début distant, longueur, 0),
    les morceaux distants voisins regroupés ; renvoie aussi le nombre d'octets à télécharger."""
    have = {sha: (off, length) for off, length, sha in local}
    steps: List[Tuple[str, int, int, int]] = []
    remote_bytes = 0
    for off, length, sha in remote["parts"]:
        found = have.get(sha)
        if found is not None and found[1] == length:
            steps.append(("local", found[0], length, 0))
            continue
        remote_bytes += length
        if steps and steps[-1][0] == "remote" and steps[-1][1] + steps[-1][2] == off:
            kind, start, ln, _ = steps[-1]
            steps[-1] = (kind, start, ln + length, 0)
        else:
            steps.append(("remote", off, length, 0))
    return steps, remote_bytes


def _range_get(url: str, start: int, length: int) -> bytes:
    import requests

    resp = requests.get(url, timeout=60, headers={"User-Agent": "DJSync", "Range": f"bytes={start}-{start + length - 1}"})
    if resp.status_code != 206 or len(resp.content) != length:
        raise ValueError(f"range not served ({resp.status_code}, {len(resp.content)} of {length} bytes)")
    return resp.content


def _json_get(url: str) -> Dict:
    import requests

    resp = requests.get(url, timeout=30, headers={"User-Agent": "DJSync"})
    resp.raise_for_status()
    return resp.json()


def download(asset_url: str, expected_sha256: str, local_exe: Path, dest_dir: Path,
             progress: Optional[Callable[[int, int], None]] = None, cancelled: Optional[Callable[[], bool]] = None,
             get_json: Callable[[str], Dict] = _json_get,
             get_range: Callable[[str, int, int], bytes] = _range_get) -> Optional[Path]:
    """Reconstruit le nouveau DJSync.exe dans `dest_dir` ; None s'il vaut mieux tout télécharger (rien n'est
    alors laissé sur le disque). Lève l'erreur « cancelled » de selfupdate si l'utilisateur annule."""
    from .selfupdate import UpdateError

    remote = get_json(asset_url + PARTS_SUFFIX)
    if remote.get("format") != 1 or str(remote.get("sha256", "")).lower() != expected_sha256:
        log.info("Delta update: parts list missing or for another file, full download")
        return None
    local = parts_of(local_exe)
    steps, need = plan(remote, local)
    total = int(remote["size"])
    if need > FULL_RATIO * total:
        log.info("Delta update: %.1f of %.1f MB changed, full download", need / 1e6, total / 1e6)
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = asset_url.rsplit("/", 1)[-1] or "DJSync.exe"
    part_file = dest_dir / (name + ".part")
    h = hashlib.sha256()
    done = 0
    try:
        with open(local_exe, "rb") as src, open(part_file, "wb") as out:
            for kind, start, length, _ in steps:
                if cancelled is not None and cancelled():
                    raise UpdateError("cancelled")
                if kind == "local":
                    src.seek(start)
                    left = length
                    while left > 0:
                        chunk = src.read(min(left, 1 << 20))
                        if not chunk:
                            raise ValueError("local file shorter than expected")
                        out.write(chunk)
                        h.update(chunk)
                        left -= len(chunk)
                else:
                    pos = start
                    while pos < start + length:            # par paquets de 8 Mo : progression et annulation
                        if cancelled is not None and cancelled():
                            raise UpdateError("cancelled")
                        n = min(8 << 20, start + length - pos)
                        chunk = get_range(asset_url, pos, n)
                        out.write(chunk)
                        h.update(chunk)
                        pos += n
                        done += n
                        if progress is not None:
                            progress(done, need)
        if h.hexdigest() != expected_sha256:
            raise ValueError("rebuilt file has the wrong SHA-256")
    except UpdateError:
        part_file.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001 - téléchargement complet à la place
        part_file.unlink(missing_ok=True)
        log.warning("Delta update failed (%s), full download", exc)
        return None
    out_path = dest_dir / name
    part_file.replace(out_path)
    log.info("Delta update: %.1f MB downloaded instead of %.1f MB", need / 1e6, total / 1e6)
    return out_path


def write_manifest(exe: Path, version: str, out: Optional[Path] = None) -> Path:
    out = out or exe.with_name(exe.name + PARTS_SUFFIX)
    out.write_text(json.dumps(manifest(exe, version), separators=(",", ":")), "ascii")
    return out


if __name__ == "__main__":     # python -m djsync.core.delta_update out/DJSync.exe 1.4.3
    import sys

    print(write_manifest(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else ""))
