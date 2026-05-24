import httpx
import pytest

from infogami import config
from openlibrary.core import fulltext


@pytest.mark.usefixtures("request_context_fixture")
class Test_fulltext_search_api:
    @pytest.mark.asyncio
    async def test_no_config(self):
        response = await fulltext.fulltext_search_api({})
        assert response == {"error": "Unable to prepare search engine"}

    @pytest.mark.asyncio
    async def test_query_exception(self, httpx_mock, monkeypatch):
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        request = httpx.Request("GET", "http://mock")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("Unable to Connect", request=request, response=response)

        httpx_mock.add_exception(error)

        response = await fulltext.fulltext_search_api({"q": "hello"})
        assert response == {"error": "Unable to query search engine"}

    @pytest.mark.asyncio
    async def test_bad_json(self, httpx_mock, monkeypatch):
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        httpx_mock.add_response(text="Not JSON")

        response = await fulltext.fulltext_search_api({"q": "hello"})
        assert response == {"error": "Error converting search engine data to JSON"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("page", "limit", "offset_kwarg", "expected_from"),
        [
            (1, 20, "NOT_PASSED", 0),  # offset not passed at all
            (1, 20, None, 0),  # offset=None explicitly
            (10, 20, "NOT_PASSED", 180),  # offset not passed, page 10
            (5, 20, 100, 100),  # explicit offset provided
        ],
    )
    async def test_pagination_offset_calculation(self, httpx_mock, monkeypatch, page, limit, offset_kwarg, expected_from):
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        httpx_mock.add_response(json={"hits": {"hits": []}})

        # Conditionally build kwargs to test "not passed" scenario
        kwargs = {"page": page, "limit": limit}
        if offset_kwarg != "NOT_PASSED":
            kwargs["offset"] = offset_kwarg

        await fulltext.fulltext_search_async("test", **kwargs)
        request = httpx_mock.get_request()
        assert f"from={expected_from}" in request.url.query.decode()
