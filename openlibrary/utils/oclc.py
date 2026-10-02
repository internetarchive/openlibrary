"""Normalize OCLC control numbers.

The Python counterpart of ``parseOclc``/``isValidOclc`` in
``openlibrary/plugins/openlibrary/js/idValidation.js``, kept in step with it
the way ``openlibrary/utils/lccn.py`` is.

An OCLC number is "a unique, sequentially assigned number associated with a
record in WorldCat": digits only, not zero-padded. Records in the wild carry
the ``ocm``/``ocn``/``on`` prefixes OCLC used for fixed-width fields, and the
``(OCoLC)`` organization code when they come from MARC 035.
"""

import re

OCLC_URL_RE = re.compile(r"worldcat\.org/(?:title|oclc)/(\d+)")
OCLC_PREFIX_RE = re.compile(r"^(?:\(ocolc\)|ocm|ocn|on)(?=\d)")
OCLC_VALID_RE = re.compile(r"^[1-9][0-9]*$")


def normalize_oclc(oclc: str) -> str | None:
    """A bare control number, or None when the value is not one."""
    s = (oclc or "").strip().lower()
    if m := OCLC_URL_RE.search(s):
        s = m.group(1)
    s = OCLC_PREFIX_RE.sub("", s)
    s = re.sub(r"[\s-]", "", s).lstrip("0")
    return s if OCLC_VALID_RE.match(s) else None
