"""Non-IA identifiers: how to clean one up into the form Open Library stores.

An identifier is a pointer into somebody else's catalog, and it is right only
when the record at the other end describes *this* edition. Open Library can't
check that without fetching the record, so the task page leaves it to the
librarian and only tidies the number.
"""

import re

from openlibrary.utils.lccn import normalize_lccn
from openlibrary.utils.oclc import normalize_oclc


def normalize_lccn_value(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if m := re.search(r"lccn\.loc\.gov/(\S+)", s):
        s = m.group(1)
    return normalize_lccn(re.sub(r"^lccn:?", "", s))


NORMALIZERS = {"lccn": normalize_lccn_value, "oclc_numbers": normalize_oclc}


def is_identifier_field(field: str) -> bool:
    return field in NORMALIZERS


def normalized(field: str, raw) -> list[str]:
    """Identifier values in the one form everything downstream compares."""
    if not (normalize := NORMALIZERS.get(field)) or raw in (None, "", []):
        return []
    values = raw if isinstance(raw, list) else [raw]
    return [v for v in (normalize(str(x)) for x in values) if v]
