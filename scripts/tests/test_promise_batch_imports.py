import pytest

from ..promise_batch_imports import format_date, map_book_to_olbook

TEST_BOOK_NO_ASIN = {
    "BookBarcode": "S0-FPI-987",
    "PackedLocation": "Mishawaka",
    "Sort": "Never Seen",
    "BookSKUB": "S0-FPI-987",
    "ISBN": "9780990697091",
    "ProductJSON": {
        "ISBN": "9780990697091",
        "Title": "Yely's Holiday Traditions",
        "MasterProductId": "62590913",
        "BookId": "0",
        "Author": "Maria Isabel Medina-Berrios",
        "Publisher": "The Kemper Foundation",
        "PublicationDate": "20151215",
        "BisacCategory": "Juvenile Fiction"
    }
}


@pytest.mark.parametrize(
    ("date", "only_year", "expected"),
    [
        ("20001020", False, "2000-10-20"),
        ("20000101", True, "2000"),
        ("20000000", True, "2000"),
    ],
)
def test_format_date(date, only_year, expected) -> None:
    assert format_date(date=date, only_year=only_year) == expected


def test_map_book_to_olbook():
    expected = {
        "local_id": ["urn:bwbsku:S0-FPI-987"],
        "isbn_13": ["9780990697091"],
        "title": "Yely's Holiday Traditions",
        "authors": [{"name": "Maria Isabel Medina-Berrios"}],
        "publishers": ["The Kemper Foundation"],
        "source_records": ["promise:bwb_daily_pallets_2026-01-09:S0-FPI-987"],
        "publish_date": "2015-12-15",
    }
    assert map_book_to_olbook(TEST_BOOK_NO_ASIN, promise_id="bwb_daily_pallets_2026-01-09") == expected
