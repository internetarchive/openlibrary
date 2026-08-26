import json
import logging
from urllib.parse import urlencode

import httpx

from infogami import config
from openlibrary.core.lending import get_availability_async
from openlibrary.plugins.openlibrary.home import format_book_data
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import req_context, site

logger = logging.getLogger("openlibrary.inside")


def language_name_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Bidirectional MARC-code ↔ English-name maps for the FTS index's
    languageSorter field: (code → name, casefolded name → code). Built from
    the OL language catalogue in one fetch — reuse the result within a request.
    """
    from openlibrary.plugins.upstream.utils import get_languages, safeget

    code_to_name: dict[str, str] = {}
    name_to_code: dict[str, str] = {}
    for key, language in get_languages().items():
        code = key.split("/")[-1]
        # Prefer the English translation: `name` itself isn't reliably the
        # bare English name (e.g. "French / français" in some records).
        name = safeget(lambda: language["name_translated"]["en"][0]) or language.name
        code_to_name[code] = name
        name_to_code.setdefault(name.casefold(), code)
    return code_to_name, name_to_code


def normalize_language_name(lang: str, code_to_name: dict[str, str] | None = None) -> str:
    """Map a MARC language code (e.g. "fre") to the English name the FTS
    index's languageSorter field stores ("French"). Values that aren't MARC
    codes (already-normalized names, e.g. facet bucket keys) pass through.
    """
    if code_to_name is None:
        code_to_name, _ = language_name_maps()
    lang = lang.strip()
    return code_to_name.get(lang.casefold(), lang)


def build_fulltext_query(q: str, languages: list[str] | None = None) -> str:
    """Combine the user's query with filter clauses.

    The FTS endpoint parses ``q`` as a Lucene query, so filters are ANDed
    field clauses. The user query is parenthesized so its own OR/AND
    structure can't leak into the filters, and quotes are stripped from
    language values so they can't break out of their clause.

    Readability is deliberately not expressible here: any field clause
    switches the endpoint to its Lucene parser, which silently ignores
    ``olonly=true`` and searches all of archive.org. Language has to pay
    that price to work at all — ``fulltext_search_async`` claws it back by
    dropping hits with no OL edition (``filter_ol_linked``). Readability
    doesn't, so it's applied to the fetched hits instead — see
    ``filter_readable``.

    >>> build_fulltext_query("moby dick")
    'moby dick'
    >>> build_fulltext_query("moby dick", ["French"])
    '(moby dick) AND languageSorter:"French"'
    >>> build_fulltext_query("moby dick", ["French", "German"])
    '(moby dick) AND (languageSorter:"French" OR languageSorter:"German")'
    >>> build_fulltext_query("whale", ['Fre"nch'])
    '(whale) AND languageSorter:"French"'
    """
    if not (names := [clean for lang in languages or [] if (clean := lang.replace('"', "").strip())]):
        return q
    lang_clauses = [f'languageSorter:"{name}"' for name in names]
    # A single field clause must stay bare: the FTS parser matches
    # nothing for a lone parenthesized term like (languageSorter:"French").
    clause = lang_clauses[0] if len(lang_clauses) == 1 else "(" + " OR ".join(lang_clauses) + ")"
    return f"({q}) AND {clause}"


def hit_ocaid(hit: dict) -> str:
    """The archive.org identifier a full-text hit was found in."""
    return hit.get("fields", {}).get("identifier", [""])[0]


def filter_ol_linked(hits: list[dict], editions_by_ocaid: dict) -> list[dict]:
    """Drop hits whose scan has no OL edition.

    Applied when the query carries a field clause (a language filter): that
    flips the FTS endpoint to its Lucene parser, which silently ignores
    ``olonly=true`` and searches all of archive.org — magazines and unlinked
    scans included. Hydration already looked every ocaid up, so this restores
    the OL-only scope at no extra cost. ``total`` still counts the dropped
    hits, so a filtered page can render short — same tradeoff as
    ``filter_readable``.

    >>> hits = [{"fields": {"identifier": ["linked"]}}, {"fields": {"identifier": ["unlinked"]}}]
    >>> [hit_ocaid(hit) for hit in filter_ol_linked(hits, {"linked": "ed"})]
    ['linked']
    """
    return [hit for hit in hits if hit_ocaid(hit) in editions_by_ocaid]


def filter_readable(hits: list[dict], availability: dict) -> list[dict]:
    """Drop hits the visitor can't actually open — print-disabled-only scans,
    which are 20-70% of an unfiltered result page.

    Uses the same test as the edition page (``is_readable`` for public domain,
    ``is_lendable`` for borrowable) rather than guessing from the scan's IA
    collections. Fails open: with no availability data at all, a whole page of
    results would otherwise vanish.

    >>> hits = [{"fields": {"identifier": ["open"]}}, {"fields": {"identifier": ["locked"]}}]
    >>> availability = {"open": {"is_readable": True}, "locked": {"is_printdisabled": True}}
    >>> [hit_ocaid(hit) for hit in filter_readable(hits, availability)]
    ['open']
    >>> len(filter_readable(hits, {}))
    2
    """
    if not availability:
        return hits
    return [hit for hit in hits if (status := availability.get(hit_ocaid(hit), {})) and (status.get("is_readable") or status.get("is_lendable"))]


async def fulltext_search_api(params):
    from openlibrary.core.lending import (
        config_fts_context,
        config_ia_ol_metadata_write_s3,
    )

    if not hasattr(config, "plugin_inside"):
        return {"error": "Unable to prepare search engine"}
    search_endpoint = config.plugin_inside["search_endpoint"]
    search_select = search_endpoint + "?" + urlencode(params, "utf-8")
    headers = {
        "x-preferred-client-id": req_context.get().x_forwarded_for or "ol-internal",
        "x-application-id": "openlibrary",
    }
    if config_fts_context is not None:
        headers["x-search-request-context"] = config_fts_context
    if config_ia_ol_metadata_write_s3:
        headers["authorization"] = "LOW {s3_key}:{s3_secret}".format(**config_ia_ol_metadata_write_s3)

    logger.debug("URL: " + search_select)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(search_select, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError:
        return {"error": "Unable to query search engine"}
    except json.decoder.JSONDecodeError:
        return {"error": "Error converting search engine data to JSON"}


async def fulltext_search_async(q, page=1, offset=None, limit=100, js=False, facets=False, readable=False, languages=None):
    if offset is None:
        offset = (page - 1) * limit
    query = build_fulltext_query(q, languages=languages)
    # A changed query means a field clause was injected, which flips the
    # endpoint to its Lucene parser and disables olonly — so the OL-only
    # scope has to be restored client-side (see filter_ol_linked).
    ol_only = query != q
    params = {
        "q": query,
        "from": offset,
        "size": limit,
        **({"nofacets": "true"} if not facets else {}),
        "olonly": "true",
    }
    ia_results = await fulltext_search_api(params)

    # Guard on the hits list itself: the old `ia_results["hits"]` check passed
    # for a zero-hit response ({"hits": [], ...} is a truthy dict), running the
    # whole hydration pipeline for nothing.
    if "error" not in ia_results and (hits := ia_results.get("hits", {}).get("hits", [])):
        ocaids = [hit_ocaid(hit) for hit in hits]
        availability = await get_availability_async("identifier", ocaids)
        if "error" in availability:
            availability = {}

        if readable:
            # Filter before hydrating: the dropped hits then cost no Infobase
            # lookup at all. `total` still counts them, so a filtered page can
            # render fewer than `limit` rows — deliberate, and the reason the
            # results line drops its "1 - 20 of" range when the filter is on.
            hits = filter_readable(hits, availability)
            ia_results["hits"]["hits"] = hits
            if not hits:
                return ia_results
            ocaids = [hit_ocaid(hit) for hit in hits]

        edition_keys = list(site.get().things({"type": "/type/edition", "ocaid": ocaids, "limit": len(ocaids)}))
        editions = site.get().get_many(edition_keys)
        # Keyed by ocaid rather than matched via ocaids.index(): index() finds
        # only the first occurrence, so when two hits share an ocaid the second
        # hit got no edition and was silently dropped by the templates.
        editions_by_ocaid = {ed.ocaid: ed for ed in editions}
        if ol_only:
            hits = filter_ol_linked(hits, editions_by_ocaid)
            ia_results["hits"]["hits"] = hits
            ocaids = [hit_ocaid(hit) for hit in hits]
        for hit, ocaid in zip(hits, ocaids):
            if ed := editions_by_ocaid.get(ocaid):
                hit["edition"] = format_book_data(ed, fetch_availability=False) if js else ed
                hit["availability"] = availability.get(ocaid, {})
    return ia_results


fulltext_search = async_bridge.wrap(fulltext_search_async)
