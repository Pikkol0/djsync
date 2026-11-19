"""Préparer une clé vierge sans Rekordbox (1.4.2, C24).

Le gabarit est l'état exact d'une clé vide préparée par Rekordbox 7.0.5 : exportLibrary.db (SANS son journal
-wal / -shm : la base seule est complète et concorde avec export.pdb), export.pdb, exportExt.pdb et
DEVSETTING.DAT. `djprofile.nxs` (nom de profil) n'est jamais écrit. Le code existant remplit ensuite cette clé
comme n'importe quelle autre (Contents, USBANLZ, Artwork et DJSync_Backups sont créés au premier son).

Garde-fous : rien n'est formaté, supprimé ni modifié ; refus si un dossier PIONEER existe (quel que soit son
contenu), sur le disque système, ou si les platines ne lisent pas le système de fichiers. Les fichiers sont
écrits dans un dossier temporaire à la racine, contrôlés (tailles, empreintes, base rouverte, export.pdb
reconnu), puis le dossier est renommé en PIONEER : une préparation interrompue ne laisse pas de clé à moitié
faite.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import shutil
import zlib
from pathlib import Path
from typing import Callable, Dict, Optional

from .errors import LibraryError
from .usb import UsbDrive, _make_drive, _system_root, drive_filesystem, filesystem_compat

log = logging.getLogger(__name__)

TEMPLATE_ORIGIN = "rekordbox 7.0.5"
TMP_NAME = "PIONEER.djsync-tmp"
DB_NAME = "PIONEER/rekordbox/exportLibrary.db"
PDB_NAME = "PIONEER/rekordbox/export.pdb"
# Ce que contient la base du gabarit (mesuré le 15/11/2026) : sert de contrôle après écriture
DB_TABLES = 22
DB_ROWS = {"color": 8, "menuItem": 27, "category": 22, "sort": 17, "content": 0, "playlist": 0, "property": 1}
NEVER_WRITTEN = ("djprofile.nxs", "exportLibrary.db-wal", "exportLibrary.db-shm")


class PrepareError(LibraryError):
    """Clé non préparée. `reason` : "pioneer_exists" | "system_disk" | "filesystem" | "not_a_drive" |
    "leftover" | "write" | "check" ; `detail` : précision technique (journal, message)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"Drive not prepared ({reason})" + (f": {detail}" if detail else ""))
        self.reason, self.detail = reason, detail


def template_files() -> Dict[str, bytes]:
    """{chemin relatif à la racine de la clé: octets}, empreintes vérifiées. Lève PrepareError("check")."""
    from ._blank_key_data import FILES

    out: Dict[str, bytes] = {}
    for name, entry in FILES.items():
        size, digest, packed = entry[0], entry[1], "".join(entry[2:])
        try:
            raw = zlib.decompress(base64.b64decode(packed))
        except (ValueError, zlib.error) as exc:
            raise PrepareError("check", f"built-in template unreadable ({name}): {exc}") from exc
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise PrepareError("check", f"built-in template damaged ({name})")
        out[name] = raw
    return out


def _has_pioneer(root: Path) -> bool:
    """Un dossier (ou fichier) PIONEER, quelle que soit la casse et quel que soit son contenu."""
    try:
        return any(e.name.lower() == "pioneer" for e in os.scandir(root))
    except OSError:
        return (root / "PIONEER").exists()


def _is_system_disk(root: Path) -> bool:
    """Windows : le lecteur de Windows. macOS / Linux : le volume de « / » ou celui du dossier personnel
    (sur macOS, ce sont deux volumes)."""
    if os.name == "nt":
        drive = (root.drive or str(root)[:2]).rstrip("\\/").upper()
        return drive == _system_root()
    try:
        dev = os.stat(root).st_dev
        return any(dev == os.stat(p).st_dev for p in ("/", str(Path.home())) if os.path.exists(p))
    except OSError:
        return True                                 # dans le doute, on n'écrit pas


def refusal(root: Path, filesystem: Optional[str] = None) -> Optional[PrepareError]:
    """Pourquoi cette clé ne peut pas être préparée (None : elle peut l'être). Lecture seule."""
    root = Path(root)
    if not root.is_dir():
        return PrepareError("not_a_drive", str(root))
    if _is_system_disk(root):
        return PrepareError("system_disk", str(root))
    if _has_pioneer(root):
        return PrepareError("pioneer_exists", str(root))
    fs = drive_filesystem(root) if filesystem is None else filesystem
    if filesystem_compat(fs) == "unsupported":
        return PrepareError("filesystem", fs)
    return None


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:                             # certains lecteurs réseau ou montages : pas bloquant
            log.debug("Ignored error in _write", exc_info=True)  # 1.4.3 (A3-4)


def _clear_leftover(tmp: Path, names: Dict[str, bytes]) -> None:
    """Reste d'une préparation interrompue : retiré seulement s'il ne contient QUE des fichiers du gabarit
    (c'est alors bien le nôtre). Sinon on ne touche à rien et on refuse."""
    allowed = {Path(n).relative_to("PIONEER").as_posix() for n in names}
    dirs = {Path(a).parent.as_posix() for a in allowed} - {"."}
    for p in tmp.rglob("*"):
        rel = p.relative_to(tmp).as_posix()
        if (p.is_dir() and rel in dirs) or (p.is_file() and rel in allowed):
            continue
        raise PrepareError("leftover", str(tmp))
    shutil.rmtree(tmp)


def check_prepared(folder: Path, files: Optional[Dict[str, bytes]] = None) -> None:
    """Contrôle d'un dossier PIONEER (temporaire ou non) fraîchement écrit : base rouverte sans rien y écrire,
    export.pdb reconnu, aucun fichier en trop, puis tailles et empreintes. Lève PrepareError("check")."""
    from sqlcipher3 import dbapi2 as sqlcipher

    from ._key import get_default_key
    from .pdb.check import report

    files = files if files is not None else template_files()
    db = folder / Path(DB_NAME).relative_to("PIONEER")
    try:
        # immutable=1 : SQLite ne crée ni -wal ni -shm et ne touche pas au fichier
        conn = sqlcipher.connect("file:" + db.resolve().as_posix().replace("?", "%3f").replace("#", "%23")
                                 + "?immutable=1", uri=True)
        try:
            conn.execute("PRAGMA key = '%s'" % get_default_key().replace("'", "''"))
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise PrepareError("check", "exportLibrary.db: integrity check failed")
            n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
            if n != DB_TABLES:
                raise PrepareError("check", f"exportLibrary.db: {n} tables instead of {DB_TABLES}")
            for table, rows in DB_ROWS.items():
                got = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                if got != rows:
                    raise PrepareError("check", f"exportLibrary.db: {table} has {got} rows instead of {rows}")
        finally:
            conn.close()
    except sqlcipher.Error as exc:
        raise PrepareError("check", f"exportLibrary.db: {exc}") from exc
    lines = report(folder / Path(PDB_NAME).relative_to("PIONEER"))
    if not lines or not lines[-1].startswith("=> Layout recognised"):
        raise PrepareError("check", "export.pdb: " + (lines[-1] if lines else "unreadable"))
    expected = {Path(n).relative_to("PIONEER").as_posix() for n in files}
    found = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if found != expected:                           # ni journal, ni djprofile.nxs, ni rien d'autre
        raise PrepareError("check", "unexpected files: " + ", ".join(sorted(found ^ expected)))
    for name, raw in files.items():
        p = folder / Path(name).relative_to("PIONEER")
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise PrepareError("check", f"{name}: {exc}") from exc
        if len(data) != len(raw) or hashlib.sha256(data).digest() != hashlib.sha256(raw).digest():
            raise PrepareError("check", f"{name}: written file differs from the template")


def prepare_drive(root: Path, filesystem: Optional[str] = None,
                  before_rename: Optional[Callable[[Path], None]] = None) -> UsbDrive:
    """Pose le gabarit sur une clé vierge et renvoie le lecteur prêt à être ouvert.

    `filesystem` : système de fichiers déjà connu (sinon détecté). `before_rename(dossier temporaire)` : pour les
    tests (interruption). Lève PrepareError ; dans ce cas la clé est telle qu'avant (le dossier temporaire est
    retiré), sauf coupure brutale, où seul le dossier temporaire peut rester (repris à l'essai suivant)."""
    root = Path(root)
    no = refusal(root, filesystem)
    if no is not None:
        raise no
    files = template_files()
    need = sum(len(b) for b in files.values())
    try:
        free = shutil.disk_usage(root).free
    except OSError:
        free = None
    if free is not None and free < need * 2:
        raise PrepareError("write", f"not enough free space ({free} bytes)")
    tmp, final = root / TMP_NAME, root / "PIONEER"
    done = False
    try:
        if tmp.exists():
            _clear_leftover(tmp, files)
        try:
            for name, raw in files.items():
                _write(tmp / Path(name).relative_to("PIONEER"), raw)
        except OSError as exc:
            raise PrepareError("write", str(exc)) from exc
        check_prepared(tmp, files)
        if before_rename is not None:
            before_rename(tmp)
        if _has_pioneer(root):                      # apparu entre-temps (Rekordbox, autre appareil)
            raise PrepareError("pioneer_exists", str(root))
        try:
            os.rename(tmp, final)
        except OSError as exc:
            raise PrepareError("write", str(exc)) from exc
        done = True
    finally:
        if not done and tmp.is_dir():
            try:
                _clear_leftover(tmp, files)
            except (PrepareError, OSError):
                log.warning("Temporary folder left on the drive: %s", tmp)
    log.info("Drive prepared from the built-in template (%s): %s", TEMPLATE_ORIGIN, root)
    return _make_drive(root)
