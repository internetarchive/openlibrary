import datetime
from openlibrary.core.mocksite import MockSite


class TestMockSite:
    def test_get(self):
        doc = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Test Book"
        }
        timestamp = datetime.datetime(2010, 1, 2, 3, 4, 5)
        
        site = MockSite()
        site.save(doc, timestamp=timestamp)
        
        assert site.get("/books/OL1M").dict() == {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Test Book",
            "revision": 1,
            "last_modified": {
                "type": "/type/datetime",
                "value": "2010-01-02T03:04:05"
            }
        }

    def test_query(self):
        doc = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Test Book",
            "subjects": ["love", "san_francisco"]
        }
        timestamp = datetime.datetime(2010, 1, 2, 3, 4, 5)

        site = MockSite()
        site.save(doc, timestamp=timestamp)
        
        for i in site.index:
            print dict(i)
            
        assert site.things({"type": "/type/edition"}) == ["/books/OL1M"]
        assert site.things({"type": "/type/work"}) == []
        
        assert site.things({"type": "/type/edition", "subjects": "love"}) == ["/books/OL1M"]
        assert site.things({"type": "/type/edition", "subjects": "hate"}) == []

        assert site.things({"key~": "/books/*"}) == ["/books/OL1M"]
        assert site.things({"key~": "/works/*"}) == []
        
        assert site.things({"last_modified>": "2010-01-01"}) == ["/books/OL1M"]
        assert site.things({"last_modified>": "2010-01-03"}) == []
        
        