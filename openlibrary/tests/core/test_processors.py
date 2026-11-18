import re

import pytest
import web

from infogami.infobase import client, common
from openlibrary.core import helpers
from openlibrary.core.processors import readableurls as processors
from openlibrary.utils.request_context import site as site_context


class MockSite:
    def __init__(self):
        self.docs = {}
        self.olids = {}

    def get(self, key):
        return self.docs.get(key)

    def add(self, doc):
        # @@ UGLY!
        doc = common.parse_query(doc)
        doc = client.Site(None, None)._process_dict(doc)

        key = doc["key"]
        self.docs[key] = client.create_thing(self, key, doc)

        olid = key.split("/")[-1]
        if re.compile(r"OL\d+[A-Z]").match(olid):
            self.olids[olid] = key

    def _request(self, path, method=None, data=None):
        if path == "/olid_to_key":
            olid = data["olid"]
            return web.storage(key=self.olids.get(olid))

    def _get_backreferences(self, keys=None):
        return {}


def test_MockSite():
    site = MockSite()
    assert site.get("/books/OL1M") is None

    book = {"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "foo"}
    site.add(book)

    assert site.get("/books/OL1M") is not None
    assert site.get("/books/OL1M").dict() == book

    assert site._request("/olid_to_key", data={"olid": "OL1M"}) == {"key": "/books/OL1M"}


def _get_mock_site():
    site = MockSite()

    book = {"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "foo"}
    site.add(book)

    list = {
        "key": "/people/joe/lists/OL1L",
        "type": {"key": "/type/list"},
        "name": "foo",
    }
    site.add(list)
    return site


def test_get_object():
    site = _get_mock_site()

    def f(key):
        doc = processors._get_object(site, key)
        return doc and doc.key

    assert f("/books/OL1M") == "/books/OL1M"
    assert f("/b/OL1M") == "/books/OL1M"
    assert f("/whatever/OL1M") == "/books/OL1M"
    assert f("/not-there") is None


_mock_site = _get_mock_site()


def get_readable_path(path, encoding=None):
    patterns = processors.ReadableUrlProcessor.patterns
    return processors.get_readable_path(_mock_site, path, patterns, encoding=encoding)


def test_book_urls():
    f = get_readable_path

    # regular pages
    assert f("/books/OL1M") == ("/books/OL1M", "/books/OL1M/foo")
    assert f("/books/OL1M/foo") == ("/books/OL1M", "/books/OL1M/foo")
    assert f("/books/OL1M/foo/edit") == ("/books/OL1M/edit", "/books/OL1M/foo/edit")

    # with bad title
    assert f("/books/OL1M/bar") == ("/books/OL1M", "/books/OL1M/foo")
    assert f("/books/OL1M/bar/edit") == ("/books/OL1M/edit", "/books/OL1M/foo/edit")
    assert f("/books/OL1M/export") == ("/books/OL1M", "/books/OL1M/foo")

    # test /b/ redirects
    assert f("/b/OL1M") == ("/books/OL1M", "/books/OL1M/foo")
    assert f("/b/OL1M/foo/edit") == ("/books/OL1M/edit", "/books/OL1M/foo/edit")

    # test olid redirects
    assert f("/whatever/OL1M") == ("/books/OL1M", "/books/OL1M/foo")

    # test encoding
    assert f("/books/OL1M.json") == ("/books/OL1M.json", "/books/OL1M.json")
    assert f("/books/OL1M", encoding="json") == ("/books/OL1M", "/books/OL1M")


def test_list_urls():
    f = get_readable_path

    print(f("/people/joe/lists/OL1L"))

    assert f("/people/joe/lists/OL1L") == (
        "/people/joe/lists/OL1L",
        "/people/joe/lists/OL1L/foo",
    )

    assert f("/people/joe/lists/OL1L/bar") == (
        "/people/joe/lists/OL1L",
        "/people/joe/lists/OL1L/foo",
    )

    assert f("/people/joe/lists/OL1L/bar/edit") == (
        "/people/joe/lists/OL1L/edit",
        "/people/joe/lists/OL1L/foo/edit",
    )


@pytest.mark.parametrize(
    ("key", "type_key"),
    [
        ("/people/joe/lists/OL1L", "/type/list"),
        ("/lists/OL1L", "/type/list"),
        ("/series/OL1L", "/type/series"),
    ],
)
@pytest.mark.parametrize("action", ["export", "embed", "edit", "editions"])
def test_list_action_urls(key, type_key, action):
    site = MockSite()
    site.add({"key": key, "type": {"key": type_key}, "name": "foo"})
    patterns = processors.ReadableUrlProcessor.patterns

    for slug in ("", "/foo", "/bar", f"/{action}"):
        assert processors.get_readable_path(site, f"{key}{slug}/{action}", patterns) == (
            f"{key}/{action}",
            f"{key}/foo/{action}",
        )


@pytest.mark.parametrize(("key", "type_key"), [("/people/joe/lists/OL1L", "/type/list"), ("/series/OL1L", "/type/series")])
@pytest.mark.parametrize("action", ["export", "embed", "edit", "editions"])
def test_list_action_name_is_canonical_slug(key, type_key, action):
    site = MockSite()
    site.add({"key": key, "type": {"key": type_key}, "name": action})
    patterns = processors.ReadableUrlProcessor.patterns

    assert processors.get_readable_path(site, key, patterns) == (key, f"{key}/{action}")
    assert processors.get_readable_path(site, f"{key}/{action}", patterns) == (key, f"{key}/{action}")
    assert processors.get_readable_path(site, f"{key}/{action}/{action}", patterns) == (
        f"{key}/{action}",
        f"{key}/{action}/{action}",
    )


@pytest.mark.parametrize("suffix", [".json", "/seeds.json", "/editions.yml"])
def test_list_encoded_urls(suffix):
    path = f"/people/joe/lists/OL1L{suffix}"
    assert get_readable_path(path) == (path, path)


def test_list_urls_with_explicit_encoding():
    path = "/people/joe/lists/OL1L/export"
    assert get_readable_path(path, encoding="json") == (path, path)


def test_list_action_name_with_nested_suffix():
    assert get_readable_path("/people/joe/lists/OL1L/export/feeds/updates.atom") == (
        "/people/joe/lists/OL1L/feeds/updates.atom",
        "/people/joe/lists/OL1L/foo/feeds/updates.atom",
    )


@pytest.mark.parametrize("action", ["export", "embed"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_list_action_request_preserves_query(action, method):
    class ActionHandler:
        def GET(self, action):
            return web.ctx.fullpath

        POST = GET

    key = "/people/joe/lists/OL1L"
    token = site_context.set(_get_mock_site())
    try:
        app = web.application((rf"{key}/(export|embed)", ActionHandler), {})
        app.add_processor(web.loadhook(lambda: setattr(web.ctx, "encoding", None)))
        app.add_processor(processors.ReadableUrlProcessor())
        response = app.request(f"{key}/{action}?format=json", method=method)
        if method == "GET":
            assert response.status == "301 Moved Permanently"
            assert response.headers["Location"] == f"http://0.0.0.0:8080{key}/foo/{action}?format=json"
            response = app.request(f"{key}/foo/{action}?format=json")
    finally:
        site_context.reset(token)

    assert response.status == "200 OK"
    assert response.data.decode() == f"{key}/{action}?format=json"


# ---------------------------------------------------------------------------
# Tests for is_exclusion / _get_author_exclusions
# ---------------------------------------------------------------------------


def _make_thing(site, key, type_key, extra=None):
    """Helper: add a minimal doc to MockSite and return the Thing."""
    doc = {"key": key, "type": {"key": type_key}}
    if extra:
        doc.update(extra)
    site.add(doc)
    return site.get(key)


def test_is_exclusion_author_excluded(monkeypatch):
    """An author whose key is in author_exclusions returns True."""
    helpers.get_author_exclusions.cache_clear()
    monkeypatch.setattr(helpers.config, "get", lambda key, *a, **kw: ["/authors/OL99A"] if key == "author_exclusions" else None)
    site = MockSite()
    author = _make_thing(site, "/authors/OL99A", "/type/author", {"name": "Test Author"})
    assert processors.is_exclusion(author) is True


def test_is_exclusion_author_not_excluded(monkeypatch):
    """An author not in author_exclusions returns False."""
    helpers.get_author_exclusions.cache_clear()
    monkeypatch.setattr(helpers.config, "get", lambda key, *a, **kw: [] if key == "author_exclusions" else None)
    site = MockSite()
    author = _make_thing(site, "/authors/OL1A", "/type/author", {"name": "Safe Author"})
    assert processors.is_exclusion(author) is False


def test_is_exclusion_empty_config_returns_false(monkeypatch):
    """When author_exclusions is absent from config, nothing is excluded."""
    helpers.get_author_exclusions.cache_clear()
    monkeypatch.setattr(helpers.config, "get", lambda key, *a, **kw: None)
    site = MockSite()
    author = _make_thing(site, "/authors/OL99A", "/type/author", {"name": "Test Author"})
    assert processors.is_exclusion(author) is False


def test_is_exclusion_none_returns_false():
    """is_exclusion(None) returns False without raising."""
    assert processors.is_exclusion(None) is False


def test_get_author_exclusions_caches(monkeypatch):
    """get_author_exclusions returns the same frozenset on repeated calls."""
    helpers.get_author_exclusions.cache_clear()
    call_count = {"n": 0}

    def fake_get(key, *a, **kw):
        if key == "author_exclusions":
            call_count["n"] += 1
            return ["/authors/OL1A", "/authors/OL2A"]
        return None

    monkeypatch.setattr(helpers.config, "get", fake_get)
    r1 = helpers.get_author_exclusions()
    r2 = helpers.get_author_exclusions()
    assert r1 is r2  # same object — cache hit
    assert call_count["n"] == 1  # config.get called only once
