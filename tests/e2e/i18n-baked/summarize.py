#!/usr/bin/env python
"""Reduce a Playwright JSON report of i18n-baked.spec.ts to one verdict line for run.sh.

Prints "all pass", "english_before fail; both, kept pass", or a description of anything
else. Zero tests, or a run where some class never appears, is never "all pass".
"""

import json
import sys
from collections import defaultdict


def specs(suite: dict):
    yield from suite.get("specs", [])
    for child in suite.get("suites", []):
        yield from specs(child)


def main(path: str) -> None:
    try:
        with open(path) as f:
            report = json.load(f)
    except (OSError, ValueError) as e:
        print(f"no report ({e})")
        return
    outcome: dict[str, list[bool]] = defaultdict(list)
    for suite in report.get("suites", []):
        for spec in specs(suite):
            # title: "<mode> <lang> <class>: <msgid>"
            cls = spec["title"].split(":", 1)[0].split()[-1]
            outcome[cls].append(spec["ok"])
    if not outcome or not outcome.get("english_before"):
        print(f"no english_before tests ran ({dict(outcome)})")
        return
    failed = {cls for cls, oks in outcome.items() if not any(oks)}
    partial = {cls for cls, oks in outcome.items() if any(oks) and not all(oks)}
    if not failed and not partial:
        print("all pass")
    elif failed == {"english_before"} and not partial:
        print("english_before fail; both, kept pass")
    else:
        print(f"failed: {sorted(failed)}, mixed: {sorted(partial)}")


if __name__ == "__main__":
    main(sys.argv[1])
