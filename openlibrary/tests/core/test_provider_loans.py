import time
from types import SimpleNamespace
from typing import Any

import pytest
from pymemcache.test.utils import MockMemcacheClient

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


class FakeMemo:
    """Stands in for the memoized lookup, recording what the page asked of it."""

    timeout = 60

    def __init__(self, cached=None, raises=False):
        self.cached = cached
        self.raises = raises
        self.refreshes: list[str] = []
        self.deletes: list[str] = []
        self.sets: list[tuple] = []
        self.inline_calls = 0

    def __call__(self, username):
        # Calling the memoized function is what blocks on a cache miss.
        self.inline_calls += 1
        return []

    def memcache_get(self, args, kw):
        if self.raises:
            raise RuntimeError("memcache down")
        return self.cached

    def update_async(self, username):
        self.refreshes.append(username)

    def memcache_delete_by_args(self, username):
        self.deletes.append(username)
        self.cached = None

    def memcache_set(self, args, kw, value, t):
        if self.raises:
            raise RuntimeError("memcache down")
        self.sets.append((args, value, t))
        self.cached = (value, t)


@pytest.fixture
def memo(monkeypatch):
    def install(cached=None, raises=False):
        fake = FakeMemo(cached=cached, raises=raises)
        monkeypatch.setattr(provider_loans, "get_cached_provider_loans", fake)
        return fake

    return install


def fresh(loans):
    return (loans, time.time())


def stale(loans):
    return (loans, time.time() - FakeMemo.timeout - 1)


def test_returns_the_loan_the_patron_holds_on_this_edition(memo):
    memo(cached=fresh([make_loan()]))
    loan = provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser())
    assert loan is not None
    assert loan["read_url"] == "https://lenny.example/read/1"


def test_a_loan_on_another_edition_is_not_this_edition_s_loan(memo):
    memo(cached=fresh([make_loan(book="/books/OL999M")]))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None


def test_no_loans_means_no_loan(memo):
    memo(cached=fresh([]))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None


def test_a_cold_cache_never_fetches_inline(memo):
    """The book page must not wait on a provider. A miss answers now and fills later.

    memcache_memoize fetches synchronously on a miss, so calling it directly
    would put the node's full deadline in front of the render.
    """
    fake = memo(cached=None)
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None
    assert fake.inline_calls == 0
    assert fake.refreshes == ["patron"]


def test_a_stale_entry_is_served_while_a_refresh_runs_behind_it(memo):
    fake = memo(cached=stale([make_loan()]))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None
    assert fake.inline_calls == 0
    assert fake.refreshes == ["patron"]


def test_a_fresh_entry_starts_no_refresh(memo):
    fake = memo(cached=fresh([make_loan()]))
    provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser())
    assert fake.refreshes == []


def test_a_broken_cache_reads_as_no_loans(memo):
    fake = memo(raises=True)
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None
    assert fake.inline_calls == 0


def test_invalidation_drops_the_patron_s_entry(memo):
    fake = memo(cached=fresh([make_loan()]))
    provider_loans.invalidate_provider_loans("patron")
    assert fake.deletes == ["patron"]


def test_no_edition_key_is_not_looked_up(memo):
    fake = memo(cached=fresh([make_loan()]))
    assert provider_loans.get_provider_loan(None, user=FakeUser()) is None
    assert provider_loans.get_provider_loan("", user=FakeUser()) is None
    assert fake.refreshes == []


def test_logged_out_patrons_are_not_looked_up(memo, monkeypatch):
    fake = memo(cached=fresh([make_loan()]))
    monkeypatch.setattr("openlibrary.accounts.get_current_user", lambda: None)
    assert provider_loans.get_provider_loan(EDITION_KEY) is None
    assert fake.refreshes == []


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
def test_a_loan_whose_read_url_is_unusable_is_ignored(memo, read_url):
    """Read with nowhere safe to send the patron is worse than Borrow, which works."""
    memo(cached=fresh([make_loan(read_url=read_url)]))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None


def test_a_junk_row_does_not_break_the_page(memo):
    memo(cached=fresh(["not a dict", None, make_loan()]))
    assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None


def test_lookup_failure_reads_as_no_loans(monkeypatch):
    """A node that is slow, broken or unauthorized must cost the book page nothing."""

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


class TestWhatTheBookPageSeesRightAfterABorrow:
    """The page re-renders from the entry written *before* the borrow unless
    the flow tells this cache otherwise."""

    def test_invalidating_alone_still_leaves_the_page_saying_borrow(self, memo):
        """Characterization, green before and after: a cold entry never fetches
        inline, so the render after an invalidation still answers "no loans".
        """
        fake = memo(cached=fresh([]))
        provider_loans.invalidate_provider_loans("patron")
        assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is None
        assert fake.inline_calls == 0

    def test_a_primed_loan_is_on_the_page_at_the_very_next_render(self, memo):
        memo(cached=fresh([]))
        provider_loans.prime_provider_loans("patron", make_loan())
        loan = provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser())
        assert loan is not None
        assert loan["read_url"] == "https://lenny.example/read/1"

    def test_a_primed_entry_is_stale_on_arrival(self, memo):
        """Served now, re-asked behind it: the node is the authority on the
        patron's holdings."""
        fake = memo(cached=fresh([]))
        provider_loans.prime_provider_loans("patron", make_loan())
        assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None
        assert fake.refreshes == ["patron"]

    def test_priming_keeps_the_loans_already_cached(self, memo):
        other = make_loan(book="/books/OL999M", read_url="https://lenny.example/read/999")
        memo(cached=fresh([other]))
        provider_loans.prime_provider_loans("patron", make_loan())
        assert provider_loans.get_provider_loan("/books/OL999M", user=FakeUser()) is not None
        assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None

    def test_borrowing_the_same_edition_twice_leaves_one_loan(self, memo):
        """Lenny's borrow is idempotent, so clicking twice must not leave two
        entries for one edition."""
        fake = memo(cached=fresh([]))
        provider_loans.prime_provider_loans("patron", make_loan(expiry="2026-10-06T12:00:00"))
        provider_loans.prime_provider_loans("patron", make_loan(expiry="2026-11-06T12:00:00"))
        loans, _t = fake.cached
        assert [loan["book"] for loan in loans] == [EDITION_KEY]
        assert loans[0]["expiry"] == "2026-11-06T12:00:00"

    def test_a_cold_cache_is_primed_rather_than_left_empty(self, memo):
        memo(cached=None)
        provider_loans.prime_provider_loans("patron", make_loan())
        assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None

    def test_a_broken_cache_does_not_break_the_borrow(self, memo):
        fake = memo(raises=True)
        provider_loans.prime_provider_loans("patron", make_loan())
        assert fake.sets == []

    def test_a_loan_with_no_usable_read_url_is_not_primed(self, memo):
        """`get_provider_loan` would drop it anyway; writing it would mask the
        patron's real holdings until the background refresh lands."""
        fake = memo(cached=fresh([]))
        provider_loans.prime_provider_loans("patron", make_loan(read_url="javascript:alert(1)"))
        assert fake.sets == []


class TestItSurvivesTheRealCacheAndNotJustTheFake:
    """The class above uses a `FakeMemo` that stores the Python object, so it
    never crosses `memcache_memoize`'s JSON round-trip. These use the shipping
    memoizer so `memcache_set`/`memcache_get` do their real encoding.

    Note a `datetime` would NOT fail here: `helpers.NothingEncoder` coerces any
    `date` to an ISO string, so it round-trips to a `str` silently.
    """

    @pytest.fixture
    def real_cache(self, monkeypatch):
        monkeypatch.setattr(
            provider_loans.get_cached_provider_loans,
            "_memcache",
            MockMemcacheClient(),
        )
        started: list[str] = []
        # A primed entry is stale, so every read below would otherwise spawn a
        # thread that asks a real node.
        monkeypatch.setattr(provider_loans, "_refresh_in_background", started.append)
        return started

    def test_a_primed_loan_comes_back_through_a_real_encode_and_decode(self, real_cache):
        provider_loans.prime_provider_loans("patron", make_loan())
        loan = provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser())
        assert loan is not None
        assert loan["read_url"] == "https://lenny.example/read/1"
        assert loan["book"] == EDITION_KEY

    def test_the_render_that_is_served_the_primed_loan_also_asks_the_node(self, real_cache):
        provider_loans.prime_provider_loans("patron", make_loan())
        assert provider_loans.get_provider_loan(EDITION_KEY, user=FakeUser()) is not None
        assert real_cache == ["patron"]

    def test_the_loan_shape_a_borrow_actually_produces_is_encodable(self, real_cache):
        """Built by `loan_from_node` rather than hand-written, so the fixture
        cannot agree with the code by being written to it."""
        lenny = pytest.importorskip("openlibrary.plugins.upstream.lenny")
        loan = lenny.loan_from_node(
            "lenny",
            "https://lennyforlibraries.org",
            "patron",
            {"status": "borrowed", "edition_id": 37044497, "due_at": "2026-10-06T12:00:00+00:00"},
        )
        provider_loans.prime_provider_loans("patron", loan)
        held = provider_loans.get_provider_loan("/books/OL37044497M", user=FakeUser())
        assert held is not None
        assert held["read_url"] == "https://lennyforlibraries.org/v1/api/items/37044497/read"

    def test_a_borrow_with_no_borrowed_at_still_reaches_the_page(self, real_cache):
        """`borrowed_at` is nullable, so `_epoch`'s substitute must encode."""
        lenny = pytest.importorskip("openlibrary.plugins.upstream.lenny")
        loan = lenny.loan_from_node("lenny", "https://lennyforlibraries.org", "patron", {"edition_id": 37044497})
        provider_loans.prime_provider_loans("patron", loan)
        assert provider_loans.get_provider_loan("/books/OL37044497M", user=FakeUser()) is not None
