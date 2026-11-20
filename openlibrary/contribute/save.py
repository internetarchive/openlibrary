"""Turn a task answer into a normal edition save.

Saves go through the same path as the edit form: a new revision, the comment in
the record's history, ``edit-book`` as the kind so edit stats are unchanged.
``data.source`` marks them as Tasks edits so the dashboard can list them.
A cover goes through the add-cover page's upload instead, and saves as ``add-cover``
so history shows the image.
"""

import re
from datetime import UTC, datetime

import web
from isbnlib import canonical

from openlibrary.contribute.field_guides import AMAZON_COVER
from openlibrary.core.tags import MANY, find_tag
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.covers import add_cover
from openlibrary.plugins.upstream.utils import get_coverstore_public_url, get_languages
from openlibrary.utils.isbn import check_digit_10, check_digit_13, isbn_10_to_isbn_13, isbn_13_to_isbn_10
from openlibrary.utils.lccn import normalize_lccn
from openlibrary.utils.oclc import normalize_oclc
from openlibrary.utils.request_context import site

SOURCE = "contribute"
ACTION = "edit-book"
COVER_ACTION = "add-cover"


def normalize_lccn_value(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if m := re.search(r"lccn\.loc\.gov/(\S+)", s):
        s = m.group(1)
    return normalize_lccn(re.sub(r"^lccn:?", "", s))


def normalize_isbn_value(raw: str) -> str | None:
    """An ISBN-10 or ISBN-13 without its hyphens and spaces, when its check digit is right."""
    s = canonical(raw or "").upper()
    if len(s) == 13 and s.isdigit() and check_digit_13(s[:-1]) == s[-1]:
        return s
    if len(s) == 10 and s[:-1].isdigit() and check_digit_10(s[:-1]) == s[-1]:
        return s
    return None


# Identifier fields, and how to tidy a pasted value into the stored form.
NORMALIZERS = {"lccn": normalize_lccn_value, "oclc_numbers": normalize_oclc, "isbn": normalize_isbn_value}


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


def editions_with_isbn(isbn: str) -> list[str]:
    """The keys of the editions that already carry this ISBN, in either of its forms."""
    other = isbn_10_to_isbn_13(isbn) if len(isbn) == 10 else isbn_13_to_isbn_10(isbn)
    forms = {isbn, other} if other else {isbn}
    return [key for form in forms for key in site.get().things({"type": "/type/edition", f"isbn_{len(form)}": form})]


class SharedIsbn(InvalidAnswer):
    """The ISBN is already on other editions. Usually the records are duplicates, but publishers do reuse ISBNs, so it
    saves once the librarian has compared them and submits the same ISBN again."""

    def __init__(self, isbn: str, others: list[str]):
        self.isbn, self.others = isbn, others
        super().__init__(_("This ISBN is already on another edition. Compare them: if they're the same book, this record is probably a duplicate."))


def other_editions_with_isbn(edition, isbn: str) -> list[str]:
    return [k for k in editions_with_isbn(isbn) if k != edition.key]


def _isbn(edition, raw: str, shared_ok: str = "") -> dict[str, list[str]]:
    """The ISBN under the key for its length. One already on another edition needs ``shared_ok`` to name it."""
    if not (isbn := normalize_isbn_value(raw)):
        raise InvalidAnswer(_("That isn't a valid ISBN. Check the digits: an ISBN has 10 or 13, and the last one is a check digit."))
    if shared_ok != isbn and (others := other_editions_with_isbn(edition, isbn)):
        raise SharedIsbn(isbn, others)
    key = f"isbn_{len(isbn)}"
    return {key: [*(str(v) for v in edition.get(key) or []), isbn]}


# The earliest year a publish date can name; printing with movable type in Europe dates from the 1450s.
EARLIEST_PUBLISH_YEAR = 1450


def _publish_date(raw: str) -> str:
    """The date as typed, once it names a plausible year. Open Library keeps publish dates as text: "2005", "March 2005"."""
    date = " ".join(raw.split())
    if len(date) > 40:
        raise InvalidAnswer(_("Enter the date with its year, for example 2005 or March 2005."))
    if re.search(r"\d{5,}", date):
        raise InvalidAnswer(_("That year doesn't look right. Enter the year this edition came out."))
    years = [int(y) for y in re.findall(r"(?<!\d)\d{4}(?!\d)", date)]
    if not years:
        raise InvalidAnswer(_("Enter the date with its year, for example 2005 or March 2005."))
    current_max_year = datetime.now(UTC).year + 1
    for y in years:
        if not EARLIEST_PUBLISH_YEAR <= y <= current_max_year:
            raise InvalidAnswer(_("That year doesn't look right. Enter the year this edition came out."))
    return date


def answer_changes(edition, fld: str, raw: str, shared_ok: str = "") -> dict:
    """The keys ``raw`` sets on ``edition`` for ``fld``, or InvalidAnswer. Only an ISBN's key differs from its field's."""
    if not raw.strip():
        raise InvalidAnswer(_("Fill in an answer, or choose “I couldn't find it”."))
    return _isbn(edition, raw, shared_ok) if fld == "isbn" else {fld: answer_value(edition, fld, raw)}


def answer_value(edition, fld: str, raw: str):
    """The stored form of ``raw`` for ``fld`` on ``edition``, or InvalidAnswer."""
    if fld == "languages":
        return [_language(raw)]
    if fld == "number_of_pages":
        return _pages(raw)
    if fld == "publishers":
        return [raw.strip()]
    if fld == "publish_date":
        return _publish_date(raw)
    if fld in NORMALIZERS:
        return _identifier(fld, raw, edition.get(fld))
    raise InvalidAnswer(_("This field can't be filled in here."))


def change_data(fld: str, initiative: str, **more) -> dict:
    """A Tasks save's ``data``: the source, the task's field, and the initiative it counts toward, so the stats can split them."""
    return {"source": SOURCE, "field": fld} | ({"initiative": initiative} if initiative else {}) | more


def save_answer(edition, fld: str, raw: str, label: str, note: str = "", initiative: str = "", shared_ok: str = "") -> None:
    """Write the answer to the edition as a normal edit by the current user. ``shared_ok`` is an ISBN the librarian
    saved knowing other editions carry it; the edit names them, so the pairs can be found and merged or corrected."""
    doc = edition.dict() | answer_changes(edition, fld, raw, shared_ok)
    comment = note.strip() or _("Filled in %(field)s from Open Library Tasks", field=label)
    shared = other_editions_with_isbn(edition, shared_ok) if fld == "isbn" and shared_ok == normalize_isbn_value(raw) else []
    data = change_data(fld, initiative, **({"isbn_shared_with": shared} if shared else {}))
    site.get().save(doc, comment=comment, action=ACTION, data=data)


def tag_answers(fld: str, raws: list[str]) -> list[dict]:
    """The references to store for the chosen tags, in the order picked and without repeats; each must be one of the field's tags."""
    keys = list(dict.fromkeys(r.strip() for r in raws if r.strip()))
    if not keys:
        raise InvalidAnswer(_("Pick at least one genre, or choose “Not sure”.") if fld in MANY else _("Choose one of the options."))
    if any(not find_tag(fld, k) for k in keys):
        raise InvalidAnswer(_("Choose one of the options."))
    return [{"key": k} for k in keys]


def save_work_answers(work, answers: dict[str, list[str]], label: str, note: str = "", initiative: str = "") -> None:
    """Write tag answers to the work in one revision, the same way as an edition answer.

    ``answers`` maps each work field to the tag keys picked for it; a field where people pick one keeps just the first.
    ``data.field`` names the task that was answered, ``data.fields`` everything the save filled.
    """
    doc = work.dict()
    for fld, raws in answers.items():
        refs = tag_answers(fld, raws)
        doc[fld] = refs if fld in MANY else refs[:1]
    fields = list(answers)
    comment = note.strip() or _("Filled in %(field)s from Open Library Tasks", field=label)
    site.get().save(doc, comment=comment, action=ACTION, data=change_data(fields[0], initiative, fields=fields))


def save_cover(edition, file, from_amazon: bool = False, initiative: str = "") -> None:
    """Upload the image and put it first on the edition, as the add-cover page does."""
    if not getattr(file, "filename", ""):
        raise InvalidAnswer(_("Choose an image of the cover."))
    data = add_cover().upload(edition.key, web.storage(file=file, url=""))
    if data.get("unavailable"):
        raise InvalidAnswer(_("We couldn't save the cover just now. Please try again in a minute."))
    if not (cover_id := data.get("id")):
        raise InvalidAnswer(_("That isn't an image Open Library can use. Choose a JPG, GIF, PNG or WebP under 10 MB."))
    edition.covers = [cover_id] + [c.id for c in edition.get_covers()]
    change = change_data("covers", initiative)
    # The browser uploads the Amazon image it showed; passing it to coverstore as a URL would download it again there.
    if from_amazon and (isbn10 := edition.get_isbn10()):
        change["url"] = AMAZON_COVER.format(isbn10=isbn10)
    # History shows an add-cover change's comment as the image, so the comment is the thumbnail's address.
    edition._save(f"{get_coverstore_public_url()}/b/id/{cover_id}-S.jpg", action=COVER_ACTION, data=change)


def _tasks_changes(query: dict) -> list:
    """The changes matching ``query`` that Tasks saved, newest first. Filtered here: ``data`` filters need an index entry."""
    changes = [c for kind in (ACTION, COVER_ACTION) for c in site.get().recentchanges(query | {"kind": kind})]
    return sorted((c for c in changes if (c.data or {}).get("source") == SOURCE), key=lambda c: c.timestamp, reverse=True)


def recent_saves(user_key: str, limit: int = 5) -> list:
    """The user's latest Tasks edits, newest first."""
    return _tasks_changes({"author": user_key, "limit": 100})[:limit]
