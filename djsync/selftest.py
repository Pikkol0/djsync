"""Autotest de l'exécutable (CI et dépannage) : `DJSYNC_SELFTEST=<fichier.json> DJSync.exe`.

L'exe Windows n'a pas de console : le résultat est écrit en JSON dans le fichier indiqué, et le
code de sortie vaut 0 si tout va bien. Vérifie que chaque dépendance s'importe depuis l'archive
de l'exe (yt-dlp et ses extracteurs YouTube / SoundCloud compris) et que les outils embarqués
(FFmpeg, runtime JavaScript) sont trouvés.
"""
from __future__ import annotations

import logging
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict

log = logging.getLogger(__name__)

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
            log.debug("Handled error in check", exc_info=True)  # 1.4.3 (A3-4)
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

    def fuzzy() -> str:
        """1.4.3-rc.3 (B126) : rapidfuzz avec sa partie compilée (en Python pur, les doublons gèlent l'app)."""
        from .core.duplicates import fuzzy_backend

        backend = fuzzy_backend()
        if backend != "compiled":
            raise RuntimeError(f"rapidfuzz runs its pure-Python fallback ({backend})")
        return backend

    check("rapidfuzz_compiled", fuzzy)

    def icons() -> Dict[str, Any]:
        """1.4.0-rc.6 (C160) : toutes les icônes dessinées se dessinent dans le build (dont l'œil « watch »)."""
        from .ui.icons import DRAW, pil_icon

        empty = [name for name in DRAW if pil_icon(name, 32, "#ffffff").getbbox() is None]
        if empty or "watch" not in DRAW:
            raise RuntimeError(f"icons not drawn: {empty or ['watch']}")
        return {"count": len(DRAW)}

    check("icons", icons)

    def analysis_processes() -> Dict[str, Any]:
        """1.4.3 (A1-6) : l'analyse tourne dans 2 processus séparés depuis l'exe (multiprocessing figé) et
        donne le même résultat que dans le fil (formes d'onde calculées comme Rekordbox, A7-3)."""
        import os
        import tempfile
        import wave

        import numpy as np

        from .analysis import analyze_file, pool

        with tempfile.TemporaryDirectory() as d:
            files = []
            t = np.arange(44100 * 6) / 44100.0
            x = (0.6 * np.sin(2 * np.pi * 55 * t) * np.exp(-10 * (t % 0.5)) * 32767).astype("<i2")
            for i in range(2):
                f = Path(d) / f"s{i}.wav"
                with wave.open(str(f), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(44100)
                    w.writeframes(x.tobytes())
                files.append(f)
            local = [analyze_file(f) for f in files]
            old = os.environ.get("DJSYNC_ANALYSIS_WORKERS")
            os.environ["DJSYNC_ANALYSIS_WORKERS"] = "2"
            try:
                with pool.prefetching(files, None) as pre:
                    if pre is None:
                        raise RuntimeError("analysis processes unavailable")
                    got = []
                    for i, f in enumerate(files):
                        pre.advance(i)
                        ready = pre.take(f, None)
                        if ready is None:
                            raise RuntimeError("no result from the analysis processes")
                        got.append(ready)
            finally:
                pool.shutdown()
                if old is None:
                    os.environ.pop("DJSYNC_ANALYSIS_WORKERS", None)
                else:
                    os.environ["DJSYNC_ANALYSIS_WORKERS"] = old
            if any(a.waveforms != b.waveforms or a.bpmx100 != b.bpmx100 for a, b in zip(local, got)):
                raise RuntimeError("results differ between processes and thread")
            return {"processes": 2, "bpm": got[0].bpm}

    check("analysis_processes", analysis_processes)
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
