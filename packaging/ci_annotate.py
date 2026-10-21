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


def main(path: str) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"::error title=pytest::No test report ({exc})")
        return 1
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
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "pytest.xml"))
