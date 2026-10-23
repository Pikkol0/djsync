"""Onglet « Retours » (1.2.1, C18) : bugs, idées et commentaires envoyés à l'auteur par e-mail.

Un envoi contient plusieurs remarques (type, titre, texte, captures). DJSync les poste en JSON à un
petit script Google Apps Script (tools/feedback/apps_script.gs, installé sur le Gmail de l'auteur
par docs/FEEDBACK_SETUP.fr.md) qui en fait un e-mail avec les captures en pièces jointes : aucune clé
ni mot de passe dans DJSync, aucun compte demandé à l'utilisateur, aucun serveur à entretenir.

Sans adresse de script configurée (`FEEDBACK_URL` vide) ou si l'envoi échoue, DJSync ouvre le
formulaire d'issue GitHub prérempli (texte seulement ; les captures se glissent dans la page).

Vie privée : le journal joint (facultatif) est raccourci et les chemins personnels y sont masqués.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import platform
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# Adresse « /exec » du script Apps Script déployé (voir docs/FEEDBACK_SETUP.fr.md). Peut aussi être
# donnée par la variable d'environnement DJSYNC_FEEDBACK_URL (tests, essais).
FEEDBACK_URL = "https://script.google.com/macros/s/AKfycbyC2ZqvGbCwQVg9XG4E6x4ZixtAIZ_ugvaxahF9zKYDHxatva8e5H-7_ouBHc_0b99L/exec"
ISSUE_URL = "https://github.com/Pikkol0/djsync/issues/new"

KINDS = ("bug", "idea", "comment")
EXTRA_KINDS = ("logs", "crash")    # 1.2.3 : « Envoyer les logs », rapport d'erreur automatique
MAX_ITEMS = 10
MAX_IMAGES = 3                     # par remarque
MAX_IMAGE_SIDE = 1600              # px : captures réduites (≈ 150-300 Ko en JPEG)
MAX_TOTAL_BYTES = 12 * 1024 * 1024
LOG_TAIL_LINES = 300


class FeedbackError(Exception):
    """Envoi impossible (message pour l'utilisateur)."""


@dataclass
class Attachment:
    name: str
    data: bytes                    # JPEG ou PNG, déjà réduit
    mime: str = "image/jpeg"


@dataclass
class Remark:
    kind: str = "bug"
    title: str = ""
    text: str = ""
    images: List[Attachment] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.title.strip() or self.text.strip() or self.images)


def feedback_url() -> str:
    return os.environ.get("DJSYNC_FEEDBACK_URL", "").strip() or FEEDBACK_URL


# ------------------------------------------------------------------------- captures
def shrink_image(data: bytes, name: str = "capture") -> Attachment:
    """Image (PNG, JPEG…) -> JPEG d'au plus MAX_IMAGE_SIDE px de côté ; PNG gardé s'il est plus léger."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise FeedbackError("bad_image") from exc
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    rgb = img.convert("RGB")
    out = io.BytesIO()
    rgb.save(out, "JPEG", quality=82, optimize=True)
    stem = Path(name).stem or "capture"
    return Attachment(f"{stem}.jpg", out.getvalue(), "image/jpeg")


# ------------------------------------------------------------------------ infos jointes
def anonymise(text: str) -> str:
    """Chemins personnels masqués : dossier de l'utilisateur -> « ~ », nom d'utilisateur -> « <user> »."""
    home = str(Path.home())
    out = text.replace(home, "~").replace(home.replace("\\", "/"), "~")
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(user) >= 3:
        out = re.sub(re.escape(user), "<user>", out, flags=re.IGNORECASE)
    return out


def log_tail(folder: Path, lines: int = LOG_TAIL_LINES) -> str:
    path = Path(folder) / "djsync.log"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return anonymise("\n".join(text.splitlines()[-lines:]))


def system_info(version: str, library: str = "") -> Dict[str, str]:
    return {"version": version, "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python": platform.python_version(), "frozen": str(bool(getattr(sys, "frozen", False))),
            "library": library}


# ------------------------------------------------------------------------- envoi
def build_payload(remarks: List[Remark], email: str, info: Dict[str, str], log_text: str, client_id: str,
                  language: str = "en") -> Dict[str, Any]:
    items = [r for r in remarks if not r.empty][:MAX_ITEMS]
    if not items:
        raise FeedbackError("empty")
    total = 0
    out_items = []
    for n, r in enumerate(items, start=1):
        imgs = []
        for k, a in enumerate(r.images[:MAX_IMAGES], start=1):
            total += len(a.data)
            kind = r.kind if r.kind in KINDS else "comment"
            imgs.append({"name": f"{n}-{kind}-capture-{k}{Path(a.name).suffix or '.jpg'}", "mime": a.mime,
                         "data": base64.b64encode(a.data).decode("ascii")})
        out_items.append({"kind": r.kind if r.kind in KINDS else "comment", "title": r.title.strip()[:200],
                          "text": r.text.strip()[:20000], "images": imgs})
    if total > MAX_TOTAL_BYTES:
        raise FeedbackError("too_big")
    return {"client": client_id[:64], "email": email.strip()[:200], "language": language, "info": info,
            "log": log_text[-200_000:], "items": out_items}


def send(payload: Dict[str, Any], url: Optional[str] = None,
         post: Optional[Callable[[str, bytes], Any]] = None) -> None:
    """POST JSON au script ; lève FeedbackError si le script refuse ou ne répond pas."""
    url = url or feedback_url()
    if not url:
        raise FeedbackError("not_configured")
    body = json.dumps(payload).encode("utf-8")
    if post is not None:
        reply = post(url, body)
    else:
        import requests

        resp = requests.post(url, data=body, timeout=60, headers={"Content-Type": "text/plain;charset=utf-8",
                                                                  "User-Agent": "DJSync"})
        resp.raise_for_status()
        reply = resp.text
    try:
        data = json.loads(reply) if isinstance(reply, (str, bytes)) else reply
    except ValueError as exc:
        raise FeedbackError("bad_reply") from exc
    if not isinstance(data, dict) or not data.get("ok"):
        reason = str((data or {}).get("error", "refused")) if isinstance(data, dict) else "refused"
        log.warning("Feedback refused by the script: %s", reason)
        raise FeedbackError("limit" if reason == "limit" else "refused")
    log.info("Feedback sent: %d remark(s)", len(payload.get("items", [])))


def issue_url(remarks: List[Remark], info: Dict[str, str]) -> str:
    """Repli : formulaire d'issue GitHub prérempli (texte seulement, URL raccourcie à ~6 000 caractères)."""
    items = [r for r in remarks if not r.empty]
    first = items[0] if items else Remark()
    kind = {"bug": "Bug", "idea": "Idea", "comment": "Comment"}.get(first.kind, "Feedback")
    title = f"[{kind}] {first.title.strip() or 'DJSync feedback'}"
    parts = []
    for n, r in enumerate(items, start=1):
        label = {"bug": "Bug", "idea": "Idea", "comment": "Comment"}.get(r.kind, "Note")
        parts.append(f"### {n}. [{label}] {r.title.strip()}\n\n{r.text.strip()}\n")
        if r.images:
            parts.append(f"_{len(r.images)} screenshot(s): drag them here._\n")
    parts.append("---\n" + "\n".join(f"- **{k}**: {v}" for k, v in info.items() if v))
    body = "\n".join(parts)[:5500]
    return ISSUE_URL + "?" + urllib.parse.urlencode({"title": title[:200], "body": body})


# ------------------------------------------------------- 1.2.3 : logs de test et rapports d'erreur
MAX_LIBRARY_ZIP = 9 * 1024 * 1024       # fichiers de la clé zippés : au-delà, export.pdb seul
LOGS_TAIL_LINES = 3000


def drive_report(drive_root: Optional[Path]) -> List[str]:
    """Tout ce qui aide à comprendre un problème de clé / de platine, en texte : format de la clé,
    espace, fichiers de PIONEER/rekordbox (taille, date), contrôle d'export.pdb, diagnostic de la base."""
    if drive_root is None:
        return ["No USB drive open."]
    import shutil
    import time

    from ..db.usb import drive_filesystem, filesystem_compat

    root = Path(drive_root)
    fs = drive_filesystem(root)
    lines = [f"Drive root   : {anonymise(str(root))}", f"File system  : {fs or 'unknown'} ({filesystem_compat(fs) or '?'})"]
    try:
        u = shutil.disk_usage(root)
        lines.append(f"Space        : {u.free / 1e9:.1f} GB free of {u.total / 1e9:.1f} GB")
    except OSError:
        pass
    rb = root / "PIONEER" / "rekordbox"
    lines.append("PIONEER/rekordbox:")
    try:
        for f in sorted(rb.iterdir()):
            if f.is_file():
                st = f.stat()
                lines.append(f"  {f.name:28s} {st.st_size:>12d} B  {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}")
    except OSError as exc:
        lines.append(f"  unreadable: {exc}")
    for sub in ("PIONEER/USBANLZ", "Contents", "DJSync_Backups"):
        lines.append(f"{sub:16s}: {'present' if (root / sub).exists() else 'absent'}")
    pdb = rb / "export.pdb"
    if pdb.is_file():
        try:
            from ..db.pdb.check import report

            lines += ["", "export.pdb check:"] + ["  " + x for x in report(pdb)]
        except Exception as exc:  # noqa: BLE001
            lines.append(f"export.pdb check failed: {exc}")
    return lines


def library_zip(drive_root: Optional[Path], limit: int = MAX_LIBRARY_ZIP) -> Optional[Attachment]:
    """PIONEER/rekordbox (exportLibrary.db, export.pdb, exportExt.pdb…) zippé, pour reproduire un
    problème de platine. Si c'est trop gros : export.pdb seul. None si rien à joindre."""
    import zipfile

    if drive_root is None:
        return None
    rb = Path(drive_root) / "PIONEER" / "rekordbox"
    try:
        files = sorted(f for f in rb.iterdir() if f.is_file() and not f.name.endswith(("-wal", "-shm")))
    except OSError:
        return None
    for choice in (files, [f for f in files if f.suffix.lower() == ".pdb"]):
        if not choice:
            continue
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in choice:
                try:
                    z.write(f, f"PIONEER/rekordbox/{f.name}")
                except OSError:
                    pass
        data = buf.getvalue()
        if len(data) <= limit:
            return Attachment("rekordbox-library.zip", data, "application/zip")
    return None


def build_logs_payload(note: str, email: str, info: Dict[str, str], log_text: str, report: List[str],
                       client_id: str, library: Optional[Attachment] = None, language: str = "en") -> Dict[str, Any]:
    """« Envoyer les logs » : journal complet (chemins masqués), rapport de la clé, fichiers de la clé."""
    files = [{"name": "djsync-report.txt", "mime": "text/plain",
              "data": base64.b64encode("\n".join(report).encode("utf-8")).decode("ascii")}]
    if library is not None:
        files.append({"name": library.name, "mime": library.mime, "data": base64.b64encode(library.data).decode("ascii")})
    item = {"kind": "logs", "title": (note.strip().splitlines() or ["Test logs"])[0][:200],
            "text": note.strip()[:20000] + ("\n\n" if note.strip() else "") + "\n".join(report[:60]), "images": files}
    return {"client": client_id[:64], "email": email.strip()[:200], "language": language, "info": info,
            "log": log_text[-900_000:], "items": [item]}


def build_error_payload(title: str, details: str, info: Dict[str, str], log_text: str, report: List[str],
                        client_id: str) -> Dict[str, Any]:
    """Rapport d'erreur automatique : trace (chemins masqués), état de la clé, fin du journal."""
    text = anonymise(details)[:20000] + "\n\n" + "\n".join(report[:40])
    return {"client": client_id[:64], "email": "", "language": "en", "info": info, "log": log_text[-200_000:],
            "items": [{"kind": "crash", "title": anonymise(title)[:200], "text": text, "images": []}]}

