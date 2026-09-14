"""Tests for openlibrary.core.layout — guarantee layout is data-only."""

import pathlib
import re

import pytest

from openlibrary.core.layout import LayoutContext

TEMPLATES_DIR = pathlib.Path(__file__).resolve().parents[3] / "openlibrary" / "templates"
LAYOUT_TEMPLATES = [
    TEMPLATES_DIR / "site.html.jinja",
    TEMPLATES_DIR / "lib" / "nav_foot.html.jinja",
    TEMPLATES_DIR / "languages" / "language_list.html.jinja",
    TEMPLATES_DIR / "site" / "stats.html.jinja",
]


def test_layout_context_contains_no_callables(request_context_fixture):
    """LayoutContext.build() must be pure data — no functions that could hide I/O."""
    request_context_fixture(lang="en")
    layout = LayoutContext.build()
    # __post_init__ already guards this, but double-check via to_dict
    for key, val in layout.to_dict().items():
        assert not callable(val), f"{key} is callable"
        if isinstance(val, dict):
            for k, v in val.items():
                assert not callable(v), f"{key}[{k!r}] is callable"
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        assert not callable(vv), f"{key}[{k!r}][{kk!r}] is callable"
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                assert not callable(item), f"{key}[{idx}] is callable"
                if isinstance(item, dict):
                    for k, v in item.items():
                        assert not callable(v), f"{key}[{idx}][{k!r}] is callable"


def test_layout_templates_do_not_call_layout_fields():
    """Site shell templates must not call layout fields as functions.

    Allowed: data traversals like `layout.stats_summary.items()` (dict method).
    Not allowed: `layout.foo()` where foo is a layout field that could be a
    passed-in function doing network I/O.

    This keeps the layout side fast and pre-computed.
    """
    # Direct layout field call: layout.<field>(...
    direct_call = re.compile(r"layout\.\w+\s*\(")
    for path in LAYOUT_TEMPLATES:
        text = path.read_text()
        # .items() / .values() / .keys() are on the *value* of a field, not on layout itself.
        # Strip those safe calls before checking, so we only flag layout.field(.
        safe_stripped = re.sub(r"layout\.\w+\.\w+\s*\(", "SAFE(", text)
        assert not direct_call.search(safe_stripped), f"{path} calls layout field as function"


def test_layout_context_is_frozen():
    """LayoutContext must stay frozen — templates must not mutate it."""
    layout = LayoutContext(
        show_ol_shell=True,
        is_debug=False,
        is_bot=False,
        total_time_ms=0.0,
        supported_languages=[],
        git_rev_hash="",
        lang="en",
        stats_summary={},
        stats_details=[],
    )
    with pytest.raises((AttributeError, TypeError)):
        layout.lang = "fr"  # type: ignore[misc]
