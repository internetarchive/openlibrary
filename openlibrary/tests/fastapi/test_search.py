"""Basic tests for the FastAPI search endpoint."""

import json
from typing import Annotated
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from openlibrary.fastapi.search import PublicQueryOptions
from openlibrary.plugins.worksearch.code import WorkSearchScheme


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


def test_check_params():
    """
    The purpose of this test is to ensure that check_params doesn't get out of sync with what is in the endpoint.
    """
    for field in WorkSearchScheme.check_params:
        if field == 'author_key':
            # Skip author_key because it's a list and can't go into the Pydantic model now
            continue
        assert field in PublicQueryOptions.model_fields


##### The tests here are to show that it's hard to get the lists working for query params
def test_multi_key():  # noqa: PLR0915

    app = FastAPI()

    # This doesn't work because it expects the author keys to be in the body
    @app.get("/search.json")
    async def search_works(
        author_key: list[str],
    ):
        return {'author_key': author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 422
    assert response.json() != {'author_key': ['OL1A', 'OL2A']}
    assert response.json()['detail'][0]['type'] == 'missing'
    assert response.json()['detail'][0]['loc'] == ['body']

    # This test does work because we're explicitly using Query but we want it moved into a Pydantic model
    app = FastAPI()

    @app.get("/search.json")
    async def search_works2(
        author_key: Annotated[list[str], Query()],
    ):
        return {'author_key': author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 200
    assert response.json() == {'author_key': ['OL1A', 'OL2A']}

    # This test does work because we're explicitly using query but we don't want None
    app = FastAPI()

    @app.get("/search.json")
    async def search_works3(
        author_key: Annotated[list[str] | None, Query()] = None,
    ):
        return {'author_key': author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 200
    assert response.json() == {'author_key': ['OL1A', 'OL2A']}

    # This this says body is missing again ok
    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: list[str]

    @app.get("/search.json")
    async def search_works4(
        params: SearchParams,
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 422
    assert response.json() != {'author_key': ['OL1A', 'OL2A']}
    assert response.json()['detail'][0]['type'] == 'missing'
    assert response.json()['detail'][0]['loc'] == ['body']

    # Ok so now this works. Yay!
    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: list[str]

    @app.get("/search.json")
    async def search_works5(
        params: Annotated[SearchParams, Query()],
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 200
    assert response.json() == {'author_key': ['OL1A', 'OL2A']}

    # But what if there are other params? Uh oh then they're missing...
    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: list[str]

    @app.get("/search.json")
    async def search_works6(
        params: Annotated[SearchParams, Query()],
        q: str | None = None,
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 422
    assert response.json()['detail'][0]['type'] == 'missing'
    assert response.json()['detail'][0]['loc'] == ['query', 'params']

    # So Gemini says it'll work if we use Depends instead of query! But then we get a body missing :(
    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: list[str]

    @app.get("/search.json")
    async def search_works7(
        params: Annotated[SearchParams, Depends()],
        q: str | None = None,
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 422
    # assert response.json() == {'author_key': ['OL1A', 'OL2A']}
    assert response.json()['detail'][0]['type'] == 'missing'
    assert response.json()['detail'][0]['loc'] == ['body']

    # So what if we make it clearer that it's a query param? Woah that works!
    """
    It seems to work because:
    1. Depends(): Tells FastAPI to explode the Pydantic model into individual arguments (dependency injection).
    2. Field(Query([])): Overrides the default behavior for lists. It forces FastAPI to look for ?author_key=...
       in the URL query string instead of expecting a JSON array in the request body.
    The Field part is needed because FastAPI's default guess for lists inside Pydantic models is wrong for your use case.
       It guesses "JSON Body," and you have to manually correct it to "Query String."
    """
    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: list[str] = Field(Query([]))

    @app.get("/search.json")
    async def search_works8(
        params: Annotated[SearchParams, Depends()],
        q: str | None = None,
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 200
    assert response.json() == {'author_key': ['OL1A', 'OL2A']}

    # A quick check to make sure it's ok with no params
    response = client.get('/search.json')
    assert response.status_code == 200
    assert response.json() == {'author_key': []}

    # But wait I think doing Query([]) is not great to put a mutable class in the default.
    # However, pydantic said don't worry about it.
    # https://docs.pydantic.dev/latest/concepts/fields/#mutable-default-values
    # Lets try to use the "proper way" just in case
    # And it works great! But it's ugly so lets not do it

    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: list[str] = Field(Query(default_factory=list))

    @app.get("/search.json")
    async def search_works9(
        params: Annotated[SearchParams, Depends()],
        q: str | None = None,
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 200
    assert response.json() == {'author_key': ['OL1A', 'OL2A']}

    # A quick check to make sure it's ok with no params
    response = client.get('/search.json')
    assert response.status_code == 200
    assert response.json() == {'author_key': []}

    # But wait AI says there's a modern standard of Annotated
    # However, after looking at the fullstack fastapi template https://github.com/fastapi/full-stack-fastapi-template
    # It seems they don't do it so we shouldn't have to either
    # So in summary we should use search_works8 I think!

    app = FastAPI()

    class SearchParams(BaseModel):
        author_key: Annotated[list[str], Field(Query([]))]

    @app.get("/search.json")
    async def search_works10(
        params: Annotated[SearchParams, Depends()],
        q: str | None = None,
    ):
        return {'author_key': params.author_key}

    client = TestClient(app)
    response = client.get('/search.json?author_key=OL1A&author_key=OL2A')
    assert response.status_code == 200
    assert response.json() == {'author_key': ['OL1A', 'OL2A']}

    # A quick check to make sure it's ok with no params
    response = client.get('/search.json')
    assert response.status_code == 200
    assert response.json() == {'author_key': []}
