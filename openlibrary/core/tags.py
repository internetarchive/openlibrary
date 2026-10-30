"""Typed tags on a work: the literary form (fiction or nonfiction) today, genres next.

A work points at ``/type/tag`` objects (``literary_form`` holds one, ``genres`` and ``subgenres`` a list).
Older migrations stored bare keys, so every reader here takes a key string, a ``{"key": ...}`` dict or a Thing.
While the feature is new, every surface that shows or edits these tags is limited to ``can_edit_tags``.
"""

import web

from infogami.utils.view import public
from openlibrary.i18n import gettext as _
from openlibrary.utils.request_context import site

LITERARY_FORM = "literary_form"
# The whitelist: admins plus this group. The group is a plain /type/usergroup document, so an admin can add people on the site.
TAGS_BETA_GROUP = "/usergroup/tags-beta"
# The work fields that hold tag references, in the order the book page shows them.
WORK_TAG_FIELDS = (LITERARY_FORM, "genres", "subgenres")


@public
def can_edit_tags(user) -> bool:
    return bool(user) and (user.is_admin() or user.is_usergroup_member(TAGS_BETA_GROUP))


@public
def tag_key(value) -> str | None:
    """The tag key behind a stored reference, whichever shape it was saved in."""
    if isinstance(value, str):
        return value or None
    if value is None:
        return None
    return value.get("key") or None


def work_tag_keys(work, fld: str) -> list[str]:
    raw = work.get(fld)
    values = raw if isinstance(raw, list) else [raw]
    return [k for k in (tag_key(v) for v in values) if k]


def get_tags_of_type(tag_type: str) -> list:
    """Every tag of ``tag_type``, by name."""
    keys = site.get().things({"type": "/type/tag", "tag_type": tag_type, "limit": 500})
    tags = [t for t in site.get().get_many(keys) if t.get("name")]
    return sorted(tags, key=lambda t: t.name.casefold())


def choice_hints(tag_type: str) -> dict[str, str]:
    """The line under each picker row, by tag name; "" is the "not sure" row.

    Written as examples and gotchas: the vocabulary's definitions only restate the name, so rows without a hint show none.
    """
    if tag_type == LITERARY_FORM:
        return {
            "fiction": _("Novels, stories, plays and poems."),
            "nonfiction": _("History, biography, memoir, essays, how-to and reference."),
            "": _("Hard to call, like a book based on a true story or a collection that mixes fiction and nonfiction."),
        }
    return {}


@public
def tag_options(tag_type: str) -> list[dict]:
    """The type's tags as picker choices: the key submits, the name shows, the hint explains."""
    hints = choice_hints(tag_type)
    return [web.storage(value=t.key, label=t.name, description=hints.get(t.name.casefold(), "")) for t in get_tags_of_type(tag_type)]


@public
def tag_choices(tag_type: str, unsure_label: str, unsure_description: str | None = None, unsure_value: str = "") -> list[dict]:
    """The type's tags as choice-list rows, with "not sure" as a row of its own rather than a way out at the bottom."""
    if unsure_description is None:
        unsure_description = choice_hints(tag_type).get("", "")
    return [*tag_options(tag_type), web.storage(value=unsure_value, label=unsure_label, description=unsure_description)]


def find_tag(tag_type: str, key: str):
    return next((t for t in get_tags_of_type(tag_type) if t.key == key), None)


def work_tags(work) -> list[dict]:
    """The work's tags as the book page shows them, in field order, each linking to its tag page."""
    keys = [k for fld in WORK_TAG_FIELDS for k in work_tag_keys(work, fld)]
    if not keys:
        return []
    tags = {t.key: t for t in site.get().get_many(keys)}
    return [{"name": tag.name, "url": tag.key, "tag_type": tag.get("tag_type") or ""} for k in keys if (tag := tags.get(k)) and tag.get("name")]
