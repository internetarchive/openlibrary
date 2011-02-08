from openlibrary.core import models

# this should be moved to openlibrary.core
from openlibrary.plugins.upstream.models import UnitParser

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


class TestSubject:
    def test_url(self):
        subject = models.Subject({
            "key": "/subjects/love"
        })
        assert subject.url() == "/subjects/love"
        assert subject.url("/lists") == "/subjects/love/lists"
        
        
class TestList:
    def test_owner(self):
        models.register_models()
        self._test_list_owner("/people/anand")
        self._test_list_owner("/people/anand-test")
        self._test_list_owner("/people/anand_test")
        
    def _test_list_owner(self, user_key):
        from openlibrary.mocks.mock_infobase import MockSite
        site = MockSite()
        list_key = user_key + "/lists/OL1L"
        
        self.save_doc(site, "/type/user", user_key)
        self.save_doc(site, "/type/list", list_key)
        
        list =  site.get(list_key)
        assert list is not None
        assert isinstance(list, models.List)
        
        assert list.get_owner() is not None
        assert list.get_owner().key == user_key
        
    def save_doc(self, site, type, key, **fields):
        d = {
            "key": key,
            "type": {"key": type}
        }
        d.update(fields)
        site.save(d)
        
class TestLibrary:
    def test_class(self, mock_site):
        mock_site.save({
            "key": "/libraries/ia",
            "type": {"key": "/type/library"}
        })
        doc = mock_site.get("/libraries/ia")
        assert doc.__class__.__name__ == "Library"
    
    def test_has_ip(self, mock_site):
        mock_site.save({
            "key": "/libraries/ia",
            "type": {"key": "/type/library"},
            "ip_ranges": "1.1.1.1\n2.2.2.0/8"
        })
        
        ia = mock_site.get("/libraries/ia")
        assert ia.has_ip("1.1.1.1") is True
        assert ia.has_ip("1.1.1.2") is False

        assert ia.has_ip("2.2.2.10") is True
        assert ia.has_ip("2.2.10.2") is False
