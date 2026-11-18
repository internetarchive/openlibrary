"""Tests for identifier resolution, searching, and result assembly."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web

from openlibrary.atproto.models import Identifier, SearchEditionsRequest
from openlibrary.atproto.provider import (
    Bundle,
    InvalidQuery,
    bcp47_tag,
    build_results,
    load_bundle,
    resolve_identifier_keys,
    search_edition_keys,
)
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme
from openlibrary.utils.request_context import site

CREATED = dt.datetime(2009, 4, 1, tzinfo=dt.UTC)


@pytest.fixture
def fake_site():
    """Install a site whose ``get_many``/``things`` are backed by a fixture dict."""
    mock = MagicMock()
    token = site.set(mock)
    try:
        yield mock
    finally:
        site.reset(token)


def _get_many(things: dict) -> MagicMock:
    return MagicMock(side_effect=lambda keys, raw=False: [things[key] for key in keys if key in things])


def test_load_bundle_resolves_edition_authors_and_falls_back_to_work_authors(fake_site):
    things = {
        "/books/OL1M": web.storage({"key": "/books/OL1M", "authors": [{"key": "/authors/OL2A"}]}),
        "/books/OL4M": web.storage({"key": "/books/OL4M", "works": [{"key": "/works/OL5W"}]}),
        "/authors/OL2A": web.storage({"key": "/authors/OL2A", "name": "Ada"}),
        "/authors/OL3A": web.storage({"key": "/authors/OL3A", "name": "Grace"}),
        "/works/OL5W": web.storage({"key": "/works/OL5W", "authors": [{"author": {"key": "/authors/OL3A"}, "type": {"key": "/type/author_role"}}]}),
    }
    fake_site.get_many = _get_many(things)

    bundles = load_bundle(["/books/OL1M", "/books/OL4M", "/books/OL404M"])

    assert set(bundles) == {"/books/OL1M", "/books/OL4M"}
    assert [author.key for author in bundles["/books/OL1M"].authors] == ["/authors/OL2A"]
    assert [author.key for author in bundles["/books/OL4M"].authors] == ["/authors/OL3A"]


def test_bcp47_tag_prefers_the_iso_639_1_code():
    things = {"/languages/eng": web.storage({"identifiers": {"iso_639_1": ["en"]}})}

    assert bcp47_tag("/languages/eng", things) == "en"
    # No ISO 639-1 equivalent, or no language record: keep the MARC code.
    assert bcp47_tag("/languages/ast", things) == "ast"
    assert bcp47_tag("/languages/yid", {}) == "yid"


def test_resolve_identifier_keys_accepts_olid_forms_and_drops_unknown(fake_site):
    queries = []

    def things(query):
        queries.append(query)
        return [] if query["key"].endswith("OL99999999M") else [query["key"]]

    fake_site.things = things

    assert resolve_identifier_keys([Identifier(issuer="openlibrary", value="/books/OL1M")]) == ["/books/OL1M"]
    assert resolve_identifier_keys([Identifier(issuer="OpenLibrary", value="OL2M")]) == ["/books/OL2M"]
    assert resolve_identifier_keys([Identifier(issuer="openlibrary", value="OL99999999M")]) == []
    # Only OL<digits>M is an edition OLID, so these cost no query.
    assert resolve_identifier_keys([Identifier(issuer="openlibrary", value="OLX")]) == []
    assert resolve_identifier_keys([Identifier(issuer="openlibrary", value="/books/OL3W")]) == []
    assert queries == [
        {"type": "/type/edition", "key": "/books/OL1M"},
        {"type": "/type/edition", "key": "/books/OL2M"},
        {"type": "/type/edition", "key": "/books/OL99999999M"},
    ]


def test_resolve_identifier_keys_queries_both_isbn_forms(fake_site):
    queries = []

    def things(query):
        queries.append(query)
        return ["/books/OL9M"] if "isbn_13" in query else ["/books/OL8M"]

    fake_site.things = things

    keys = resolve_identifier_keys([Identifier(issuer="isbn10", value="059035342X")])

    assert queries == [
        {"type": "/type/edition", "isbn_13": "9780590353427"},
        {"type": "/type/edition", "isbn_10": "059035342X"},
    ]
    assert keys == ["/books/OL9M", "/books/OL8M"]


def test_resolve_identifier_keys_skips_unknown_issuers_and_dedupes(fake_site):
    fake_site.things = MagicMock(return_value=["/books/OL7M"])

    keys = resolve_identifier_keys(
        [
            Identifier(issuer="oclc", value="1234"),
            Identifier(issuer="unknown", value="whatever"),
            Identifier(issuer="oclc", value="1234"),
        ]
    )

    assert keys == ["/books/OL7M"]
    fake_site.things.assert_called_once_with({"type": "/type/edition", "oclc_numbers": "1234"})


@pytest.mark.asyncio
async def test_search_edition_keys_requires_a_term():
    with pytest.raises(InvalidQuery):
        await search_edition_keys(SearchEditionsRequest(q="   ", title=""))
    with pytest.raises(InvalidQuery):
        await search_edition_keys(SearchEditionsRequest())


@pytest.mark.asyncio
async def test_search_edition_keys_turns_hints_into_phrase_filters():
    run_solr_query = AsyncMock(return_value=web.storage(error=None, num_found=0, num_found_exact=True, docs=[]))

    with patch("openlibrary.atproto.provider.run_solr_query_async", new=run_solr_query):
        await search_edition_keys(SearchEditionsRequest(title='Dune "Messiah"', author="Frank Herbert", q="", limit=2, offset=4))

    call = run_solr_query.call_args_list[0]
    assert isinstance(call.args[0], EditionSearchScheme)
    assert call.args[1] == {"q": "*:*"}
    assert call.kwargs["extra_params"] == [
        ("fq", 'title:"Dune \\"Messiah\\""'),
        ("fq", 'author_name:"Frank Herbert"'),
    ]
    assert call.kwargs["rows"] == 2
    assert call.kwargs["offset"] == 4


@pytest.mark.asyncio
async def test_search_edition_keys_returns_nothing_when_solr_errors():
    run_solr_query = AsyncMock(return_value=web.storage(error="invalid query", num_found=None, docs=[]))

    with patch("openlibrary.atproto.provider.run_solr_query_async", new=run_solr_query):
        keys, total = await search_edition_keys(SearchEditionsRequest(q="dune ("))

    assert (keys, total) == ([], None)
    assert run_solr_query.call_count == 1


@pytest.mark.asyncio
async def test_search_edition_keys_prefers_resolved_identifiers(fake_site):
    fake_site.things = MagicMock(return_value=["/books/OL1M", "/books/OL2M"])

    keys, total = await search_edition_keys(SearchEditionsRequest(identifiers=[Identifier(issuer="oclc", value="1")], limit=1))

    assert keys == ["/books/OL1M"]
    assert total == 2


def test_build_results_skips_unrepresentable_editions(coverstore):
    bundles = {
        "/books/OL1M": Bundle(edition=web.storage({"key": "/books/OL1M", "title": "Dune", "created": CREATED}), authors=[], languages=[]),
        "/books/OL2M": Bundle(edition=web.storage({"key": "/books/OL2M", "title": "", "created": CREATED}), authors=[], languages=[]),
        "/books/OL3M": Bundle(edition=web.storage({"key": "/books/OL3M", "title": "Emma", "created": CREATED}), authors=[], languages=[]),
    }

    results = build_results(list(bundles), bundles, total=3, offset=0, limit=2)

    assert [item["title"] for item in results["items"]] == ["Dune", "Emma"]
    assert results["hasMore"] is True
    assert results["total"] == 3


def test_build_results_pages_from_the_total_and_the_page(coverstore):
    bundles = {"/books/OL1M": Bundle(edition=web.storage({"key": "/books/OL1M", "title": "Dune", "created": CREATED}), authors=[], languages=[])}

    off_the_end = build_results(["/books/OL1M"], {}, total=10, offset=10, limit=5)
    assert off_the_end["items"] == []
    assert off_the_end["hasMore"] is False
    assert "total" not in off_the_end

    # Solr's numFound is a lower bound when results are partial, so ask for more.
    assert build_results(["/books/OL1M"], bundles, total=None, offset=0, limit=25)["hasMore"] is True
