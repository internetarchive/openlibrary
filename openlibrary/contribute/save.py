"""Turn a task answer into a normal edition save.

Saves go through the same path as the edit form: a new revision, the comment in
the record's history, ``edit-book`` as the kind so edit stats are unchanged.
``data.source`` marks them as dashboard edits so the dashboard can list them.
"""

import re

import web

from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import get_languages
from openlibrary.utils.lccn import normalize_lccn
from openlibrary.utils.oclc import normalize_oclc

SOURCE = "contribute"
ACTION = "edit-book"


def normalize_lccn_value(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if m := re.search(r"lccn\.loc\.gov/(\S+)", s):
        s = m.group(1)
    return normalize_lccn(re.sub(r"^lccn:?", "", s))


# Identifier fields, and how to tidy a pasted value into the stored form.
NORMALIZERS = {"lccn": normalize_lccn_value, "oclc_numbers": normalize_oclc}


def normalized(fld: str, raw) -> list[str]:
    if not (normalize := NORMALIZERS.get(fld)) or raw in (None, "", []):
        return []
    values = raw if isinstance(raw, list) else [raw]
    return [v for v in (normalize(str(x)) for x in values) if v]


class InvalidAnswer(ValueError):
    """The answer can't be stored as given; the message is shown to the librarian."""


def language_options() -> list[dict]:
    """Every current language as picker items: the code submits, the name shows."""
    return sorted(({"value": lang.code, "label": lang.name} for lang in get_languages().values() if lang.get("name")), key=lambda x: x["label"])


def _language(raw: str) -> dict:
    wanted = raw.strip().casefold()
    for lang in get_languages().values():
        if wanted in {(lang.get("name") or "").casefold(), (lang.get("code") or "").casefold()}:
            return {"key": lang.key}
    raise InvalidAnswer(_("Pick a language from the list."))


def _pages(raw: str) -> int:
    try:
        pages = int(raw.strip())
    except ValueError:
        raise InvalidAnswer(_("Enter the page count as a whole number."))
    if not 0 < pages < 100_000:
        raise InvalidAnswer(_("Enter the page count as a whole number."))
    return pages


def _identifier(fld: str, raw: str, current: list) -> list[str]:
    """Add to the identifiers already on the record; never replace them."""
    if not (values := normalized(fld, raw)):
        raise InvalidAnswer(_("That is not a valid number for this catalog."))
    existing = [str(v) for v in current or []]
    return existing + [v for v in values if v not in existing]


def answer_value(edition, fld: str, raw: str):
    """The stored form of ``raw`` for ``fld`` on ``edition``, or InvalidAnswer."""
    if not raw.strip():
        raise InvalidAnswer(_("Fill in an answer, or choose “I couldn't find it”."))
    if fld == "languages":
        return [_language(raw)]
    if fld == "number_of_pages":
        return _pages(raw)
    if fld == "publishers":
        return [raw.strip()]
    if fld in NORMALIZERS:
        return _identifier(fld, raw, edition.get(fld))
    raise InvalidAnswer(_("This field can't be filled in here."))


def save_answer(edition, fld: str, raw: str, label: str, note: str = "") -> None:
    """Write the answer to the edition as a normal edit by the current user."""
    doc = edition.dict()
    doc[fld] = answer_value(edition, fld, raw)
    comment = note.strip() or _("Filled in %(field)s from the contribute dashboard", field=label)
    web.ctx.site.save(doc, comment=comment, action=ACTION, data={"source": SOURCE, "field": fld})


def recent_saves(user_key: str, limit: int = 5) -> list:
    """The user's latest dashboard edits, newest first. Filtered here: ``data`` filters need an index entry."""
    changes = web.ctx.site.recentchanges({"author": user_key, "kind": ACTION, "limit": 100})
    return [c for c in changes if (c.data or {}).get("source") == SOURCE][:limit]
