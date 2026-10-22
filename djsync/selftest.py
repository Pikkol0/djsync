"""Autotest de l'exécutable (CI et dépannage) : `DJSYNC_SELFTEST=<fichier.json> DJSync.exe`.

L'exe Windows n'a pas de console : le résultat est écrit en JSON dans le fichier indiqué, et le
code de sortie vaut 0 si tout va bien. Vérifie que chaque dépendance s'importe depuis l'archive
de l'exe (yt-dlp et ses extracteurs YouTube / SoundCloud compris) et que les outils embarqués
(FFmpeg, runtime JavaScript) sont trouvés.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict

MODULES = ("PySide6.QtWidgets", "numpy", "PIL", "mutagen", "miniaudio", "sqlcipher3", "pyrekordbox",
           "ytmusicapi", "requests", "rapidfuzz", "psutil")


def _ytdlp() -> Dict[str, Any]:
    import yt_dlp
    from yt_dlp.extractor import gen_extractor_classes, get_info_extractor

    for name in ("Youtube", "YoutubeTab", "Soundcloud", "SoundcloudPlaylist", "Generic"):
        get_info_extractor(name)
    info: Dict[str, Any] = {"version": yt_dlp.version.__version__,
                            "extractors": sum(1 for _ in gen_extractor_classes())}
    try:
        import yt_dlp_ejs  # noqa: F401

        info["ejs"] = True
    except ImportError:
        info["ejs"] = False
    return info


def run(target: str) -> int:
    from . import full_version, portable

    portable.prepare_environment(hide=False)      # l'autotest ne touche à rien (CI : zip fait ensuite)
    report: Dict[str, Any] = {"djsync": full_version(), "frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    ok = True

    def check(name: str, fn: Callable[[], Any]) -> None:
        nonlocal ok
        try:
            report["checks"][name] = {"ok": True, "value": fn()}
        except Exception as exc:  # noqa: BLE001 - tout est consigné dans le rapport
            ok = False
            report["checks"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                                      "trace": traceback.format_exc()[-1500:]}

    for mod in MODULES:
        check(mod, lambda m=mod: __import__(m) and "imported")
    check("yt_dlp", _ytdlp)

    def tools() -> Dict[str, Any]:
        from .analysis.decode import find_ffmpeg
        from .core.engine import js_runtimes

        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")
        return {"ffmpeg": ffmpeg, "js": js_runtimes()}

    check("tools", tools)
    if sys.platform == "darwin":                  # sortie de la « translocation » (premier lancement)
        def mac_translocation() -> str:
            import ctypes
            import ctypes.util

            sec = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Security"))
            getattr(sec, "SecTranslocateCreateOriginalPathForURL")
            getattr(sec, "SecTranslocateIsTranslocatedURL")
            return "available"

        check("mac_translocation", mac_translocation)
    report["ok"] = ok
    Path(target).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if ok else 1
