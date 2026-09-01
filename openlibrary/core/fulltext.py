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
from openlibrary.core.lending import get_availability_async
from openlibrary.plugins.openlibrary.home import format_book_data
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import req_context, site

logger = logging.getLogger("openlibrary.inside")


# ── Language resolution ────────────────────────────────────────────────────


@functools.cache
def language_name_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Bidirectional MARC-code ↔ English-name maps for the FTS index's
    languageSorter field: (code → name, casefolded name → code).
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


def resolve_language(values: Iterable[str] | None) -> tuple[str, str] | None:
    """The (MARC code, English name) pair for the first value that resolves, or
    None when nothing usable was passed.

    Accepts either form, because both handlers take the same `language` param:
    "fre" from our own URLs, "French" from a hand-edited one. Callers want both
    halves back — the FTS query needs the name, generated URLs stay on the code.

    Only ever one language: the FTS `lang` param is single-valued (`lang=a,b`
    matches nothing, and a repeated param keeps only the first). This is the one
    place that narrowing happens, so no surface can show a filter the search
    didn't apply.
    """
    code_to_name, name_to_code = language_name_maps()
    for raw in values or []:
        if not (lang := raw.strip()):
            continue
        code = name_to_code.get(lang.casefold(), lang.casefold())
        return code, code_to_name.get(code, lang)
    return None


# ── Response envelope → rows ───────────────────────────────────────────────
#
# The FTS wire format — {"hits": {"hits": [...], "total": n}}, multi-valued
# `fields` lists, {{{ }}} match markers, page numbers nested one level deeper
# than you'd expect — stops at fulltext_page(). Templates and partials take
# FulltextRow, so no consumer re-parses the envelope or indexes [0] into a
# field that may be present but empty.


def _first(values: Any, default: Any = "") -> Any:
    """First element of a multi-valued FTS field, tolerating [] and non-lists."""
    if isinstance(values, list):
        return values[0] if values else default
    return default if values is None else values


def hit_ocaid(hit: dict) -> str:
    """The archive.org identifier a full-text hit was found in."""
    return _first(hit.get("fields", {}).get("identifier"))


# Word count at/above which an unquoted query reads as a passage, not a title.
PASSAGE_WORD_COUNT = 5


def is_passage_query(query: str) -> bool:
    """True when a query reads like a passage (words remembered from inside a
    book) rather than a title/author lookup — a quoted phrase (straight or
    curly), or PASSAGE_WORD_COUNT+ words. Mirrors isPassageQuery() in
    search-modal/fulltext.js.

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

    Segments rather than an HTML string so each half can be escaped normally by
    whoever renders it — the snippet is API-controlled text and never belongs in
    an unescaped template expression. Mirrors parseSnippet() in
    search-modal/fulltext.js, which does the same for the JSON endpoint.

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
            # An unbalanced marker means a truncated snippet: keep the text as a
            # match rather than dropping it.
            segments.append((matched, True))
        if marker and tail:
            segments.append((tail, False))
    return segments


@dataclass(frozen=True)
class Snippet:
    """One matched passage as (text, is_match) segments. No page number: the
    cross-document FTS index has no page knowledge (per IA), so links hand the
    query to BookReader, whose own in-book search locates and highlights it."""

    segments: list[tuple[str, bool]]

    @property
    def html(self) -> str:
        """The passage as markup, matches wrapped in <strong>.

        Escaping happens here, once, for every surface that renders a snippet.
        The text is API-controlled OCR; the templates used to hand-roll it with
        a replace() chain that turned < and > into guillemets and left & alone.
        """
        return "".join(f"<strong>{web.websafe(text)}</strong>" if is_match else web.websafe(text) for text, is_match in self.segments)


@dataclass(frozen=True)
class FulltextRow:
    """One full-text hit, ready to render.

    `edition` is the OL record the scan hydrated to, or None — a scan with no OL
    edition still renders from its own IA metadata (title/year/authors) rather
    than vanishing, because the total and pagination count it either way.
    """

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
    """Normalize an FTS response into (rows, total).

    `total` counts every match the service found, including ones this page
    filtered out or couldn't identify — so len(rows) < limit is normal and the
    caller decides how to describe it (see empty_reason in plugins/inside).
    """
    if not results or "error" in results:
        return [], 0
    envelope = results.get("hits") or {}
    rows = [_row(hit) for hit in envelope.get("hits") or [] if hit_ocaid(hit)]
    return rows, envelope.get("total") or 0


# ── Search ─────────────────────────────────────────────────────────────────


def exclude_ocaids(rows: list[FulltextRow], exclude: Iterable[str]) -> list[FulltextRow]:
    """Drop the rows whose scan is in `exclude` — on /search, the scans the
    metadata results already list, so the Search Inside band only shows books
    the page doesn't.

    >>> rows = [FulltextRow("a", []), FulltextRow("b", []), FulltextRow("c", [])]
    >>> [r.ocaid for r in exclude_ocaids(rows, {"b", "zzz"})]
    ['a', 'c']
    """
    excluded = set(exclude)
    return [row for row in rows if row.ocaid not in excluded]


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
    return [hit for hit in hits if (status := availability.get(hit_ocaid(hit))) and (status.get("is_readable") or status.get("is_lendable"))]


# ── Query normalization ────────────────────────────────────────────────────

# Pasted passages carry curly quotes, which the FTS backend treats as ordinary
# characters rather than phrase delimiters.
_CURLY_DOUBLE_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"'})


def phrase_query(q: str | None) -> str:
    """Send every Search Inside query to the backend as one quoted phrase.

    Bare words match anywhere in a book (1.5M hits for `it was the best of
    times`); the quoted phrase matches the passage (14K). Measured against
    the FTS backend: an unbalanced quote silently degrades to a bare-word
    search, an inner quote splits the phrase into fragments, and backslash
    escaping does nothing — so a quote the user typed can only be removed.
    Apostrophes and operators are literal inside a phrase and stay as-is.

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
    # Nothing left once the quotes are stripped: skip the upstream call rather
    # than ask the backend what an empty phrase matches.
    if not (q := phrase_query(q)):
        return {"hits": {"hits": [], "total": 0}}
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
    # archive.org. Single-valued by the backend's rules, hence the str type —
    # see resolve_language, which is where a request gets narrowed to one.
    if language:
        params["lang"] = language
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
