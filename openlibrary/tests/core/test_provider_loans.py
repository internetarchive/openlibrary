from types import SimpleNamespace
from typing import Any

import pytest

from openlibrary.core import provider_loans

EDITION_KEY = "/books/OL37044497M"


def make_loan(**overrides: Any) -> dict[str, Any]:
    """A loan shaped like the ones ``lenny.provider_loans`` returns."""
    loan = {
        "book": EDITION_KEY,
        "loaned_at": 1758000000,
        "expiry": "2026-10-06T12:00:00",
        "userid": "openlibrary",
        "provider": "lenny",
        "resource_type": "provider",
        "read_url": "https://lenny.example/read/1",
    }
    loan.update(overrides)
    return loan


class FakeUser:
    def __init__(self, username: str = "patron"):
        self._username = username

    def get_username(self) -> str:
        return self._username


@pytest.fixture
def loans(monkeypatch):
    """Control what the cached lookup returns, without touching memcache."""
    holder: list[dict[str, Any]] = []
    monkeypatch.setattr(provider_loans, "get_cached_provider_loans", lambda username: holder)
    return holder


def test_returns_the_loan_the_patron_holds_on_this_edition(loans):
    loans.append(make_loan())
    loan = provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser())
    assert loan is not None
    assert loan["read_url"] == "https://lenny.example/read/1"


def test_a_loan_on_another_edition_is_not_this_edition_s_loan(loans):
    loans.append(make_loan(book="/books/OL999M"))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None


def test_no_loans_means_no_loan(loans):
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None


def test_no_edition_key_is_not_looked_up(monkeypatch):
    def fail(username):
        raise AssertionError("no lookup should happen without an edition key")

    monkeypatch.setattr(provider_loans, "get_cached_provider_loans", fail)
    assert provider_loans.get_provider_loan(None, user=FakeUser()) is None
    assert provider_loans.get_provider_loan("", user=FakeUser()) is None


def test_logged_out_patrons_are_not_looked_up(monkeypatch):
    def fail(username):
        raise AssertionError("no lookup should happen for a logged-out patron")

    monkeypatch.setattr(provider_loans, "get_cached_provider_loans", fail)
    monkeypatch.setattr("openlibrary.accounts.get_current_user", lambda: None)
    assert provider_loans.get_provider_loan(EDITION_KEY) is None


@pytest.mark.parametrize(
    "read_url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "",
        None,
        123,
    ],
)
def test_a_loan_whose_read_url_is_unusable_is_ignored(loans, read_url):
    """Read with nowhere safe to send the patron is worse than Borrow, which works."""
    loans.append(make_loan(read_url=read_url))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None


def test_a_junk_row_does_not_break_the_page(loans):
    loans.extend(["not a dict", None, make_loan()])
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None


def test_lookup_failure_reads_as_no_loans(monkeypatch):
    """A node that is slow, broken or unauthorized must cost the book page nothing.

    Degrading to Borrow is harmless: Lenny's borrow is idempotent for a loan the
    patron already holds, so a second attempt just returns that loan.
    """

    class Boom:
        @staticmethod
        def provider_loans(username):
            raise RuntimeError("node unreachable")

    monkeypatch.setitem(__import__("sys").modules, "openlibrary.plugins.upstream.lenny", Boom)
    assert provider_loans._fetch_provider_loans("patron") == []


def test_unreachable_and_unauthorized_nodes_are_dropped(monkeypatch):
    """The book page has nowhere to report them, and no way to act on them."""

    result = SimpleNamespace(loans=[make_loan()], unreachable=["lenny"], unauthorized=["other"])

    class Lenny:
        @staticmethod
        def provider_loans(username):
            return result

    monkeypatch.setitem(__import__("sys").modules, "openlibrary.plugins.upstream.lenny", Lenny)
    assert provider_loans._fetch_provider_loans("patron") == [make_loan()]
