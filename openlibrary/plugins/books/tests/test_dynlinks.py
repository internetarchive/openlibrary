from .. import dynlinks

import re
import simplejson

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
    #assert simplejson.loads(json) == expected_result