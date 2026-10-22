"""Nouvelle version de DJSync ? (V1.2.0) — releases GitHub du dépôt.

Au démarrage (au plus une fois par jour, désactivable dans les Réglages), DJSync lit la liste des
releases publiées et propose la plus récente si elle est plus récente que la sienne. Une version de
test (« 1.1.0-rc.1 ») se voit aussi proposer les pré-versions ; une version stable, seulement les
versions stables. Rien n'est téléchargé tout seul : le bouton ouvre la page de la release.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

REPO = "Pikkol0/djsync"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
PAGE = f"https://github.com/{REPO}/releases/latest"

Fetcher = Callable[[str], bytes]
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([a-z]+)\.?(\d+)?)?$", re.I)


@dataclass(frozen=True)
class Update:
    version: str
    url: str                      # page de la release (notes + fichiers)
    prerelease: bool
    asset: str = ""               # lien direct du fichier pour ce système ("" si absent)


def parse_version(text: str) -> Optional[Tuple[int, int, int, int, int]]:
    """'1.1.0' > '1.1.0-rc.2' > '1.1.0-rc.1' > '1.0.9'. None si illisible (ex. '-dev.abc1234')."""
    m = _VERSION.match((text or "").strip())
    if not m:
        return None
    major, minor, patch, tag, num = m.groups()
    final = 1 if tag is None else 0
    return int(major), int(minor), int(patch), final, int(num or 0)


def asset_name() -> str:
    """Nom du fichier à télécharger pour ce système (cf. .github/workflows/windows.yml)."""
    if sys.platform == "win32":
        return "DJSync.exe"
    if sys.platform == "darwin":
        return "DJSync-macOS.dmg"
    return "DJSync-Linux-x86_64.tar.gz"


def _http_get(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=20, headers={"User-Agent": "DJSync",
                                                  "Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    return resp.content


def check(current: str, fetch: Optional[Fetcher] = None,
          include_prerelease: Optional[bool] = None) -> Optional[Update]:
    """Release plus récente que `current`, ou None. Réseau : hors thread UI."""
    mine = parse_version(current.split("-dev")[0] if "-dev" in current else current)
    if mine is None:
        return None
    if include_prerelease is None:
        include_prerelease = mine[3] == 0
    releases: List[dict] = json.loads((fetch or _http_get)(API).decode("utf-8"))
    best: Optional[Tuple[Tuple[int, ...], dict]] = None
    for rel in releases:
        if rel.get("draft") or (rel.get("prerelease") and not include_prerelease):
            continue
        v = parse_version(str(rel.get("tag_name") or ""))
        if v is None or v <= mine:
            continue
        if best is None or v > best[0]:
            best = (v, rel)
    if best is None:
        return None
    rel = best[1]
    wanted = asset_name()
    asset = next((a.get("browser_download_url", "") for a in rel.get("assets") or [] if a.get("name") == wanted), "")
    return Update(str(rel["tag_name"]).lstrip("v"), str(rel.get("html_url") or PAGE), bool(rel.get("prerelease")), asset)
