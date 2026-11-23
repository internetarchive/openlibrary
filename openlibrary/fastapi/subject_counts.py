"""Read-only endpoint for exact subject counts and enumeration over Solr's raw
``subject_facet`` field.

``subject_facet`` stores the exact subject string (case and punctuation preserved), so
Solr can count a precise variant separately from its spelling/case siblings — which
``/search.json`` (which re-parses the query and mangles exact matches with commas) and
``/search/subjects.json`` (which searches normalized subject pages) cannot. This endpoint
wraps that faceting without exposing raw Solr to callers.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from openlibrary.plugins.worksearch.search import get_solr

router = APIRouter()

SUBJECT_TYPE_TO_FACET = {
    "subject": "subject_facet",
    "person": "person_facet",
    "place": "place_facet",
    "time": "time_facet",
}

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
# Ceiling on offset+limit. Besides bounding deep paging, it caps the Solr facet.limit the
# contains path derives from offset, so a caller cannot force a huge allocation.
MAX_WINDOW = 10_000
# Most subject strings one batch exact-count request may ask about.
MAX_BATCH = 100
# Per-string length caps, so a batch can't carry multi-megabyte terms.
MAX_SUBJECT_LEN = 500
MIN_CONTAINS_LEN = 2
MAX_CONTAINS_LEN = 200
# classic facet.contains is Solr's only substring filter over facet values, but it cannot
# sort by count, so for the rare tail we pull the whole match set and order it in-process.
# A match set larger than this cannot yield a reliable rare tail, so such a request is
# refused rather than answered from an arbitrary slice.
CONTAINS_SCAN_CAP = 5_000

REQUEST_LABEL = "SUBJECT_COUNTS_API"
_UNAVAILABLE = "subject counts are temporarily unavailable"


class SubjectType(StrEnum):
    subject = "subject"
    person = "person"
    place = "place"
    time = "time"


class SubjectCountsParams(BaseModel):
    subject: list[str] = Field(
        default_factory=list,
        description="Exact subject string(s) to count. Repeat for a batch (e.g. ?subject=A&subject=B).",
    )
    subject_type: SubjectType = Field(SubjectType.subject, description="Which facet to count over.")
    contains: str | None = Field(None, max_length=MAX_CONTAINS_LEN, description="Case-insensitive substring filter for enumeration.")
    max_works: int | None = Field(None, ge=0, description="Only return subjects used in at most this many works (the rare tail).")
    sort: Literal["count", "count_asc"] = Field("count", description="count = most-used first; count_asc = rarest first.")
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _validate(self) -> SubjectCountsParams:
        if self.subject:
            if len(self.subject) > MAX_BATCH:
                raise ValueError(f"at most {MAX_BATCH} subject values per request")
            if any(not s.strip() for s in self.subject):
                raise ValueError("subject must be a non-empty string")
            if any(len(s) > MAX_SUBJECT_LEN for s in self.subject):
                raise ValueError(f"each subject must be at most {MAX_SUBJECT_LEN} characters")
            return self
        if self.offset + self.limit > MAX_WINDOW:
            raise ValueError(f"offset + limit must not exceed {MAX_WINDOW}")
        if self.contains is not None:
            trimmed = self.contains.strip()
            if not trimmed:
                self.contains = None
            elif len(trimmed) < MIN_CONTAINS_LEN:
                raise ValueError(f"contains must be at least {MIN_CONTAINS_LEN} characters")
            else:
                self.contains = trimmed
        return self


def build_batch_count_params(field: str, subjects: list[str]) -> list[tuple[str, object]]:
    """Solr params that count each exact subject string in a single request.

    Each string is bound to its own ``vN`` request param and read by ``{!term f=... v=$vN}``,
    so Solr matches it as a literal term and never parses it as query syntax — the injection
    boundary. ``field`` is always a whitelisted facet name, never caller text.
    """
    facet = {f"c{idx}": {"type": "query", "q": "{!term f=%s v=$v%d}" % (field, idx)} for idx in range(len(subjects))}
    params: list[tuple[str, object]] = [("q", "*:*"), ("rows", 0), ("json.facet", json.dumps(facet))]
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
    """Solr params for substring enumeration via classic ``facet.contains`` (Solr's only
    substring filter over facet values). The substring is a literal param value."""
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
    """True when Solr timed out and returned approximate results, so counts aren't
    authoritative."""
    return bool(result.get("responseHeader", {}).get("partialResults"))


def _flatten_facet(result: dict, field: str) -> list[tuple[str, int]]:
    """Classic facet counts come back as a flat ``[value, count, value, count, ...]``."""
    try:
        flat = result["facet_counts"]["facet_fields"][field]
        return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
    except (KeyError, TypeError, IndexError) as e:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e


async def _run_solr(params: list[tuple[str, object]]) -> dict:
    resp = await get_solr().raw_request("select", urlencode(params, doseq=True))
    try:
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e
    try:
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e


async def batch_exact_count(field: str, subjects: list[str]) -> tuple[list[int], bool]:
    """Return ``(counts, partial)`` with one count per subject, in request order."""
    result = await _run_solr(build_batch_count_params(field, subjects))
    try:
        facets = result.get("facets", {})
        counts = [int(facets.get(f"c{idx}", {}).get("count", 0)) for idx in range(len(subjects))]
    except (AttributeError, TypeError, ValueError) as e:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e
    return counts, is_partial(result)


async def enumerate_subjects(
    field: str,
    contains: str | None,
    max_works: int | None,
    ascending: bool,
    offset: int,
    limit: int,
) -> tuple[list[tuple[str, int]], bool, bool]:
    """Return ``(items, has_more, partial)`` for one enumeration page."""
    if contains and ascending:
        result = await _run_solr(build_contains_params(field, contains, CONTAINS_SCAN_CAP, "index"))
        pairs = _flatten_facet(result, field)
        if len(pairs) >= CONTAINS_SCAN_CAP:
            # We only have an alphabetical slice, so the globally rarest values may be
            # unscanned — refusing is honest where returning them would be wrong.
            raise HTTPException(
                status_code=400,
                detail="`contains` matches too many subjects to rank the rare tail; use a more specific substring",
            )
        kept = pairs if max_works is None else [vc for vc in pairs if vc[1] <= max_works]
        items = sorted(kept, key=lambda vc: vc[1])
        return items[offset : offset + limit], (offset + limit) < len(items), is_partial(result)

    if contains:
        # Descending top-N needs only the top offset+limit matches (exact and cheap from
        # classic faceting); one extra row tells us whether a further page exists.
        result = await _run_solr(build_contains_params(field, contains, offset + limit + 1, "count"))
        pairs = _flatten_facet(result, field)
        return pairs[offset : offset + limit], len(pairs) > offset + limit, is_partial(result)

    result = await _run_solr(build_enumerate_params(field, limit, offset, ascending))
    try:
        facet = result.get("facets", {}).get("s", {})
        buckets = [(b["val"], b["count"]) for b in facet.get("buckets", [])]
    except (AttributeError, TypeError, KeyError) as e:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e
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


@router.get("/search/subjects/counts.json", tags=["search"])
async def subject_counts_json(params: Annotated[SubjectCountsParams, Query()]):
    """Exact work counts for precise subject strings, and enumeration of subjects by count.

    - Exact count: ``?subject=<string>`` (repeat for a batch) returns the work count for each
      exact string, distinguishing case/punctuation variants.
    - Enumerate: with no ``subject``, list subject values and counts, optionally filtered by
      ``contains`` (substring) and/or ``max_works`` (rare tail), paged by ``offset``/``limit``.
    """
    field = SUBJECT_TYPE_TO_FACET[params.subject_type.value]

    if params.subject:
        counts, partial = await batch_exact_count(field, params.subject)
        if len(params.subject) == 1:
            return {
                "subject_type": params.subject_type.value,
                "subject": params.subject[0],
                "work_count": counts[0],
                "partial": partial,
            }
        return {
            "subject_type": params.subject_type.value,
            "partial": partial,
            "subjects": [{"subject": s, "work_count": c} for s, c in zip(params.subject, counts, strict=True)],
        }

    # The rare tail is count-ascending, and so is an explicit sort=count_asc.
    ascending = params.max_works is not None or params.sort == "count_asc"
    items, has_more, partial = await enumerate_subjects(field, params.contains, params.max_works, ascending, params.offset, params.limit)
    return {
        "subject_type": params.subject_type.value,
        "contains": params.contains,
        "max_works": params.max_works,
        "sort": "count_asc" if ascending else "count",
        "limit": params.limit,
        "offset": params.offset,
        "has_more": has_more,
        "partial": partial,
        "subjects": [{"subject": v, "work_count": c} for v, c in items],
    }
