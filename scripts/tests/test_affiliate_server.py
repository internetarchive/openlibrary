"""
# docker compose run --rm home pytest scripts/tests/test_affiliate_server.py
"""

import json
import sys
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest

# TODO: Can we remove _init_path someday :(
sys.modules["_init_path"] = MagicMock()
from openlibrary.mocks.mock_infobase import mock_site  # noqa: F401
from scripts.affiliate_server import (
    PrioritizedIdentifier,
    Priority,
    get_editions_for_books,
    get_isbns_from_book,
    get_isbns_from_books,
    get_pending_books,
    load_config,
    make_cache_key,
    process_amazon_batch,
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
        "authors": [{"name": f"Last_{i}a, First"}, {"name": f"Last_{i}b, First"}],
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
    assert sorted(edition.key for edition in editions) == [f"/books/OL{i}M" for i in range(8)]


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
        "1234567890",
        "1234567890123",
        "1234567890124",
        "1234567891",
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
    p_identifier = PrioritizedIdentifier(identifier="1111111111", priority=Priority.HIGH)
    dumped_identifier = json.dumps(p_identifier.to_dict())
    dict_identifier = json.loads(dumped_identifier)

    assert dict_identifier["priority"] == "HIGH"
    assert isinstance(dict_identifier["timestamp"], str)


@pytest.mark.parametrize(
    ("isbn_or_asin", "expected_key"),
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
    ("input_data", "expected_output"),
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
                            "industryIdentifiers": [{"type": "ISBN_10", "identifier": "5699350136"}],
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
                            "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9785699350131"}],
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


class TestLoadConfigRequiresCreatorsAPI:
    """
    The Creators API is the only supported Amazon client as of #13277; the legacy
    PA-API fallback was removed once Creators was confirmed live in production.

    Before that, `load_config` silently downgraded to legacy whenever Creators
    credentials were incomplete -- which is why the outage post-mortem could not tell
    from the code which client was serving traffic. These pin that a downgrade can no
    longer happen quietly.
    """

    CREATORS: ClassVar[dict[str, str]] = {"key": "ck", "secret": "cs", "id": "ci", "version": "3.1"}
    LEGACY: ClassVar[dict[str, str]] = {"key": "lk", "secret": "ls", "id": "li"}

    def _load(self, creators: dict | None, legacy: dict | None):
        """Run load_config against a synthetic config; return the patched Creators class."""
        cfg: dict[str, Any] = {"http_proxy": "http://user:pass@squid:3128"}
        if creators is not None:
            cfg["amazon_creators_api"] = creators
        if legacy is not None:
            cfg["amazon_api"] = legacy

        with (
            patch("scripts.affiliate_server.openlibrary_load_config"),
            patch("scripts.affiliate_server.stats"),
            patch("scripts.affiliate_server.config", new=cfg),
            patch("scripts.affiliate_server.AmazonCreatorsAPI") as creators_cls,
        ):
            load_config("openlibrary.yml")
            return creators_cls

    def test_creators_credentials_build_the_client(self):
        assert self._load(self.CREATORS, None).called

    def test_only_legacy_credentials_raises(self):
        """Legacy creds no longer buy a working affiliate server -- fail, don't downgrade."""
        with pytest.raises(RuntimeError, match="missing required amazon_creators_api"):
            self._load(None, self.LEGACY)

    def test_partial_creators_credentials_raises(self):
        """One missing key must fail loudly, not half-configure or revert to legacy."""
        with pytest.raises(RuntimeError, match="missing required amazon_creators_api"):
            self._load({"key": "ck", "secret": None, "id": "ci"}, self.LEGACY)


# ---- 979-prefix ISBN-13 resolution via search (#13316) ----------------------
#
# A 979 ISBN-13 has no ISBN-10 equivalent, so `get_items` (an exact-id lookup) can never
# reach it. These lock in that such identifiers are routed to search instead, and that
# the routing does not disturb the ISBN-10 / B* ASIN paths.

ISBN_979 = "9798776159572"
ASIN_979 = "B09MJ3TKX3"


def _serialized_979_product() -> dict[str, Any]:
    """What AmazonCreatorsAPI.serialize() yields for a search-resolved 979 book."""
    return {
        "source_records": [f"amazon:{ASIN_979}"],
        "isbn_10": [],
        "isbn_13": [ISBN_979],
        "title": "Pickleball Soap Opera",
        "authors": [{"name": "Test Author"}],
        "publish_date": "Jan 01, 2022",
        "publishers": ["Test Publisher"],
    }


def test_make_cache_key_for_979_product_uses_isbn_13() -> None:
    """A search-resolved 979 product caches under its ISBN-13, not its B* ASIN.

    This is what lets Submit.GET read the result back: it looks up
    `amazon_product_{isbn_13 or b_asin}`, which for a 979 request is the ISBN-13.
    """
    assert make_cache_key(_serialized_979_product()) == ISBN_979


def _run_batch(asins, resolved=_serialized_979_product, direct_products=None):
    """Run process_amazon_batch with a stubbed Amazon client; return (mock_api, mock_batch)."""
    mock_api = MagicMock()
    mock_api.get_products.return_value = direct_products or []
    mock_api.get_product_by_isbn_13.return_value = resolved() if callable(resolved) else resolved

    with (
        patch("scripts.affiliate_server.web") as mock_web,
        patch("scripts.affiliate_server.cache") as _mock_cache,
        patch("scripts.affiliate_server.stats"),
        patch("scripts.affiliate_server.config") as mock_config,
        patch("scripts.affiliate_server.get_current_batch") as mock_batch,
    ):
        mock_web.amazon_api = mock_api
        mock_config.infobase = {"db_parameters": {"db": "test"}}
        process_amazon_batch(asins)

    return mock_api, mock_batch


def test_process_amazon_batch_partitions_direct_and_search() -> None:
    """A mixed batch makes one batched get_items call plus one search per 979 ISBN."""
    mock_api, _ = _run_batch(
        {
            PrioritizedIdentifier(identifier="0190906766"),
            PrioritizedIdentifier(identifier=ISBN_979),
        }
    )

    # The ISBN-10 goes through the batched path; the 979 ISBN does not.
    assert mock_api.get_products.call_count == 1
    assert mock_api.get_products.call_args.args[0] == ["0190906766"]
    mock_api.get_product_by_isbn_13.assert_called_once_with(ISBN_979, serialize=True)


def test_process_amazon_batch_search_only_batch_skips_get_products() -> None:
    """A batch of only 979 ISBNs makes no get_items call at all."""
    mock_api, _ = _run_batch({PrioritizedIdentifier(identifier=ISBN_979)})

    mock_api.get_products.assert_not_called()
    mock_api.get_product_by_isbn_13.assert_called_once_with(ISBN_979, serialize=True)


def test_process_amazon_batch_isbn_10_never_searched() -> None:
    """Regression guard: an ISBN-10 batch is untouched by the new search path."""
    mock_api, _ = _run_batch({PrioritizedIdentifier(identifier="0190906766")})

    mock_api.get_product_by_isbn_13.assert_not_called()
    assert mock_api.get_products.call_args.args[0] == ["0190906766"]


def test_process_amazon_batch_b_asin_never_searched() -> None:
    """Regression guard: a B* ASIN is a direct lookup, never a search."""
    mock_api, _ = _run_batch({PrioritizedIdentifier(identifier="B000KRRIZI")})

    mock_api.get_product_by_isbn_13.assert_not_called()
    assert mock_api.get_products.call_args.args[0] == ["B000KRRIZI"]


def test_979_with_stage_import_false_is_not_staged() -> None:
    """Regression: stage_import=false must be honoured for search-resolved products.

    The staging filter compares `source_records[0]` — which for a search-resolved product
    is `amazon:{B-ASIN}` — against the queued identifiers, which for a 979 request hold the
    *ISBN-13*. Those never compare equal, so without a back-mapping from resolved product
    to originating identifier the item would be staged despite stage_import=false.
    """
    _, mock_batch = _run_batch({PrioritizedIdentifier(identifier=ISBN_979, stage_import=False)})

    mock_batch.return_value.add_items.assert_not_called()


def test_979_with_stage_import_true_is_staged() -> None:
    """The positive counterpart: stage_import=true does stage the resolved product."""
    _, mock_batch = _run_batch({PrioritizedIdentifier(identifier=ISBN_979, stage_import=True)})

    mock_batch.return_value.add_items.assert_called_once()
    staged = mock_batch.return_value.add_items.call_args.args[0]
    assert staged[0]["ia_id"] == f"amazon:{ASIN_979}"


def test_unverified_979_search_result_is_not_staged() -> None:
    """If resolution returns None (ISBN mismatch), nothing is staged."""
    _, mock_batch = _run_batch({PrioritizedIdentifier(identifier=ISBN_979)}, resolved=None)

    mock_batch.return_value.add_items.assert_not_called()
