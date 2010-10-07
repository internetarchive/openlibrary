"""Test suite for dynlinks.

Most of the tests here use 3 sets of data. 

data0: This contains OL0A, OL0M and OL0W with each having just name/title.
data1: This contains OL1A, OL1M, OL1W with each having name/tile and interconnections.
data9: This contans OL9A, OL9M and OL9W with interconnections and almost all fields.
"""
from .. import dynlinks

import re
import simplejson

def pytest_funcarg__data0(request):
    return {
        "/books/OL0M": {
            "key": "/books/OL0M",
            "title": "book-0"
        },
        "/authors/OL0A": {
            "key": "/authors/OL0A",
            "name": "author-0"
        },
        "/works/OL0W": {
            "key": "/works/OL0W",
            "title": "work-0"
        },
        "result": {
            "data": {
                "url": "http://openlibrary.org/books/OL0M/book-0",
                "key": "/books/OL0M",
                "title": "book-0",
                "identifiers": {
                    "openlibrary": ["OL0M"]
                }
            }
        }
    }

def pytest_funcarg__data1(request):
    return {
        "/books/OL1M": {
            "key": "/books/OL1M",
            "title": "foo",
            "works": [{"key": "/works/OL1W"}]
        },
        "/authors/OL1A": {
            "key": "/authors/OL1A",
            "name": "Mark Twain"
        },
        "/works/OL1W": {
            "key": "/works/OL1W",
            "title": "Foo",
            "authors": [{
                "author": {"key": "/authors/OL1A"}
            }]
        }
    }
    
def pytest_funcarg__data9(request):
    return {
        "/authors/OL9A": {
            "key": "/authors/OL9A",
            "name": "Mark Twain"
        },
        "/works/OL9W": {
            "key": "/works/OL9W",
            "title": "Foo",
            "authors": [{
                "author": {"key": "/authors/OL9A"}
            }],
            "links": [{
                "title": "wikipedia article",
                "url": "http://en.wikipedia.org/wiki/foo"
            }],
            "subjects": ["Test Subject"],
            "subject_people": ["Test Person"],
            "subject_places": ["Test Place"],
            "subject_times": ["Test Time"],
            "excerpts": [{
                "excerpt": {
                    "type": "/type/text",
                    "value": "This is an excerpt."
                },
                "comment": "foo"
            }, {
                # sometimes excerpt was plain string instead of /type/text.
                "excerpt": "This is another excerpt.",
                "comment": "bar"
            }]
        },
        "/books/OL9M": {
            "key": "/books/OL9M",
            "title": "foo",
            "subtitle": "bar",
            "by_statement":  "Mark Twain",
            "works": [{"key": "/works/OL9W"}],
            "publishers": ["Dover Publications"],
            "publish_places": ["New York"],
            "identifiers": {
                "goodreads": ["12345"]
            },
            "isbn_10": ["1234567890"],
            "lccn": ["lccn-1"],
            "oclc_numbers": ["oclc-1"],
            "classifications": {
                "indcat": ["12345"]
            },
            "lc_classifications": ["LC1234"],
            "covers": [42, 53],
            "ocaid": "foo12bar",
            "number_of_pages": "100",
            "pagination": "100 p."
        },
        "result": {
            "viewapi": {
                "info_url": "http://openlibrary.org/books/OL9M",
                "thumbnail_url": "http://covers.openlibrary.org/b/id/42-S.jpg",
                "preview": "noview",
                "preview_url": "http://openlibrary.org/books/OL9M",
            },
            "data": {
                "url": "http://openlibrary.org/books/OL9M/foo",
                "key": "/books/OL9M",
                "title": "foo",
                "subtitle": "bar",
                "by_statement": "Mark Twain",
                "authors": [{
                    "url": "http://openlibrary.org/authors/OL9A/Mark_Twain",
                    "name": "Mark Twain"
                }],
                "identifiers": {
                    "isbn_10": ["1234567890"],
                    "lccn": ["lccn-1"],
                    "oclc": ["oclc-1"],
                    "goodreads": ["12345"],
                    "openlibrary": ["OL9M"]
                },
                "classifications": {
                    "lc_classifications": ["LC1234"],
                    "indcat": ["12345"]
                },
                "publishers": [{
                    "name": "Dover Publications"
                }],
                "publish_places": [{
                    "name": "New York"
                }],
                "links": [{
                    "title": "wikipedia article",
                    "url": "http://en.wikipedia.org/wiki/foo"
                }],
                'subjects': [{
                    'url': 'http://openlibrary.org/subjects/test_subject', 
                    'name': 'Test Subject'
                }], 
                'subject_places': [{
                    'url': 'http://openlibrary.org/subjects/place:test_place', 
                    'name': 'Test Place'
                }],
                'subject_people': [{
                    'url': 'http://openlibrary.org/subjects/person:test_person', 
                    'name': 'Test Person'
                }], 
                'subject_times': [{
                    'url': 'http://openlibrary.org/subjects/time:test_time', 
                    'name': 'Test Time'
                }],
                "cover": {
                    "small": "http://covers.openlibrary.org/b/id/42-S.jpg",
                    "medium": "http://covers.openlibrary.org/b/id/42-M.jpg",
                    "large": "http://covers.openlibrary.org/b/id/42-L.jpg",
                },
                "excerpts": [{
                    "text": "This is an excerpt.",
                    "comment": "foo",
                }, {
                    "text": "This is another excerpt.",
                    "comment": "bar"
                }],
                "ebooks": [{
                    "preview_url": "http://www.archive.org/details/foo12bar"
                }],
                "number_of_pages": "100",
                "pagination": "100 p."
            }
        }
    }

class Mock:
    def __init__(self):
        self.calls = []
        self.default = None
        
    def __call__(self, *a, **kw):
        for a2, kw2, _return in self.calls:
            if (a, kw) == (a2, kw2):
                return _return
        return self.default
        
    def setup_call(self, *a, **kw):
        _return = kw.pop("_return", None)
        call = a, kw, _return
        self.calls.append(call)
        
def monkeypatch_ol(monkeypatch):
    mock = Mock()
    mock.setup_call("isbn_10", "1234567890", _return="/books/OL1M")
    mock.setup_call("key", "/books/OL2M", _return="/books/OL2M")
    monkeypatch.setattr(dynlinks, "ol_query", mock)

    mock = Mock()
    mock.setup_call(["/books/OL1M"], _return=[{"key": "/books/OL1M", "title": "foo"}])
    mock.setup_call(["/books/OL2M"], _return=[{"key": "/books/OL2M", "title": "bar", "ocaid": "ia-bar"}])
    mock.default = []
    monkeypatch.setattr(dynlinks, "ol_get_many", mock)

def test_query_keys(monkeypatch):
    monkeypatch_ol(monkeypatch)
    
    assert dynlinks.query_keys(["isbn:1234567890"]) == {"isbn:1234567890": "/books/OL1M"}
    assert dynlinks.query_keys(["isbn:9876543210"]) == {}
    assert dynlinks.query_keys(["isbn:1234567890", "isbn:9876543210"]) == {"isbn:1234567890": "/books/OL1M"}

def test_query_docs(monkeypatch):
    monkeypatch_ol(monkeypatch)
    
    assert dynlinks.query_docs(["isbn:1234567890"]) == {"isbn:1234567890": {"key": "/books/OL1M", "title": "foo"}}
    assert dynlinks.query_docs(["isbn:9876543210"]) == {}
    assert dynlinks.query_docs(["isbn:1234567890", "isbn:9876543210"]) == {"isbn:1234567890": {"key": "/books/OL1M", "title": "foo"}}
    
def test_process_doc_for_view_api():
    bib_key = "isbn:1234567890"
    doc = {"key": "/books/OL1M", "title": "foo"}
    expected_result = {
        "bib_key": "isbn:1234567890",
        "info_url": "http://openlibrary.org/books/OL1M/foo",
        "preview": "noview",
        "preview_url": "http://openlibrary.org/books/OL1M/foo"
    }
    assert dynlinks.process_doc_for_viewapi(bib_key, doc) == expected_result
    
    doc['ocaid'] = "ia-foo"
    expected_result["preview"] = "full"
    expected_result["preview_url"] = "http://www.archive.org/details/ia-foo"
    assert dynlinks.process_doc_for_viewapi(bib_key, doc) == expected_result
    
    doc['covers'] = [42, 53]
    expected_result["thumbnail_url"] = "http://covers.openlibrary.org/b/id/42-S.jpg"
    assert dynlinks.process_doc_for_viewapi(bib_key, doc) == expected_result

def test_process_result_for_details(monkeypatch):
    assert dynlinks.process_result_for_details({
        "isbn:1234567890": {"key": "/books/OL1M", "title": "foo"}}) == {
            "isbn:1234567890": {
                    "bib_key": "isbn:1234567890",
                    "info_url": "http://openlibrary.org/books/OL1M/foo",
                    "preview": "noview",
                    "preview_url": "http://openlibrary.org/books/OL1M/foo",
                    "details": {
                        "key": "/books/OL1M",
                        "title": "foo"
                    }
            }}
            
    OL1A = {
        "key": "/authors/OL1A",
        "type": {"key": "/type/author"},
        "name": "Mark Twain",
    }
    mock = Mock()
    mock.setup_call(["/authors/OL1A"], _return=[OL1A])
    monkeypatch.setattr(dynlinks, "ol_get_many", mock)

    result = {
        "isbn:1234567890": {
            "key": "/books/OL1M", 
            "title": "foo", 
            "authors": [{"key": "/authors/OL1A"}]
        }
    }
    
    expected_result = {
        "isbn:1234567890": {
            "bib_key": "isbn:1234567890",
            "info_url": "http://openlibrary.org/books/OL1M/foo",
            "preview": "noview",
            "preview_url": "http://openlibrary.org/books/OL1M/foo",
            "details": {
                "key": "/books/OL1M",
                "title": "foo",
                "authors": [{
                    "key": "/authors/OL1A",
                    "name": "Mark Twain"
                }]
            }
        }
    }
    
    assert dynlinks.process_result_for_details(result) == expected_result
    
def test_dynlinks(monkeypatch):
    monkeypatch_ol(monkeypatch)
    
    expected_result = {
        "isbn:1234567890": {
            "bib_key": "isbn:1234567890",
            "info_url": "http://openlibrary.org/books/OL1M/foo",
            "preview": "noview",
            "preview_url": "http://openlibrary.org/books/OL1M/foo"
        }
    }
    
    js = dynlinks.dynlinks(["isbn:1234567890"], {})    
    match = re.match('^var _OLBookInfo = ({.*});$', js)
    assert match is not None
    assert simplejson.loads(match.group(1)) == expected_result

    js = dynlinks.dynlinks(["isbn:1234567890"], {"callback": "func"})
    match = re.match('^func\(({.*})\);$', js)
    assert match is not None
    assert simplejson.loads(match.group(1)) == expected_result

    js = dynlinks.dynlinks(["isbn:1234567890"], {"format": "json"})
    assert simplejson.loads(js) == expected_result

def test_dynlinks_ia(monkeypatch):
    monkeypatch_ol(monkeypatch)

    expected_result = {
        "OL2M": {
            "bib_key": "OL2M",
            "info_url": "http://openlibrary.org/books/OL2M/bar",
            "preview": "full",
            "preview_url": "http://www.archive.org/details/ia-bar"
        }
    }
    json = dynlinks.dynlinks(["OL2M"], {"format": "json"})
    assert simplejson.loads(json) == expected_result

def test_dynlinks_details(monkeypatch):
    monkeypatch_ol(monkeypatch)

    expected_result = {
        "OL2M": {
            "bib_key": "OL2M",
            "info_url": "http://openlibrary.org/books/OL2M/bar",
            "preview": "full",
            "preview_url": "http://www.archive.org/details/ia-bar", 
            "details": {
                "key": "/books/OL2M", 
                "title": "bar", 
                "ocaid": "ia-bar"
            }
        },
    }
    json = dynlinks.dynlinks(["OL2M"], {"format": "json", "details": "true"})
    assert simplejson.loads(json) == expected_result
    
class TestDataProcessor:        
    def test_get_authors0(self, data0):
        p = dynlinks.DataProcessor()
        p.authors = data0
        assert p.get_authors(data0['/books/OL0M']) == []
        
    def test_get_authors1(self, data1):
        p = dynlinks.DataProcessor()
        p.authors = data1
        assert p.get_authors(data1['/works/OL1W']) == [{"url": "http://openlibrary.org/authors/OL1A/Mark_Twain", "name": "Mark Twain"}]
        
    def test_process_doc0(self, data0):
        p = dynlinks.DataProcessor()
        assert p.process_doc(data0['/books/OL0M']) == data0['result']['data']
        
    def test_process_doc9(self, data9):
        p = dynlinks.DataProcessor()
        p.authors = data9
        p.works = data9
        assert p.process_doc(data9['/books/OL9M']) == data9['result']['data']
