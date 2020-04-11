from openlibrary.core import ia
from six.moves.urllib.parse import urlencode


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


def test_clean_params():
    f = ia.IAEditionSearch._clean_params
    assert f() == {
        'q': '',
        'page': 1,
        'rows': 20,
        'sort[]': '',
        'fl[]': [
            'identifier', 'loans__status__status', 'openlibrary_edition',
            'openlibrary_work', 'loans__status__num_waitlist',
            'loans__status__num_loans',
        ],
        'output': 'json'
    }


def test_clean_params_max_limit():
    f = ia.IAEditionSearch._clean_params
    assert f(q='test', limit=200).get('rows') == ia.IAEditionSearch.MAX_EDITIONS_LIMIT


def test_ia_search_queries():
    """Make sure IA Advanced Search and Human Browsable urls are
    constructed correctly
    """
    query = 'test'
    prepared_query = (
        'mediatype:texts AND !noindex:* AND openlibrary_work:(*) AND '
        'loans__status__status:AVAILABLE AND test'
    )
    browse_url = 'https://archive.org/search.php?' + urlencode({
        'query': ('mediatype:texts AND '
                  '!noindex:* AND openlibrary_work:(*) AND '
                  'loans__status__status:AVAILABLE AND test'),
        'sort': '',
    })
    _expanded_query = ia.IAEditionSearch._expand_api_query(query)
    assert(_expanded_query == prepared_query)
    assert(ia.IAEditionSearch._compose_browsable_url(prepared_query) == browse_url)
