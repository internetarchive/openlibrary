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
            (
                generate_test_params_from_model(PublicQueryOptions),
                'all PublicQueryOptions fields (generated)',
            ),
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
