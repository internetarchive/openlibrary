from scripts.import_bookdash import map_data, strip_author_role

SAMPLE_1 = {
    "url": "https://bookdash.org/books/a-beautiful-day/",
    "title": "A Beautiful Day",
    "cover_url": "https://bookdash.org/wp-content/uploads/2016/01/a-beautiful-day_cover_20160104.jpg",
    "description": "It’s a beautiful day for a picnic. Everyone wants to join in the fun.",  # noqa: RUF001
    "languages": ["eng"],
    "subjects": ["Family, friends, and home", "Let's go on an adventure"],
    "authors": ["Raeesah Vawda(Designer)", "Lindy Pelzl(Illustrator)", "Elana Bregin(Writer)"],
    "isbn": "978-1-928318-15-6",
}


def test_strip_author_role():
    assert strip_author_role("Raeesah Vawda(Designer)") == "Raeesah Vawda"
    assert strip_author_role("Elana Bregin (Writer)") == "Elana Bregin"
    assert strip_author_role("Jane Doe") == "Jane Doe"


def test_map_data():
    assert map_data(SAMPLE_1) == {
        "title": "A Beautiful Day",
        "source_records": ["bookdash:a-beautiful-day"],
        "publishers": ["Bookdash"],
        "authors": [
            {"name": "Raeesah Vawda"},
            {"name": "Lindy Pelzl"},
            {"name": "Elana Bregin"},
        ],
        "languages": ["eng"],
        "subjects": ["Family, friends, and home", "Let's go on an adventure"],
        "description": "It’s a beautiful day for a picnic. Everyone wants to join in the fun.",  # noqa: RUF001
        "identifiers": {"isbn_13": ["978-1-928318-15-6"]},
        "cover": "https://bookdash.org/wp-content/uploads/2016/01/a-beautiful-day_cover_20160104.jpg",
    }


def test_map_data_no_isbn_or_cover():
    scraped = {**SAMPLE_1, "isbn": None, "cover_url": None}
    record = map_data(scraped)
    assert "identifiers" not in record
    assert "cover" not in record
