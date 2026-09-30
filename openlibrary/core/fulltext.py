import functools
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import web

from infogami import config
from openlibrary.core.carousels import format_book_data
from openlibrary.core.lending import get_availability_async
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import req_context, site

logger = logging.getLogger("openlibrary.inside")


# ── Language resolution ────────────────────────────────────────────────────


@functools.cache
def language_name_maps() -> tuple[dict[str, str], dict[str, str]]:
    """(code → English name, casefolded name → code) for the FTS languageSorter field."""
    from openlibrary.plugins.upstream.utils import get_languages, safeget

    code_to_name: dict[str, str] = {}
    name_to_code: dict[str, str] = {}
    for key, language in get_languages().items():
        code = key.split("/")[-1]
        # `name` isn't always bare English (e.g. "French / français").
        name = safeget(lambda: language["name_translated"]["en"][0]) or language.name
        code_to_name[code] = name
        name_to_code.setdefault(name.casefold(), code)
    return code_to_name, name_to_code


def resolve_language(values: Iterable[str] | None) -> tuple[str, str] | None:
    """(MARC code, English name) for the first usable value, given "fre" or "French".
    FTS `lang` is single-valued, so this is the one place a request narrows to one language."""
    code_to_name, name_to_code = language_name_maps()
    for raw in values or []:
        if not (lang := raw.strip()):
            continue
        code = name_to_code.get(lang.casefold(), lang.casefold())
        return code, code_to_name.get(code, lang)
    return None


# ── Response envelope → rows ───────────────────────────────────────────────
# The FTS wire format stops at fulltext_page(); templates and partials only see FulltextRow.


def _first(values: Any, default: Any = "") -> Any:
    """First element of a multi-valued FTS field, tolerating [] and non-lists."""
    if isinstance(values, list):
        return values[0] if values else default
    return default if values is None else values


def hit_ocaid(hit: dict) -> str:
    return _first(hit.get("fields", {}).get("identifier"))


# Word count at/above which an unquoted query reads as a passage, not a title.
PASSAGE_WORD_COUNT = 5


def is_passage_query(query: str) -> bool:
    """True for a quoted phrase or PASSAGE_WORD_COUNT+ words. Mirrors isPassageQuery() in search-modal/fulltext.js.

    >>> is_passage_query('"the best of times"')
    True
    >>> is_passage_query("it was the best of times")
    True
    >>> is_passage_query("happiness paradox")
    False
    """
    q = (query or "").strip()
    if not q:
        return False
    if re.search(r'"[^"]+"|“[^”]+”', q):
        return True
    return len(q.split()) >= PASSAGE_WORD_COUNT


def parse_snippet(snippet: str) -> list[tuple[str, bool]]:
    """Split a snippet into (text, is_match) segments on the API's {{{ }}} markers.
    Segments, not HTML, so the renderer escapes each part. Mirrors parseSnippet() in search-modal/fulltext.js.

    >>> parse_snippet("never came. But {{{Lokesh}}} had never")
    [('never came. But ', False), ('Lokesh', True), (' had never', False)]
    >>> parse_snippet("{{{red}}} rising and {{{red}}} falling")
    [('red', True), (' rising and ', False), ('red', True), (' falling', False)]
    >>> parse_snippet("no markers here")
    [('no markers here', False)]
    >>> parse_snippet("ends with {{{truncated")
    [('ends with ', False), ('truncated', True)]
    >>> parse_snippet("")
    []
    """
    if not snippet:
        return []
    segments: list[tuple[str, bool]] = []
    head, *rest = snippet.split("{{{")
    if head:
        segments.append((head, False))
    for chunk in rest:
        matched, marker, tail = chunk.partition("}}}")
        if matched:
            # Unbalanced marker = truncated snippet; keep it as a match.
            segments.append((matched, True))
        if marker and tail:
            segments.append((tail, False))
    return segments


@dataclass(frozen=True)
class Snippet:
    """One matched passage. No page number: the FTS index has none, so links let BookReader find it."""

    segments: list[tuple[str, bool]]

    @property
    def html(self) -> str:
        """Escaped markup with matches in <strong>; the one place snippet text is escaped."""
        return "".join(f"<strong>{web.websafe(text)}</strong>" if is_match else web.websafe(text) for text, is_match in self.segments)


@dataclass(frozen=True)
class FulltextRow:
    """One full-text hit. `edition` is None when the scan has no OL record;
    it still renders from IA metadata, since the total counts it."""

    ocaid: str
    snippets: list[Snippet]
    edition: Any = None
    availability: dict | None = None
    title: str = ""
    year: Any = None
    authors: list[str] | None = None


def _row(hit: dict) -> FulltextRow:
    fields = hit.get("fields") or {}
    ocaid = _first(fields.get("identifier"))
    texts = (hit.get("highlight") or {}).get("text") or []
    return FulltextRow(
        ocaid=ocaid,
        snippets=[Snippet(parse_snippet(text)) for text in texts if text],
        edition=hit.get("edition"),
        availability=hit.get("availability") or {},
        title=_first(fields.get("meta_title")) or ocaid,
        year=_first(fields.get("meta_year"), None),
        authors=[creator for creator in (fields.get("meta_creator") or []) if creator],
    )


def fulltext_page(results: dict | None) -> tuple[list[FulltextRow], int]:
    """Normalize an FTS response into (rows, total). `total` includes hits this page dropped."""
    if not results or "error" in results:
        return [], 0
    envelope = results.get("hits") or {}
    rows = [_row(hit) for hit in envelope.get("hits") or [] if hit_ocaid(hit)]
    return rows, envelope.get("total") or 0


# ── Search ─────────────────────────────────────────────────────────────────


def exclude_ocaids(rows: list[FulltextRow], exclude: Iterable[str]) -> list[FulltextRow]:
    """Drop rows whose scan is in `exclude` (on /search: books the page already lists).

    >>> rows = [FulltextRow("a", []), FulltextRow("b", []), FulltextRow("c", [])]
    >>> [r.ocaid for r in exclude_ocaids(rows, {"b", "zzz"})]
    ['a', 'c']
    """
    excluded = set(exclude)
    return [row for row in rows if row.ocaid not in excluded]


def filter_readable(hits: list[dict], availability: dict) -> list[dict]:
    """Drop hits the visitor can't open (print-disabled-only scans), by the edition page's test.
    Fails open with no availability data, or a whole page would vanish.

    >>> hits = [{"fields": {"identifier": ["open"]}}, {"fields": {"identifier": ["locked"]}}]
    >>> availability = {"open": {"is_readable": True}, "locked": {"is_printdisabled": True}}
    >>> [hit_ocaid(hit) for hit in filter_readable(hits, availability)]
    ['open']
    >>> len(filter_readable(hits, {}))
    2
    """
    if not availability:
        return hits
    return [hit for hit in hits if (status := availability.get(hit_ocaid(hit))) and (status.get("is_readable") or status.get("is_lendable"))]


# ── Query normalization ────────────────────────────────────────────────────

# FTS treats curly quotes as ordinary characters, not phrase delimiters.
_CURLY_DOUBLE_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"'})


def phrase_query(q: str | None) -> str:
    """Quote the whole query as one phrase: bare words match anywhere (1.5M hits vs 14K).
    FTS can't escape quotes and stray ones break the phrase, so typed quotes are dropped.

    >>> phrase_query("it was the best of times")
    '"it was the best of times"'
    >>> phrase_query('"it was the best of times"')
    '"it was the best of times"'
    >>> phrase_query("“it was the best of times”")
    '"it was the best of times"'
    >>> phrase_query('he said "hello there" softly')
    '"he said hello there softly"'
    >>> phrase_query('"it was the best of times')
    '"it was the best of times"'
    >>> print(phrase_query("it's a truth\\n  universally acknowledged"))
    "it's a truth universally acknowledged"
    >>> phrase_query('  "  "  ')
    ''
    """
    words = (q or "").translate(_CURLY_DOUBLE_QUOTES).replace('"', " ").split()
    return f'"{" ".join(words)}"' if words else ""


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


async def fulltext_search_async(q, page=1, offset=None, limit=100, js=False, facets=False, readable=False, language: str | None = None):
    if offset is None:
        offset = (page - 1) * limit
    # Empty once quotes are stripped: skip the upstream call.
    if not (q := phrase_query(q)):
        return {"hits": {"hits": [], "total": 0}}
    params = {
        "q": q,
        "from": offset,
        "size": limit,
        **({"nofacets": "true"} if not facets else {}),
        "olonly": "true",
    }
    # `lang` takes an English name. Keep it a param: a languageSorter: clause in `q`
    # flips FTS to its Lucene parser, which ignores olonly and searches all of archive.org.
    if language:
        params["lang"] = language
    ia_results = await fulltext_search_api(params)

    if "error" not in ia_results and (hits := ia_results.get("hits", {}).get("hits", [])):
        ocaids = [hit_ocaid(hit) for hit in hits]
        availability = await get_availability_async("identifier", ocaids)
        if "error" in availability:
            availability = {}

        if readable:
            # Filter before hydrating so dropped hits cost no Infobase lookup.
            hits = filter_readable(hits, availability)
            ia_results["hits"]["hits"] = hits
            if not hits:
                return ia_results
            ocaids = [hit_ocaid(hit) for hit in hits]

        edition_keys = list(site.get().things({"type": "/type/edition", "ocaid": ocaids, "limit": len(ocaids)}))
        editions = site.get().get_many(edition_keys)
        # Keyed by ocaid so hits sharing an ocaid all get their edition.
        editions_by_ocaid = {ed.ocaid: ed for ed in editions}
        for hit, ocaid in zip(hits, ocaids):
            if ed := editions_by_ocaid.get(ocaid):
                hit["edition"] = format_book_data(ed, fetch_availability=False) if js else ed
                hit["availability"] = availability.get(ocaid, {})
    return ia_results


fulltext_search = async_bridge.wrap(fulltext_search_async)
