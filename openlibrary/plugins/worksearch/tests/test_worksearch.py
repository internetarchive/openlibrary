import pytest
import web
from openlibrary.plugins.worksearch.code import (
    process_facet,
    sorted_work_editions,
    parse_query_fields,
    escape_bracket,
    get_doc,
    build_q_list,
    escape_colon,
    parse_search_response,
)


def test_escape_bracket():
    assert escape_bracket('foo') == 'foo'
    assert escape_bracket('foo[') == 'foo\\['
    assert escape_bracket('[ 10 TO 1000]') == '[ 10 TO 1000]'


def test_escape_colon():
    vf = ['key', 'name', 'type', 'count']
    assert (
        escape_colon('test key:test http://test/', vf) == 'test key:test http\\://test/'
    )


def test_process_facet():
    facets = [('false', 46), ('true', 2)]
    assert list(process_facet('has_fulltext', facets)) == [
        ('true', 'yes', 2),
        ('false', 'no', 46),
    ]


def test_sorted_work_editions():
    json_data = '''{
"responseHeader":{
"status":0,
"QTime":1,
"params":{
"fl":"edition_key",
"indent":"on",
"wt":"json",
"q":"key:OL100000W"}},
"response":{"numFound":1,"start":0,"docs":[
{
 "edition_key":["OL7536692M","OL7825368M","OL3026366M"]}]
}}'''
    expect = ["OL7536692M", "OL7825368M", "OL3026366M"]
    assert sorted_work_editions('OL100000W', json_data=json_data) == expect


# {'Test name': ('query', fields[])}
QUERY_PARSER_TESTS = {
    'No fields': ('query here', [{'field': 'text', 'value': 'query here'}]),
    'Author field': (
        'food rules author:pollan',
        [
            {'field': 'text', 'value': 'food rules'},
            {'field': 'author_name', 'value': 'pollan'},
        ],
    ),
    'Field aliases': (
        'title:food rules by:pollan',
        [
            {'field': 'title', 'value': 'food rules'},
            {'field': 'author_name', 'value': 'pollan'},
        ],
    ),
    'Fields are case-insensitive aliases': (
        'food rules By:pollan',
        [
            {'field': 'text', 'value': 'food rules'},
            {'field': 'author_name', 'value': 'pollan'},
        ],
    ),
    'Quotes': (
        'title:"food rules" author:pollan',
        [
            {'field': 'title', 'value': '"food rules"'},
            {'field': 'author_name', 'value': 'pollan'},
        ],
    ),
    'Leading text': (
        'query here title:food rules author:pollan',
        [
            {'field': 'text', 'value': 'query here'},
            {'field': 'title', 'value': 'food rules'},
            {'field': 'author_name', 'value': 'pollan'},
        ],
    ),
    'Colons in query': (
        'flatland:a romance of many dimensions',
        [
            {'field': 'text', 'value': r'flatland\:a romance of many dimensions'},
        ],
    ),
    'Colons in field': (
        'title:flatland:a romance of many dimensions',
        [
            {
                'field': 'title',
                'value': r'flatland\:a romance of many dimensions',
            },
        ],
    ),
    'Operators': (
        'authors:Kim Harrison OR authors:Lynsay Sands',
        [
            {'field': 'author_name', 'value': 'Kim Harrison'},
            {'op': 'OR'},
            {'field': 'author_name', 'value': 'Lynsay Sands'},
        ],
    ),
    # LCCs
    'LCC: quotes added if space present': (
        'lcc:NC760 .B2813 2004',
        [
            {'field': 'lcc', 'value': '"NC-0760.00000000.B2813 2004"'},
        ],
    ),
    'LCC: star added if no space': (
        'lcc:NC760 .B2813',
        [
            {'field': 'lcc', 'value': 'NC-0760.00000000.B2813*'},
        ],
    ),
    'LCC: Noise left as is': (
        'lcc:good evening',
        [
            {'field': 'lcc', 'value': 'good evening'},
        ],
    ),
    'LCC: range': (
        'lcc:[NC1 TO NC1000]',
        [
            {'field': 'lcc', 'value': '[NC-0001.00000000 TO NC-1000.00000000]'},
        ],
    ),
    'LCC: prefix': (
        'lcc:NC76.B2813*',
        [
            {'field': 'lcc', 'value': 'NC-0076.00000000.B2813*'},
        ],
    ),
    'LCC: suffix': (
        'lcc:*B2813',
        [
            {'field': 'lcc', 'value': '*B2813'},
        ],
    ),
    'LCC: multi-star without prefix': (
        'lcc:*B2813*',
        [
            {'field': 'lcc', 'value': '*B2813*'},
        ],
    ),
    'LCC: multi-star with prefix': (
        'lcc:NC76*B2813*',
        [
            {'field': 'lcc', 'value': 'NC-0076*B2813*'},
        ],
    ),
    'LCC: quotes preserved': (
        'lcc:"NC760 .B2813"',
        [
            {'field': 'lcc', 'value': '"NC-0760.00000000.B2813"'},
        ],
    ),
    # TODO Add tests for DDC
}


@pytest.mark.parametrize(
    "query,parsed_query", QUERY_PARSER_TESTS.values(), ids=QUERY_PARSER_TESTS.keys()
)
def test_query_parser_fields(query, parsed_query):
    assert list(parse_query_fields(query)) == parsed_query


#     def test_public_scan(lf):
#         param = {'subject_facet': ['Lending library']}
#         (reply, solr_select, q_list) = run_solr_query(param, rows = 10, spellcheck_count = 3)
#         print solr_select
#         print q_list
#         print reply
#         root = etree.XML(reply)
#         docs = root.find('result')
#         for doc in docs:
#             assert get_doc(doc).public_scan == False


def test_get_doc():
    doc = get_doc(
        {
            'author_key': ['OL218224A'],
            'author_name': ['Alan Freedman'],
            'cover_edition_key': 'OL1111795M',
            'edition_count': 14,
            'first_publish_year': 1981,
            'has_fulltext': True,
            'ia': ['computerglossary00free'],
            'key': '/works/OL1820355W',
            'lending_edition_s': 'OL1111795M',
            'public_scan_b': False,
            'title': 'The computer glossary',
        }
    )
    assert doc == web.storage(
        {
            'key': '/works/OL1820355W',
            'title': 'The computer glossary',
            'url': '/works/OL1820355W/The_computer_glossary',
            'edition_count': 14,
            'ia': ['computerglossary00free'],
            'collections': set(),
            'has_fulltext': True,
            'public_scan': False,
            'lending_edition': 'OL1111795M',
            'lending_identifier': None,
            'authors': [
                web.storage(
                    {
                        'key': 'OL218224A',
                        'name': 'Alan Freedman',
                        'url': '/authors/OL218224A/Alan_Freedman',
                    }
                )
            ],
            'first_publish_year': 1981,
            'first_edition': None,
            'subtitle': None,
            'cover_edition_key': 'OL1111795M',
            'languages': [],
            'id_project_gutenberg': [],
            'id_librivox': [],
            'id_standard_ebooks': [],
            'id_openstax': [],
        }
    )


def test_build_q_list():
    param = {'q': 'test'}
    expect = (['test'], True)
    assert build_q_list(param) == expect

    param = {
        'q': 'title:(Holidays are Hell) authors:(Kim Harrison) OR authors:(Lynsay Sands)'
    }
    expect = (
        [
            'title:((Holidays are Hell))',
            'author_name:((Kim Harrison))',
            'OR',
            'author_name:((Lynsay Sands))',
        ],
        False,
    )
    query_fields = [
        {'field': 'title', 'value': '(Holidays are Hell)'},
        {'field': 'author_name', 'value': '(Kim Harrison)'},
        {'op': 'OR'},
        {'field': 'author_name', 'value': '(Lynsay Sands)'},
    ]
    assert list(parse_query_fields(param['q'])) == query_fields
    assert build_q_list(param) == expect


def test_parse_search_response():
    test_input = (
        '<pre>org.apache.lucene.queryParser.ParseException: This is an error</pre>'
    )
    expect = {'error': 'This is an error'}
    assert parse_search_response(test_input) == expect
    assert parse_search_response('{"aaa": "bbb"}') == {'aaa': 'bbb'}
