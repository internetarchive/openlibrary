"""Typed tags on a work: the literary form (fiction or nonfiction) and the genres.

A work points at ``/type/tag`` objects (``literary_form`` holds one, ``genres`` and ``subgenres`` a list).
Older migrations stored bare keys, so every reader here takes a key string, a ``{"key": ...}`` dict or a Thing.
Editing these tags on the book and edit pages is limited to ``can_edit_tags`` while the vocabulary is new.
"""

import re
import time
from functools import lru_cache

import web

from infogami.utils.view import public
from openlibrary.i18n import gettext as _
from openlibrary.utils import normalize_subject_name
from openlibrary.utils.request_context import site

LITERARY_FORM = "literary_form"
GENRES = "genres"
# The whitelist: admins plus this group. The group is a plain /type/usergroup document, so an admin can add people on the site.
TAGS_BETA_GROUP = "/usergroup/tags-beta"
# The work fields that hold tag references, in the order the book page shows them.
WORK_TAG_FIELDS = (LITERARY_FORM, GENRES, "subgenres")
# Fields that hold a list of tags; the others hold one.
MANY = frozenset({GENRES, "subgenres"})
# A field's tags by their ``tag_type``. Production typed tags with the plural field name first and is moving to the
# singular (#14229), so both are read; the field name is the one the rest of the code uses.
FIELD_TAG_TYPES = {LITERARY_FORM: ("literary_form",), GENRES: ("genres", "genre"), "subgenres": ("subgenres", "subgenre")}
# How long a field's tag list is kept in the process before the site is asked again.
TAGS_TTL_SECONDS = 300


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


@lru_cache(maxsize=32)
def _tags_cached(fld: str, _bucket: int) -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    """``(key, name, description, slugs)`` for each of the field's tags, by name. ``_bucket`` turns over every ``TAGS_TTL_SECONDS``."""
    keys = [k for tag_type in FIELD_TAG_TYPES.get(fld, (fld,)) for k in site.get().things({"type": "/type/tag", "tag_type": tag_type, "limit": 500})]
    tags = [t for t in site.get().get_many(keys) if t.get("name")]
    return tuple(
        (t.key, t.name, t.get("tag_description") or "", tuple(t.get("slugs") or [normalize_subject_name(t.name)]))
        for t in sorted(tags, key=lambda t: t.name.casefold())
    )


def clear_cache() -> None:
    _tags_cached.cache_clear()


def get_tags_of_type(fld: str) -> list:
    """Every tag a work's ``fld`` may point at, by name. Read from the site at most once per ``TAGS_TTL_SECONDS``: the
    task pool checks thousands of works against the list at a time."""
    return [
        web.storage(key=key, name=name, tag_description=description, slugs=list(slugs))
        for key, name, description, slugs in _tags_cached(fld, int(time.time() // TAGS_TTL_SECONDS))
    ]


def _words(text: str) -> list[str]:
    """A subject or slug as lowercase word stems, so "Horror stories" and "horror_stories" and "Thrillers" all compare plainly."""
    return [re.sub(r"(ies|s)$", lambda m: "y" if m[1] == "ies" else "", w) for w in re.findall(r"[a-z0-9]+", text.casefold())]


def subject_matches(fld: str, subjects: list[str]) -> dict[str, list[str]]:
    """The field's tags a work's free-text subjects point at: tag key to the subjects that named it, in vocabulary order.

    A tag matches a subject when one of its slugs appears in it as whole words, so "Horror stories" and "Fiction, horror"
    both name Horror and "History" does not name Historical. The slugs are the tag's own, editable on the tag page, so
    a librarian can teach Horror to answer "ghost stories" without a deploy.
    """
    found: dict[str, list[str]] = {}
    for tag in get_tags_of_type(fld):
        phrases = [p for p in (_words(s) for s in tag.slugs) if p]
        for subject in subjects:
            words = _words(subject)
            if any(words[i : i + len(p)] == p for p in phrases for i in range(len(words) - len(p) + 1)):
                found.setdefault(tag.key, []).append(subject)
    return found


def choice_hints(fld: str) -> dict[str, str]:
    """The line under each picker row, by tag name; "" is the "not sure" row.

    Written as examples and gotchas: the vocabulary's definitions only restate the name, so rows without a hint show none.
    """
    if fld == LITERARY_FORM:
        return {
            "fiction": _("Novels, stories, plays and poems."),
            "nonfiction": _("History, biography, memoir, essays, how-to and reference."),
            "": _("Hard to call, like a book based on a true story or a collection that mixes fiction and nonfiction."),
        }
    return {}


@public
def tag_options(fld: str) -> list[dict]:
    """The field's tags as picker choices: the key submits, the name shows, the hint explains."""
    hints = choice_hints(fld)
    return [web.storage(value=t.key, label=t.name, description=hints.get(t.name.casefold(), "")) for t in get_tags_of_type(fld)]


@public
def tag_choices(fld: str, unsure_label: str, unsure_description: str | None = None, unsure_value: str = "") -> list[dict]:
    """The field's tags as choice-list rows, with "not sure" as a row of its own rather than a way out at the bottom."""
    if unsure_description is None:
        unsure_description = choice_hints(fld).get("", "")
    return [*tag_options(fld), web.storage(value=unsure_value, label=unsure_label, description=unsure_description)]


def find_tag(fld: str, key: str):
    return next((t for t in get_tags_of_type(fld) if t.key == key), None)


def tag_key_named(fld: str, name: str) -> str | None:
    """The key of the field's tag called ``name``, whatever its case; None when the vocabulary has none."""
    return next((t.key for t in get_tags_of_type(fld) if t.name.casefold() == name.casefold()), None)


def work_tag_names(work, fld: str) -> list[str]:
    """The names of the work's tags in ``fld``, in stored order; a key the vocabulary no longer has is skipped."""
    return [tag.name for k in work_tag_keys(work, fld) if (tag := find_tag(fld, k))]


def literary_form_of(work) -> str:
    """ "fiction", "nonfiction" or "" when the work doesn't say."""
    names = work_tag_names(work, LITERARY_FORM)
    return names[0].casefold() if names else ""


def is_nonfiction(work) -> bool:
    return literary_form_of(work) == "nonfiction"


def work_tags(work) -> list[dict]:
    """The work's tags as the book page shows them, in field order, each linking to its tag page."""
    keys = [k for fld in WORK_TAG_FIELDS for k in work_tag_keys(work, fld)]
    if not keys:
        return []
    tags = {t.key: t for t in site.get().get_many(keys)}
    return [{"name": tag.name, "url": tag.key, "tag_type": tag.get("tag_type") or ""} for k in keys if (tag := tags.get(k)) and tag.get("name")]
