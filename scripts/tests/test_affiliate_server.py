"""
Requires pytest-mock to be installed: `pip install pytest-mock`
for access to the mocker fixture.

# docker compose run --rm home pytest scripts/tests/test_affiliate_server.py
"""

import json
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

# TODO: Can we remove _init_path someday :(
sys.modules['_init_path'] = MagicMock()
from openlibrary.mocks.mock_infobase import mock_site  # noqa: F401
from scripts.affiliate_server import (  # noqa: E402
    PrioritizedIdentifier,
    Priority,
    get_editions_for_books,
    get_isbns_from_book,
    get_isbns_from_books,
    get_pending_books,
    make_cache_key,
    process_google_book,
)

ol_editions = {
    f"123456789{i}": {
        "type": "/type/edition",
        "key": f"/books/OL{i}M",
        "isbn_10": [f"123456789{i}"],
        "isbn_13": [f"123456789012{i}"],
        "covers": [int(f"1234567{i}")],
        "title": f"Book {i}",
        "authors": [{"key": f"/authors/OL{i}A"}],
        "publishers": [f"Publisher {i}"],
        "publish_date": f"Aug 0{i}, 2023",
        "number_of_pages": int(f"{i}00"),
    }
    for i in range(8)
}
ol_editions["1234567891"].pop("covers")
ol_editions["1234567892"].pop("title")
ol_editions["1234567893"].pop("authors")
ol_editions["1234567894"].pop("publishers")
ol_editions["1234567895"].pop("publish_date")
ol_editions["1234567896"].pop("number_of_pages")

amz_books = {
    f"123456789{i}": {
        "isbn_10": [f"123456789{i}"],
        "isbn_13": [f"12345678901{i}"],
        "cover": [int(f"1234567{i}")],
        "title": f"Book {i}",
        "authors": [{'name': f"Last_{i}a, First"}, {'name': f"Last_{i}b, First"}],
        "publishers": [f"Publisher {i}"],
        "publish_date": f"Aug 0{i}, 2023",
        "number_of_pages": int(f"{i}00"),
    }
    for i in range(8)
}


def test_ol_editions_and_amz_books():
    assert len(ol_editions) == len(amz_books) == 8


def test_get_editions_for_books(mock_site):  # noqa: F811
    """
    Attempting to save many ol editions and then get them back...
    """
    start = len(mock_site.docs)
    mock_site.save_many(ol_editions.values())
    assert len(mock_site.docs) - start == len(ol_editions)
    editions = get_editions_for_books(amz_books.values())
    assert len(editions) == len(ol_editions)
    assert sorted(edition.key for edition in editions) == [
        f"/books/OL{i}M" for i in range(8)
    ]


def test_get_pending_books(mock_site):  # noqa: F811
    """
    Testing get_pending_books() with no ol editions saved and then with ol editions.
    """
    # All books will be pending if they have no corresponding ol editions
    assert len(get_pending_books(amz_books.values())) == len(amz_books)
    # Save corresponding ol editions into the mock site
    start = len(mock_site.docs)
    mock_site.save_many(ol_editions.values())  # Save the ol editions
    assert len(mock_site.docs) - start == len(ol_editions)
    books = get_pending_books(amz_books.values())
    assert len(books) == 6  # Only 6 books are missing covers, titles, authors, etc.


def test_get_isbns_from_book():
    """
    Testing get_isbns_from_book() with a book that has both isbn_10 and isbn_13.
    """
    book = {
        "isbn_10": ["1234567890"],
        "isbn_13": ["1234567890123"],
    }
    assert get_isbns_from_book(book) == ["1234567890", "1234567890123"]


def test_get_isbns_from_books():
    """
    Testing get_isbns_from_books() with a list of books that have both isbn_10 and isbn_13.
    """
    books = [
        {
            "isbn_10": ["1234567890"],
            "isbn_13": ["1234567890123"],
        },
        {
            "isbn_10": ["1234567891"],
            "isbn_13": ["1234567890124"],
        },
    ]
    assert get_isbns_from_books(books) == [
        '1234567890',
        '1234567890123',
        '1234567890124',
        '1234567891',
    ]


def test_prioritized_identifier_equality_set_uniqueness() -> None:
    """
    `PrioritizedIdentifier` is unique in a set when no other class instance
    in the set has the same identifier.
    """
    identifier_1 = PrioritizedIdentifier(identifier="1111111111")
    identifier_2 = PrioritizedIdentifier(identifier="2222222222")

    set_one = set()
    set_one.update([identifier_1, identifier_1])
    assert len(set_one) == 1

    set_two = set()
    set_two.update([identifier_1, identifier_2])
    assert len(set_two) == 2


def test_prioritized_identifier_serialize_to_json() -> None:
    """
    `PrioritizedIdentifier` needs to be be serializable to JSON because it is sometimes
    called in, e.g. `json.dumps()`.
    """
    p_identifier = PrioritizedIdentifier(
        identifier="1111111111", priority=Priority.HIGH
    )
    dumped_identifier = json.dumps(p_identifier.to_dict())
    dict_identifier = json.loads(dumped_identifier)

    assert dict_identifier["priority"] == "HIGH"
    assert isinstance(dict_identifier["timestamp"], str)


@pytest.mark.parametrize(
    ["isbn_or_asin", "expected_key"],
    [
        ({"isbn_10": [], "isbn_13": ["9780747532699"]}, "9780747532699"),  # Use 13.
        (
            {"isbn_10": ["0747532699"], "source_records": ["amazon:B06XYHVXVJ"]},
            "9780747532699",
        ),  # 10 -> 13.
        (
            {"isbn_10": [], "isbn_13": [], "source_records": ["amazon:B06XYHVXVJ"]},
            "B06XYHVXVJ",
        ),  # Get non-ISBN 10 ASIN from `source_records` if necessary.
        ({"isbn_10": [], "isbn_13": [], "source_records": []}, ""),  # Nothing to use.
        ({}, ""),  # Nothing to use.
    ],
)
def test_make_cache_key(isbn_or_asin: dict[str, Any], expected_key: str) -> None:
    got = make_cache_key(isbn_or_asin)
    assert got == expected_key


# Sample Google Book data with all fields present
complete_book_data = {
    "kind": "books#volumes",
    "totalItems": 1,
    "items": [
        {
            "kind": "books#volume",
            "id": "YJ1uQwAACAAJ",
            "etag": "a6JFgm2Cyu0",
            "selfLink": "https://www.googleapis.com/books/v1/volumes/YJ1uQwAACAAJ",
            "volumeInfo": {
                "title": "Бал моей мечты",
                "subtitle": "[для сред. шк. возраста]",
                "authors": ["Светлана Лубенец"],
                "publishedDate": "2009",
                "industryIdentifiers": [
                    {"type": "ISBN_10", "identifier": "5699350136"},
                    {"type": "ISBN_13", "identifier": "9785699350131"},
                ],
                "pageCount": 153,
                "publisher": "Some Publisher",
                "description": "A cool book",
            },
            "saleInfo": {
                "country": "US",
                "saleability": "NOT_FOR_SALE",
                "isEbook": False,
            },
            "accessInfo": {
                "country": "US",
                "viewability": "NO_PAGES",
            },
        }
    ],
}

# Expected output for the complete book data
expected_output_complete = {
    "isbn_10": ["5699350136"],
    "isbn_13": ["9785699350131"],
    "title": "Бал моей мечты",
    "subtitle": "[для сред. шк. возраста]",
    "authors": [{"name": "Светлана Лубенец"}],
    "source_records": ["google_books:9785699350131"],
    "publishers": ["Some Publisher"],
    "publish_date": "2009",
    "number_of_pages": 153,
    "description": "A cool book",
}


# Parametrized tests for different missing fields
@pytest.mark.parametrize(
    "input_data, expected_output",
    [
        (complete_book_data, expected_output_complete),
        # Missing ISBN_13
        (
            {
                "kind": "books#volumes",
                "totalItems": 1,
                "items": [
                    {
                        "volumeInfo": {
                            "title": "Бал моей мечты",
                            "authors": ["Светлана Лубенец"],
                            "publishedDate": "2009",
                            "industryIdentifiers": [
                                {"type": "ISBN_10", "identifier": "5699350136"}
                            ],
                            "pageCount": 153,
                            "publisher": "Some Publisher",
                        }
                    }
                ],
            },
            {
                "isbn_10": ["5699350136"],
                "isbn_13": [],
                "title": "Бал моей мечты",
                "subtitle": None,
                "authors": [{"name": "Светлана Лубенец"}],
                "source_records": ["google_books:5699350136"],
                "publishers": ["Some Publisher"],
                "publish_date": "2009",
                "number_of_pages": 153,
                "description": None,
            },
        ),
        # Missing authors
        (
            {
                "kind": "books#volumes",
                "totalItems": 1,
                "items": [
                    {
                        "volumeInfo": {
                            "title": "Бал моей мечты",
                            "publishedDate": "2009",
                            "industryIdentifiers": [
                                {"type": "ISBN_10", "identifier": "5699350136"},
                                {"type": "ISBN_13", "identifier": "9785699350131"},
                            ],
                            "pageCount": 153,
                            "publisher": "Some Publisher",
                        }
                    }
                ],
            },
            {
                "isbn_10": ["5699350136"],
                "isbn_13": ["9785699350131"],
                "title": "Бал моей мечты",
                "subtitle": None,
                "authors": [],
                "source_records": ["google_books:9785699350131"],
                "publishers": ["Some Publisher"],
                "publish_date": "2009",
                "number_of_pages": 153,
                "description": None,
            },
        ),
        # Missing everything but the title and ISBN 13.
        (
            {
                "kind": "books#volumes",
                "totalItems": 1,
                "items": [
                    {
                        "volumeInfo": {
                            "title": "Бал моей мечты",
                            "industryIdentifiers": [
                                {"type": "ISBN_13", "identifier": "9785699350131"}
                            ],
                        }
                    }
                ],
            },
            {
                "isbn_10": [],
                "isbn_13": ["9785699350131"],
                "title": "Бал моей мечты",
                "subtitle": None,
                "authors": [],
                "source_records": ["google_books:9785699350131"],
                "publishers": [],
                "publish_date": "",
                "number_of_pages": None,
                "description": None,
            },
        ),
    ],
)
def test_process_google_book(input_data, expected_output):
    """
    Test a few permutations to make sure the function can handle missing fields.

    It is assumed there will always be an ISBN 10 or 13 as that is what this queries
    by. If both are absent this will crash.
    """
    assert process_google_book(input_data) == expected_output


def test_process_google_book_no_items():
    """Sometimes there will be no results from Google Books."""
    input_data = {"kind": "books#volumes", "totalItems": 0, "items": []}
    assert process_google_book(input_data) is None


def test_process_google_book_multiple_items():
    """We should only get one result per ISBN."""
    input_data = {
        "kind": "books#volumes",
        "totalItems": 2,
        "items": [
            {"volumeInfo": {"title": "Book One"}},
            {"volumeInfo": {"title": "Book Two"}},
        ],
    }
    assert process_google_book(input_data) is None
