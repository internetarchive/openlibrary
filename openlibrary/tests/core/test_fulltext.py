from json import JSONDecodeError
from unittest.mock import Mock, patch

import httpx

from infogami import config
from openlibrary.core import fulltext


class Test_fulltext_search_api:
    async def test_no_config(self):
        response = await fulltext.fulltext_search_api({})
        assert response == {"error": "Unable to prepare search engine"}

    async def test_query_exception(self):
        with patch("openlibrary.core.fulltext.httpx.get") as mock_get:
            config.plugin_inside = {"search_endpoint": "mock"}
            raiser = Mock(
                side_effect=httpx.HTTPStatusError(
                    "Unable to Connect", request=Mock(), response=Mock()
                )
            )
            mock_response = Mock()
            mock_response.raise_for_status = raiser
            mock_get.return_value = mock_response
            response = await fulltext.fulltext_search_api({"q": "hello"})
            assert response == {"error": "Unable to query search engine"}

    async def test_bad_json(self):
        with patch("openlibrary.core.fulltext.httpx.get") as mock_get:
            config.plugin_inside = {"search_endpoint": "mock"}
            mock_response = Mock(
                json=Mock(side_effect=JSONDecodeError('Not JSON', 'Not JSON', 0))
            )
            mock_get.return_value = mock_response

            response = await fulltext.fulltext_search_api({"q": "hello"})
            assert response == {"error": "Error converting search engine data to JSON"}
