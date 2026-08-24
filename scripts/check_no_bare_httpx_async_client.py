#!/usr/bin/env python
"""Pre-commit hook: fail if any given file assigns httpx.AsyncClient() directly.

A directly-assigned httpx.AsyncClient() (as opposed to a scoped
`async with httpx.AsyncClient() as client:`, which closes before it could
ever be reused from another loop) is unsafe to share across this codebase's
event loops -- AsyncBridge's persistent background-thread loop vs. a caller's
own loop (e.g. FastAPI's). See cache_per_event_loop in
openlibrary/utils/async_utils.py for why, and wrap the constructor with it
instead.
"""

import re
import sys

PATTERN = re.compile(r"=\s*httpx\.AsyncClient\(")


def main(files: list[str]) -> int:
    hits: list[str] = []
    for filename in files:
        with open(filename, encoding="utf-8") as f:
            hits += (f"{filename}:{i}:{line.rstrip()}" for i, line in enumerate(f, 1) if PATTERN.search(line))

    if not hits:
        return 0

    sys.stderr.write("\n".join(hits))
    sys.stderr.write(
        "\nhttpx.AsyncClient() assigned directly is unsafe to share across "
        "this codebase's event loops (AsyncBridge's background loop vs. a "
        "caller's own loop). Wrap it with cache_per_event_loop instead, e.g.:\n"
        "    get_async_session = cache_per_event_loop(httpx.AsyncClient)\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
