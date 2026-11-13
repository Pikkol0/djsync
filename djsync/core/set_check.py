"""« Prêt pour le set ? » (1.4.2, C67, fusion de C106) : la clé contrôlée en un clic avant de partir jouer.

Une liste verte / orange / rouge, calculée hors du fil de l'interface et en lecture seule : rien n'est modifié ici.
Chaque ligne orange ou rouge porte une action (`Check.action`) que l'interface propose en bouton.

Le matériel visé (réglage `set_players`) adapte les contrôles aux limites connues des platines (players.py) :
  * « recent » : CDJ-3000, OPUS-QUAD, XDJ-AZ, XDJ-RX3… : FLAC, exFAT, haute fréquence ;
  * « nxs2 » : CDJ-2000NXS2, XDJ-1000MK2, XDJ-XZ, XDJ-RX2… : FLAC, mais pas d'exFAT ;
  * « old » : CDJ-2000NXS, CDJ-900NXS, XDJ-1000, XDJ-700 et plus anciennes : ni FLAC, ni plus de 48 kHz, ni exFAT ;
  * « all » (je ne sais pas) : les limites les plus strictes, pour que la clé passe partout.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..i18n import plural, t

PLAYERS = ("all", "recent", "nxs2", "old")
LIMITS: Dict[str, Dict[str, Any]] = {
    "recent": {"flac": True, "exfat": True, "max_rate": 0},
    "nxs2": {"flac": True, "exfat": False, "max_rate": 0},
    "old": {"flac": False, "exfat": False, "max_rate": 48000},
    "all": {"flac": False, "exfat": False, "max_rate": 48000},
}
LOW_SPACE = 0.05                      # moins de 5 % libres : orange
BACKUP_OLD_DAYS = 30                  # dernière sauvegarde de plus d'un mois : orange
LEVELS = ("ok", "warn", "error", "skip")


@dataclass
class Check:
    key: str
    level: str                        # ok, warn, error, skip
    text: str
    action: str = ""                  # analyse, pdb, missing, convert, space, backup, no_cue, empty_playlists
    ids: List[int] = field(default_factory=list)

    @property
    def mark(self) -> str:
        return {"ok": "✓", "warn": "!", "error": "✕", "skip": "–"}.get(self.level, "•")


def limits(players: str) -> Dict[str, Any]:
    return LIMITS.get(players, LIMITS["all"])


def _exists(lib: Any, track: Any) -> bool:
    try:
        return lib.absolute_path(track).is_file()
    except (OSError, ValueError):
        return False


def check_filesystem(fs: str, players: str) -> Check:
    from ..db.usb import filesystem_compat

    compat = filesystem_compat(fs)
    if not compat:
        return Check("fs", "skip", t("set.fs_unknown"))
    if compat == "ok":
        return Check("fs", "ok", t("set.fs_ok", fs=fs))
    if compat == "recent_only":
        if limits(players)["exfat"]:
            return Check("fs", "ok", t("set.fs_ok", fs=fs))
        return Check("fs", "error", t("set.fs_recent_only", fs=fs))
    return Check("fs", "error", t("set.fs_unsupported", fs=fs))


def check_pdb(status: Any) -> Check:
    state = getattr(status, "state", "") if status is not None else ""
    if state == "ok":
        return Check("pdb", "ok", t("set.pdb_ok", n=getattr(status, "pdb_tracks", 0)))
    if state == "stale":
        return Check("pdb", "warn", t("set.pdb_stale", detail=getattr(status, "detail", "") or "?"), action="pdb")
    if state == "absent":
        return Check("pdb", "warn", t("set.pdb_absent"))
    if state == "off":
        return Check("pdb", "warn", t("set.pdb_off"))
    if state == "unsupported":
        return Check("pdb", "error", t("set.pdb_unreadable", detail=getattr(status, "detail", "") or "?"))
    return Check("pdb", "skip", t("set.pdb_unknown"))


def check_tracks(lib: Any, tracks: Sequence[Any], players: str, marks: Optional[Dict[int, Any]] = None) -> List[Check]:
    """Fichiers présents, sons analysés, formats lus par le matériel visé, sons sans cue."""
    out: List[Check] = []
    missing = [x.content_id for x in tracks if not _exists(lib, x)]
    if missing:
        out.append(Check("files", "error", plural("set.files_missing_one", "set.files_missing_many", len(missing)),
                         action="missing", ids=missing))
    else:
        out.append(Check("files", "ok", t("set.files_ok", n=len(tracks))))
    todo = [x.content_id for x in tracks if not x.is_analysed and x.content_id not in set(missing)]
    if todo:
        out.append(Check("analysis", "warn", plural("set.unanalysed_one", "set.unanalysed_many", len(todo)),
                         action="analyse", ids=todo))
    else:
        out.append(Check("analysis", "ok", t("set.analysed_ok")))
    lim = limits(players)
    bad: List[int] = []
    if not lim["flac"]:
        bad += [x.content_id for x in tracks if Path(x.path or "").suffix.lower() == ".flac"]
    if lim["max_rate"]:
        bad += [x.content_id for x in tracks if (x.sample_rate or 0) > lim["max_rate"]
                and x.content_id not in bad]
    if bad:
        out.append(Check("formats", "error", plural("set.formats_bad_one", "set.formats_bad_many", len(bad)),
                         action="convert", ids=bad))
    else:
        out.append(Check("formats", "ok", t("set.formats_ok")))
    if marks is not None:
        bare = [x.content_id for x in tracks if marks.get(x.content_id) is None or marks[x.content_id].empty]
        if bare:
            out.append(Check("cues", "warn", plural("set.no_cue_one", "set.no_cue_many", len(bare)),
                             action="no_cue", ids=bare))
        else:
            out.append(Check("cues", "ok", t("set.cues_ok")))
    return out


def check_playlists(playlists: Sequence[Any]) -> Check:
    lists = [p for p in playlists if not p.is_folder]
    empty = [p for p in lists if p.is_editable and not p.track_count]
    if not lists:
        return Check("playlists", "warn", t("set.no_playlist"))
    if empty:
        names = ", ".join(p.name for p in empty[:4]) + (" …" if len(empty) > 4 else "")
        return Check("playlists", "warn", plural("set.empty_playlists_one", "set.empty_playlists_many", len(empty))
                     + f" ({names})", action="empty_playlists", ids=[p.playlist_id for p in empty])
    return Check("playlists", "ok", t("set.playlists_ok", n=len(lists)))


def _hs(n: float) -> str:
    """Taille lisible (comme ui.views.common.human_size, sans dépendre de l'interface)."""
    from ..i18n import get_language

    fr = get_language() == "fr"
    units = ("o", "Ko", "Mo", "Go", "To") if fr else ("B", "KB", "MB", "GB", "TB")
    for i, unit in enumerate(units):
        if n < 1024 or i == len(units) - 1:
            text = f"{n:.0f}" if i < 2 else f"{n:.1f}"
            return f"{text.replace('.', ',') if fr else text} {unit}"
        n /= 1024
    return str(n)


def check_space(root: Path) -> Check:
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return Check("space", "skip", t("set.space_unknown"))
    low = usage.total and usage.free < usage.total * LOW_SPACE
    return Check("space", "warn" if low else "ok", t("set.space", free=_hs(usage.free), total=_hs(usage.total)),
                 action="space" if low else "")


def check_backup(points: Sequence[Any], now: Optional[datetime] = None) -> Check:
    now = now or datetime.now()
    if not points:
        return Check("backup", "warn", t("set.backup_none"), action="backup")
    last = max(p.created for p in points)
    days = max(0, (now - last).days)
    when = last.strftime("%d/%m/%Y")
    if days > BACKUP_OLD_DAYS:
        return Check("backup", "warn", t("set.backup_old", date=when, days=days), action="backup")
    return Check("backup", "ok", t("set.backup_ok", date=when))


def run(lib: Any, filesystem: str, players: str, should_stop: Optional[Callable[[], bool]] = None) -> List[Check]:
    """Tous les contrôles d'une clé ouverte, dans l'ordre d'affichage (lecture seule, hors du fil de l'interface)."""
    from ..db import backups
    from .cue_marks import read_marks

    checks: List[Check] = [check_filesystem(filesystem, players)]
    try:
        status = lib.pdb_status()
    except Exception as exc:  # noqa: BLE001 - export.pdb illisible : une ligne rouge, pas une erreur
        status = type("S", (), {"state": "unsupported", "detail": str(exc)})()
    checks.append(check_pdb(status))
    tracks = lib.list_tracks()
    try:
        marks = read_marks(lib, tracks, should_stop=should_stop)
    except Exception:  # noqa: BLE001
        marks = None
    checks += check_tracks(lib, tracks, players, marks)
    checks.append(check_playlists(lib.list_playlists()))
    checks.append(check_space(lib.drive.root))
    try:
        points = backups.list_points(lib.backup_dir)
    except Exception:  # noqa: BLE001
        points = []
    checks.append(check_backup(points))
    return checks


def verdict(checks: Sequence[Check]) -> str:
    levels = {c.level for c in checks}
    return "error" if "error" in levels else "warn" if "warn" in levels else "ok"


def report(checks: Sequence[Check], drive_name: str, players: str, when: Optional[datetime] = None) -> str:
    """Rapport court, en texte, à garder (ex-C106)."""
    when = when or datetime.now()
    lines = [t("set.report_title", drive=drive_name, date=when.strftime("%d/%m/%Y %H:%M")),
             t("set.report_players", players=t(f"set.players_{players}")),
             t(f"set.verdict_{verdict(checks)}"), ""]
    lines += [f"{c.mark} {t(f'set.row_{c.key}')} : {c.text}" for c in checks]
    return "\n".join(lines) + "\n"
