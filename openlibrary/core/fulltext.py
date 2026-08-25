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


def build_fulltext_query(q: str, languages: list[str] | None = None, readable: bool = False) -> str:
    """Combine the user's query with filter clauses.

    The FTS endpoint parses ``q`` as a Lucene query, so filters are ANDed
    field clauses. The user query is parenthesized so its own OR/AND
    structure can't leak into the filters, and quotes are stripped from
    language values so they can't break out of their clause.

    >>> build_fulltext_query("moby dick")
    'moby dick'
    >>> build_fulltext_query("moby dick", ["French"])
    '(moby dick) AND languageSorter:"French"'
    >>> build_fulltext_query("moby dick", ["French", "German"])
    '(moby dick) AND (languageSorter:"French" OR languageSorter:"German")'
    >>> build_fulltext_query("whale", ['Fre"nch'])
    '(whale) AND languageSorter:"French"'
    >>> build_fulltext_query("whale", readable=True)
    '(whale) AND (collection:(inlibrary) OR (!collection:(printdisabled)))'
    """
    clauses = []
    if names := [clean for lang in languages or [] if (clean := lang.replace('"', "").strip())]:
        lang_clauses = [f'languageSorter:"{name}"' for name in names]
        # A single field clause must stay bare: the FTS parser matches
        # nothing for a lone parenthesized term like (languageSorter:"French").
        clauses.append(lang_clauses[0] if len(lang_clauses) == 1 else "(" + " OR ".join(lang_clauses) + ")")
    if readable:
        # Readable = public or borrowable scans. Mirrors core.lending's
        # collection heuristic: lendable (inlibrary) or not print-disabled-only.
        clauses.append("(collection:(inlibrary) OR (!collection:(printdisabled)))")
    if not clauses:
        return q
    return " AND ".join([f"({q})", *clauses])


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


async def fulltext_search_async(q, page=1, offset=None, limit=100, js=False, facets=False):
    if offset is None:
        offset = (page - 1) * limit
    params = {
        "q": q,
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
        ocaids = [hit["fields"].get("identifier", [""])[0] for hit in hits]
        availability = await get_availability_async("identifier", ocaids)
        if "error" in availability:
            availability = {}

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
