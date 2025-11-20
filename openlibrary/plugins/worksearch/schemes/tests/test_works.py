from unittest.mock import patch

import pytest

from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

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
    import web  # noqa: PLC0415

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
