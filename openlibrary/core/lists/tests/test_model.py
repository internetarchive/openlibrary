import web

from openlibrary.core.lists import model

class MockCouchDB:
    def __init__(self, docs):
        self.docs = docs
    
    def view(self, name, keys=None, include_docs=False):
        return [web.storage(id=doc['_id'], key=doc['_id'], value=doc, doc=doc) for doc in self.docs]

class MockList(model.ListMixin):
    def __init__(self, db, seeds):
        self.db = db
        self.seeds = seeds
        
    def _get_seeds_db(self):
        return self.db

class TestListMixin:
    def test_simple(self):
        doc1 = {
            "_id": "/works/OL1W",
            "editions": 10, 
            "works": 1,
            "ebooks": 2, 
            "subjects": [
                {"key": "subject:love", "name": "Love", "count": 2}
            ]
        }

        doc2 = {
            "_id": "/authors/OL1A",
            "editions": 10, 
            "works": 5, 
            "ebooks": 2, 
            "subjects": [
                {"key": "place:san_francisco", "name": "San Francisco", "count": 3},
                {"key": "subject:love", "name": "Love", "count": 2}
            ]
        }
        
        db = MockCouchDB([doc1, doc2])
        list = MockList(db, ['/works/OL1W', '/authors/OL1A'])
        
        assert list.edition_count == 20
        assert list.work_count == 6
        assert list.ebook_count == 4
        assert list.get_subjects() == [
            {"key": "subject:love", "url": "/subjects/love", "name": "Love", "title": "Love", "count": 4},
            {"key": "place:san_francisco", "url": "/subjects/place:san_francisco", "name": "San Francisco", "title": "San Francisco", "count": 3}
        ]
        assert list.get_subjects(limit=1) == [
            {"key": "subject:love", "url": "/subjects/love", "name": "Love", "title": "Love", "count": 4}
        ]