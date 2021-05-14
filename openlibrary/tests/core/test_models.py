from openlibrary.core import models


class MockSite:
    def get(self, key):
        return models.Thing(self, key, data={})

    def _get_backreferences(self, thing):
        return {}

class MockLendableEdition(models.Edition):
    def get_ia_collections(self):
        return ['lendinglibrary']

class MockPrivateEdition(models.Edition):
    def get_ia_collections(self):
        return ['lendinglibrary', 'georgetown-university-law-library-rr']


class TestEdition:
    def mock_edition(self, edition_class):
        data = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "foo"
        }
        return edition_class(MockSite(), "/books/OL1M", data=data)

    def test_url(self):
        e = self.mock_edition(models.Edition)
        assert e.url() == "/books/OL1M/foo"
        assert e.url(v=1) == "/books/OL1M/foo?v=1"
        assert e.url(suffix="/add-cover") == "/books/OL1M/foo/add-cover"

        data = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
        }
        e = models.Edition(MockSite(), "/books/OL1M", data=data)
        assert e.url() == "/books/OL1M/untitled"

    def test_get_ebook_info(self):
        e = self.mock_edition(models.Edition)
        assert e.get_ebook_info() == {}

    def test_is_not_in_private_collection(self):
        e = self.mock_edition(MockLendableEdition)
        assert not e.is_in_private_collection()

    def test_in_borrowable_collection_cuz_not_in_private_collection(self):
        e = self.mock_edition(MockLendableEdition)
        assert e.in_borrowable_collection()

    def test_is_in_private_collection(self):
        e = self.mock_edition(MockPrivateEdition)
        assert e.is_in_private_collection()

    def test_not_in_borrowable_collection_cuz_in_private_collection(self):
        e = self.mock_edition(MockPrivateEdition)
        assert not e.in_borrowable_collection()


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
