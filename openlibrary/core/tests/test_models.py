from openlibrary.core import models

class MockSite:
    def get(self, key):
        return models.Thing(self, key, data={})
        
    def _get_backreferences(self, thing):
        return {}


class TestEdition:
    def test_url(self):
        data = {
            "key": "/books/OL1M", 
            "type": {"key": "/type/edition"},
            "title": "foo"
        }
        
        e = models.Edition(MockSite(), "/books/OL1M", data=data)
        
        assert e.url() == "/books/OL1M/foo"
        assert e.url(v=1) == "/books/OL1M/foo?v=1"
        assert e.url(suffix="/add-cover") == "/books/OL1M/foo/add-cover"
        

        data = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
        }
        e = models.Edition(MockSite(), "/books/OL1M", data=data)
        assert e.url() == "/books/OL1M/untitled"
        

class TestAuthor:
    def test_url(self):
        data = {
            "key": "/authors/OL1A", 
            "type": {"key": "/type/author"},
            "name": "foo"
        }
        
        e = models.Author(MockSite(), "/authors/OL1A", data=data)
        
        assert e.url() == "/authors/OL1A/foo"
        assert e.url(v=1) == "/authors/OL1A/foo?v=1"
        assert e.url(suffix="/add-photo") == "/authors/OL1A/foo/add-photo"        

        data = {
            "key": "/authors/OL1A",
            "type": {"key": "/type/author"},
        }
        e = models.Author(MockSite(), "/authors/OL1A", data=data)
        assert e.url() == "/authors/OL1A/unnamed"
        
    