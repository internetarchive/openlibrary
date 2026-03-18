from openlibrary.core.lists import engine


def test_reduce_seeds():
    d1 = [1, 2, 1, "2010-11-11 10:20:30", {"subjects": ["Love", "Hate"]}]

    d2 = [1, 1, 0, "2009-01-02 10:20:30", {"subjects": ["Love"]}]
    assert engine.reduce_seeds([d1, d2]) == {
        "works": 2,
        "editions": 3,
        "ebooks": 1,
        "last_update": "2010-11-11 10:20:30",
        "subjects": [
            {"key": "subject:love", "name": "Love", "count": 2},
            {"key": "subject:hate", "name": "Hate", "count": 1},
        ],
    }
