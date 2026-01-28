"""Tests for request context parsing and management."""

from unittest.mock import Mock, patch

import pytest
from fastapi import Request

from openlibrary.utils.request_context import (
    _parse_solr_editions_from_fastapi,
    _parse_solr_editions_from_web,
)


def create_mock_request(query_params=None, cookies=None):
    """Helper to create a mock FastAPI Request object."""
    mock_request = Mock(spec=Request)
    mock_request.query_params = query_params or {}
    mock_request.cookies = cookies or {}
    return mock_request


@pytest.mark.parametrize(
    ('query_param', 'cookie_value', 'expected', 'description'),
    [
        # Query param takes precedence
        ('true', 'false', True, 'Query param true overrides cookie false'),
        ('false', 'true', False, 'Query param false overrides cookie true'),
        ('True', 'false', True, 'FastAPI: Query param True (case-insensitive)'),
        ('FALSE', 'true', False, 'FastAPI: Query param FALSE (case-insensitive)'),
        ('other', 'true', False, 'FastAPI: Query param other value treated as false'),
        # Only cookie present
        (None, 'true', True, 'Cookie true when no query param'),
        (None, 'false', False, 'Cookie false when no query param'),
        (None, 'True', True, 'FastAPI: Cookie True (case-insensitive)'),
        (None, 'FALSE', False, 'FastAPI: Cookie FALSE (case-insensitive)'),
        # Neither present - default to True
        (None, None, True, 'Default to True when no query param or cookie'),
    ],
)
def test_parse_solr_editions_from_fastapi(
    query_param, cookie_value, expected, description
):
    """Test _parse_solr_editions_from_fastapi with various inputs."""
    query_params = {}
    if query_param is not None:
        query_params['editions'] = query_param

    cookies = {}
    if cookie_value is not None:
        cookies['SOLR_EDITIONS'] = cookie_value

    request = create_mock_request(query_params=query_params, cookies=cookies)
    result = _parse_solr_editions_from_fastapi(request)

    assert result == expected, f"Failed: {description}"


@pytest.mark.parametrize(
    ('query_param', 'cookie_value', 'http_cookie', 'expected', 'description'),
    [
        # Query param tests
        ('true', None, '', True, 'Query param true'),
        ('false', None, '', False, 'Query param false'),
        # Precedence test: query param overrides cookie
        (
            'false',
            'true',
            'SOLR_EDITIONS=true',
            False,
            'Query param takes precedence over cookie',
        ),
        # Cookie tests
        (None, 'true', 'SOLR_EDITIONS=true', True, 'Cookie true'),
        (None, 'false', 'SOLR_EDITIONS=false', False, 'Cookie false'),
        # Default test
        (None, None, '', True, 'Default to True when no query param or cookie'),
        # Case-sensitivity test
        (
            None,
            'True',
            'SOLR_EDITIONS=True',
            False,
            'Cookie is case-sensitive (True != true)',
        ),
    ],
)
def test_parse_solr_editions_from_web(
    query_param, cookie_value, http_cookie, expected, description
):
    """Test _parse_solr_editions_from_web with various inputs."""
    import web

    web.ctx.env = {'HTTP_COOKIE': http_cookie}
    with (
        patch.object(web, 'input') as mock_input,
        patch.object(web, 'cookies') as mock_cookies,
    ):
        mock_input.return_value.get.return_value = query_param
        if cookie_value is not None:
            mock_cookies.return_value.get.return_value = cookie_value
        result = _parse_solr_editions_from_web()

        assert result == expected, f"Failed: {description}"


@pytest.mark.parametrize(
    ('query_param', 'cookie_value', 'expected', 'description'),
    [
        ('true', None, True, 'Query param true'),
        ('false', None, False, 'Query param false'),
        (None, 'true', True, 'Cookie true'),
        (None, 'false', False, 'Cookie false'),
        (None, None, True, 'Default when neither present'),
    ],
)
def test_parse_solr_editions_parity(query_param, cookie_value, expected, description):
    """
    Test that both implementations handle common cases the same way.
    Documents any behavioral differences between the two versions.
    """
    import web

    # Test FastAPI version
    query_params = {'editions': query_param} if query_param is not None else {}
    cookies = {'SOLR_EDITIONS': cookie_value} if cookie_value is not None else {}
    request = create_mock_request(query_params=query_params, cookies=cookies)
    fastapi_result = _parse_solr_editions_from_fastapi(request)

    # Test web.py version
    cookie_str = f'SOLR_EDITIONS={cookie_value}' if cookie_value is not None else ''
    web.ctx.env = {'HTTP_COOKIE': cookie_str}
    with (
        patch.object(web, 'input') as mock_input,
        patch.object(web, 'cookies') as mock_cookies,
    ):
        mock_input.return_value.get.return_value = query_param
        if cookie_value is not None:
            mock_cookies.return_value.get.return_value = cookie_value
        web_result = _parse_solr_editions_from_web()

    assert fastapi_result == expected, f"FastAPI version failed: {description}"
    assert web_result == expected, f"web.py version failed: {description}"
    assert (
        fastapi_result == web_result
    ), f"Mismatch between FastAPI and web.py: {description}"
