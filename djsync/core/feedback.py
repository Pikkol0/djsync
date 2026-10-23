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
