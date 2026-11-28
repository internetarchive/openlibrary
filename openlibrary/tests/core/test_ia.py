import asyncio
import time

import httpx
import pytest
from pymemcache.test.utils import MockMemcacheClient

from openlibrary.core import cache, ia


def test_get_metadata(monkeypatch, mock_memcache):
    metadata = {
        "metadata": {
            "title": "Foo",
            "identifier": "foo00bar",
            "collection": ["printdisabled", "inlibrary"],
        }
    }

    monkeypatch.setattr(ia, "get_api_response", lambda *args: metadata)
    assert ia.get_metadata("foo00bar") == {
        "title": "Foo",
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        "access-restricted": False,
        "_filenames": [],
    }


def test_get_metadata_empty(monkeypatch, mock_memcache):
    monkeypatch.setattr(ia, "get_api_response", lambda *args: {})
    assert ia.get_metadata("foo02bar") == {}


@pytest.fixture
def fresh_ia_metadata_cache(monkeypatch):
    """An empty memcache behind ia.get_metadata, shared by its sync and async paths."""
    monkeypatch.setattr(ia.get_metadata, "_memcache", MockMemcacheClient())


def itemid_of(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def ia_response(itemid: str) -> dict:
    return {"metadata": {"identifier": itemid, "collection": ["inlibrary"]}, "files": [{"name": f"{itemid}.pdf"}]}


@pytest.mark.asyncio
async def test_get_api_response_async_success(monkeypatch):
    class FakeSession:
        async def get(self, url, **kwargs):
            return httpx.Response(200, json={"result": "ok"})

    monkeypatch.setattr(ia, "get_async_session", FakeSession)
    result = await ia.get_api_response_async("http://example.com")
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_get_api_response_async_non_200(monkeypatch):
    class FakeSession:
        async def get(self, url, **kwargs):
            return httpx.Response(503, json={"error": "busy"})

    monkeypatch.setattr(ia, "get_async_session", FakeSession)
    result = await ia.get_api_response_async("http://example.com")
    assert result == {}


@pytest.mark.asyncio
async def test_get_api_response_async_exception(monkeypatch):
    class FakeSession:
        async def get(self, url, **kwargs):
            raise httpx.RequestError("network failure")

    monkeypatch.setattr(ia, "get_async_session", FakeSession)
    result = await ia.get_api_response_async("http://example.com")
    assert result == {}


@pytest.mark.asyncio
async def test_get_metadata_many_async_matches_get_metadata(monkeypatch, fresh_ia_metadata_cache):
    itemids = ["foo00bar", "baz00qux", "foo00bar", "missing00item"]

    def response(itemid):
        return {} if itemid == "missing00item" else ia_response(itemid)

    monkeypatch.setattr(ia, "get_api_response", lambda url, params=None: response(itemid_of(url)))
    expected = {itemid: ia.get_metadata(itemid) for itemid in itemids}

    monkeypatch.setattr(ia.get_metadata, "_memcache", MockMemcacheClient())

    async def get_api_response_async(url, params=None):
        return response(itemid_of(url))

    monkeypatch.setattr(ia, "get_api_response_async", get_api_response_async)
    result = await ia.get_metadata_many_async(itemids)

    assert result == expected
    assert list(result) == list(expected)
    assert result["missing00item"] == {}


@pytest.mark.asyncio
async def test_get_metadata_many_async_fetches_concurrently(monkeypatch, fresh_ia_metadata_cache):
    in_flight = max_in_flight = 0

    async def slow_get_api_response_async(url, params=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.2)
        in_flight -= 1
        return ia_response(itemid_of(url))

    monkeypatch.setattr(ia, "get_api_response_async", slow_get_api_response_async)
    itemids = [f"item{i}" for i in range(10)]

    start = time.monotonic()
    result = await ia.get_metadata_many_async(itemids, max_concurrency=10)
    elapsed = time.monotonic() - start

    assert list(result) == itemids
    assert elapsed < 0.6  # about one fetch, not ten (2 s)
    assert max_in_flight == 10


@pytest.mark.asyncio
async def test_get_metadata_many_async_bounds_concurrency(monkeypatch, fresh_ia_metadata_cache):
    in_flight = max_in_flight = 0

    async def slow_get_api_response_async(url, params=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {}

    monkeypatch.setattr(ia, "get_api_response_async", slow_get_api_response_async)
    await ia.get_metadata_many_async([f"item{i}" for i in range(25)], max_concurrency=4)
    assert max_in_flight == 4


@pytest.mark.asyncio
async def test_get_metadata_many_async_invalid_concurrency():
    with pytest.raises(ValueError, match="max_concurrency must be at least 1"):
        await ia.get_metadata_many_async(["item1"], max_concurrency=0)


@pytest.mark.asyncio
async def test_get_metadata_many_async_empty():
    assert await ia.get_metadata_many_async([]) == {}
    assert await ia.get_metadata_many_async(i for i in []) == {}


@pytest.mark.asyncio
async def test_get_metadata_many_async_survives_failed_fetches(monkeypatch, fresh_ia_metadata_cache):
    class FakeClient:
        async def get(self, url, **kwargs):
            request = httpx.Request("GET", url)
            if itemid_of(url) == "slow00item":
                raise httpx.ReadTimeout("timed out", request=request)
            if itemid_of(url) == "broken00item":
                return httpx.Response(503, request=request)
            return httpx.Response(200, json=ia_response(itemid_of(url)), request=request)

    monkeypatch.setattr(ia, "get_async_session", FakeClient)
    result = await ia.get_metadata_many_async(["good00item", "slow00item", "broken00item"])

    assert result["slow00item"] == {}
    assert result["broken00item"] == {}
    assert result["good00item"]["collection"] == ["inlibrary"]
    assert result["good00item"]["_filenames"] == ["good00item.pdf"]


@pytest.mark.asyncio
async def test_get_metadata_many_async_shares_get_metadata_cache(monkeypatch, fresh_ia_metadata_cache):
    monkeypatch.setattr(ia, "get_api_response", lambda url, params=None: ia_response(itemid_of(url)))
    ia.get_metadata("cached00item")  # the sync path fills the cache

    fetched = []

    async def get_api_response_async(url, params=None):
        fetched.append(itemid_of(url))
        return ia_response(itemid_of(url))

    monkeypatch.setattr(ia, "get_api_response_async", get_api_response_async)
    result = await ia.get_metadata_many_async(["cached00item", "new00item"])

    assert fetched == ["new00item"]
    assert result["cached00item"]["identifier"] == "cached00item"

    # ...and the async path fills the cache the sync path reads.
    monkeypatch.setattr(ia, "get_api_response", lambda *args, **kw: pytest.fail("should be cached"))
    assert ia.get_metadata("new00item") == result["new00item"]


@pytest.mark.asyncio
async def test_get_metadata_many_async_negative_caching(monkeypatch, fresh_ia_metadata_cache):
    fetch_count = 0

    async def get_api_response_async(url, params=None):
        nonlocal fetch_count
        fetch_count += 1
        return {}

    monkeypatch.setattr(ia, "get_api_response_async", get_api_response_async)

    # First fetch: empty dict returned and cached
    result1 = await ia.get_metadata_many_async(["missing00item"])
    assert result1["missing00item"] == {}
    assert fetch_count == 1

    # Second fetch: served from cache without re-fetching
    result2 = await ia.get_metadata_many_async(["missing00item"])
    assert result2["missing00item"] == {}
    assert fetch_count == 1


@pytest.mark.asyncio
async def test_get_metadata_many_async_refreshes_stale_values_in_background(monkeypatch, fresh_ia_metadata_cache):
    ia.get_metadata.memcache_set(("stale00item",), {}, {"identifier": "old"}, time.time() - 3600)

    async def get_api_response_async(url, params=None):
        return {"metadata": {"identifier": "new"}}

    monkeypatch.setattr(ia, "get_api_response_async", get_api_response_async)
    result = await ia.get_metadata_many_async(["stale00item"])
    assert result["stale00item"] == {"identifier": "old"}  # the stale value is served right away

    await cache.wait_for_background_tasks()
    value_time = ia.get_metadata.memcache_get(("stale00item",), {})
    assert value_time is not None
    assert value_time[0]["identifier"] == "new"
