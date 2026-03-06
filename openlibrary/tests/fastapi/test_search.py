"""Basic tests for the FastAPI search endpoint."""

import json

import pytest

from openlibrary.fastapi.search import PublicQueryOptions
from openlibrary.plugins.worksearch.code import WorkSearchScheme


@pytest.fixture
def client(fastapi_client):
    """Alias for backward compatibility with existing tests."""
    # TODO: refactor to remove this fixture before merging
    return fastapi_client


@pytest.fixture
def mock_work_search(mock_work_search_async):
    """Alias for backward compatibility with existing tests."""
    # TODO: refactor to remove this fixture before merging
    return mock_work_search_async


def search(client, **params):
    """Helper function to make search requests with query parameters.

    This helper provides a cleaner interface for making search requests
    by accepting keyword arguments directly instead of building URL strings.
    """
    from urllib.parse import urlencode

    query_string = urlencode(params, doseq=True)
    return client.get(f"/search.json?{query_string}")


class TestSearchEndpoint:
    """Tests for the /search.json endpoint."""

    def test_search_uses_query_param(self, client, mock_work_search):
        """Test that the search endpoint uses the 'q' query parameter."""
        response = search(client, q="lord of the rings")

        assert response.status_code == 200
        data = response.json()

        # Verify the response contains the query
        assert data["q"] == "lord of the rings"
        assert "docs" in data
        assert "numFound" in data

        # Verify work_search_async was called with the query
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args
        query_arg = call_args[0][0]  # First positional argument
        assert query_arg["q"] == "lord of the rings"

    def test_query_param_takes_precedence_over_individual_params(self, client, mock_work_search):
        """If both 'query=' and individual params are sent, 'query=' wins completely."""
        response = search(
            client,
            query=json.dumps({"title": "Override"}),
            title="Should be ignored",
            author_key=["OL999A"],
        )
        assert response.status_code == 200
        query_dict = mock_work_search.call_args[0][0]
        assert query_dict == {"title": "Override"}

    @pytest.mark.parametrize(
        ("query_dict", "description"),
        [
            # Simple query with just 'q'
            ({"q": "python programming"}, "simple q param"),
            # Query with multiple fields
            (
                {"q": "fantasy", "author": "Tolkien", "title": "Ring"},
                "multiple fields",
            ),
            # Query with list values
            (
                {"author_key": ["OL1A", "OL2A"], "subject": "fiction"},
                "list values",
            ),
            # Query with boolean fields
            ({"q": "open access", "has_fulltext": True}, "boolean fields"),
            # Query with numeric fields
            ({"q": "history", "first_publish_year": 1990}, "numeric fields"),
        ],
    )
    def test_query_param_parsing(self, client, mock_work_search, query_dict, description):
        """Test that the 'query' JSON parameter is correctly parsed and passed to work_search_async.

        When the 'query' parameter is specified, it should be JSON-decoded and passed
        directly as the first positional argument to work_search_async, bypassing
        the individual query parameter parsing.
        """

        response = search(client, query=json.dumps(query_dict))

        assert response.status_code == 200, f"Failed for case: {description}"
        mock_work_search.assert_called_once()

        # Verify the query dict is passed as the first positional argument
        call_args = mock_work_search.call_args
        actual_query = call_args[0][0]
        assert actual_query == query_dict, f"Query mismatch for case: {description}"

    @pytest.mark.parametrize(
        "invalid_json",
        [
            "{not valid json}",
            '{"unclosed": "brace"',
            "{'single': 'quotes'}",  # JSON requires double quotes
            "just a string",
            "[1, 2, 3",  # unclosed array
        ],
    )
    def test_query_param_invalid_json(self, client, mock_work_search, invalid_json):
        """Test that invalid JSON in the 'query' parameter returns an error.

        When the 'query' parameter contains malformed JSON, the endpoint should
        return an error response rather than crashing.
        """
        response = search(client, query=invalid_json)

        # Should return a 422 validation error for invalid JSON
        assert response.status_code == 422
        mock_work_search.assert_not_called()

    @pytest.mark.parametrize(
        ("params", "expected_kwargs"),
        [
            (
                # It's useful to have limit zero so we can get the total number of results without getting results
                {"q": "test", "limit": 0},
                {"page": 1, "limit": 0, "offset": None},
            ),
            (
                {"q": "test", "page": 3, "limit": 10},
                {"page": 3, "limit": 10, "offset": None},
            ),
            (
                {"q": "test", "offset": 50, "limit": 25},
                {"offset": 50, "limit": 25, "page": None},
            ),
            (
                {"q": "test", "page": 5, "offset": 30, "limit": 10},
                {"offset": 30, "limit": 10, "page": None},
            ),
            (
                {"q": "test"},
                {"limit": 100, "page": 1, "offset": None},
            ),
        ],
    )
    def test_pagination_variants(self, client, mock_work_search, params, expected_kwargs):
        """Test pagination behavior for various query parameter combinations.

        The mock is configured to return a generic successful response; the focus is on
        verifying that ``work_search_async`` receives the correct pagination arguments.
        """
        response = search(client, **params)
        assert response.status_code == 200

        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]
        for key, expected in expected_kwargs.items():
            assert call_kwargs.get(key) == expected

    def test_response_includes_metadata(self, client, mock_work_search):
        """Test that the response includes expected metadata fields."""

        response = search(client, q="test", offset=10)

        assert response.status_code == 200
        data = response.json()

        # Verify metadata fields are present
        assert "documentation_url" in data
        assert data["documentation_url"] == "https://openlibrary.org/dev/docs/api/search"
        assert "q" in data
        assert data["q"] == "test"
        assert "offset" in data
        assert data["offset"] == 10
        assert "docs" in data
        # Verify docs is at the end (last key)
        assert list(data.keys())[-1] == "docs"

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": -1},
            {"offset": -1},
            {"page": 0},
        ],
    )
    def test_pagination_validation_errors(self, client, mock_work_search, params):
        """Test validation errors for invalid pagination parameters."""
        response = search(client, q="test", **params)

        # Should return a validation error
        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("params", "key_to_check", "expected_value"),
        [
            # Case 1: publisher should pass as a string
            ({"publisher": "Lab of Thought"}, "publisher", "Lab of Thought"),
            # Case 2: has_fulltext should pass as a boolean
            ({"has_fulltext": "true"}, "has_fulltext", "true"),
            ({"has_fulltext": "false"}, "has_fulltext", "false"),
        ],
    )
    def test_search_parameter_types(self, client, mock_work_search, params, key_to_check, expected_value):
        """Test that specific parameters are passed down with the correct types."""

        # Add a required 'q' param to satisfy potential validation, then merge with params
        response = search(client, q="test", **params)

        assert response.status_code == 200
        mock_work_search.assert_called_once()

        # Get the query dictionary passed to the mock
        query_arg = mock_work_search.call_args[0][0]

        assert key_to_check in query_arg
        assert query_arg[key_to_check] == expected_value

    def test_arbitrary_query_params_not_passed_down(self, client, mock_work_search):
        """Test that arbitrary query parameters like osp_count_fake are NOT passed down."""

        # Make a request with osp_count_fake parameter
        response = search(client, q="test", osp_count_fake="5")

        assert response.status_code == 200

        # Verify work_search_async was called
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args

        # The query dict should NOT contain the osp_count_fake parameter
        query_arg = call_args[0][0]  # First positional argument
        assert "osp_count_fake" not in query_arg
        assert query_arg["q"] == "test"

    def test_multiple_author_keys(self, client, mock_work_search):
        """Test that multiple author_key parameters are parsed correctly.
        Supporting multiple keys from query params isn't the default so this is important to check.
        """

        response = search(client, author_key=["OL1A", "OL2A"])

        assert response.status_code == 200
        mock_work_search.assert_called_once()
        call_args = mock_work_search.call_args
        query_arg = call_args[0][0]
        assert "author_key" in query_arg
        assert query_arg["author_key"] == ["OL1A", "OL2A"]

    @pytest.mark.parametrize(
        ("q_value", "expected_status"),
        [
            (None, 200),  # q is optional
            ("python", 200),  # valid
            ("lord", 200),  # valid
            ("ab", 422),  # too short
            ("a", 422),  # too short
            ("the", 422),  # blocked word
            ("THE", 422),  # blocked word (case-insensitive)
            ("the hobbit", 200),  # "the" allowed when not alone
        ],
    )
    def test_q_param_validation(self, client, mock_work_search, q_value, expected_status):
        """Test that the 'q' parameter is optional, ≥3 chars when present, and not exactly 'the'."""
        params = {} if q_value is None else {"q": q_value}
        response = search(client, **params)

        assert response.status_code == expected_status

        if expected_status == 200:
            mock_work_search.assert_called_once()
        else:
            mock_work_search.assert_not_called()

    @pytest.mark.parametrize(
        ("params", "expected_fields"),
        [
            # No fields param: should use default fields
            ({"q": "test"}, sorted(WorkSearchScheme.default_fetched_fields)),
            # Single field as comma-separated string
            ({"q": "test", "fields": "title"}, ["title"]),
            # Multiple fields as comma-separated string
            (
                {"q": "test", "fields": "title,author_name,key"},
                ["title", "author_name", "key"],
            ),
            # Fields with spaces (edge case)
            ({"q": "test", "fields": "title, author_name"}, ["title", "author_name"]),
        ],
    )
    def test_fields_passed_as_list(self, client, mock_work_search, params, expected_fields):
        """Test that the 'fields' parameter is always passed as a list to work_search_async.

        This ensures that comma-separated field strings are properly split into lists,
        and that default fields are used when no fields parameter is provided.
        """
        response = search(client, doseq=False, **params)

        assert response.status_code == 200
        mock_work_search.assert_called_once()
        call_kwargs = mock_work_search.call_args[1]

        assert "fields" in call_kwargs
        assert isinstance(call_kwargs["fields"], list)
        assert call_kwargs["fields"] == expected_fields


def test_public_api_params():
    """
    This test is to ensure that public_api_params doesn't get out of sync with what is in the endpoint.
    If this test is failing, then you probably need to update the other model with the difference
    """
    for param in WorkSearchScheme.public_api_params:
        assert param in PublicQueryOptions.model_fields


class TestOpenAPIDocumentation:
    """Tests to verify OpenAPI documentation is generated correctly."""

    def test_openapi_contains_search_endpoint(self, client):
        """Test that the OpenAPI spec contains the /search.json endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()

        assert "paths" in openapi
        assert "/search.json" in openapi["paths"]

    def test_openapi_parameters_have_descriptions(self, client):
        """Test that query parameters in the OpenAPI spec have descriptions.

        This test verifies that the descriptions we define in our Pydantic models
        are correctly propagated to the OpenAPI schema.
        """
        response = client.get("/openapi.json")
        openapi = response.json()

        search_endpoint = openapi["paths"]["/search.json"]["get"]
        parameters = search_endpoint.get("parameters", [])

        # Build a dict of parameter name -> parameter info for easier testing
        params_by_name = {p["name"]: p for p in parameters}

        # Check that specific parameters have descriptions
        expected_descriptions = {
            "fields": "The fields to return.",
            "query": "A full JSON encoded solr query.",
            "sort": "The sort order of results.",
            "spellcheck_count": "The number of spellcheck suggestions.",
        }

        for param_name, expected_desc in expected_descriptions.items():
            assert param_name in params_by_name, f"Parameter '{param_name}' not found in OpenAPI spec"
            param = params_by_name[param_name]
            # Check both top-level description and schema description
            actual_desc = param.get("description") or param.get("schema", {}).get("description")
            assert actual_desc == expected_desc, f"Parameter '{param_name}' has description '{actual_desc}', expected '{expected_desc}'"

    def test_debug_openapi_structure(self, client):
        """Debug test to see the actual OpenAPI structure for search endpoint parameters."""
        response = client.get("/openapi.json")
        openapi = response.json()

        search_endpoint = openapi["paths"]["/search.json"]["get"]
        parameters = search_endpoint.get("parameters", [])

        print("\n\n=== OpenAPI Parameters for /search.json ===")
        # Only print the parameters we care about for descriptions
        for param in parameters:
            if param["name"] in [
                "fields",
                "query",
                "sort",
                "spellcheck_count",
                "limit",
            ]:
                print(f"\n{param['name']}:")
                print(f"  top-level description: {param.get('description')}")
                print(f"  schema description: {param.get('schema', {}).get('description')}")
                print(f"  schema default: {param.get('schema', {}).get('default')}")

        # This test always passes - it's just for debug output
        assert True
