"""C230 (1.4.4) : chiffres d'un build écrits par le build lui-même, sans API côté lecteur.

Appelé à la fin du workflow Build (job « release » pour Windows + Linux, job « macos » pour le .dmg) :

    python packaging/build_metrics_record.py <tag> <dossier des fichiers publiés> [--started <ISO>] [--result ok|ko]

Écrit ou complète `metrics/<tag>.json` sur la branche `metrics` du dépôt (clés fusionnées : le job macOS
ajoute `dmg_mb` sans effacer ce que le job release a écrit). Lecture ensuite par simple git :

    git fetch origin metrics && git show origin/metrics:metrics/v1.4.4-rc.1.json

Champs : tag, at (fin), build_min (début du run → fin du job qui écrit), build_ok, exe_mb, linux_mb, dmg_mb.
Aucun changement dans l'application.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

KINDS = (("exe", lambda n: n == "DJSync.exe" or n.endswith("windows.zip")),
         ("dmg", lambda n: n.endswith(".dmg")),
         ("linux", lambda n: n.endswith(".tar.gz")))


def sizes(folder: Path) -> dict:
    """Taille en Mo (1 décimale) de chaque fichier publié reconnu (exe, dmg, tar.gz)."""
    out = {}
    for f in sorted(folder.iterdir()) if folder.is_dir() else []:
        for kind, test in KINDS:
            if f.is_file() and test(f.name):
                out[f"{kind}_mb"] = round(f.stat().st_size / 1e6, 1)
    return out


def record(tag: str, folder: Path, started: str = "", result: str = "", now: datetime | None = None) -> dict:
    """Champs à fusionner dans metrics/<tag>.json."""
    now = now or datetime.now(timezone.utc)
    m = {"tag": tag, "at": now.isoformat(timespec="seconds"), **sizes(folder)}
    if started:
        t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        m["build_min"] = round((now - t0).total_seconds() / 60, 1)
    if result in ("ok", "ko"):
        m["build_ok"] = result == "ok"
    return m


def merge(old: dict, new: dict) -> dict:
    """Ancien contenu complété ; `build_min` gardé s'il existe déjà (le job release passe avant macOS)."""
    out = dict(old)
    for k, v in new.items():
        if k == "build_min" and "build_min" in old:
            continue
        out[k] = v
    return out


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def push(tag: str, fields: dict, remote: str = "origin", tries: int = 5) -> None:
    """Clone léger de la branche `metrics` (créée si absente), fusion, commit, push ; réessaie si un autre
    job a poussé entre-temps."""
    for attempt in range(tries):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            url = _git(Path("."), "remote", "get-url", remote).stdout.strip()
            _git(repo, "init", "-q")
            _git(repo, "remote", "add", "origin", url)
            # même identifiant que le checkout (actions/checkout garde le jeton dans la config locale)
            for key in ("http.https://github.com/.extraheader",):
                val = _git(Path("."), "config", "--get", key, check=False).stdout.strip()
                if val:
                    _git(repo, "config", key, val)
            _git(repo, "config", "user.name", "github-actions[bot]")
            _git(repo, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
            exists = _git(repo, "fetch", "-q", "--depth", "1", "origin", "metrics", check=False).returncode == 0
            if exists:
                _git(repo, "checkout", "-q", "-b", "metrics", "FETCH_HEAD")
            else:
                _git(repo, "checkout", "-q", "--orphan", "metrics")
            f = repo / "metrics" / f"{tag}.json"
            old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            f.parent.mkdir(exist_ok=True)
            f.write_text(json.dumps(merge(old, fields), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            _git(repo, "add", str(f.relative_to(repo)))
            _git(repo, "commit", "-q", "-m", f"metrics: {tag}")
            if _git(repo, "push", "-q", "origin", "HEAD:metrics", check=False).returncode == 0:
                print(f"metrics/{tag}.json: {json.dumps(merge(old, fields), ensure_ascii=False)}")
                return
        time.sleep(5 * (attempt + 1))
    print("::warning title=metrics::branch metrics not updated", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("folder")
    ap.add_argument("--started", default="")
    ap.add_argument("--result", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    fields = record(a.tag, Path(a.folder), a.started, a.result)
    if a.dry_run:
        print(json.dumps(fields, ensure_ascii=False))
        return 0
    try:
        push(a.tag, fields)
    except Exception as exc:  # noqa: BLE001 — never fail the release for a dashboard figure
        print(f"::warning title=metrics::{exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
