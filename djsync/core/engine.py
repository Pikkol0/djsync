"""Moteur de téléchargement (yt-dlp) : runtime JavaScript, version de remplacement, mises à jour.

Principe voulu (V0.5.0) : un outil simple qui marche à chaque fois, donc AUCUNE mise à jour
automatique ni vérification au démarrage. yt-dlp n'est mis à jour que :
  * quand une fonction essentielle échoue d'une façon qui ressemble à un yt-dlp périmé (YouTube a
    changé : signature, format introuvable, extraction impossible…) — DJSync propose alors UNE
    fois par session d'installer la nouvelle version ;
  * à la main, dans Réglages > Moteur de téléchargement (rechercher / installer / revenir en arrière).

La nouvelle version est un « wheel » officiel de PyPI (vérifié par son empreinte SHA-256),
décompressé dans `<réglages>/engine/` : l'exe lui-même n'est jamais modifié. Au lancement, ce
dossier passe devant la version embarquée s'il est plus récent. Après une installation, les
modules yt_dlp sont déchargés : le téléchargement suivant utilise la nouvelle version, sans redémarrer.

Runtime JavaScript (requis par YouTube) : Deno ou Node s'ils sont installés sur le PC (rapides),
sinon QuickJS-NG (`qjs.exe`, 2,5 Mo) embarqué à côté de l'exe — au lieu de Deno (≈ 100 Mo).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

PACKAGES = ("yt-dlp", "yt-dlp-ejs")           # distributions PyPI installées ensemble
MODULES = ("yt_dlp", "yt_dlp_ejs")
PYPI = "https://pypi.org/pypi/{name}/json"

_lock = threading.Lock()


# ------------------------------------------------------------------------------- versions
def parse_version(text: str) -> Tuple[int, ...]:
    """« 2026.08.19 », « 2026.8.19.1 » -> (2026, 8, 19[, 1]) ; texte inconnu -> ()."""
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts[:4])


def engine_dir() -> Path:
    from ..settings import settings_dir

    return settings_dir() / "engine"


def _installed_info(folder: Path) -> Dict[str, str]:
    try:
        return json.loads((folder / "engine.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bundled_version() -> str:
    """Version embarquée (métadonnées du paquet : rien n'est importé)."""
    try:
        from importlib.metadata import version

        return version("yt-dlp")
    except Exception:  # noqa: BLE001
        return ""


def override_version(folder: Optional[Path] = None) -> str:
    return _installed_info(folder or engine_dir()).get("yt-dlp", "")


def activate(folder: Optional[Path] = None) -> bool:
    """À appeler AVANT tout import de yt_dlp : la version téléchargée passe devant si plus récente."""
    folder = folder or engine_dir()
    over = override_version(folder)
    if not over or not (folder / "yt_dlp" / "__init__.py").is_file():
        return False
    if parse_version(over) <= parse_version(bundled_version()):
        return False                                  # l'exe a été mis à jour depuis : version embarquée
    path = str(folder)
    if path not in sys.path:
        sys.path.insert(0, path)
    return True


def running_version() -> str:
    """Version effectivement utilisée (importe yt_dlp)."""
    try:
        from yt_dlp.version import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return ""


def _unload() -> None:
    for name in list(sys.modules):
        if name.split(".")[0] in MODULES:
            del sys.modules[name]


# ------------------------------------------------------------------------ JS runtime
def _which(names: List[str], extra: List[Path]) -> Optional[str]:
    for base in extra:
        for n in names:
            cand = base / n
            if cand.is_file():
                return str(cand)
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return None


def js_runtimes() -> Dict[str, Dict[str, str]]:
    """Runtimes JavaScript pour yt-dlp, du plus rapide au plus léger (le premier disponible sert)."""
    from ..portable import tool_dirs

    extra = tool_dirs()
    found: Dict[str, Dict[str, str]] = {}
    for key, names in (("deno", ["deno.exe", "deno"]), ("node", ["node.exe", "node"]),
                       ("quickjs", ["qjs.exe", "qjs", "quickjs.exe", "quickjs"])):
        path = _which(names, extra)
        if path:
            found[key] = {"path": path}
    return found or {"deno": {}}


def ydl_options(**extra) -> dict:
    """Options communes à tous les appels yt-dlp de DJSync."""
    opts = {"js_runtimes": js_runtimes()}
    opts.update(extra)
    return opts


# ---------------------------------------------------------------- détection d'échec
_NETWORK = ("unable to connect", "timed out", "getaddrinfo", "network is unreachable", "connection reset",
            "temporary failure in name resolution", "no route to host", "proxy", "ssl", "connection refused",
            "remote end closed", "nodename nor servname")
_CONTENT = ("private video", "video unavailable", "has been removed", "not available in your country",
            "members-only", "age-restricted", "confirm your age", "copyright", "this video is no longer", "premiere", "live event",
            "no such file", "permission denied", "disk", "no space")
_ENGINE = ("signature", "nsig", "n challenge", "jsc", "javascript", "unable to extract", "requested format is not available",
           "format is not available", "only images are available", "http error 403", "unable to download api page",
           "player response", "precondition", "no video formats", "unsupported url",
           "please report this issue", "confirm you are on the latest version", "keyerror", "attributeerror",
           "regexnotfound", "extractor error")


def looks_outdated(message: str) -> bool:
    """L'erreur ressemble-t-elle à un yt-dlp périmé (et non au réseau ou à une vidéo privée) ?"""
    text = (message or "").lower()
    if any(k in text for k in _NETWORK):
        return False
    if any(k in text for k in _CONTENT) or "not a bot" in text:
        return False
    return any(k in text for k in _ENGINE)


# --------------------------------------------------------------------- mises à jour
@dataclass
class Release:
    version: str
    files: Dict[str, Tuple[str, str]]          # distribution -> (url du wheel, sha256)

    def newer_than(self, current: str) -> bool:
        return parse_version(self.version) > parse_version(current)


Fetcher = Callable[[str], bytes]


def _http_get(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=30, headers={"User-Agent": "DJSync"})
    resp.raise_for_status()
    return resp.content


def latest(fetch: Optional[Fetcher] = None) -> Release:
    """Dernière version publiée sur PyPI (yt-dlp + son composant JavaScript yt-dlp-ejs)."""
    fetch = fetch or _http_get
    files: Dict[str, Tuple[str, str]] = {}
    version = ""
    for name in PACKAGES:
        data = json.loads(fetch(PYPI.format(name=name)))
        wheel = next((u for u in data.get("urls", []) if u.get("packagetype") == "bdist_wheel"), None)
        if wheel is None:
            raise RuntimeError(f"No wheel published for {name}")
        files[name] = (wheel["url"], wheel["digests"]["sha256"])
        if name == "yt-dlp":
            version = data["info"]["version"]
    return Release(version, files)


def current_version() -> str:
    """Version qui sera utilisée par le prochain téléchargement."""
    over = override_version()
    if over and parse_version(over) > parse_version(bundled_version()):
        return over
    return running_version() or bundled_version()


def install(release: Release, fetch: Optional[Fetcher] = None, folder: Optional[Path] = None,
            on_progress: Optional[Callable[[str], None]] = None) -> str:
    """Télécharge, vérifie et installe la version ; l'ancienne est gardée (retour arrière)."""
    fetch = fetch or _http_get
    folder = folder or engine_dir()
    notify = on_progress or (lambda _m: None)
    with _lock:
        staging = folder.with_name(folder.name + ".new")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        try:
            for name, (url, sha) in release.files.items():
                notify(name)
                blob = fetch(url)
                if hashlib.sha256(blob).hexdigest() != sha:
                    raise RuntimeError(f"Checksum mismatch for {name}: download refused")
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    for member in zf.namelist():
                        top = member.split("/")[0]
                        if top.split(".")[0] in MODULES and ".." not in Path(member).parts:
                            zf.extract(member, staging)
            if not (staging / "yt_dlp" / "__init__.py").is_file():
                raise RuntimeError("Unexpected package content")
            info = {"yt-dlp": release.version}
            (staging / "engine.json").write_text(json.dumps(info), encoding="utf-8")
            previous = folder.with_name(folder.name + ".prev")
            if folder.exists():
                shutil.rmtree(previous, ignore_errors=True)
                os.replace(folder, previous)
            os.replace(staging, folder)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        _reload(folder)
    log.info("yt-dlp %s installed in %s", release.version, folder)
    return release.version


def rollback(folder: Optional[Path] = None) -> str:
    """Revient à la version précédente (ou à la version embarquée s'il n'y en a pas)."""
    folder = folder or engine_dir()
    with _lock:
        previous = folder.with_name(folder.name + ".prev")
        broken = folder.with_name(folder.name + ".old")
        shutil.rmtree(broken, ignore_errors=True)
        if folder.exists():
            os.replace(folder, broken)
        if previous.exists():
            os.replace(previous, folder)
        shutil.rmtree(broken, ignore_errors=True)
        _reload(folder)
    return current_version()


def _reload(folder: Path) -> None:
    path = str(folder)
    while path in sys.path:
        sys.path.remove(path)
    _unload()
    activate(folder)
