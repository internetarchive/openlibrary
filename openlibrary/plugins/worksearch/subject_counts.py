"""Read-only endpoint for exact subject counts and enumeration over the raw
``subject_facet`` Solr field.

``subject_facet`` stores the exact subject string (case and punctuation preserved),
so Solr can count a precise variant such as ``Handbooks, Manuals`` separately from
``Handbooks, manuals``. The public ``/search.json`` re-parses the query and mangles
exact matches that contain a comma or space, and ``/search/subjects`` queries the
*normalized* subject pages (lumping variants together), so neither can answer "how
many works carry this exact subject string". This endpoint wraps the faceting the
server already has Solr access for, without exposing raw Solr to callers.

Two capabilities:

* **Exact count** — ``?subject=<exact string>`` returns the work count for that one
  string. The string is passed to Solr's ``{!term}`` parser by dereference (``v=$subj``),
  so it is matched literally and never interpreted as query syntax.
* **Enumerate** — list subject values with their work counts, optionally filtered to a
  substring (``contains``) or to the rare tail (``max_works``), with count-ascending or
  count-descending ordering and offset paging.
"""

import json

import web

from infogami.utils import delegate
from infogami.utils.view import safeint
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.async_utils import async_bridge

SUBJECT_TYPE_TO_FACET = {
    "subject": "subject_facet",
    "person": "person_facet",
    "place": "place_facet",
    "time": "time_facet",
}

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# Upper bound on how many substring-matching values we pull back when we must
# post-filter by count (the rare-tail + substring case). Solr's only substring
# primitive is classic ``facet.contains``, which cannot sort by count ascending, so
# we over-fetch the matching values and order them in-process. A match set larger
# than this is reported with ``truncated: true`` rather than silently cut.
CONTAINS_SCAN_CAP = 2000

REQUEST_LABEL = "SUBJECT_COUNTS_API"


class InvalidSubjectQuery(ValueError):
    """A caller-supplied parameter was invalid; surfaced as HTTP 400."""


def resolve_facet_field(subject_type: str) -> str:
    """Map a public ``subject_type`` to its whitelisted Solr facet field.

    >>> resolve_facet_field("subject")
    'subject_facet'
    >>> resolve_facet_field("nope")
    Traceback (most recent call last):
        ...
    openlibrary.plugins.worksearch.subject_counts.InvalidSubjectQuery: ...
    """
    try:
        return SUBJECT_TYPE_TO_FACET[subject_type]
    except KeyError:
        raise InvalidSubjectQuery(f"unknown subject_type {subject_type!r}; expected one of " + ", ".join(sorted(SUBJECT_TYPE_TO_FACET)))


def build_exact_count_params(field: str, subject: str) -> list[tuple[str, object]]:
    """Solr params for the exact-count query.

    ``field`` is a whitelisted facet name (never caller text). ``subject`` is bound to
    the ``subj`` request param and dereferenced by ``{!term ... v=$subj}``, so Solr
    matches it as a literal term with no query parsing — the injection boundary.
    """
    return [
        ("q", "*:*"),
        ("rows", 0),
        ("fq", "{!term f=%s v=$subj}" % field),
        ("subj", subject),
        ("ol.label", REQUEST_LABEL),
        ("wt", "json"),
    ]


def build_enumerate_params(field: str, limit: int, offset: int, ascending: bool) -> list[tuple[str, object]]:
    """Solr params for substring-free enumeration via the JSON Facet API.

    JSON faceting is the only Solr mode that sorts terms by count ascending, which the
    rare-tail (``max_works``) case needs, and it pages natively.
    """
    facet = {
        "s": {
            "type": "terms",
            "field": field,
            "mincount": 1,
            "limit": limit,
            "offset": offset,
            "numBuckets": True,
            "sort": "count asc" if ascending else "count desc",
        }
    }
    return [
        ("q", "*:*"),
        ("rows", 0),
        ("json.facet", json.dumps(facet)),
        ("ol.label", REQUEST_LABEL),
        ("wt", "json"),
    ]


def build_contains_params(field: str, contains: str, scan_limit: int, solr_sort: str) -> list[tuple[str, object]]:
    """Solr params for substring enumeration via classic ``facet.contains``.

    ``facet.contains`` is Solr's only substring filter over facet *values*; JSON
    faceting silently ignores a ``contains`` key. The substring is a literal param
    value, never spliced into query syntax.
    """
    return [
        ("q", "*:*"),
        ("rows", 0),
        ("facet", "true"),
        ("facet.field", field),
        ("facet.mincount", 1),
        ("facet.contains", contains),
        ("facet.contains.ignoreCase", "true"),
        ("facet.limit", scan_limit),
        ("facet.sort", solr_sort),
        ("ol.label", REQUEST_LABEL),
        ("wt", "json"),
    ]


def postprocess_contains(
    pairs: list[tuple[str, int]],
    max_works: int | None,
    ascending: bool,
    offset: int,
    limit: int,
    scan_cap: int,
) -> tuple[list[tuple[str, int]], bool, bool]:
    """Filter, order and page substring matches that Solr returned unordered-by-count.

    Returns ``(page, has_more, truncated)``. ``truncated`` means Solr returned a full
    ``scan_cap`` of matches, so the match set was larger than we scanned and the result
    may be missing values. ``has_more`` means the scanned set has more pages after this
    one (distinct from ``truncated``, which is about scan completeness).

    >>> postprocess_contains(
    ...     [("a fiction", 5), ("b fiction", 1), ("c fiction", 3)],
    ...     max_works=3, ascending=True, offset=0, limit=10, scan_cap=2000)
    ([('b fiction', 1), ('c fiction', 3)], False, False)
    """
    truncated = len(pairs) >= scan_cap
    items = pairs
    if max_works is not None:
        items = [(v, c) for v, c in items if c <= max_works]
    items = sorted(items, key=lambda vc: vc[1], reverse=not ascending)
    page = items[offset : offset + limit]
    has_more = (offset + limit) < len(items)
    return page, has_more, truncated


def _flatten_facet(result: dict, field: str) -> list[tuple[str, int]]:
    """Solr returns classic facet counts as a flat ``[value, count, value, count, ...]``."""
    flat = result["facet_counts"]["facet_fields"][field]
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


async def _run_solr_async(params: list[tuple[str, object]]) -> dict:
    from urllib.parse import urlencode

    resp = await get_solr().raw_request("select", urlencode(params, doseq=True))
    return resp.json()


_run_solr = async_bridge.wrap(_run_solr_async, "subject_counts")


def exact_count(field: str, subject: str) -> int:
    result = _run_solr(build_exact_count_params(field, subject))
    return result["response"]["numFound"]


def enumerate_subjects(
    field: str,
    contains: str | None,
    max_works: int | None,
    ascending: bool,
    offset: int,
    limit: int,
) -> tuple[list[tuple[str, int]], bool, bool]:
    """Return ``(items, has_more, truncated)`` for one enumeration page."""
    if contains and ascending:
        # Rare-tail with a substring: classic faceting can filter by substring but not
        # sort by count, so we over-fetch the match set and order it ourselves. A match
        # set larger than the scan cap is reported truncated rather than silently cut.
        result = _run_solr(build_contains_params(field, contains, CONTAINS_SCAN_CAP, "index"))
        pairs = _flatten_facet(result, field)
        return postprocess_contains(pairs, max_works, ascending=True, offset=offset, limit=limit, scan_cap=CONTAINS_SCAN_CAP)

    if contains:
        # Descending top-N needs only the top offset+limit matches, which classic
        # faceting returns exactly and cheaply; one extra row tells us a further page
        # exists. This is a has_more probe, not truncation.
        result = _run_solr(build_contains_params(field, contains, offset + limit + 1, "count"))
        pairs = _flatten_facet(result, field)
        page, has_more, _ = postprocess_contains(pairs, max_works=None, ascending=False, offset=offset, limit=limit, scan_cap=offset + limit + 2)
        return page, has_more, False

    result = _run_solr(build_enumerate_params(field, limit, offset, ascending))
    facet = result["facets"].get("s", {})
    buckets = [(b["val"], b["count"]) for b in facet.get("buckets", [])]
    if max_works is not None:
        kept = [(v, c) for v, c in buckets if c <= max_works]
        # buckets arrive count-ascending, so a short page means we reached the first
        # value above the cutoff — there is no further rare tail to page into.
        has_more = len(kept) == len(buckets) == limit
        buckets = kept
    else:
        # numBuckets is the exact distinct-value total, so paging is precise.
        has_more = (offset + len(buckets)) < facet.get("numBuckets", offset + len(buckets))
    return buckets, has_more, False


class subject_counts(delegate.page):
    path = r"/search/subjects/counts(?:\.json)?"

    def GET(self):
        web.header("Content-Type", "application/json")
        try:
            return delegate.RawText(json.dumps(self.respond()))
        except InvalidSubjectQuery as e:
            web.ctx.status = "400 Bad Request"
            return delegate.RawText(json.dumps({"error": str(e)}))

    def respond(self) -> dict:
        i = web.input(
            subject_type="subject",
            subject=None,
            contains=None,
            max_works=None,
            sort=None,
            limit=None,
            offset=None,
        )
        field = resolve_facet_field(i.subject_type)

        if i.subject is not None:
            return {
                "subject_type": i.subject_type,
                "subject": i.subject,
                "work_count": exact_count(field, i.subject),
            }

        max_works = None
        if i.max_works is not None:
            max_works = safeint(i.max_works, None)
            if max_works is None or max_works < 0:
                raise InvalidSubjectQuery("max_works must be a non-negative integer")

        limit = min(max(safeint(i.limit, DEFAULT_LIMIT), 1), MAX_LIMIT)
        offset = max(safeint(i.offset, 0), 0)
        contains = i.contains or None
        # The rare tail is count-ascending; so is an explicit sort=count_asc.
        ascending = max_works is not None or i.sort == "count_asc"

        items, has_more, truncated = enumerate_subjects(field, contains, max_works, ascending, offset, limit)
        return {
            "subject_type": i.subject_type,
            "contains": contains,
            "max_works": max_works,
            "sort": "count_asc" if ascending else "count",
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "truncated": truncated,
            "subjects": [{"subject": v, "work_count": c} for v, c in items],
        }


def setup():
    pass
