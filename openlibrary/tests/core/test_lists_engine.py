from openlibrary.core.lists import engine


def test_get_seeds():
    work = {
        "key": "/works/OL1W",
        "authors": [
            {"author": {"key": "/authors/OL1A"}},
            {"author": {"key": "/authors/OL2A"}},
            {"not_author": {"key": "/authors/ignored"}},
        ],
        "editions": [
            {"key": "/books/OL1M"},
            {"key": "/books/OL2M"},
        ],
        "subjects": ["Love Story", "love_story", 123],
        "subject_places": ["New York", None],
        "subject_people": ["Jane Doe", {"name": "ignored"}],
        "subject_times": ["2000-2099"],
    }

    seeds = engine.get_seeds(work)

    assert seeds == [
        "/works/OL1W",
        "/authors/OL1A",
        "/authors/OL2A",
        "/books/OL1M",
        "/books/OL2M",
        "subject:love_story",
        "place:new_york",
        "person:jane_doe",
        "time:2000-2099",
    ]
