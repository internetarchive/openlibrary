from __future__ import print_function
from openlibrary.core import ia
from infogami import config

def test_xml2dict():
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>") == {"x": "1", "y": "2"}
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>", x=[]) == {"x": ["1"], "y": "2"}

    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>") == {"x": "2"}
    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>", x=[]) == {"x": ["1", "2"]}

def test_get_metaxml(monkeypatch, mock_memcache):
    import StringIO
    import urllib2

    metadata_json = None
    def urlopen(url):
        return StringIO.StringIO(metadata_json)

    monkeypatch.setattr(urllib2, "urlopen", urlopen)

    # test with correct xml
    metadata_json = """{
        "metadata": {
            "title": "Foo",
            "identifier": "foo00bar",
            "collection": ["printdisabled", "inlibrary"]
        }
    }
    """

    print(ia.get_meta_xml("foo00bar"))
    assert ia.get_meta_xml("foo00bar") == {
        "title": "Foo",
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        "access-restricted": False,
        "_filenames": []
    }

    # test with metadata errors
    metadata_json = "{}"
    assert ia.get_meta_xml("foo02bar") == {}

def test_normalize_sorts():
    sorts = ['loans__status__last_loan_date+desc']
    assert(ia.IAEditionSearch._normalize_sorts(sorts) == ['loans__status__last_loan_date desc'])

def test_ia_search_queries():
    """Make sure IA Advanced Search and Human Browsable urls are constructed correctly"""
    query = 'test'
    prepared_query = 'mediatype:texts AND !noindex:* AND openlibrary_work:(*) AND loans__status__status:AVAILABLE AND test'
    assert(ia.IAEditionSearch.MAX_LIMIT == 20)
    advancedsearch_url = 'http://archive.org/advancedsearch.php?rows=20&q=mediatype%3Atexts+AND+%21noindex%3A%2A+AND+openlibrary_work%3A%28%2A%29+AND+loans__status__status%3AAVAILABLE+AND+test&output=json&fl%5B%5D=identifier&fl%5B%5D=loans__status__status&fl%5B%5D=openlibrary_edition&fl%5B%5D=openlibrary_work&page=1&sort%5B%5D='
    browse_url = 'https://archive.org/search.php?query=mediatype:texts AND !noindex:* AND openlibrary_work:(*) AND loans__status__status:AVAILABLE AND test&sort='

    _expanded_query = ia.IAEditionSearch._expand_api_query(query)
    _params = ia.IAEditionSearch._clean_params(q=_expanded_query)
    assert(_expanded_query == prepared_query)
    assert(ia.IAEditionSearch._clean_params(q='test', limit=200).get('rows') == ia.IAEditionSearch.MAX_LIMIT)
    assert(ia.IAEditionSearch._compose_advancedsearch_url(**_params) == advancedsearch_url)
    assert(ia.IAEditionSearch._compose_browsable_url(prepared_query) == browse_url)
