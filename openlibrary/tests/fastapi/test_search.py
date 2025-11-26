"""Basic tests for the FastAPI search endpoint."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from openlibrary.asgi_app import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_work_search():
    """Mock the work_search_async function to avoid actual Solr calls."""
    # autospec=True ensures the mock has the same signature as the real function
    with patch('openlibrary.fastapi.search.work_search_async', autospec=True) as mock:
        # Default mock response
        mock.return_value = {
            'numFound': 2,
            'start': 0,
            'docs': [
                {'key': '/works/OL1W', 'title': 'Test Work 1'},
                {'key': '/works/OL2W', 'title': 'Test Work 2'},
            ],
        }
        yield mock


class TestSearchEndpoint:
    """Tests for the /search.json endpoint."""

    def test_search_uses_query_param(self, client, mock_work_search):
        """Test that the search endpoint uses the 'q' query parameter."""
        # Mock the async function
        mock_work_search.return_value = {
            'numFound': 1,
            'start': 0,
            'docs': [{'key': '/works/OL1W', 'title': 'The Lord of the Rings'}],
        }

        response = client.get('/search.json?q=lord+of+the+rings')

        assert response.status_code == 200
        data = response.json()

        # Verify the response contains the query
        assert data['q'] == 'lord of the rings'
        assert 'docs' in data
        assert 'numFound' in data

        # Verify work_search_async was called with the query
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args
        query_arg = call_args[0][0]  # First positional argument
        assert query_arg['q'] == 'lord of the rings'

    def test_search_uses_query_alias_param(self, client, mock_work_search):
        """Test that the search endpoint uses the 'query' query parameter (alias for full JSON query)."""
        mock_work_search.return_value = {
            'numFound': 1,
            'start': 0,
            'docs': [{'key': '/works/OL1W', 'title': 'Test'}],
        }

        # The 'query' param should accept a full JSON-encoded Solr query
        query_dict = {'q': 'test', 'author': 'Tolkien'}
        query_str = json.dumps(query_dict)

        response = client.get(f'/search.json?query={query_str}')

        assert response.status_code == 200

        # Verify work_search_async was called with the parsed query
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args
        query_arg = call_args[0][0]
        assert query_arg == query_dict

    @pytest.mark.parametrize(
        ('query', 'expected_kwargs'),
        [
            (
                "q=test&page=3&limit=10",
                {"page": 3, "limit": 10, "offset": None},
            ),
            (
                "q=test&offset=50&limit=25",
                {"offset": 50, "limit": 25, "page": None},
            ),
            (
                "q=test&page=5&offset=30&limit=10",
                {"offset": 30, "limit": 10, "page": None},
            ),
            (
                "q=test",
                {"limit": 100, "page": 1, "offset": None},
            ),
        ],
    )
    def test_pagination_variants(
        self, client, mock_work_search, query, expected_kwargs
    ):
        """Test pagination behavior for various query parameter combinations.

        The mock is configured to return a generic successful response; the focus is on
        verifying that ``work_search_async`` receives the correct pagination arguments.
        """
        mock_work_search.return_value = {
            "numFound": 10,
            "start": 0,
            "docs": [],
        }

        response = client.get(f"/search.json?{query}")
        assert response.status_code == 200

        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]
        for key, expected in expected_kwargs.items():
            assert call_kwargs.get(key) == expected

    def test_response_includes_metadata(self, client, mock_work_search):
        """Test that the response includes expected metadata fields."""
        mock_work_search.return_value = {
            'numFound': 5,
            'start': 0,
            'docs': [{'key': '/works/OL5W', 'title': 'Test'}],
        }

        response = client.get('/search.json?q=test&offset=10')

        assert response.status_code == 200
        data = response.json()

        # Verify metadata fields are present
        assert 'documentation_url' in data
        assert (
            data['documentation_url'] == 'https://openlibrary.org/dev/docs/api/search'
        )
        assert 'q' in data
        assert data['q'] == 'test'
        assert 'offset' in data
        assert data['offset'] == 10
        assert 'docs' in data
        # Verify docs is at the end (last key)
        assert list(data.keys())[-1] == 'docs'

    @pytest.mark.parametrize(
        'params',
        [
            {'limit': 0},
            {'offset': -1},
            {'page': 0},
        ],
    )
    def test_pagination_validation_errors(self, client, mock_work_search, params):
        """Test validation errors for invalid pagination parameters."""
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        response = client.get(f'/search.json?q=test&{query}')

        # Should return a validation error
        assert response.status_code == 422
