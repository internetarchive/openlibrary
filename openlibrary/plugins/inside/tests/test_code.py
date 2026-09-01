import pytest

from openlibrary.core import fulltext
from openlibrary.core.fulltext import (
    Snippet,
    filter_readable,
    fulltext_page,
    parse_snippet,
    resolve_language,
)
from openlibrary.plugins.inside.code import empty_reason


def hit(ocaid: str) -> dict:
    return {"fields": {"identifier": [ocaid]}}


# ── filter_readable ────────────────────────────────────────────────────────


def test_readable_keeps_public_and_borrowable():
    hits = [hit("public"), hit("borrowable"), hit("restricted")]
    availability = {
        "public": {"is_readable": True, "is_lendable": False},
        "borrowable": {"is_readable": False, "is_lendable": True},
        "restricted": {"is_readable": False, "is_lendable": False, "is_printdisabled": True},
    }
    assert [h["fields"]["identifier"][0] for h in filter_readable(hits, availability)] == ["public", "borrowable"]


def test_readable_drops_hits_with_no_availability_record():
    # An unknown scan can't be shown as readable — but see the fail-open case
    # below: that's about the lookup failing wholesale, not one missing entry.
    assert filter_readable([hit("unknown")], {"other": {"is_readable": True}}) == []


def test_readable_fails_open_when_availability_lookup_failed():
    # Better a page of unfiltered results than an empty page.
    hits = [hit("public"), hit("restricted")]
    assert filter_readable(hits, {}) == hits


# ── The response envelope stops at fulltext_page ───────────────────────────


def test_rows_carry_parsed_snippets():
    """page_num stays on the wire untouched: the cross-document FTS index has
    no page knowledge (per IA), so rows never carry page numbers."""
    rows, total = fulltext_page(
        {
            "hits": {
                "total": 4312,
                "hits": [
                    {
                        "fields": {"identifier": ["scan1"], "page_num": [[270]]},
                        "highlight": {"text": ["But {{{Lokesh}}} had", "and {{{Lokesh}}} again"]},
                    }
                ],
            }
        }
    )
    assert total == 4312
    (row,) = rows
    assert row.ocaid == "scan1"
    assert len(row.snippets) == 2
    assert row.snippets[0].segments == [("But ", False), ("Lokesh", True), (" had", False)]


def test_rows_fall_back_to_ia_metadata_when_no_edition_hydrated():
    rows, _ = fulltext_page(
        {
            "hits": {
                "total": 1,
                "hits": [
                    {
                        "fields": {
                            "identifier": ["scan2"],
                            "meta_title": ["Water touching stone"],
                            "meta_year": [1999],
                            "meta_creator": ["Eliot Pattison", ""],
                        },
                        "highlight": {"text": ["a {{{match}}}"]},
                    }
                ],
            }
        }
    )
    (row,) = rows
    assert row.edition is None
    assert (row.title, row.year, row.authors) == ("Water touching stone", 1999, ["Eliot Pattison"])


def test_rows_tolerate_fields_that_are_present_but_empty():
    """A present-but-empty field used to raise IndexError off `[0]` indexing."""
    rows, _ = fulltext_page({"hits": {"total": 1, "hits": [{"fields": {"identifier": ["scan3"], "meta_title": [], "page_num": []}}]}})
    (row,) = rows
    assert (row.title, row.snippets) == ("scan3", [])


@pytest.mark.parametrize("results", [None, {}, {"error": "Unable to query search engine"}, {"hits": {"hits": [], "total": 0}}])
def test_no_rows_from_an_empty_or_failed_response(results):
    assert fulltext_page(results) == ([], 0)


def test_snippet_html_escapes_every_segment():
    """The snippet is API-controlled OCR text: it becomes markup in exactly one
    place, and the only tags in the result are the ones we added."""
    (snippet,) = fulltext_page({"hits": {"total": 1, "hits": [{"fields": {"identifier": ["x"]}, "highlight": {"text": ['<b>a & b</b> {{{"c"}}}']}}]}})[0][
        0
    ].snippets
    assert snippet.html == "&lt;b&gt;a &amp; b&lt;/b&gt; <strong>&quot;c&quot;</strong>"


def test_unbalanced_marker_keeps_the_text():
    assert parse_snippet("ends with {{{truncated") == [("ends with ", False), ("truncated", True)]
    assert Snippet(parse_snippet("ends with {{{truncated")).html == "ends with <strong>truncated</strong>"


# ── resolve_language ───────────────────────────────────────────────────────


@pytest.fixture
def languages(monkeypatch):
    monkeypatch.setattr(
        fulltext,
        "language_name_maps",
        lambda: ({"ger": "German", "fre": "French"}, {"german": "ger", "french": "fre"}),
    )


@pytest.mark.parametrize("value", ["ger", "German", "  german  "])
def test_resolve_language_accepts_codes_and_names(languages, value):
    """Our own URLs carry MARC codes; a hand-edited one may carry the name."""
    assert resolve_language([value]) == ("ger", "German")


def test_resolve_language_narrows_to_one(languages):
    # `lang=a,b` matches nothing upstream and a repeated param keeps only the
    # first, so one language is all we can honor — and this is the only place
    # that gets decided.
    assert resolve_language(["ger", "fre"]) == ("ger", "German")


@pytest.mark.parametrize("values", [None, [], ["", "   "]])
def test_resolve_language_returns_none_without_a_usable_value(languages, values):
    assert resolve_language(values) is None


# ── empty_reason ───────────────────────────────────────────────────────────


def test_empty_reason_distinguishes_filtered_from_past_the_end():
    """`total` counts matches the page never rendered, so an empty page always
    needs a reason — a count above an empty list with no explanation is the bug
    this replaced."""
    assert empty_reason("dune", [], 0, filtered=False) == "no_matches"
    assert empty_reason("dune", [], 4312, filtered=True) == "filtered_out"
    assert empty_reason("dune", [], 4312, filtered=False) == "past_end"
    assert empty_reason("dune", ["row"], 4312, filtered=True) is None


# ── Outgoing search params ─────────────────────────────────────────────────


class FakeSearchAPI:
    """Captures the params fulltext_search_async sends upstream."""

    def __init__(self):
        self.params = None

    async def __call__(self, params):
        self.params = params
        return {"hits": {"hits": [], "total": 0}}


async def search_params(monkeypatch, **kwargs) -> dict:
    api = FakeSearchAPI()
    monkeypatch.setattr(fulltext, "fulltext_search_api", api)
    await fulltext.fulltext_search_async("moby dick", **kwargs)
    return api.params


@pytest.mark.asyncio
async def test_query_is_sent_as_a_phrase_with_olonly(monkeypatch):
    # Only the phrase quotes may be added to `q`: a field clause would flip the
    # endpoint to its Lucene parser, which silently ignores olonly.
    params = await search_params(monkeypatch)
    assert params["q"] == '"moby dick"'
    assert params["olonly"] == "true"
    assert "lang" not in params


@pytest.mark.asyncio
async def test_language_is_sent_as_the_lang_param(monkeypatch):
    params = await search_params(monkeypatch, language="German")
    assert params["q"] == '"moby dick"'
    assert params["lang"] == "German"
