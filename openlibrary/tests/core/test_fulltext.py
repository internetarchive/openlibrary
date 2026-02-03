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
        monkeypatch.setattr(
            config, "plugin_inside", {"search_endpoint": url}, raising=False
        )
        request = httpx.Request("GET", "http://mock")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError(
            "Unable to Connect", request=request, response=response
        )

        httpx_mock.add_exception(error)

        response = await fulltext.fulltext_search_api({"q": "hello"})
        assert response == {"error": "Unable to query search engine"}

    @pytest.mark.asyncio
    async def test_bad_json(self, httpx_mock, monkeypatch):
        url = "http://mock"
        monkeypatch.setattr(
            config, "plugin_inside", {"search_endpoint": url}, raising=False
        )
        httpx_mock.add_response(text="Not JSON")

        response = await fulltext.fulltext_search_api({"q": "hello"})
        assert response == {"error": "Error converting search engine data to JSON"}

    @pytest.mark.asyncio
    async def test_pagination_offset_calculation(self, httpx_mock, monkeypatch):
        """Test that page parameter correctly calculates offset for pagination."""
        url = "http://mock"
        monkeypatch.setattr(
            config, "plugin_inside", {"search_endpoint": url}, raising=False
        )

        # Mock a successful response
        httpx_mock.add_response(json={"hits": {"hits": []}})

        # Test page 1 should have offset 0
        await fulltext.fulltext_search_async("test", page=1, limit=20)
        request = httpx_mock.get_request()
        assert "from=0" in request.url.query.decode()

        # Reset mock
        httpx_mock.reset()
        httpx_mock.add_response(json={"hits": {"hits": []}})

        # Test page 10 should have offset 180 (9 * 20)
        await fulltext.fulltext_search_async("test", page=10, limit=20)
        request = httpx_mock.get_request()
        assert "from=180" in request.url.query.decode()

        # Reset mock
        httpx_mock.reset()
        httpx_mock.add_response(json={"hits": {"hits": []}})

        # Test explicit offset overrides page
        await fulltext.fulltext_search_async("test", page=5, offset=100, limit=20)
        request = httpx_mock.get_request()
        assert "from=100" in request.url.query.decode()
