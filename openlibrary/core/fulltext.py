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


def hit_ocaid(hit: dict) -> str:
    """The archive.org identifier a full-text hit was found in."""
    return hit.get("fields", {}).get("identifier", [""])[0]


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
    params = {
        "q": q,
        "from": offset,
        "size": limit,
        **({"nofacets": "true"} if not facets else {}),
        "olonly": "true",
    }
    # `lang` filters on the FTS index's normalized languageSorter field and
    # takes an English name ("German", not "ger"). It has to stay a request
    # param: a languageSorter: clause inside `q` would flip the endpoint to
    # its Lucene parser, which silently ignores olonly and searches all of
    # archive.org. The param is single-valued — the handlers narrow to one
    # language before calling, so the UI can't promise a filter we'd drop.
    if languages:
        params["lang"] = languages[0]
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
        for hit, ocaid in zip(hits, ocaids):
            if ed := editions_by_ocaid.get(ocaid):
                hit["edition"] = format_book_data(ed, fetch_availability=False) if js else ed
                hit["availability"] = availability.get(ocaid, {})
    return ia_results


fulltext_search = async_bridge.wrap(fulltext_search_async)
