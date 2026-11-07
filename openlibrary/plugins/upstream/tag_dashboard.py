"""Data assembly for the Tags dashboard rendered at ``/tags`` (#13928).

The dashboard is read-only. It groups every Tag by ``tag_type``, counts each
group, and surfaces the data-quality problems a curator would otherwise have to
find by hand.

Everything here is a pure function of the tag list, with no dependency on the
web stack, so the grouping and the rules can be unit tested on their own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# The problems worth flagging, in the order the dashboard lists them.
FLAG_KINDS = (
    "singular_type",
    "test_tag",
    "missing_type",
    "missing_description",
    "missing_slugs",
)

# Singular tag types that duplicate a canonical plural one. Taken from the tag
# census in #13924, which shows both forms in the data (``genre`` 1 vs
# ``genres`` 30). A singular type is only reported when tags carrying it
# actually exist, so this table can stay aspirational without adding noise.
SINGULAR_TAG_TYPE_CANONICAL: dict[str, str] = {
    "audience": "audiences",
    "award": "awards",
    "content_feature": "content_features",
    "content_format": "content_formats",
    "content_warning": "content_warnings",
    "genre": "genres",
    "literary_form": "literary_forms",
    "literary_theme": "literary_themes",
    "literary_trope": "literary_tropes",
    "mood": "moods",
    "subgenre": "subgenres",
}

# ``test`` in a tag name is almost always scaffolding rather than vocabulary:
# OL85T..OL93T are all "Science Fiction Test" (#13924).
TEST_TAG_RE = re.compile(r"\btest\b", re.IGNORECASE)


def _name_key(tag: Any) -> str:
    """Sort key for tags: names sort case-insensitively."""
    return (tag.get("name") or "").casefold()


@dataclass(frozen=True)
class TagGroup:
    """Every tag sharing one ``tag_type``, sorted by name."""

    tag_type: str
    tags: list[Any]

    @property
    def count(self) -> int:
        return len(self.tags)


@dataclass(frozen=True)
class TagDashboard:
    """Everything the ``type/tag/index`` template renders."""

    total: int
    groups: list[TagGroup]
    flags: dict[str, list[Any]]
    canonical_types: dict[str, str] = field(default_factory=dict)
    truncated: bool = False


def build_tag_dashboard(tags: list[Any], *, truncated: bool = False) -> TagDashboard:
    """Group ``tags`` by type and flag the ones that need a curator's attention.

    :param tags: Tag objects (anything with ``.get()``) to display.
    :param truncated: True when the tag list was cut short before grouping, so
        the counts on the page are a floor rather than a total.
    """
    grouped: dict[str, list[Any]] = {}
    for tag in tags:
        grouped.setdefault(tag.get("tag_type") or "", []).append(tag)

    groups = [TagGroup(tag_type=tag_type, tags=sorted(group, key=_name_key)) for tag_type, group in grouped.items()]
    # Largest vocabulary first, then alphabetically; the untyped bucket last.
    groups.sort(key=lambda group: (not group.tag_type, -group.count, group.tag_type))

    flags: dict[str, list[Any]] = {kind: [] for kind in FLAG_KINDS}
    for tag in tags:
        tag_type = tag.get("tag_type") or ""
        if tag_type in SINGULAR_TAG_TYPE_CANONICAL:
            flags["singular_type"].append(tag)
        if TEST_TAG_RE.search(tag.get("name") or ""):
            flags["test_tag"].append(tag)
        if not tag_type:
            flags["missing_type"].append(tag)
        if not (tag.get("tag_description") or "").strip():
            flags["missing_description"].append(tag)
        if not tag.get("slugs"):
            flags["missing_slugs"].append(tag)

    for flagged in flags.values():
        flagged.sort(key=_name_key)

    return TagDashboard(
        total=len(tags),
        groups=groups,
        flags=flags,
        canonical_types=SINGULAR_TAG_TYPE_CANONICAL,
        truncated=truncated,
    )
