from unittest.mock import Mock, patch

import pytest
from fastapi import Request

from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.utils.request_context import (
    _parse_solr_editions_from_fastapi,
    _parse_solr_editions_from_web,
)

pytestmark = pytest.mark.usefixtures("request_context_fixture")


# {'Test name': ('query', fields[])}
QUERY_PARSER_TESTS = {
    'No fields': ('query here', 'query here'),
    'Misc': (
        'title:(Holidays are Hell) authors:(Kim Harrison) OR authors:(Lynsay Sands)',
        'alternative_title:(Holidays are Hell) author_name:(Kim Harrison) OR author_name:(Lynsay Sands)',
    ),
    'Author field': (
        'food rules author:pollan',
        'food rules author_name:pollan',
    ),
    'Invalid dashes': (
        'foo foo bar -',
        'foo foo bar \\-',
    ),
    'Field aliases': (
        'title:food rules by:pollan',
        'alternative_title:(food rules) author_name:pollan',
    ),
    'Fields are case-insensitive aliases': (
        'food rules By:pollan',
        'food rules author_name:pollan',
    ),
    'Spaces after fields': (
        'title: "Harry Potter"',
        'alternative_title:"Harry Potter"',
    ),
    'Quotes': (
        'title:"food rules" author:pollan',
        'alternative_title:"food rules" author_name:pollan',
    ),
    'Unmatched double-quote': (
        'title:Compilation Group for the "History of Modern China',
        'title\\:Compilation Group for the \\"History of Modern China',
    ),
    'Leading text': (
        'query here title:food rules author:pollan',
        'query here alternative_title:(food rules) author_name:pollan',
    ),
    'Colons in query': (
        'flatland:a romance of many dimensions',
        'flatland\\:a romance of many dimensions',
    ),
    'Spaced colons in query': (
        'flatland : a romance of many dimensions',
        'flatland\\: a romance of many dimensions',
    ),
    'Colons in field': (
        'title:flatland:a romance of many dimensions',
        'alternative_title:(flatland\\:a romance of many dimensions)',
    ),
    'Operators': (
        'authors:Kim Harrison OR authors:Lynsay Sands',
        'author_name:(Kim Harrison) OR author_name:(Lynsay Sands)',
    ),
    'ISBN-like': (
        '978-0-06-093546-7',
        'isbn:(9780060935467)',
    ),
    'Normalizes ISBN': (
        'isbn:978-0-06-093546-7',
        'isbn:9780060935467',
    ),
    'Does not normalize ISBN stars': (
        'isbn:979*',
        'isbn:979*',
    ),
    # LCCs
    'LCC: quotes added if space present': (
        'lcc:NC760 .B2813 2004',
        'lcc:"NC-0760.00000000.B2813 2004"',
    ),
    'LCC: star added if no space': (
        'lcc:NC760 .B2813',
        'lcc:NC-0760.00000000.B2813*',
    ),
    'LCC: Noise left as is': (
        'lcc:good evening',
        'lcc:(good evening)',
    ),
    'LCC: range': (
        'lcc:[NC1 TO NC1000]',
        'lcc:[NC-0001.00000000 TO NC-1000.00000000]',
    ),
    'LCC: prefix': (
        'lcc:NC76.B2813*',
        'lcc:NC-0076.00000000.B2813*',
    ),
    'LCC: suffix': (
        'lcc:*B2813',
        'lcc:*B2813',
    ),
    'LCC: multi-star without prefix': (
        'lcc:*B2813*',
        'lcc:*B2813*',
    ),
    'LCC: multi-star with prefix': (
        'lcc:NC76*B2813*',
        'lcc:NC-0076*B2813*',
    ),
    'LCC: quotes preserved': (
        'lcc:"NC760 .B2813"',
        'lcc:"NC-0760.00000000.B2813"',
    ),
    # TODO Add tests for DDC
}


@pytest.mark.parametrize(
    ('query', 'parsed_query'),
    QUERY_PARSER_TESTS.values(),
    ids=QUERY_PARSER_TESTS.keys(),
)
def test_process_user_query(query, parsed_query):
    s = WorkSearchScheme()
    assert s.process_user_query(query) == parsed_query


EDITION_KEY_TESTS = {
    'edition_key:OL123M': '+key:"/books/OL123M"',
    'edition_key:"OL123M"': '+key:"/books/OL123M"',
    'edition_key:"/books/OL123M"': '+key:"/books/OL123M"',
    'edition_key:(OL123M)': '+key:("/books/OL123M")',
    'edition_key:(OL123M OR OL456M)': '+key:("/books/OL123M" OR "/books/OL456M")',
}


@pytest.mark.parametrize(('query', 'edQuery'), EDITION_KEY_TESTS.items())
def test_q_to_solr_params_edition_key(query, edQuery):
    import web

    web.ctx.lang = 'en'
    s = WorkSearchScheme()

    with patch(
        'openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc'
    ) as mock_fn:
        mock_fn.return_value = 'eng'
        params = s.q_to_solr_params(query, {'editions:[subquery]'}, [])
    params_d = dict(params)
    assert params_d['userWorkQuery'] == query
    assert params_d['userEdQuery'] == edQuery


# Tests for _parse_solr_editions_from_fastapi and _parse_solr_editions_from_web
# These tests ensure both implementations follow the same rules


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
