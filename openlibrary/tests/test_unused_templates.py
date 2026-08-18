"""Fail on templates and macros that no code references.

This is the pytest wrapper around ``openlibrary/utils/template_usage.py``,
which inventories every Templetor template (``openlibrary/templates/**/*.html``),
Templetor macro (``openlibrary/macros/*.html``), Jinja template
(``*.html.jinja``), and Jinja ``{% macro %}`` definition, then searches every
git-tracked source file for references.  Templates only reachable through
runtime name construction (``templates/type/``, ``recentchanges/``,
``book_providers/``, ``design/``) are documented in the analyzer's
``DYNAMIC_DISPATCH_RULES`` and never flagged.

The main test fails and lists every unused template/macro.  Fix it by
deleting the template, or -- if it is used only from database content -- by
adding it to ``DB_USED_EXCLUSIONS`` below with a justification.
"""

from collections import Counter

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

# Templates/macros that are used only from *database* content: wiki-stored
# templates (/upstream/templates/*), wiki-stored macros (/upstream/macros/*),
# or {{Macro(...)}} markdown in any page body.  None of these are visible to
# static analysis.
#
# To check a candidate, search the "other" dump -- it contains every dump
# document that is not an edition/work/author/redirect/delete/list, i.e. all
# wiki templates, macros, and page bodies:
#
#   curl -sO https://openlibrary.org/data/ol_dump_other_latest.txt.gz
#   zcat ol_dump_other_latest.txt.gz | grep -F 'TheName'
#
# Interpreting what you find (verified 2026-08-17): production renders the
# repo's file templates -- db copies under /upstream/templates/ and
# /templates/ are generally stale shadows, and a reference *from* such a db
# template (e.g. $:macros.RecentChangesUsers in /upstream/templates/type/
# user/view.tmpl) does NOT count unless you can confirm the macro's output on
# a live page.  What does count is invocation from db page content: markdown
# like {{ListCarousel("...")}} in a /type/page doc that renders publicly.
#
# ONLY add an entry if you are totally confident it is used on the frontend
# but not visible in the code base.  Otherwise do NOT add it -- leaving it
# out just keeps the test failing, which is the safe failure mode.  Stale
# entries (renamed/deleted templates, or ones that later become referenced in
# code) fail test_exclusion_lists_are_not_stale.
DB_USED_EXCLUSIONS: dict[str, str] = {
    "ListCarousel": (
        'invoked via {{ListCarousel("/people/digital_s/lists/OL238301L", ...)}} '
        "markdown in live /type/page docs under /collections/the_haunted_library/*; "
        "verified rendering on production (carousel markup with that list ID "
        "present in the page HTML)"
    ),
    "SubjectSearch": (
        "created (f7b9ae436, 2026-08-03) to be embedded as {{SubjectSearch()}} "
        "in the /subjects wiki pages (/type/i18n_page docs stored in the "
        "production db); verified rendering live on production /subjects "
        "(form with id=searchSubjects). Note: the July dump predates the "
        "macro, so dump greps miss this one"
    ),
}

# Exclusions that are NOT db-usage: the maintainer has reason to believe the
# template is used even though static analysis and the db dump both come up
# empty.  Each entry needs a justification and should be revisited.
MANUAL_EXCLUSIONS: dict[str, str] = {
    "CodeBlock.html.jinja": (
        "maintainer believes this is used on the frontend (2026-08-17); no "
        "code, db, or design-registry reference found -- added per "
        "maintainer's call, drop this entry if that turns out to be wrong"
    ),
    "code_block": ("the {% macro %} inside CodeBlock.html.jinja; excluded together with its file -- see that entry"),
}

ALL_EXCLUSIONS = {**DB_USED_EXCLUSIONS, **MANUAL_EXCLUSIONS}


@pytest.fixture(scope="module")
def analysis() -> Analysis:
    return analyze(ALL_EXCLUSIONS)


def test_inventory_is_not_vacuous(analysis: Analysis):
    """Guard against silently broken discovery (moved roots, renamed globs)
    that would make test_no_unused_templates_and_macros vacuously pass.

    Every kind the analyzer can inventory must be present, and every
    dynamic-dispatch rule must still match real files on disk.  Unlike count
    floors, this survives any amount of legitimate template deletion.
    """
    kinds = {t.kind for t in analysis.templates}
    assert kinds == {KIND_TEMPLETOR_TEMPLATE, KIND_TEMPLETOR_MACRO, KIND_JINJA_TEMPLATE, KIND_JINJA_MACRO}, kinds
    for rule_dir in DYNAMIC_DISPATCH_RULES:
        assert any(t.rel_to_root.startswith(rule_dir) for t in analysis.templates), (
            f"dynamic-dispatch rule {rule_dir!r} matches no template on disk (stale rule -- update or remove it)"
        )


def test_no_unused_templates_and_macros(analysis: Analysis):
    counts = Counter(t.kind for t in analysis.templates)
    assert sum(counts.values()) > 0, counts

    if not analysis.unused:
        return
    listing = "\n".join(f"  {t.kind}: {t.relpath}" for t in analysis.unused)
    pytest.fail(
        f"{len(analysis.unused)} templates/macros are not referenced in any Python, "
        "Templetor, Jinja, or JS source. For each one: verify against the "
        "'other' dump as described in DB_USED_EXCLUSIONS and add it there with "
        "a justification if (and only if) it is used from database content; "
        f"otherwise delete it:\n{listing}"
    )


def test_exclusion_lists_are_not_stale(analysis: Analysis):
    assert not analysis.missing_exclusions, (
        f"exclusion entries (DB_USED_EXCLUSIONS/MANUAL_EXCLUSIONS) matching no template/macro on disk (remove them): {sorted(analysis.missing_exclusions)}"
    )
    assert not analysis.used_exclusions, (
        "exclusion entries (DB_USED_EXCLUSIONS/MANUAL_EXCLUSIONS) that are actually referenced in code "
        "(remove them -- the exclusion hides real usage):\n"
        + "\n".join(f"  {name}: referenced in {evidence}" for name, evidence in sorted(analysis.used_exclusions.items()))
    )
