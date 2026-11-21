"""Resolve identifiers and search the catalog for ``editionView`` results.

Exact identifier resolution uses Infobase (one ``/things`` query per
identifier); text search uses the existing Solr index. Both are read-only.
"""

from __future__ import annotations

import logging
import re
from typing import Any, NamedTuple

from fastapi.concurrency import run_in_threadpool

from openlibrary.atproto.edition_view import as_list, build_edition_view, olid_from_key
from openlibrary.atproto.errors import RecordError
from openlibrary.atproto.models import EditionResults, Identifier, SearchEditionsRequest
from openlibrary.plugins.worksearch.code import run_solr_query_async
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme
from openlibrary.utils.isbn import get_isbn_10_and_13
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.atproto")

OPENLIBRARY_OLID_PATTERN = re.compile(r"^OL\d+M$")


class InvalidQuery(Exception):
    """The request carries no usable search term."""


class Bundle(NamedTuple):
    edition: Any
    authors: list
    languages: list[str]


def author_key(ref) -> str | None:
    """Edition authors are ``{"key": ...}``; work authors wrap ``{"author": ...}``."""
    if not hasattr(ref, "get"):
        return None
    if author := ref.get("author"):
        return author.get("key")
    return ref.get("key")


def _work_key(edition) -> str | None:
    works = as_list(edition.get("works"))
    return works[0].get("key") if works and hasattr(works[0], "get") else None


def _ref_key(ref) -> str | None:
    return ref.get("key") if hasattr(ref, "get") else None


def bcp47_tag(key: str, things: dict[str, Any]) -> str:
    """``/languages/eng`` -> ``en``; keep the MARC code when nothing is mapped."""
    language = things.get(key) or {}
    iso_639_1 = as_list((language.get("identifiers") or {}).get("iso_639_1"))
    tag = iso_639_1[0] if iso_639_1 else None
    return tag if isinstance(tag, str) and tag else olid_from_key(key)


def load_bundle(keys: list[str]) -> dict[str, Bundle]:
    """Load editions with their resolved authors, falling back to work authors."""
    if not keys:
        return {}
    s = site.get()
    editions = s.get_many(sorted(set(keys)))
    direct: dict[str, list[str]] = {}
    work_keys: dict[str, str | None] = {}
    language_keys: dict[str, list[str]] = {}
    for edition in editions:
        direct[edition.key] = [key for ref in as_list(edition.get("authors")) if (key := author_key(ref))]
        work_keys[edition.key] = _work_key(edition)
        language_keys[edition.key] = [key for ref in as_list(edition.get("languages")) if (key := _ref_key(ref))]

    refs = (
        {key for keys_ in direct.values() for key in keys_}
        | {key for key in work_keys.values() if key}
        | {key for keys_ in language_keys.values() for key in keys_}
    )
    related = {thing.key: thing for thing in s.get_many(sorted(refs))}

    fallback: dict[str, list[str]] = {}
    for edition in editions:
        if direct[edition.key]:
            continue
        work = related.get(work_keys[edition.key])
        if work:
            fallback[edition.key] = [key for ref in as_list(work.get("authors")) if (key := author_key(ref))]

    missing = sorted({key for keys_ in fallback.values() for key in keys_} - related.keys())
    related |= {thing.key: thing for thing in s.get_many(missing)}

    return {
        edition.key: Bundle(
            edition=edition,
            authors=[related[key] for key in direct[edition.key] or fallback.get(edition.key, []) if key in related],
            languages=[bcp47_tag(key, related) for key in language_keys[edition.key]],
        )
        for edition in editions
    }


def _edition_keys(s, query: dict) -> list[str]:
    return [key for key in s.things(query) if isinstance(key, str)]


def _lookup(s, issuer: str, value: str) -> list[str]:
    if issuer == "openlibrary":
        olid = olid_from_key(value)
        if not OPENLIBRARY_OLID_PATTERN.match(olid):
            return []
        # Existence is checked here so a well-formed but unknown OLID cannot
        # inflate the reported total above the number of real matches.
        return _edition_keys(s, {"type": "/type/edition", "key": f"/books/{olid}"})
    if issuer in ("isbn13", "isbn10"):
        isbn_10, isbn_13 = get_isbn_10_and_13(value)
        keys = _edition_keys(s, {"type": "/type/edition", "isbn_13": isbn_13}) if isbn_13 else []
        return keys + (_edition_keys(s, {"type": "/type/edition", "isbn_10": isbn_10}) if isbn_10 else [])
    if issuer == "oclc":
        return _edition_keys(s, {"type": "/type/edition", "oclc_numbers": value})
    if issuer == "lccn":
        return _edition_keys(s, {"type": "/type/edition", "lccn": value})
    if issuer == "asin":
        return _edition_keys(s, {"type": "/type/edition", "identifiers": {"amazon": value}})
    return []


def resolve_identifier_keys(identifiers: list[Identifier]) -> list[str]:
    """Edition keys matching any identifier exactly, in request then DB order."""
    s = site.get()
    keys: list[str] = []
    pairs = dict.fromkeys((identifier.issuer.strip().lower(), identifier.value.strip()) for identifier in identifiers)
    for issuer, value in pairs:
        if value:
            keys.extend(_lookup(s, issuer, value))
    return list(dict.fromkeys(keys))


def _phrase_filter(field: str, value: str) -> tuple[str, str]:
    """An ``fq`` phrase filter, so a structured hint cannot be widened by ``q``."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return "fq", f'{field}:"{escaped}"'


async def search_edition_keys(params: SearchEditionsRequest) -> tuple[list[str], int | None]:
    """Return one page of matching edition keys and the total, when Solr knows it."""
    if params.identifiers:
        keys = await run_in_threadpool(resolve_identifier_keys, params.identifiers)
        if keys:
            return keys[params.offset : params.offset + params.limit], len(keys)

    q = (params.q or "").strip()
    title = (params.title or "").strip()
    author = (params.author or "").strip()
    if not (q or title or author):
        raise InvalidQuery

    # Hints are filters, not boosts, so boolean text in ``q`` cannot widen them.
    extra_params = []
    if title:
        extra_params.append(_phrase_filter("title", title))
    if author:
        extra_params.append(_phrase_filter("author_name", author))

    response = await run_solr_query_async(
        EditionSearchScheme(),
        {"q": q or "*:*"},
        rows=params.limit,
        offset=params.offset,
        fields=["key"],
        facet=False,
        spellcheck_count=0,
        extra_params=extra_params or None,
        request_label="EDITION_SEARCH_API",
    )
    if response.error:
        logger.warning("edition search failed: %s", response.error)
        return [], None
    # A partial count is a lower bound, so report no total rather than a lie.
    return [doc["key"] for doc in response.docs], response.num_found if response.num_found_exact else None


def build_results(keys: list[str], bundles: dict[str, Bundle], total: int | None, offset: int, limit: int) -> dict:
    items = []
    for key in keys:
        bundle = bundles.get(key)
        if bundle is None:
            continue
        try:
            items.append(build_edition_view(bundle.edition, bundle.authors, bundle.languages))
        except RecordError as e:
            logger.warning("skipping %s: %s", key, e)
    results = EditionResults(
        items=items,
        hasMore=bool(items) and (total is None or offset + limit < total),
        total=total if offset == 0 else None,
    )
    return results.model_dump(exclude_none=True)
