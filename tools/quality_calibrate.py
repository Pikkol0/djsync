"""Check the estimated-quality rules (djsync.analysis.spectrum.classify) on the A05 bench output.

    python tools/quality_calibrate.py bench_out/features.jsonl [--hold ALBUM,ALBUM]

Reads only features.jsonl (hashed ids, spectral features: no title, no audio). Prints the confusion matrix
"true class x estimate" for the albums used to set the thresholds and for the albums kept aside.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from djsync.analysis import spectrum  # noqa: E402

CLASSES = ["lossless", "320", "256", "192", "128"]


def name(kbps: int) -> str:
    return "lossless" if kbps >= spectrum.LOSSLESS else (str(kbps) if kbps else "unknown")


def report(rows: list, title: str) -> str:
    m = {t: collections.Counter() for t in CLASSES}
    for r in rows:
        m[r["truth"]][r["_est"]] += 1
    out = [title, "truth      " + "".join(f"{c:>9}" for c in CLASSES) + "   exact"]
    for t in CLASSES:
        n = sum(m[t].values()) or 1
        out.append(f"{t:<11}" + "".join(f"{m[t][c]:>9}" for c in CLASSES) + f"   {100 * m[t][t] / n:5.1f} %")
    fake = [r for r in rows if r["truth"] != "lossless" and r["variant"].endswith(("_wav", "_flac"))]
    fake2 = [r for r in fake if not r["variant"].startswith("aac_256")]
    true = [r for r in rows if r["truth"] == "lossless"]
    det = sum(r["_est"] != "lossless" for r in fake)
    det2 = sum(r["_est"] != "lossless" for r in fake2)
    out.append(f"fake lossless detected: {det}/{len(fake)} ({100 * det / max(1, len(fake)):.1f} %), "
               f"without AAC 256: {det2}/{len(fake2)} ({100 * det2 / max(1, len(fake2)):.1f} %)")
    out.append(f"true lossless kept: {sum(r['_est'] == 'lossless' for r in true)}/{len(true)}, "
               f"shown 128 or 192: {sum(r['_est'] in ('128', '192') for r in true)}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--hold", default="cfe05474,db31724c", help="album hashes kept aside (verification)")
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in Path(args.features).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("variant") != "_done" and "error" not in r]
    for r in rows:
        r["_est"] = name(spectrum.classify([s for s in r["slices"] if s and "error" not in s])[0])
    hold = set(filter(None, args.hold.split(",")))
    print(report([r for r in rows if r["album"] not in hold], "== thresholds set on"))
    print()
    print(report([r for r in rows if r["album"] in hold], "== kept aside (verification)"))
    print()
    for v in sorted({r["variant"] for r in rows}):
        sub = [r for r in rows if r["variant"] == v]
        c = collections.Counter(r["_est"] for r in sub)
        print(f"{v:22s} {sub[0]['truth']:>9}  " + "  ".join(f"{k}:{c[k]}" for k in CLASSES + ["unknown"] if c[k]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
