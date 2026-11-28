from unittest.mock import Mock, patch

from scripts.import_bookdash import get_sitemap_urls, map_data, scrape_book_page, strip_author_role

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://bookdash.org/books/</loc></url>
<url><loc>https://bookdash.org/books/a-beautiful-day/</loc></url>
<url><loc>https://bookdash.org/books/usuku-oluhle/</loc></url>
</urlset>
"""

BOOK_PAGE_HTML = """
<html>
<head>
<meta property="og:description" content="It's a beautiful day for a picnic.">
</head>
<body>
<h1>A Beautiful Day</h1>
<picture><img data-src="https://bookdash.org/wp-content/uploads/2016/01/cover.jpg" src="placeholder.jpg"></picture>
<a href="/languages/eng">English</a>
<a href="/themes/family-friends-and-home">Family, friends, and home</a>
<a href="/team-members/raeesah-vawda">Raeesah Vawda(Designer)</a>
<a href="/team-members/elana-bregin">Elana Bregin(Writer)</a>
<p>ISBN: 978-1-928318-15-6</p>
</body>
</html>
"""

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


@patch("scripts.import_bookdash.requests.get")
def test_get_sitemap_urls(mock_get):
    mock_get.return_value = Mock(content=SITEMAP_XML.encode(), status_code=200)
    urls = get_sitemap_urls()
    assert urls == [
        "https://bookdash.org/books/a-beautiful-day/",
        "https://bookdash.org/books/usuku-oluhle/",
    ]


@patch("scripts.import_bookdash.requests.get")
def test_scrape_book_page(mock_get):
    mock_get.return_value = Mock(text=BOOK_PAGE_HTML, status_code=200)
    scraped = scrape_book_page("https://bookdash.org/books/a-beautiful-day/")
    assert scraped == {
        "url": "https://bookdash.org/books/a-beautiful-day/",
        "title": "A Beautiful Day",
        "cover_url": "https://bookdash.org/wp-content/uploads/2016/01/cover.jpg",
        "description": "It's a beautiful day for a picnic.",
        "languages": ["eng"],
        "subjects": ["Family, friends, and home"],
        "authors": ["Raeesah Vawda(Designer)", "Elana Bregin(Writer)"],
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
