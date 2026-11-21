import json

from openlibrary.plugins.openlibrary.contribute import build_book_header


def test_a_book_missing_its_isbn_title_and_work_still_serializes(mock_site):
    mock_site.save({"key": "/books/OL1M", "type": {"key": "/type/edition"}})
    header = build_book_header(mock_site.get("/books/OL1M"))
    assert json.loads(json.dumps(header)) == header
    assert (header["title"], header["isbn13"], header["cover_url"], header["edition_count"]) == ("", None, None, 1)
