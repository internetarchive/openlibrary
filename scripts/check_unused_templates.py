#!/usr/bin/env python
"""Pre-commit hook: fail on templates and macros that no code references.

Wraps openlibrary/utils/template_usage.py (see its docstring for the matching
rules and DYNAMIC_DISPATCH_RULES). Fix a failure by deleting the template,
or -- if it is used only from database content -- by adding it to
DB_USED_EXCLUSIONS with a one-line justification.

Runs as a pre-commit hook (on the host) rather than a pytest test because it
shells out to `git ls-files --recurse-submodules`, which needs a real git
repository -- unavailable inside a container that only bind-mounts a git
worktree's working tree, without its linked main repo's .git dir.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openlibrary.utils.template_usage import analyze

# Templates/macros used only from *database* content (wiki templates/macros,
# or {{Macro(...)}} in page bodies) -- invisible to static analysis. Verify
# candidates against the "other" dump:
#   curl -sO https://openlibrary.org/data/ol_dump_other_latest.txt.gz
#   zcat ol_dump_other_latest.txt.gz | grep -F 'TheName'
# Only db-page invocations that render publicly count; db copies under
# /upstream/* are stale shadows. When in doubt leave it out -- a missing
# entry just keeps this check failing (safe). Stale entries fail the
# staleness check below.
DB_USED_EXCLUSIONS: dict[str, str] = {
    "SubjectSearch": "{{SubjectSearch()}} in db-stored /subjects wiki pages (f7b9ae436)",
}

# Maintainer-verified without evidence; revisit periodically.
MANUAL_EXCLUSIONS: dict[str, str] = {
    "CodeBlock.html.jinja": "believed live on frontend (2026-08-17)",
    "code_block": "the {% macro %} inside CodeBlock.html.jinja; excluded with its file",
}

ALL_EXCLUSIONS = {**DB_USED_EXCLUSIONS, **MANUAL_EXCLUSIONS}


def main() -> int:
    analysis = analyze(ALL_EXCLUSIONS)
    ok = True

    # Guard against silently broken discovery (moved roots, renamed globs)
    # that would make the unused-template check below vacuously pass.
    if analysis.missing_kinds:
        sys.stderr.write(f"template discovery looks broken (no templates found of kind(s) {sorted(analysis.missing_kinds)})\n")
        ok = False
    for rule_dir in analysis.stale_dynamic_dispatch_rules:
        sys.stderr.write(f"dynamic-dispatch rule {rule_dir!r} matches no template on disk (stale rule -- update or remove it)\n")
        ok = False

    if analysis.unused:
        listing = "\n".join(f"  {t.kind}: {t.relpath}" for t in analysis.unused)
        sys.stderr.write(
            f"{len(analysis.unused)} templates/macros are not referenced in any Python, "
            "Templetor, Jinja, or JS source. For each one: verify against the "
            "'other' dump and add it to DB_USED_EXCLUSIONS with a justification "
            "if (and only if) it is used from database content; otherwise delete "
            f"it:\n{listing}\n"
        )
        ok = False

    if analysis.missing_exclusions:
        sys.stderr.write(
            f"exclusion entries (DB_USED_EXCLUSIONS/MANUAL_EXCLUSIONS) matching no template/macro on disk (remove them): {sorted(analysis.missing_exclusions)}\n"
        )
        ok = False

    if analysis.used_exclusions:
        sys.stderr.write(
            "exclusion entries (DB_USED_EXCLUSIONS/MANUAL_EXCLUSIONS) that are referenced "
            "in code (remove them -- the exclusion hides real usage):\n"
            + "\n".join(f"  {name}: referenced in {evidence}" for name, evidence in sorted(analysis.used_exclusions.items()))
            + "\n"
        )
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
