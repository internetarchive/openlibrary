"""Tests for the feed match-preview tool (#12844).

The classification is the part worth testing: the tool exists to distinguish a
match to the RIGHT edition from a confident match to the wrong one, and the
second looks completely successful.
"""

from __future__ import annotations

import pytest

from scripts.bookworm_preview_match import (
    MATCHED_EXPECTED,
    MATCHED_OTHER,
    NO_ANSWER,
    WOULD_CREATE,
    classify,
    expected_edition_key,
)


def record(local_id: str | None) -> dict:
    acquisitions = [{"provider_name": "lenny", "local_id": local_id}] if local_id else []
    return {"title": "A Book", "source_records": [f"lenny:{local_id}"], "acquisitions": acquisitions}


def reply(key: str | None, status: str = "matched") -> dict:
    return {"success": True, "edition": {"key": key, "status": status} if key else {}}


class TestExpectedEditionKey:
    def test_a_numeric_local_id_names_an_edition(self):
        """Lenny encodes the OL edition number in its self link."""
        assert expected_edition_key(record("51008637")) == "/books/OL51008637M"

    def test_a_non_numeric_id_names_nothing(self):
        assert expected_edition_key(record("urn:isbn:9781737408802")) is None

    def test_no_acquisitions_names_nothing(self):
        assert expected_edition_key(record(None)) is None


class TestClassify:
    def test_the_expected_edition(self):
        bucket, matched, expected = classify(record("51008637"), reply("/books/OL51008637M"))
        assert bucket == MATCHED_EXPECTED
        assert matched == expected == "/books/OL51008637M"

    def test_a_different_edition_is_flagged(self):
        """The silent failure. Feeds of public-domain classics hit the most
        duplicated records in the catalog, so title matching finds a large pool
        and picks one -- confidently, and with no error."""
        bucket, matched, expected = classify(record("51008637"), reply("/books/OL999M"))
        assert bucket == MATCHED_OTHER
        assert matched == "/books/OL999M"
        assert expected == "/books/OL51008637M"

    def test_a_create_is_its_own_bucket(self):
        bucket, _, _ = classify(record("51008637"), reply("/books/OL__new__1M", status="created"))
        assert bucket == WOULD_CREATE

    def test_no_edition_resolved(self):
        assert classify(record("51008637"), reply(None))[0] == NO_ANSWER

    def test_an_empty_reply_does_not_crash(self):
        assert classify(record("51008637"), {})[0] == NO_ANSWER

    @pytest.mark.parametrize("status", ["matched", "modified"])
    def test_both_non_create_statuses_are_compared(self, status):
        assert classify(record("51008637"), reply("/books/OL999M", status=status))[0] == MATCHED_OTHER

    def test_a_feed_without_edition_ids_is_not_judged(self):
        """For a feed whose local_id is an ISBN there is nothing to compare, so
        a match must not be reported as wrong."""
        bucket, _, expected = classify(record("urn:isbn:1"), reply("/books/OL5M"))
        assert bucket == MATCHED_EXPECTED
        assert expected is None

    def test_expectations_can_be_turned_off(self):
        bucket, _, _ = classify(record("51008637"), reply("/books/OL999M"), expect_edition_ids=False)
        assert bucket == MATCHED_EXPECTED
