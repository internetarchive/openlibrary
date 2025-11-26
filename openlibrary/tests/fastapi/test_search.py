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


def search(client, **params):
    """Helper function to make search requests with query parameters.

    This helper provides a cleaner interface for making search requests
    by accepting keyword arguments directly instead of building URL strings.
    """
    from urllib.parse import urlencode

    query_string = urlencode(params, doseq=True)
    return client.get(f'/search.json?{query_string}')


class TestSearchEndpoint:
    """Tests for the /search.json endpoint."""

    def test_search_uses_query_param(self, client, mock_work_search):
        """Test that the search endpoint uses the 'q' query parameter."""
        mock_work_search.return_value = {
            'numFound': 1,
            'start': 0,
            'docs': [{'key': '/works/OL1W', 'title': 'The Lord of the Rings'}],
        }

        response = search(client, q='lord of the rings')

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
        response = search(client, query=json.dumps(query_dict))

        assert response.status_code == 200

        # Verify work_search_async was called with the parsed query
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args
        query_arg = call_args[0][0]
        assert query_arg == query_dict

    @pytest.mark.parametrize(
        ('params', 'expected_kwargs'),
        [
            (
                # It's useful to have limit zero so we can get the total number of results without getting results
                {'q': 'test', 'limit': 0},
                {'page': 1, 'limit': 0, 'offset': None},
            ),
            (
                {'q': 'test', 'page': 3, 'limit': 10},
                {'page': 3, 'limit': 10, 'offset': None},
            ),
            (
                {'q': 'test', 'offset': 50, 'limit': 25},
                {'offset': 50, 'limit': 25, 'page': None},
            ),
            (
                {'q': 'test', 'page': 5, 'offset': 30, 'limit': 10},
                {'offset': 30, 'limit': 10, 'page': None},
            ),
            (
                {'q': 'test'},
                {'limit': 100, 'page': 1, 'offset': None},
            ),
        ],
    )
    def test_pagination_variants(
        self, client, mock_work_search, params, expected_kwargs
    ):
        """Test pagination behavior for various query parameter combinations.

        The mock is configured to return a generic successful response; the focus is on
        verifying that ``work_search_async`` receives the correct pagination arguments.
        """
        mock_work_search.return_value = {
            'numFound': 10,
            'start': 0,
            'docs': [],
        }

        response = search(client, **params)
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

        response = search(client, q='test', offset=10)

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
            {'limit': -1},
            {'offset': -1},
            {'page': 0},
        ],
    )
    def test_pagination_validation_errors(self, client, mock_work_search, params):
        """Test validation errors for invalid pagination parameters."""
        response = search(client, q='test', **params)

        # Should return a validation error
        assert response.status_code == 422

    @pytest.mark.parametrize(
        ('params', 'key_to_check', 'expected_value'),
        [
            # Case 1: publisher should pass as a string
            ({'publisher': 'Lab of Thought'}, 'publisher', 'Lab of Thought'),
            # Case 2: has_fulltext should pass as a boolean
            ({'has_fulltext': 'true'}, 'has_fulltext', True),
            ({'has_fulltext': 'false'}, 'has_fulltext', False),
        ],
    )
    def test_search_parameter_types(
        self, client, mock_work_search, params, key_to_check, expected_value
    ):
        """Test that specific parameters are passed down with the correct types."""
        mock_work_search.return_value = {'numFound': 0, 'start': 0, 'docs': []}

        # Add a required 'q' param to satisfy potential validation, then merge with params
        response = search(client, q='test', **params)

        assert response.status_code == 200
        mock_work_search.assert_called_once()

        # Get the query dictionary passed to the mock
        query_arg = mock_work_search.call_args[0][0]

        assert key_to_check in query_arg
        assert query_arg[key_to_check] == expected_value

    def test_arbitrary_query_params_not_passed_down(self, client, mock_work_search):
        """Test that arbitrary query parameters like osp_count are NOT passed down."""
        mock_work_search.return_value = {
            'numFound': 1,
            'start': 0,
            'docs': [{'key': '/works/OL1W', 'title': 'Test Work'}],
        }

        # Make a request with osp_count parameter
        response = search(client, q='test', osp_count='5')

        assert response.status_code == 200

        # Verify work_search_async was called
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args

        # The query dict should NOT contain the osp_count parameter
        query_arg = call_args[0][0]  # First positional argument
        assert 'osp_count' not in query_arg
        assert query_arg['q'] == 'test'

    def test_multiple_author_keys(self, client, mock_work_search):
        """Test that multiple author_key parameters are parsed correctly.
        Supporting multiple keys from query params isn't the default so this is important to check.
        """
        mock_work_search.return_value = {
            'numFound': 1,
            'start': 0,
            'docs': [{'key': '/works/OL1W', 'title': 'Test Work'}],
        }

        response = search(client, author_key=['OL1A', 'OL2A'])

        assert response.status_code == 200
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args
        query_arg = call_args[0][0]
        assert 'author_key' in query_arg
        assert query_arg['author_key'] == ['OL1A', 'OL2A']
