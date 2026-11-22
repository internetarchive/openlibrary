"""Read-only endpoint for exact subject counts and enumeration over Solr's raw
``subject_facet`` field.

``subject_facet`` stores the exact subject string (case and punctuation preserved), so
Solr can count a precise variant separately from its spelling/case siblings — which
``/search.json`` (which re-parses the query and mangles exact matches with commas) and
``/search/subjects`` (which searches normalized subject pages) cannot. This endpoint
wraps that faceting without exposing raw Solr to callers.
"""

import json
import logging
from urllib.parse import urlencode

import httpx
import web

from infogami.utils import delegate
from infogami.utils.view import safeint
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.async_utils import async_bridge

logger = logging.getLogger("openlibrary.subject_counts")

SUBJECT_TYPE_TO_FACET = {
    "subject": "subject_facet",
    "person": "person_facet",
    "place": "place_facet",
    "time": "time_facet",
}

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
# Ceiling on offset+limit. Besides bounding deep paging, it caps the Solr facet.limit
# the contains path derives from offset, so a caller cannot force a huge allocation.
MAX_WINDOW = 10_000
# Most subject strings one batch exact-count request may ask about.
MAX_BATCH = 100
MIN_CONTAINS_LEN = 2
# classic facet.contains is Solr's only substring filter over facet values, but it
# cannot sort by count, so for the rare tail we pull the whole match set and order it
# in-process. A match set larger than this cannot yield a reliable rare tail, so such a
# request is refused rather than answered from an arbitrary slice.
CONTAINS_SCAN_CAP = 5_000

REQUEST_LABEL = "SUBJECT_COUNTS_API"


class InvalidSubjectQuery(ValueError):
    """A caller-supplied parameter was invalid; surfaced as HTTP 400."""


class SubjectCountsUnavailable(Exception):
    """Solr failed or returned an unexpected shape; surfaced as HTTP 503."""


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


def build_batch_count_params(field: str, subjects: list[str]) -> list[tuple[str, object]]:
    """Solr params that count each exact subject string in a single request.

    Each string is bound to its own ``vN`` request param and read by ``{!term f=... v=$vN}``,
    so Solr matches it as a literal term and never parses it as query syntax — the injection
    boundary. ``field`` is always a whitelisted facet name, never caller text.
    """
    facet = {f"c{idx}": {"type": "query", "q": "{!term f=%s v=$v%d}" % (field, idx)} for idx in range(len(subjects))}
    params: list[tuple[str, object]] = [
        ("q", "*:*"),
        ("rows", 0),
        ("json.facet", json.dumps(facet)),
    ]
    params += [(f"v{idx}", s) for idx, s in enumerate(subjects)]
    params += [("ol.label", REQUEST_LABEL), ("wt", "json")]
    return params


def build_enumerate_params(field: str, limit: int, offset: int, ascending: bool) -> list[tuple[str, object]]:
    """Solr params for substring-free enumeration via the JSON Facet API — the only Solr
    mode that sorts terms by count ascending (the rare tail) and pages natively."""
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
    """Solr params for substring enumeration via classic ``facet.contains``. The substring
    is a literal param value, never spliced into query syntax."""
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


def is_partial(result: dict) -> bool:
    """True when Solr timed out and returned approximate/truncated results, so the counts
    are not authoritative."""
    return bool(result.get("responseHeader", {}).get("partialResults"))


def _flatten_facet(result: dict, field: str) -> list[tuple[str, int]]:
    """Classic facet counts come back as a flat ``[value, count, value, count, ...]``."""
    try:
        flat = result["facet_counts"]["facet_fields"][field]
    except (KeyError, TypeError) as e:
        raise SubjectCountsUnavailable("unexpected Solr facet response") from e
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


async def _run_solr_async(params: list[tuple[str, object]]) -> dict:
    resp = await get_solr().raw_request("select", urlencode(params, doseq=True))
    try:
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise SubjectCountsUnavailable("Solr request failed") from e
    try:
        return resp.json()
    except ValueError as e:
        raise SubjectCountsUnavailable("Solr returned a non-JSON response") from e


_run_solr = async_bridge.wrap(_run_solr_async, "subject_counts")


def batch_exact_count(field: str, subjects: list[str]) -> tuple[list[int], bool]:
    """Return ``(counts, partial)`` with one count per subject, in request order."""
    result = _run_solr(build_batch_count_params(field, subjects))
    facets = result.get("facets", {})
    counts = [int(facets.get(f"c{idx}", {}).get("count", 0)) for idx in range(len(subjects))]
    return counts, is_partial(result)


def enumerate_subjects(
    field: str,
    contains: str | None,
    max_works: int | None,
    ascending: bool,
    offset: int,
    limit: int,
) -> tuple[list[tuple[str, int]], bool, bool]:
    """Return ``(items, has_more, partial)`` for one enumeration page."""
    if contains and ascending:
        result = _run_solr(build_contains_params(field, contains, CONTAINS_SCAN_CAP, "index"))
        pairs = _flatten_facet(result, field)
        if len(pairs) >= CONTAINS_SCAN_CAP:
            # We only have an alphabetical slice, so the globally rarest values may be
            # unscanned — refusing is honest where returning them would be wrong.
            raise InvalidSubjectQuery("`contains` matches too many subjects to rank the rare tail; use a more specific substring")
        kept = pairs if max_works is None else [vc for vc in pairs if vc[1] <= max_works]
        items = sorted(kept, key=lambda vc: vc[1])
        return items[offset : offset + limit], (offset + limit) < len(items), is_partial(result)

    if contains:
        # Descending top-N needs only the top offset+limit matches (exact and cheap from
        # classic faceting); one extra row tells us whether a further page exists.
        result = _run_solr(build_contains_params(field, contains, offset + limit + 1, "count"))
        pairs = _flatten_facet(result, field)
        return pairs[offset : offset + limit], len(pairs) > offset + limit, is_partial(result)

    result = _run_solr(build_enumerate_params(field, limit, offset, ascending))
    facet = result.get("facets", {}).get("s", {})
    buckets = [(b["val"], b["count"]) for b in facet.get("buckets", [])]
    if max_works is not None:
        kept = [(v, c) for v, c in buckets if c <= max_works]
        # buckets arrive count-ascending, so a short page means we reached the first value
        # above the cutoff — there is no further rare tail to page into.
        has_more = len(kept) == len(buckets) == limit
        buckets = kept
    else:
        # numBuckets is the exact distinct-value total, so paging is precise.
        has_more = (offset + len(buckets)) < facet.get("numBuckets", offset + len(buckets))
    return buckets, has_more, is_partial(result)


class subject_counts(delegate.page):
    path = r"/search/subjects/counts(?:\.json)?"

    def GET(self):
        web.header("Content-Type", "application/json")
        try:
            return delegate.RawText(json.dumps(self.respond()))
        except InvalidSubjectQuery as e:
            web.ctx.status = "400 Bad Request"
            return delegate.RawText(json.dumps({"error": str(e)}))
        except SubjectCountsUnavailable, KeyError, IndexError, ValueError:
            # Keep Solr internals and stack traces off a public endpoint.
            logger.exception("subject counts query failed")
            web.ctx.status = "503 Service Unavailable"
            return delegate.RawText(json.dumps({"error": "subject counts are temporarily unavailable"}))

    def respond(self) -> dict:
        i = web.input(
            subject_type="subject",
            subject=[],
            contains=None,
            max_works=None,
            sort=None,
            limit=None,
            offset=None,
        )
        field = resolve_facet_field(i.subject_type)

        subjects = i.subject if isinstance(i.subject, list) else [i.subject]
        if subjects:
            return self._exact(i.subject_type, field, subjects)

        max_works = None
        if i.max_works is not None:
            max_works = safeint(i.max_works, None)
            if max_works is None or max_works < 0:
                raise InvalidSubjectQuery("max_works must be a non-negative integer")

        limit = min(max(safeint(i.limit, DEFAULT_LIMIT), 1), MAX_LIMIT)
        offset = max(safeint(i.offset, 0), 0)
        if offset + limit > MAX_WINDOW:
            raise InvalidSubjectQuery(f"offset + limit must not exceed {MAX_WINDOW}")

        contains = (i.contains or "").strip() or None
        if contains is not None and len(contains) < MIN_CONTAINS_LEN:
            raise InvalidSubjectQuery(f"contains must be at least {MIN_CONTAINS_LEN} characters")

        # The rare tail is count-ascending, and so is an explicit sort=count_asc.
        ascending = max_works is not None or i.sort == "count_asc"
        items, has_more, partial = enumerate_subjects(field, contains, max_works, ascending, offset, limit)
        return {
            "subject_type": i.subject_type,
            "contains": contains,
            "max_works": max_works,
            "sort": "count_asc" if ascending else "count",
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "partial": partial,
            "subjects": [{"subject": v, "work_count": c} for v, c in items],
        }

    def _exact(self, subject_type: str, field: str, subjects: list[str]) -> dict:
        if len(subjects) > MAX_BATCH:
            raise InvalidSubjectQuery(f"at most {MAX_BATCH} subject values per request")
        if any(not s.strip() for s in subjects):
            raise InvalidSubjectQuery("subject must be a non-empty string")
        counts, partial = batch_exact_count(field, subjects)
        if len(subjects) == 1:
            return {
                "subject_type": subject_type,
                "subject": subjects[0],
                "work_count": counts[0],
                "partial": partial,
            }
        return {
            "subject_type": subject_type,
            "partial": partial,
            "subjects": [{"subject": s, "work_count": c} for s, c in zip(subjects, counts, strict=True)],
        }


def setup():
    pass
