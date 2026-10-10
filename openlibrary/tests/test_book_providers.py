"""Tests for openlibrary.book_providers.get_best_edition."""

from __future__ import annotations

from unittest.mock import MagicMock

from openlibrary.book_providers import get_best_edition


def _make_edition(
    key: str,
    languages: list[str] | None = None,
    availability_status: str = "error",
    ocaid: str | None = None,
    num_fields: int = 5,
) -> MagicMock:
    """Build a minimal fake Edition for testing get_best_edition."""
    ed = MagicMock()
    ed.key = key
    ed.get = lambda k, default=None: {
        "availability": {"status": availability_status, "identifier": ocaid},
        "languages": [{"key": f"/languages/{lang}"} for lang in (languages or [])],
        "ocaid": ocaid,
    }.get(k, default)
    # len(dict(edition)) used as field-count tiebreaker
    ed.__iter__ = lambda self: iter(range(num_fields))
    ed.__len__ = lambda self: num_fields
    # Make dict(ed) return a dict of the right length
    ed.keys = lambda: list(range(num_fields))
    ed.__getitem__ = lambda self, k: k
    ed.ocaid = ocaid
    return ed


class TestGetBestEditionAvailabilityBoosting:
    def test_prefers_borrowable_over_unavailable(self):
        unavailable = _make_edition("/books/OL1M", availability_status="error")
        borrowable = _make_edition("/books/OL2M", availability_status="borrow_available")

        edition, _ = get_best_edition([unavailable, borrowable])
        assert edition is borrowable

    def test_prefers_open_over_unavailable(self):
        unavailable = _make_edition("/books/OL1M", availability_status="error")
        open_ed = _make_edition("/books/OL2M", availability_status="open")

        edition, _ = get_best_edition([unavailable, open_ed])
        assert edition is open_ed

    def test_falls_back_when_no_borrowable_exists(self):
        """Should still return something even if nothing is borrowable."""
        ed1 = _make_edition("/books/OL1M", availability_status="error")
        ed2 = _make_edition("/books/OL2M", availability_status="error")

        edition, _ = get_best_edition([ed1, ed2])
        assert edition is not None

    def test_returns_none_for_empty_list(self):
        edition, provider = get_best_edition([])
        assert edition is None
        assert provider is None


class TestGetBestEditionLanguageBoosting:
    def test_prefers_matching_language(self):
        english = _make_edition("/books/OL1M", languages=["eng"])
        french = _make_edition("/books/OL2M", languages=["fre"])

        edition, _ = get_best_edition([french, english], user_lang="eng")
        assert edition is english

    def test_matches_iso_2_letter_lang_to_marc(self):
        """2-letter ISO user_lang ('en') should match 3-letter MARC edition language ('eng')."""
        english = _make_edition("/books/OL1M", languages=["eng"])
        french = _make_edition("/books/OL2M", languages=["fre"])

        edition, _ = get_best_edition([french, english], user_lang="en")
        assert edition is english

    def test_falls_back_to_other_language_when_no_match(self):
        """Should still return something if no edition matches user_lang."""
        french = _make_edition("/books/OL1M", languages=["fre"])
        german = _make_edition("/books/OL2M", languages=["ger"])

        edition, _ = get_best_edition([french, german], user_lang="eng")
        assert edition is not None

    def test_no_user_lang_does_not_affect_result(self):
        """When user_lang is None all editions score equally on language."""
        ed1 = _make_edition("/books/OL1M", languages=["eng"])
        ed2 = _make_edition("/books/OL2M", languages=["fre"])

        # Should not raise; result is deterministic (first in wins on tie)
        edition, _ = get_best_edition([ed1, ed2], user_lang=None)
        assert edition is not None


class TestGetBestEditionCombined:
    def test_borrowable_same_language_wins(self):
        unavailable_english = _make_edition("/books/OL1M", languages=["eng"], availability_status="error")
        borrowable_french = _make_edition("/books/OL2M", languages=["fre"], availability_status="borrow_available")
        borrowable_english = _make_edition("/books/OL3M", languages=["eng"], availability_status="borrow_available")

        edition, _ = get_best_edition(
            [unavailable_english, borrowable_french, borrowable_english],
            user_lang="eng",
        )
        assert edition is borrowable_english

    def test_same_language_unavailable_beats_other_language_borrowable(self):
        """Language ranks higher than availability to preserve user readability."""
        unavailable_english = _make_edition("/books/OL1M", languages=["eng"], availability_status="error")
        borrowable_french = _make_edition("/books/OL2M", languages=["fre"], availability_status="borrow_available")

        edition, _ = get_best_edition(
            [unavailable_english, borrowable_french],
            user_lang="eng",
        )
        assert edition is unavailable_english
