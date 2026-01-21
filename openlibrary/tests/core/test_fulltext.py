import httpx
import pytest

from infogami import config
from openlibrary.core import fulltext


class Test_fulltext_search_api:

    @pytest.fixture(autouse=True)
    def setup_interactions(self, request_context_fixture, monkeypatch):
        # Automatically set up RequestContextVars for all tests in this class.
        return  # This yields control to the test function

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
