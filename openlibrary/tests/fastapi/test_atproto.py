"""Tests for the anonymous XRPC procedures serving ``editionView`` results."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import web

RESOLVE = "/xrpc/community.lexicon.media.book.resolveEditions"
SEARCH = "/xrpc/community.lexicon.media.book.searchEditions"

CREATED = dt.datetime(2009, 4, 1, tzinfo=dt.UTC)
AUTHOR = web.storage({"key": "/authors/OL2A", "name": "Ada Lovelace"})


def _edition(key: str, title: str) -> web.storage:
    return web.storage({"key": key, "title": title, "created": CREATED, "authors": [{"key": "/authors/OL2A"}]})


class _SiteVar:
    """Stands in for the request-scoped ``site`` ContextVar."""

    def __init__(self, site):
        self._site = site

    def get(self):
        return self._site


def _infobase(matches=("/books/OL1M",), things=None):
    """Patch Infobase so resolution and bundling run for real against fake data."""
    things = things or {"/books/OL1M": _edition("/books/OL1M", "Dune"), "/authors/OL2A": AUTHOR}
    site = MagicMock()
    site.things.return_value = list(matches)
    site.get_many.side_effect = lambda keys, raw=False: [things[key] for key in keys if key in things]
    return patch("openlibrary.atproto.provider.site", new=_SiteVar(site))


def test_resolve_editions_returns_edition_view(fastapi_client):
    with _infobase():
        response = fastapi_client.post(RESOLVE, json={"identifiers": [{"issuer": "isbn13", "value": "9780590353427"}]})

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["title"] == "Dune"
    assert body["items"][0]["contributors"] == [{"displayName": "Ada Lovelace", "role": "A01", "identifiers": [{"issuer": "openlibrary", "value": "OL2A"}]}]
    assert body["items"][0]["createdAt"] == "2009-04-01T00:00:00Z"
    assert body["hasMore"] is False
    assert body["total"] == 1


def test_resolve_editions_returns_empty_page_for_unknown_identifiers(fastapi_client):
    with _infobase(matches=()):
        response = fastapi_client.post(RESOLVE, json={"identifiers": [{"issuer": "isbn13", "value": "9780590353427"}]})

    assert response.status_code == 200
    assert response.json() == {"items": [], "hasMore": False, "total": 0}


def test_resolve_editions_paginates(fastapi_client):
    things = {"/books/OL1M": _edition("/books/OL1M", "Dune"), "/books/OL2M": _edition("/books/OL2M", "Emma"), "/authors/OL2A": AUTHOR}

    with _infobase(matches=("/books/OL1M", "/books/OL2M"), things=things):
        first = fastapi_client.post(RESOLVE, json={"identifiers": [{"issuer": "oclc", "value": "1"}], "limit": 1}).json()
        second = fastapi_client.post(RESOLVE, json={"identifiers": [{"issuer": "oclc", "value": "1"}], "limit": 1, "offset": 1}).json()

    assert [item["title"] for item in first["items"]] == ["Dune"]
    assert first["hasMore"] is True
    assert first["total"] == 2
    assert [item["title"] for item in second["items"]] == ["Emma"]
    assert second["hasMore"] is False
    assert "total" not in second


def test_search_editions_requires_a_term(fastapi_client):
    response = fastapi_client.post(SEARCH, json={})

    assert response.status_code == 400
    assert response.json()["error"] == "InvalidQuery"


def test_search_editions_returns_matching_page(fastapi_client):
    with (
        _infobase(),
        patch("openlibrary.fastapi.atproto.search_edition_keys", new=AsyncMock(return_value=(["/books/OL1M"], 1))),
    ):
        response = fastapi_client.post(SEARCH, json={"q": "dune", "limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["title"] == "Dune"
    assert body["hasMore"] is False
    assert body["total"] == 1


def test_resolve_editions_answers_bad_input_in_xrpc_shape(fastapi_client):
    empty = fastapi_client.post(RESOLVE, json={"identifiers": []})
    oversized = fastapi_client.post(RESOLVE, json={"identifiers": [{"issuer": "openlibrary", "value": f"OL{i}M"} for i in range(26)]})

    for response in (empty, oversized):
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "InvalidRequest"
        assert "identifiers" in body["message"]


def test_resolve_editions_reports_bcp47_language(fastapi_client):
    things = {
        "/books/OL1M": web.storage({"key": "/books/OL1M", "title": "Dune", "created": CREATED, "languages": [{"key": "/languages/eng"}]}),
        "/languages/eng": web.storage({"key": "/languages/eng", "identifiers": {"iso_639_1": ["en"]}}),
    }
    with _infobase(things=things):
        response = fastapi_client.post(RESOLVE, json={"identifiers": [{"issuer": "oclc", "value": "1"}]})

    assert response.json()["items"][0]["language"] == "en"


def test_cors_preflight_allows_post(fastapi_client):
    response = fastapi_client.options(
        SEARCH,
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
