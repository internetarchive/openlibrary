from openlibrary.core.lists import engine

def test_reduce():
    def test_reduce(self):
        d1 = [1, 2, 1, "2010-11-11 10:20:30", {
            "subjects": ["Love", "Hate"]
        }]

        d2 = [1, 1, 0, "2009-01-02 10:20:30", {
            "subjects": ["Love"]
        }]
        assert engine.reduce([d1, d2]) == {
            "works": 2,
            "editions": 3,
            "ebooks": 1,
            "last_modified": "2010-11-11 10:20:30",
            "subjects": [
                {"name": "Love", "key": "subject:love", "count": 2},
                {"name": "Hate", "key": "subject:hate", "count": 1}
            ]
        }
    