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

    def test_pagination_with_page(self, client, mock_work_search):
        """Test pagination using the 'page' parameter."""
        mock_work_search.return_value = {
            'numFound': 100,
            'start': 20,
            'docs': [{'key': '/works/OL3W', 'title': 'Test Work 3'}],
        }

        response = client.get('/search.json?q=test&page=3&limit=10')

        assert response.status_code == 200

        # Verify work_search_async was called with correct pagination
        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]
        assert call_kwargs['page'] == 3
        assert call_kwargs['limit'] == 10
        assert call_kwargs['offset'] is None

    def test_pagination_with_offset(self, client, mock_work_search):
        """Test pagination using the 'offset' parameter."""
        mock_work_search.return_value = {
            'numFound': 100,
            'start': 50,
            'docs': [{'key': '/works/OL4W', 'title': 'Test Work 4'}],
        }

        response = client.get('/search.json?q=test&offset=50&limit=25')

        assert response.status_code == 200

        # Verify work_search_async was called with correct pagination
        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]
        assert call_kwargs['offset'] == 50
        assert call_kwargs['limit'] == 25
        # When offset is provided, page should be None
        assert call_kwargs['page'] is None

    def test_pagination_offset_overrides_page(self, client, mock_work_search):
        """Test that offset takes precedence over page when both are provided."""
        mock_work_search.return_value = {
            'numFound': 100,
            'start': 30,
            'docs': [],
        }

        response = client.get('/search.json?q=test&page=5&offset=30&limit=10')

        assert response.status_code == 200

        # Verify that offset is used and page is None
        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]
        assert call_kwargs['offset'] == 30
        assert call_kwargs['page'] is None

    def test_default_pagination(self, client, mock_work_search):
        """Test default pagination values when not specified."""
        mock_work_search.return_value = {
            'numFound': 10,
            'start': 0,
            'docs': [],
        }

        response = client.get('/search.json?q=test')

        assert response.status_code == 200

        # Verify default pagination values
        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]
        assert call_kwargs['limit'] == 100  # Default limit
        assert call_kwargs['page'] == 1  # Default page
        assert call_kwargs['offset'] is None

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
