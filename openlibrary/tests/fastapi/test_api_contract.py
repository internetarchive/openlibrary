"""API contract tests to verify webpy and FastAPI search endpoints maintain parity.

These tests ensure that both implementations call their underlying search functions
with identical arguments when given the same HTTP request parameters.
"""

from urllib.parse import urlencode

import pytest
import web
from webtest import TestApp


@pytest.fixture
def webpy_client(mock_work_search):
    """Create a WebTest client for the webpy search_json endpoint.

    This creates a minimal web.py application that routes /search.json
    to the actual search_json handler, allowing real HTTP request parsing.
    """
    from openlibrary.plugins.worksearch.code import search_json

    # Create a minimal web.py app with just the search endpoint
    urls = (
        '/search.json',
        'search_json',
    )

    # Create app with the search_json class in the global namespace
    app = web.application(urls, {'search_json': search_json})

    # Return a WebTest TestApp wrapping the WSGI app
    return TestApp(app.wsgifunc())


class TestAPIContract:
    """Tests to verify webpy and FastAPI endpoints maintain the same contract."""

    @pytest.mark.parametrize(
        ('params', 'description'),
        [
            ({'q': 'python programming'}, 'basic query'),
            ({'q': 'test', 'page': '2', 'limit': '50'}, 'pagination with page'),
            ({'q': 'test', 'offset': '100', 'limit': '25'}, 'pagination with offset'),
            (
                {'q': 'test', 'has_fulltext': 'true', 'public_scan_b': 'true'},
                'boolean parameters',
            ),
            ({'author_key': ['OL1A', 'OL2A']}, 'multiple author keys'),
        ],
    )
    def test_both_endpoints_call_search_with_same_query(
        self,
        fastapi_client,
        webpy_client,
        mock_work_search_async,
        mock_work_search,
        params,
        description,
    ):
        """Verify both endpoints pass equivalent query dicts to their search functions.

        This test makes real HTTP requests to both FastAPI and webpy endpoints,
        then compares the query dict (first positional argument) passed to
        their respective search functions.
        """
        query_string = urlencode(params, doseq=True)

        # === Call FastAPI endpoint ===
        fastapi_response = fastapi_client.get(f'/search.json?{query_string}')
        assert fastapi_response.status_code == 200, f"FastAPI failed for: {description}"

        mock_work_search_async.assert_called_once()
        fastapi_query = mock_work_search_async.call_args[0][0]

        # === Call webpy endpoint ===
        webpy_response = webpy_client.get(f'/search.json?{query_string}')
        assert webpy_response.status_code == 200, f"webpy failed for: {description}"

        mock_work_search.assert_called_once()
        webpy_query = mock_work_search.call_args[0][0]

        # === Compare the query dicts ===
        fastapi_keys = set(fastapi_query)
        webpy_keys = set(webpy_query)
        all_keys = fastapi_keys.union(webpy_keys)
        only_in_one = set(fastapi_keys.symmetric_difference(webpy_keys))

        for key in all_keys:
            fastapi_val = fastapi_query.get(key)
            webpy_val = webpy_query.get(key)
            if key in only_in_one and [] in [fastapi_val, webpy_val]:
                # It's ok if one of them is an empty list and the other is not present
                continue

            assert fastapi_val == webpy_val, (
                f"Query '{key}' mismatch for {description}: "
                f"FastAPI={fastapi_val}, webpy={webpy_val}"
            )
