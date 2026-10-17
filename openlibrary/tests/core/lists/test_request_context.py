import anyio
import pytest
import web

from openlibrary.core.lists.model import List, Series
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.utils.request_context import site


@pytest.fixture(params=["webpy", "worker", "stale_worker"])
def run_list_helper(request, mock_site):
    async def run(helper):
        def call():
            assert site.get() is mock_site
            assert hasattr(web.ctx, "site") == (request.param == "webpy")
            if request.param == "stale_worker":
                web.ctx.site = MockSite()
                try:
                    return helper()
                finally:
                    del web.ctx.site
            return helper()

        if request.param != "webpy":
            return await anyio.to_thread.run_sync(call)
        return call()

    return run


@pytest.mark.asyncio
async def test_export_list_uses_request_site(mock_site, run_list_helper):
    keys = {"works": "/works/OL1W", "editions": "/books/OL1M", "authors": "/authors/OL1A"}
    for kind, key in keys.items():
        mock_site.save({"key": key, "type": {"key": f"/type/{kind[:-1]}"}})
    list_key = "/people/test/lists/OL1L"
    mock_site.save({"key": list_key, "type": {"key": "/type/list"}, "seeds": [{"key": key} for key in keys.values()] + ["subject:fiction"]})
    lst = List(mock_site, list_key)

    exported = await run_list_helper(lst.get_export_list)

    assert {kind: [document["key"] for document in documents] for kind, documents in exported.items()} == {kind: [key] for kind, key in keys.items()}


@pytest.mark.asyncio
async def test_list_redirects_use_request_site(mock_site, run_list_helper):
    mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Target"})
    mock_site.save({"key": "/works/OL2W", "type": {"key": "/type/redirect"}, "location": "/works/OL1W"})
    list_key = "/people/test/lists/OL1L"
    mock_site.save({"key": list_key, "type": {"key": "/type/list"}, "seeds": [{"key": "/works/OL2W"}]})
    lst = List(mock_site, list_key)

    seeds = await run_list_helper(lambda: lst.get_seeds(resolve_redirects=True))

    assert [seed.key for seed in seeds] == ["/works/OL1W"]
    assert seeds[0].type == "work"


@pytest.mark.asyncio
async def test_series_seeds_use_request_site(mock_site, run_list_helper):
    series_key = "/series/OL1L"
    for key in [series_key, "/series/OL2L"]:
        mock_site.save({"key": key, "type": {"key": "/type/series"}, "name": key})
    for key, position, notes, series in [
        ("/works/OL1W", "2", "Second", series_key),
        ("/works/OL2W", "1", "First", series_key),
        ("/works/OL3W", "0", "Unrelated", "/series/OL2L"),
    ]:
        mock_site.save(
            {
                "key": key,
                "type": {"key": "/type/work"},
                "series": [{"series": {"key": series}, "position": position, "notes": notes}],
            }
        )
    series = Series(mock_site, series_key)

    seeds = await run_list_helper(series.get_seeds)

    assert [(seed.key, seed.position, seed.notes) for seed in seeds] == [
        ("/works/OL2W", "1", "First"),
        ("/works/OL1W", "2", "Second"),
    ]
