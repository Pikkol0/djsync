"""CI: turns pytest's JUnit report into GitHub annotations (readable in the run summary and through
the API, without opening the raw logs).

    python -m pytest --junitxml=pytest.xml ...
    python packaging/ci_annotate.py pytest.xml

One annotation lists every failing test, then one per failure (GitHub keeps 10 per step) with the
end of its traceback.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def _prop(text: str) -> str:
    return _escape(text).replace(":", "%3A").replace(",", "%2C")


def slowest(root: ET.Element, n: int = 30) -> None:
    """C91 : durées par fichier et tests les plus lents, en annotation (lisible par l'API) et dans le
    résumé du job (GITHUB_STEP_SUMMARY)."""
    import os
    from collections import defaultdict

    cases = [(float(c.get("time") or 0), f"{c.get('classname', '')}::{c.get('name', '')}") for c in root.iter("testcase")]
    if not cases:
        return
    files = defaultdict(float)
    for t, name in cases:
        files[name.split("::")[0]] += t
    top = sorted(cases, reverse=True)[:n]
    top_files = sorted(((t, f) for f, t in files.items()), reverse=True)[:20]
    total = sum(t for t, _ in cases)
    lines = [f"total {total:.0f} s for {len(cases)} tests"] + [f"{t:6.1f} s  {f}" for t, f in top_files]
    print(f"::notice title=pytest slowest files::{_escape(chr(10).join(lines))}")
    print(f"::notice title=pytest slowest tests::{_escape(chr(10).join(f'{t:6.1f} s  {name}' for t, name in top))}")
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"### Test durations ({len(cases)} tests, {total:.0f} s)\n\n| s | file |\n|---:|---|\n")
            f.writelines(f"| {t:.1f} | {name} |\n" for t, name in top_files)
            f.write("\n| s | test |\n|---:|---|\n")
            f.writelines(f"| {t:.1f} | {name} |\n" for t, name in top)


def main(path: str, durations: bool = False) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"::error title=pytest::No test report ({exc})")
        return 1
    if durations:
        slowest(root)
    failures = []
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None:
                name = f"{case.get('classname', '')}::{case.get('name', '')}"
                detail = (node.text or node.get("message") or "").strip().splitlines()
                failures.append((name, kind, detail))
    total = sum(int(s.get("tests", 0)) for s in root.iter("testsuite"))
    if not failures:
        print(f"::notice title=pytest::{total} tests, all passed")
        return 0
    summary = "\n".join(f"{kind.upper()} {name}" for name, kind, _ in failures)
    print(f"::error title={_prop(f'pytest: {len(failures)} of {total} failed')}::{_escape(summary)}")
    for name, kind, detail in failures[:9]:
        print(f"::error title={_prop(f'{kind} {name}')}::{_escape(chr(10).join(detail[-40:]))}")
    return 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0] if args else "pytest.xml", durations="--durations" in sys.argv))
