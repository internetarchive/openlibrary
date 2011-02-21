import datetime
from openlibrary.mocks.mock_infobase import MockSite


class TestMockSite:
    def test_get(self, mock_site):
        doc = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Test Book"
        }
        timestamp = datetime.datetime(2010, 1, 2, 3, 4, 5)
        
        mock_site.save(doc, timestamp=timestamp)
        
        assert mock_site.get("/books/OL1M").dict() == {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Test Book",
            "revision": 1,
            "last_modified": {
                "type": "/type/datetime",
                "value": "2010-01-02T03:04:05"
            }
        }
        assert mock_site.get("/books/OL1M").__class__.__name__ == "Edition"

    def test_query(self, mock_site):
        doc = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "title": "The Test Book",
            "subjects": ["love", "san_francisco"]
        }
        timestamp = datetime.datetime(2010, 1, 2, 3, 4, 5)

        mock_site.reset()
        mock_site.save(doc, timestamp=timestamp)
        
        for i in mock_site.index:
            print dict(i)
            
        assert mock_site.things({"type": "/type/edition"}) == ["/books/OL1M"]
        assert mock_site.things({"type": "/type/work"}) == []
        
        assert mock_site.things({"type": "/type/edition", "subjects": "love"}) == ["/books/OL1M"]
        assert mock_site.things({"type": "/type/edition", "subjects": "hate"}) == []

        assert mock_site.things({"key~": "/books/*"}) == ["/books/OL1M"]
        assert mock_site.things({"key~": "/works/*"}) == []
        
        assert mock_site.things({"last_modified>": "2010-01-01"}) == ["/books/OL1M"]
        assert mock_site.things({"last_modified>": "2010-01-03"}) == []
        
    def test_work_authors(self, mock_site):
        a2 = mock_site.quicksave("/authors/OL2A", "/type/author", name="A2")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo", authors=[{"author": {"key": "/authors/OL2A"}}])
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo", works=[{"key": "/works/OL1W"}])
         
        w = book.works[0]
        
        assert w.dict() == work.dict()
        
        a = w.authors[0].author
        assert a.dict() == a2.dict()
        
        
        assert a.key == "/authors/OL2A"
        assert a.type.key == "/type/author"
        assert a.name == "A2"
        
        assert [a.type.key for a in work.get_authors()] == ['/type/author']
        assert [a.type.key for a in work.get_authors()] == ['/type/author']
        