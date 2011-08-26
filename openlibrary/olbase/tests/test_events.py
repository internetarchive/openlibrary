from .. import events

class TestMemcacheInvalidater:
    def test_seed_to_key(self):
        m = events.MemcacheInvalidater()        
        assert m.seed_to_key({"key": "/books/OL1M"}) == "/books/OL1M"
        assert m.seed_to_key("subject:love") == "/subjects/love"
        assert m.seed_to_key("place:san_francisco") == "/subjects/place:san_francisco"
        assert m.seed_to_key("person:mark_twain") == "/subjects/person:mark_twain"
        assert m.seed_to_key("time:2000") == "/subjects/time:2000"
        
    def test_find_lists(self):
        changeset = {
            "changes": [
                {"key": "/people/anand/lists/OL1L", "revision": 1}
            ],
            "old_docs": [None],
            "docs": [{
                "key": "/people/anand/lists/OL1L",
                "type": {"key": "/type/list"},
                "revision": 1,
                "seeds": [
                    {"key": "/books/OL1M"}, 
                    "subject:love"
                ]
            }]
        }
        m = events.MemcacheInvalidater()
        assert sorted(m.find_lists(changeset)) == ["d/books/OL1M", "d/people/anand", "d/subjects/love"]
                
    def test_find_lists2(self):
        changeset = {
            "changes": [
                {"key": "/people/anand/lists/OL1L", "revision": 2}
            ],
            "old_docs": [{
                "key": "/people/anand/lists/OL1L",
                "type": {"key": "/type/list"},
                "revision": 1,
                "seeds": [
                    {"key": "/books/OL1M"}, 
                    "subject:love"
                ]
            }],
            "docs": [{
                "key": "/people/anand/lists/OL1L",
                "type": {"key": "/type/list"},
                "revision": 2,
                "seeds": [
                    {"key": "/authors/OL1A"}, 
                    "subject:love",
                    "place:san_francisco"
                ]            
            }]
        }
        
        m = events.MemcacheInvalidater()
        keys = sorted(set(m.find_lists(changeset)))
        assert keys == [
            "d/authors/OL1A", 
            "d/books/OL1M", 
            "d/people/anand",
            "d/subjects/love", 
            "d/subjects/place:san_francisco"
        ]
        
    def test_edition_count_for_doc(self):
        m = events.MemcacheInvalidater()
        
        assert m.find_edition_counts_for_doc(None) == []

        doc = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
            "works": [{"key": "/works/OL1W"}]
        }
        assert m.find_edition_counts_for_doc(doc) == ["d/works/OL1W"]
        
    def test_find_keys(self):
        m = events.MemcacheInvalidater()
        
        changeset = {
            "changes": [
                {"key": "/sandbox", "revision": 1}
            ],
            "old_docs": [None],
            "docs": [{
                "key": "/sandbox",
                "type": {"key": "/type/page"},
                "revision": 1,
                "title": "Sandbox"
            }]
        }
        m.find_keys(changeset) == ["d/sandbox"]