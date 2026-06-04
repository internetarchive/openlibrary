"""Tests for get_days_registered — Matomo retention dimension helper."""

import datetime
from unittest.mock import MagicMock

import pytest

from openlibrary.accounts import get_days_registered


def _user(days_ago):
    """Return a mock user whose account was created `days_ago` days ago (UTC)."""
    user = MagicMock()
    user.created = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)
    return user


# ---------------------------------------------------------------------------
# Unauthenticated / missing data
# ---------------------------------------------------------------------------


def test_no_user_returns_visitor():
    assert get_days_registered(None) == "visitor"


def test_falsy_user_returns_visitor():
    assert get_days_registered(0) == "visitor"
    assert get_days_registered("") == "visitor"


def test_missing_created_returns_d90_plus():
    user = MagicMock()
    user.created = None
    assert get_days_registered(user) == "d90+"


def test_invalid_created_returns_d90_plus():
    user = MagicMock()
    user.created = "not-a-date"
    assert get_days_registered(user) == "d90+"


# ---------------------------------------------------------------------------
# Bucket boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (0, "d0"),
        (1, "d1+"),
        (6, "d1+"),
        (7, "d7+"),
        (13, "d7+"),
        (14, "d14+"),
        (29, "d14+"),
        (30, "d30+"),
        (89, "d30+"),
        (90, "d90+"),
        (365, "d90+"),
    ],
)
def test_day_buckets(days_ago, expected):
    assert get_days_registered(_user(days_ago)) == expected
