#!/usr/bin/env python
"""Pre-commit hook: reject legacy site access in application code."""

import re
import sys
from pathlib import Path

PATTERN = re.compile(r"\bweb\s*\.\s*ctx\s*\.\s*site\b")
REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"


def main(files: list[str]) -> int:
    if "github.com/webpy/webpy" not in REQUIREMENTS.read_text(encoding="utf-8"):
        sys.stderr.write(
            "web.py is no longer in requirements.txt, so this check is obsolete. Delete the no-legacy-site hook from "
            ".pre-commit-config.yaml, scripts/check_no_legacy_site.py, and the web.db / web.database TID251 bans in pyproject.toml.\n"
        )
        return 1

    found = False
    for filename in files:
        with open(filename, encoding="utf-8") as source:
            for number, line in enumerate(source, 1):
                if not line.lstrip().startswith("#") and PATTERN.search(line):
                    found = True
                    sys.stderr.write(f"{filename}:{number}:{line.rstrip()}\n")

    if found:
        sys.stderr.write(
            "\nLegacy thread-local site access is unsafe in FastAPI. Import site from openlibrary.utils.request_context and use site.get() instead.\n"
        )
    return int(found)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
