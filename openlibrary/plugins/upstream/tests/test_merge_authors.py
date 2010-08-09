import web

from infogami.infobase import client
from infogami.utils import delegate

from infogami.infobase.tests.pytest_wildcard import *

from .. import merge

def setup_module(mod):
    delegate.fakeload()

class MockSite:
    def __init__(self):
        self.docs = {}
        
    def get(self, key):
        doc = self.docs[key]
        return client.create_thing(self, key, doc)
        
    def things(self, query):
        return []
        
    def get_dict(self, key):
        return self.get(key).dict()
    
    def get_many(self, keys):
        return [self.get(k) for k in keys]
        
    def _get_backreferences(self, thing):
        return {}
        
    def save_many(self, docs, comment=None, data={}, action=None):
        self.add(docs)
        
    def add(self, docs):
        self.docs.update((doc['key'], doc) for doc in docs)

def test_MockSite():
    site = MockSite()
    assert site.docs.keys() == []
    
    site.add([{
            "key": "a",
            "type": {"key": "/type/object"}
        }, {
            "key": "b",
            "type": {"key": "/type/object"}
        }
    ])
    assert site.docs.keys() == ["a", "b"]
    
testdata = web.storage({
    "a": {
        "key": "/authors/a",
        "type": {"key": "/type/author"},
        "name": "a"
    },
    "b": {
        "key": "/authors/b",
        "type": {"key": "/type/author"},
        "name": "b"
    },
    "c": {
        "key": "/authors/c",
        "type": {"key": "/type/author"},
        "name": "c"
    }
})

class TestMergeAuthorsImpl:
    def setup_method(self, method):
        self.merger = merge.MergeAuthorsImpl()
        web.ctx.site = MockSite()
        
    def test_redirection(self):
        web.ctx.site.add([testdata.a, testdata.b, testdata.c])
        self.merger.merge("/authors/a", ["/authors/b", "/authors/c"])
        
        # assert redirection
        assert web.ctx.site.get("/authors/b").dict() == {
            "key": "/authors/b",
            "type": {"key": "/type/redirect"},
            "location": "/authors/a"
        }
        assert web.ctx.site.get("/authors/c").dict() == {
            "key": "/authors/c",
            "type": {"key": "/type/redirect"},
            "location": "/authors/a"
        }
        
    def test_alternate_names(self):
        web.ctx.site.add([testdata.a, testdata.b, testdata.c])
        self.merger.merge("/authors/a", ["/authors/b", "/authors/c"])
        assert web.ctx.site.get("/authors/a").alternate_names == ["b", "c"]

    def test_photos(self):
        a = dict(testdata.a, photos=[1, 2])
        b = dict(testdata.b, photos=[3, 4])

        web.ctx.site.add([a, b])
        self.merger.merge("/authors/a", ["/authors/b"])
        
        photos = web.ctx.site.get("/authors/a").photos
        assert photos == [1, 2, 3, 4]
        
    def test_links(self):
        link_a = {
            "title": "link a",
            "url": "http://example.com/a"
        }
        link_b = {
            "title": "link b",
            "url": "http://example.com/b"
        }
        
        a = dict(testdata.a, links=[link_a])
        b = dict(testdata.b, links=[link_b])
        web.ctx.site.add([a, b])
        
        self.merger.merge("/authors/a", ["/authors/b"])
        links = web.ctx.site.get("/authors/a").links        
        assert links == [link_a, link_b]
        
    def test_new_field(self):
        """When the duplicate has a new field which is not there in the master,
        the new filed must be copied to the master.
        """
        birth_date = "1910-01-02"
        a = testdata.a
        b = dict(testdata.b, birth_date=birth_date)
        web.ctx.site.add([a, b])
        
        self.merger.merge("/authors/a", ["/authors/b"])
        master_birth_date = web.ctx.site.get("/authors/a").get('birth_date')
        assert master_birth_date == birth_date
