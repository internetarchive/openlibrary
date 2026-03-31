"""Tests for get_patron_status — Matomo retention dimension helper."""
import datetime
from unittest.mock import MagicMock

import pytest

from openlibrary.plugins.openlibrary.code import get_patron_status


def _user(days_ago):
    """Return a mock user whose account was created `days_ago` days ago (UTC)."""
    user = MagicMock()
    user.created = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)
    return user


# ---------------------------------------------------------------------------
# Unauthenticated / missing data
# ---------------------------------------------------------------------------


def test_no_user_returns_visitor():
    assert get_patron_status(None) == 'visitor'


def test_falsy_user_returns_visitor():
    assert get_patron_status(0) == 'visitor'
    assert get_patron_status('') == 'visitor'


def test_missing_created_returns_d90_plus():
    user = MagicMock()
    user.created = None
    assert get_patron_status(user) == 'd90+'


def test_invalid_created_returns_d90_plus():
    user = MagicMock()
    user.created = 'not-a-date'
    assert get_patron_status(user) == 'd90+'


# ---------------------------------------------------------------------------
# Bucket boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (0, 'd0'),
        (1, 'd1+'),
        (6, 'd1+'),
        (7, 'd7+'),
        (13, 'd7+'),
        (14, 'd14+'),
        (29, 'd14+'),
        (30, 'd30+'),
        (89, 'd30+'),
        (90, 'd90+'),
        (365, 'd90+'),
    ],
)
def test_day_buckets(days_ago, expected):
    assert get_patron_status(_user(days_ago)) == expected
