"""Fail on templates and macros that no code references.

Wraps openlibrary/utils/template_usage.py (see its docstring for the matching
rules and DYNAMIC_DISPATCH_RULES).  Fix a failure by deleting the template,
or -- if it is used only from database content -- by adding it to
DB_USED_EXCLUSIONS with a one-line justification.
"""

import pytest

from openlibrary.utils.template_usage import (
    DYNAMIC_DISPATCH_RULES,
    KIND_JINJA_MACRO,
    KIND_JINJA_TEMPLATE,
    KIND_TEMPLETOR_MACRO,
    KIND_TEMPLETOR_TEMPLATE,
    Analysis,
    analyze,
)

# Templates/macros used only from *database* content (wiki templates/macros,
# or {{Macro(...)}} in page bodies) -- invisible to static analysis.  Verify
# candidates against the "other" dump:
#   curl -sO https://openlibrary.org/data/ol_dump_other_latest.txt.gz
#   zcat ol_dump_other_latest.txt.gz | grep -F 'TheName'
# Only db-page invocations that render publicly count; db copies under
# /upstream/* are stale shadows.  When in doubt leave it out -- a missing
# entry just keeps the test failing (safe).  Stale entries fail the staleness
# test below.
DB_USED_EXCLUSIONS: dict[str, str] = {
    "ListCarousel": "{{ListCarousel(...)}} markdown in live /collections/* db pages (verified on prod)",
    "SubjectSearch": "{{SubjectSearch()}} in db-stored /subjects wiki pages (f7b9ae436)",
}

# Maintainer-verified without evidence; revisit periodically.
MANUAL_EXCLUSIONS: dict[str, str] = {
    "CodeBlock.html.jinja": "believed live on frontend (2026-08-17)",
    "code_block": "the {% macro %} inside CodeBlock.html.jinja; excluded with its file",
}

ALL_EXCLUSIONS = {**DB_USED_EXCLUSIONS, **MANUAL_EXCLUSIONS}


@pytest.fixture(scope="module")
def analysis() -> Analysis:
    return analyze(ALL_EXCLUSIONS)


def test_inventory_is_not_vacuous(analysis: Analysis):
    """Guard against silently broken discovery (moved roots, renamed globs)
    that would make the main test vacuously pass."""
    kinds = {t.kind for t in analysis.templates}
    assert kinds == {KIND_TEMPLETOR_TEMPLATE, KIND_TEMPLETOR_MACRO, KIND_JINJA_TEMPLATE, KIND_JINJA_MACRO}, kinds
    for rule_dir in DYNAMIC_DISPATCH_RULES:
        assert any(t.rel_to_root.startswith(rule_dir) for t in analysis.templates), (
            f"dynamic-dispatch rule {rule_dir!r} matches no template on disk (stale rule -- update or remove it)"
        )


def test_no_unused_templates_and_macros(analysis: Analysis):
    if not analysis.unused:
        return
    listing = "\n".join(f"  {t.kind}: {t.relpath}" for t in analysis.unused)
    pytest.fail(
        f"{len(analysis.unused)} templates/macros are not referenced in any Python, "
        "Templetor, Jinja, or JS source. For each one: verify against the "
        "'other' dump and add it to DB_USED_EXCLUSIONS with a justification "
        "if (and only if) it is used from database content; otherwise delete "
        f"it:\n{listing}"
    )


def test_exclusion_lists_are_not_stale(analysis: Analysis):
    assert not analysis.missing_exclusions, (
        f"exclusion entries (DB_USED_EXCLUSIONS/MANUAL_EXCLUSIONS) matching no template/macro on disk (remove them): {sorted(analysis.missing_exclusions)}"
    )
    assert not analysis.used_exclusions, (
        "exclusion entries (DB_USED_EXCLUSIONS/MANUAL_EXCLUSIONS) that are referenced in code "
        "(remove them -- the exclusion hides real usage):\n"
        + "\n".join(f"  {name}: referenced in {evidence}" for name, evidence in sorted(analysis.used_exclusions.items()))
    )
