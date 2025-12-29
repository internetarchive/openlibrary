"""API contract tests to verify webpy and FastAPI search endpoints maintain parity.

These tests ensure that both implementations call their underlying search functions
with identical arguments when given the same HTTP request parameters.
"""

from typing import Literal, get_args, get_origin
from urllib.parse import urlencode

import pytest
import web
from pydantic import BaseModel
from webtest import TestApp

from openlibrary.fastapi.search import PublicQueryOptions


def generate_test_params_from_model(
    model: type[BaseModel],
) -> dict[str, str | list[str]]:
    """Generate test parameters by introspecting pydantic model fields.

    Uses examples if specified, otherwise generates sensible defaults:
    - bool: 'true'
    - str: 'VVV'
    - list[str]: ['VVV1', 'VVV2']
    """
    params: dict[str, str | list[str]] = {}

    for field_name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        origin = get_origin(annotation)
        args = get_args(annotation)

        # Determine if this is a list field
        is_list_field = origin is list

        # Get the first example value if examples are specified
        examples = field_info.examples
        if examples:
            # examples can be a list or a dict of named examples
            if isinstance(examples, dict):
                # Get the first example's value
                first_example = next(iter(examples.values()))
                if isinstance(first_example, dict) and 'value' in first_example:
                    example_val = first_example['value']
                else:
                    example_val = first_example
            else:
                example_val = examples[0] if examples else None

            if example_val is not None:
                # For list fields, ensure we have a list with multiple values
                if is_list_field:
                    if isinstance(example_val, list):
                        params[field_name] = example_val
                    else:
                        # Wrap single example in list and add a second value
                        params[field_name] = [str(example_val), 'VVV2']
                else:
                    params[field_name] = str(example_val)
                continue

        # Check if one of the arguments is a Literal (handles Optional[Literal])
        nested_literal = next((arg for arg in args if get_origin(arg) is Literal), None)

        # Handle types without examples
        if origin is Literal:
            # Direct Literal: x: Literal['A', 'B']
            params[field_name] = str(args[0])
        elif nested_literal:
            # Optional Literal: x: Literal['A', 'B'] | None
            # Extract args from the nested literal type
            literal_values = get_args(nested_literal)
            params[field_name] = str(literal_values[0])
        elif annotation is bool or (origin is type(None | bool) and bool in args):
            # Boolean field
            params[field_name] = 'true'
        elif is_list_field:
            # List field - use two values to test list handling
            params[field_name] = ['VVV1', 'VVV2']
        elif annotation is str or (origin is type(None | str) and str in args):
            # String field
            params[field_name] = 'VVV'
        else:
            raise ValueError(f"Unsupported type: {annotation}, {origin}, {args}")

    return params


@pytest.fixture
def webpy_client(mock_work_search, mock_fulltext_search, mock_run_solr_query):
    """Create a WebTest client for webpy search endpoints.

    This creates a minimal web.py application allowing real HTTP request parsing for endpoints.
    """
    from openlibrary.plugins.inside.code import search_inside_json
    from openlibrary.plugins.worksearch.code import search_json, subject_search_json

    # Create a minimal web.py app with all search endpoints
    urls = (
        '/search.json',
        'search_json',
        '/search/inside',
        'search_inside_json',
        '/search/subjects',
        'subject_search_json',
    )

    # Create app with all handlers in the global namespace
    app = web.application(
        urls,
        {
            'search_json': search_json,
            'search_inside_json': search_inside_json,
            'subject_search_json': subject_search_json,
        },
    )

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
            (
                generate_test_params_from_model(PublicQueryOptions),
                'all PublicQueryOptions fields (generated)',
            ),
            ({'isbn': '9780143038252'}, 'isbn'),
            ({'author': 'mark twain'}, 'author'),
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

    @pytest.mark.parametrize(
        ('params', 'description', 'expected_kwargs'),
        [
            (
                {'q': 'test search inside', 'page': '5', 'limit': '25'},
                'all parameters',
                {
                    'q': 'test search inside',
                    'page': 5,
                    'limit': 25,
                    'js': True,
                    'facets': True,
                },
            ),
        ],
    )
    def test_search_inside_parameters(
        self,
        fastapi_client,
        mock_fulltext_search_async,
        params,
        description,
        expected_kwargs,
    ):
        """Test search_inside endpoint passes all parameters correctly."""

        query_string = urlencode(params)
        response = fastapi_client.get(f'/search/inside.json?{query_string}')

        assert response.status_code == 200, f"Failed for: {description}"
        mock_fulltext_search_async.assert_called_once()

        # Verify all parameters were passed correctly
        call_args = mock_fulltext_search_async.call_args
        # q is passed as positional arg (first element)
        q = call_args[0][0]
        assert q == expected_kwargs['q'], (
            f"Parameter 'q' mismatch for {description}: "
            f"expected={expected_kwargs['q']}, actual={q}"
        )

        # Other params are keyword arguments
        for key in ['page', 'limit', 'js', 'facets']:
            expected_val = expected_kwargs[key]
            actual_val = call_args.kwargs.get(key)
            assert actual_val == expected_val, (
                f"Parameter '{key}' mismatch for {description}: "
                f"expected={expected_val}, actual={actual_val}"
            )

    @pytest.mark.parametrize(
        ('params', 'description'),
        [
            ({'q': 'python programming'}, 'basic query'),
            ({'q': 'test', 'page': '2', 'limit': '15'}, 'pagination'),
        ],
    )
    def test_both_search_inside_endpoints_call_search_with_same_params(
        self,
        fastapi_client,
        webpy_client,
        mock_fulltext_search_async,
        mock_fulltext_search,
        params,
        description,
    ):
        """Verify both webpy and FastAPI search_inside endpoints pass equivalent parameters.

        This test makes real HTTP requests to both FastAPI and webpy search_inside endpoints,
        then compares the arguments passed to their respective search functions.
        """
        query_string = urlencode(params, doseq=True)

        # === Call FastAPI endpoint ===
        fastapi_response = fastapi_client.get(f'/search/inside.json?{query_string}')
        assert fastapi_response.status_code == 200, f"FastAPI failed for: {description}"

        mock_fulltext_search_async.assert_called_once()
        fastapi_call_args = mock_fulltext_search_async.call_args

        # === Call webpy endpoint ===
        webpy_response = webpy_client.get(f'/search/inside?{query_string}')
        assert webpy_response.status_code == 200, f"webpy failed for: {description}"

        mock_fulltext_search.assert_called_once()
        webpy_call_args = mock_fulltext_search.call_args

        # === Compare the positional args (q) ===
        fastapi_q = fastapi_call_args[0][0]
        webpy_q = webpy_call_args[0][0]
        assert fastapi_q == webpy_q, (
            f"Parameter 'q' mismatch for {description}: "
            f"FastAPI={fastapi_q}, webpy={webpy_q}"
        )

        # === Compare the keyword args (page, limit, js, facets) ===
        fastapi_kwargs = fastapi_call_args.kwargs
        webpy_kwargs = webpy_call_args.kwargs

        for key in ['page', 'limit', 'js', 'facets']:
            fastapi_val = fastapi_kwargs.get(key)
            webpy_val = webpy_kwargs.get(key)
            assert fastapi_val == webpy_val, (
                f"Parameter '{key}' mismatch for {description}: "
                f"FastAPI={fastapi_val}, webpy={webpy_val}"
            )

    @pytest.mark.parametrize(
        ('params', 'description'),
        [
            ({'q': 'science'}, 'basic query'),
            ({'q': 'history', 'offset': '10', 'limit': '25'}, 'pagination'),
        ],
    )
    def test_both_subjects_endpoints_call_search_with_same_params(
        self,
        fastapi_client,
        webpy_client,
        mock_async_run_solr_query,
        mock_run_solr_query,
        params,
        description,
    ):
        """Verify both webpy and FastAPI search/subjects endpoints pass equivalent parameters.

        This test makes real HTTP requests to both FastAPI and webpy search/subjects endpoints,
        then compares the arguments passed to their respective solr query functions.
        """
        query_string = urlencode(params, doseq=True)

        # === Call FastAPI endpoint ===
        fastapi_response = fastapi_client.get(f'/search/subjects.json?{query_string}')
        assert fastapi_response.status_code == 200, f"FastAPI failed for: {description}"

        mock_async_run_solr_query.assert_called_once()
        fastapi_call_args = mock_async_run_solr_query.call_args

        # === Call webpy endpoint ===
        webpy_response = webpy_client.get(f'/search/subjects?{query_string}')
        assert webpy_response.status_code == 200, f"webpy failed for: {description}"

        mock_run_solr_query.assert_called_once()
        webpy_call_args = mock_run_solr_query.call_args

        # === Compare the call arguments ===
        # Both call their respective solr query functions with scheme, param dict, and kwargs

        # Compare the param dict (second positional arg)
        fastapi_param = fastapi_call_args[0][1]
        webpy_param = webpy_call_args[0][1]

        # FastAPI uses pagination.offset, webpy uses web.input().offset
        # Both should result in the same offset/limit values
        for key in ['q']:
            fastapi_val = fastapi_param.get(key)
            webpy_val = webpy_param.get(key)
            assert fastapi_val == webpy_val, (
                f"Parameter '{key}' mismatch for {description}: "
                f"FastAPI={fastapi_val}, webpy={webpy_val}"
            )

        # Compare kwargs
        fastapi_kwargs = {
            k: v for k, v in fastapi_call_args[1].items() if k not in ['scheme']
        }
        webpy_kwargs = {
            k: v for k, v in webpy_call_args[1].items() if k not in ['scheme']
        }

        for key in ['offset', 'rows', 'sort', 'request_label']:
            fastapi_val = fastapi_kwargs.get(key)
            webpy_val = webpy_kwargs.get(key)

            # Handle offset: FastAPI may pass None, webpy defaults to 0
            if key == 'offset' and fastapi_val is None and webpy_val == 0:
                continue

            assert fastapi_val == webpy_val, (
                f"Parameter '{key}' mismatch for {description}: "
                f"FastAPI={fastapi_val}, webpy={webpy_val}"
            )
