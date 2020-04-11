from openlibrary.core import ia


def test_get_metadata(monkeypatch, mock_memcache):
    metadata = {
        "metadata": {
            "title": "Foo",
            "identifier": "foo00bar",
            "collection": ["printdisabled", "inlibrary"]
        }
    }

    monkeypatch.setattr(ia, 'get_api_response', lambda *args: metadata)
    assert ia.get_metadata('foo00bar') == {
        "title": "Foo",
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        "access-restricted": False,
        "_filenames": []
    }


def test_get_metadata_empty(monkeypatch, mock_memcache):
    monkeypatch.setattr(ia, 'get_api_response', lambda *args: {})
    assert ia.get_metadata('foo02bar') == {}


def test_normalize_sorts():
    dirty_sorts = ['loans__status__last_loan_date+desc']
    clean_sorts = ['loans__status__last_loan_date desc']
    assert(ia.IAEditionSearch._normalize_sorts(dirty_sorts) == clean_sorts)


def test_ia_search_queries():
    """Make sure IA Advanced Search and Human Browsable urls are
    constructed correctly
    """
    query = 'test'
    prepared_query = (
        'mediatype:texts AND !noindex:* AND openlibrary_work:(*) AND '
        'loans__status__status:AVAILABLE AND test'
    )
    assert(ia.IAEditionSearch.MAX_EDITIONS_LIMIT == 20)
    advancedsearch_url = (
        'http://archive.org/advancedsearch.php?'
        'rows=20&q=mediatype%3Atexts+AND+%21noindex%3A%2A+AND+'
        'openlibrary_work%3A%28%2A%29+AND+'
        'loans__status__status%3AAVAILABLE+AND+'
        'test&output=json&fl%5B%5D=identifier'
        '&fl%5B%5D=loans__status__status&fl%5B%5D=openlibrary_edition'
        '&fl%5B%5D=openlibrary_work&page=1&sort%5B%5D='
    )
    browse_url = (
        'https://archive.org/search.php?'
        'query=mediatype:texts AND '
        '!noindex:* AND openlibrary_work:(*) AND '
        'loans__status__status:AVAILABLE AND test&sort='
    )
    _expanded_query = ia.IAEditionSearch._expand_api_query(query)
    _params = ia.IAEditionSearch._clean_params(q=_expanded_query)
    assert(_expanded_query == prepared_query)
    assert(ia.IAEditionSearch._clean_params(
        q='test', limit=200).get('rows') == ia.IAEditionSearch.MAX_EDITIONS_LIMIT)
    composed_url = ia.IAEditionSearch._compose_advancedsearch_url(**_params)
    assert(composed_url == advancedsearch_url)
    assert(ia.IAEditionSearch._compose_browsable_url(prepared_query) == browse_url)
