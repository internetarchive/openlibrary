#!/usr/bin/env python
"""Pre-commit hook: reject legacy site access in application code."""

import re
import sys

PATTERN = re.compile(r"\bweb\s*\.\s*ctx\s*\.\s*site\b")


def main(files: list[str]) -> int:
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
