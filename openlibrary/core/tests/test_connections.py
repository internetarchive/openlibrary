# This will be moved to core soon.
from openlibrary.plugins.openlibrary import connection as connections
import simplejson

class MockConnection:
    def __init__(self):
        self.docs = {}
        
    def request(self, sitename, path, method="GET", data={}):
        if path == "/get":
            key = data['key']
            if key in self.docs:
                return simplejson.dumps(self.docs[key])
        if path == "/get_many":
            keys = simplejson.loads(data['keys'])
            return simplejson.dumps(dict((k, self.docs[k]) for k in keys))
        else:
            return None

class TestMigrationMiddleware:
    def test_title_prefix(self):
        conn = connections.MigrationMiddleware(MockConnection())

        def add(doc):
            conn.conn.docs[doc['key']] = doc
        
        def get(key):
            json = conn.request("openlibrary.org", "/get", data={"key": key}) 
            return simplejson.loads(json)
            
        add({
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title_prefix": "The",
            "title": "Book"
        })
            
        assert get("/books/OL1M") == {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Book"
        }

        add({
            "key": "/books/OL2M",
            "type": {"key": "/type/edition"},
            "title_prefix": "The ",
            "title": "Book"
        })
            
        assert get("/books/OL2M") == {
            "key": "/books/OL2M",
            "type": {"key": "/type/edition"},
            "title": "The Book"
        }

        add({
            "key": "/books/OL3M",
            "type": {"key": "/type/edition"},
            "title_prefix": "The Book",
        })
        
        assert get("/books/OL3M") == {
            "key": "/books/OL3M",
            "type": {"key": "/type/edition"},
            "title": "The Book"
        }

    def test_authors(self):
        conn = connections.MigrationMiddleware(MockConnection())

        def add(doc):
            conn.conn.docs[doc['key']] = doc
        
        def get(key):
            json = conn.request("openlibrary.org", "/get", data={"key": key}) 
            return simplejson.loads(json)

        def get_many(keys):
            data = dict(keys=simplejson.dumps(keys))
            json = conn.request("openlibrary.org", "/get_many", data=data) 
            return simplejson.loads(json)
        
        add({
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": [{
                "type": {"key": "/type/author_role"}
            }]
        })
        
        assert get("/works/OL1W") == {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "authors": []
        }
        assert get_many(["/works/OL1W"]) == {
            "/works/OL1W": {
                "key": "/works/OL1W",
                "type": {"key": "/type/work"},
                "authors": []
            }
        }
        
        OL2W = {
            "key": "/works/OL2W",
            "type": {"key": "/type/work"},
            "authors": [{
                "type": {"key": "/type/author_role"},
                "author": {"key": "/authors/OL2A"}
            }]
        }
        add(OL2W)
        
        assert get("/works/OL2W") == OL2W