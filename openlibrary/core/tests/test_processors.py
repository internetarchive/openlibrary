from openlibrary.core.processors import readableurls as processors
from infogami.infobase import client, common
import web

class MockSite:
    def __init__(self):
        self.docs = {}
        self.olids = {}
    
    def get(self, key):
        return self.docs.get(key)
        
    def add(self, doc):
        #@@ UGLY!
        doc = common.parse_query(doc)
        doc = client.Site(None, None)._process_dict(doc)
        
        key = doc['key']
        self.docs[key] = client.create_thing(self, key, doc)
        
        olid = key.split("/")[-1]
        if web.re_compile(r'OL\d+[A-Z]').match(olid):
            self.olids[olid] = key
            
    def _request(self, path, method=None, data=None):
        if path == "/olid_to_key":
            olid = data['olid']
            return web.storage(key=self.olids.get(olid))
        
    def _get_backreferences(self):
        return {}
        
def test_MockSite():
    site = MockSite()
    assert site.get("/books/OL1M") == None
    
    book = {
        "key": "/books/OL1M",
        "type": {
            "key": "/type/edition"
        },
        "title": "foo"
    }
    site.add(book)
    
    assert site.get("/books/OL1M") is not None
    assert site.get("/books/OL1M").dict() == book
    
    assert site._request("/olid_to_key", data={"olid": "OL1M"}) == {"key": "/books/OL1M"}
    
def _get_mock_site():
    site = MockSite()
    
    book = {
        "key": "/books/OL1M",
        "type": {
            "key": "/type/edition"
        },
        "title": "foo"
    }
    site.add(book)
    
    list = {
        "key": "/people/joe/lists/OL1L",
        "type": {
            "key": "/type/list"
        },
        "name": "foo"
    }
    site.add(list)    
    return site
    
def test_get_object():
    site = _get_mock_site()
    
    def f(key):
        doc = processors._get_object(site, key)
        return doc and doc.key
    
    assert f("/books/OL1M") == "/books/OL1M"
    assert f("/b/OL1M") == "/books/OL1M"
    assert f("/whatever/OL1M") == "/books/OL1M"
    assert f("/not-there") == None
    
_mock_site = _get_mock_site()
def get_readable_path(path, encoding=None):
    patterns = processors.ReadableUrlProcessor.patterns
    return processors.get_readable_path(_mock_site, path, patterns, encoding=encoding)
    
def test_book_urls():
    f = get_readable_path
    
    # regular pages
    assert f(u"/books/OL1M") == (u"/books/OL1M", u"/books/OL1M/foo")
    assert f(u"/books/OL1M/foo") == (u"/books/OL1M", u"/books/OL1M/foo")
    assert f(u"/books/OL1M/foo/edit") == (u"/books/OL1M/edit", u"/books/OL1M/foo/edit")

    # with bad title
    assert f(u"/books/OL1M/bar") == (u"/books/OL1M", u"/books/OL1M/foo")
    assert f(u"/books/OL1M/bar/edit") == (u"/books/OL1M/edit", u"/books/OL1M/foo/edit")
    
    # test /b/ redirects
    assert f(u"/b/OL1M") == (u"/books/OL1M", u"/books/OL1M/foo")
    assert f(u"/b/OL1M/foo/edit") == (u"/books/OL1M/edit", u"/books/OL1M/foo/edit")
    
    # test olid redirects
    assert f(u"/whatever/OL1M") == (u"/books/OL1M", u"/books/OL1M/foo")
    
    # test encoding
    assert f(u"/books/OL1M.json") == (u"/books/OL1M.json", u"/books/OL1M.json")
    assert f(u"/books/OL1M", encoding="json") == (u"/books/OL1M", u"/books/OL1M")

def test_list_urls():
    f = get_readable_path
    
    print f(u"/people/joe/lists/OL1L")

    assert f(u"/people/joe/lists/OL1L") == (
        u"/people/joe/lists/OL1L", 
        u"/people/joe/lists/OL1L/foo"
    )

    assert f(u"/people/joe/lists/OL1L/bar") == (
        u"/people/joe/lists/OL1L", 
        u"/people/joe/lists/OL1L/foo"
    )

    assert f(u"/people/joe/lists/OL1L/bar/edit") == (
        u"/people/joe/lists/OL1L/edit", 
        u"/people/joe/lists/OL1L/foo/edit"
    )
    
    assert f(u"/people/sam/lists/OL1L/foo") == (
        u"/people/joe/lists/OL1L", 
        u"/people/joe/lists/OL1L/foo"
    )
