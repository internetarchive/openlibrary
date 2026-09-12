"""
End-to-end integration tests for mybooks_home.render_template.

Exercises the actual production code path with realistic data flows,
mocking only external I/O (DB, IA API, availability) while keeping all
internal logic unmodified.

Run: python -m pytest openlibrary/tests/fastapi/test_mybooks_integration.py -v
"""

from unittest.mock import MagicMock, patch

from openlibrary.plugins.upstream.mybooks import MyBooksTemplate, mybooks_home
from openlibrary.utils.request_context import RequestContextVars, req_context


def _req_context():
    req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
            is_bot=False,
        )
    )


def _make_book(key, work_key=None, *, is_redirect=False, redirect_target=None):
    """Build a mock Thing that behaves like a real OL edition."""
    book = MagicMock()
    book.key = key
    if is_redirect:
        book.type.key = "/type/redirect"
        book.location = redirect_target
    else:
        book.type.key = "/type/edition"
    if work_key:
        wk = MagicMock()
        wk.key = work_key
        book.works = [wk]
    else:
        book.works = []
    return book


def _make_mb(**overrides):
    mb = MagicMock(spec=MyBooksTemplate)
    mb.me = MagicMock()
    mb.me.key = "/people/testuser"
    mb.username = "testuser"
    mb.user = MagicMock()
    mb.is_public = False
    mb.key = "mybooks"
    mb.counts = {}
    mb.lists = []
    mb.component_times = {}
    mb.is_my_page = True
    mb.current_goal = None
    mb.readlog = MagicMock()
    mb.readlog.get_works.return_value = MagicMock(docs=[])
    for k, v in overrides.items():
        setattr(mb, k, v)
    return mb


def _render(loans, get_many_side_effect, *, is_my_page=True, history_docs=None):
    """Run render_template and return the loans carousel docs dict."""
    _req_context()
    mb = _make_mb(is_my_page=is_my_page)

    mock_site = MagicMock()
    mock_site.get_many.side_effect = get_many_side_effect
    mock_site_ctx = MagicMock()
    mock_site_ctx.get.return_value = mock_site
    mock_render = MagicMock()
    history_docs = history_docs or []

    with (
        patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=loans),
        patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data", return_value={"docs": history_docs}),
        patch("openlibrary.plugins.upstream.mybooks.site", mock_site_ctx),
        patch("openlibrary.plugins.upstream.mybooks.render", mock_render),
    ):
        mybooks_home().render_template(mb)

    args, _ = mock_render.__getitem__.return_value.call_args
    return args[1]["loans"]


# =========================================================================
# Basic flows
# =========================================================================
class TestNormalLoans:
    def test_two_active_loans_sorted_by_timestamp(self):
        b1 = _make_book("/books/OL1M", "/works/OL1W")
        b2 = _make_book("/books/OL2M", "/works/OL2W")
        loans = [
            {"book": "/books/OL1M", "loaned_at": 100.0},
            {"book": "/books/OL2M", "loaned_at": 200.0},
        ]
        c = _render(loans, lambda k: [b1, b2])

        assert len(c.docs) == 2
        assert c.docs[0].key == "/books/OL2M"  # newer first
        assert c.docs[1].key == "/books/OL1M"
        assert c.docs[0].loan["loaned_at"] == 200.0
        assert c.docs[1].loan["loaned_at"] == 100.0

    def test_single_get_many_call(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        calls = []
        _render(
            [{"book": "/books/OL1M", "loaned_at": 10.0}],
            lambda k: calls.append(list(k)) or [b],
        )
        assert len(calls) == 1
        assert calls[0] == ["/books/OL1M"]

    def test_no_loans_skips_get_many(self):
        calls = []
        _render([], lambda k: calls.append(k) or [])
        assert calls == []

    def test_missing_loaned_at_defaults_to_zero(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        c = _render([{"book": "/books/OL1M"}], lambda k: [b])
        assert len(c.docs) == 1
        # The raw loan dict is stored as-is; loaned_at defaults to 0.0
        # for sort purposes, but is not injected into the dict.
        assert c.docs[0].loan == {"book": "/books/OL1M"}


# =========================================================================
# Redirect resolution
# =========================================================================
class TestRedirects:
    def test_single_hop_redirect(self):
        redirect = _make_book("/books/ia:olc5", is_redirect=True, redirect_target="/books/OL2M")
        resolved = _make_book("/books/OL2M", "/works/OL2W")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            if "/books/ia:olc5" in keys:
                return [redirect]
            if "/books/OL2M" in keys:
                return [resolved]
            return []

        c = _render([{"book": "/books/ia:olc5", "loaned_at": 500.0}], gm)

        assert len(c.docs) == 1
        assert c.docs[0].key == "/books/OL2M"
        assert c.docs[0].loan["book"] == "/books/ia:olc5"
        assert len(calls) == 2

    def test_two_hop_redirect(self):
        h1 = _make_book("/books/ia:abc", is_redirect=True, redirect_target="/books/OL10M")
        h2 = _make_book("/books/OL10M", is_redirect=True, redirect_target="/books/OL20M")
        final = _make_book("/books/OL20M", "/works/OL20W")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            s = set(keys)
            r = []
            if "/books/ia:abc" in s:
                r.append(h1)
            if "/books/OL10M" in s:
                r.append(h2)
            if "/books/OL20M" in s:
                r.append(final)
            return r

        c = _render([{"book": "/books/ia:abc", "loaned_at": 300.0}], gm)
        assert c.docs[0].key == "/books/OL20M"
        assert len(calls) == 3

    def test_redirect_to_nonexistent_drops_loan(self):
        redirect = _make_book("/books/ia:x", is_redirect=True, redirect_target="/books/OL_NOPE")
        c = _render(
            [{"book": "/books/ia:x", "loaned_at": 10.0}],
            lambda k: [redirect] if "/books/ia:x" in k else [],
        )
        assert len(c.docs) == 0

    def test_missing_redirect_target_fetched_once(self):
        """A redirect to a missing target is fetched once, not once per hop iteration."""
        redirect = _make_book("/books/ia:x", is_redirect=True, redirect_target="/books/OL_NOPE")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            return [r for r in [redirect] if r.key in keys]

        c = _render([{"book": "/books/ia:x", "loaned_at": 1.0}], gm)
        assert len(c.docs) == 0
        assert calls == [["/books/ia:x"], ["/books/OL_NOPE"]]

    def test_redirect_target_already_fetched_reused(self):
        """A redirect pointing to a key already fetched (e.g. another loan's book)
        does not trigger an extra get_many call."""
        redirect = _make_book("/books/ia:r1", is_redirect=True, redirect_target="/books/OL1M")
        direct = _make_book("/books/OL1M", "/works/OL1W")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            s = set(keys)
            r = []
            if "/books/ia:r1" in s:
                r.append(redirect)
            if "/books/OL1M" in s:
                r.append(direct)
            return r

        loans = [
            {"book": "/books/OL1M", "loaned_at": 100.0},
            {"book": "/books/ia:r1", "loaned_at": 200.0},
        ]
        c = _render(loans, gm)
        # Initial batch only; the redirect's target was already fetched.
        assert calls == [["/books/OL1M", "/books/ia:r1"]]
        assert len(c.docs) == 1
        # Both loans resolve to the same work; the last one wins.
        assert c.docs[0].key == "/books/OL1M"
        assert c.docs[0].loan["loaned_at"] == 200.0

    def test_concurrent_redirects_batched_in_one_hop(self):
        """Two loans both redirecting should share a single get_many call per hop."""
        r1 = _make_book("/books/ia:a", is_redirect=True, redirect_target="/books/OL1M")
        r2 = _make_book("/books/ia:b", is_redirect=True, redirect_target="/books/OL2M")
        b1 = _make_book("/books/OL1M", "/works/OL1W")
        b2 = _make_book("/books/OL2M", "/works/OL2W")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            s = set(keys)
            r = []
            if "/books/ia:a" in s:
                r.append(r1)
            if "/books/ia:b" in s:
                r.append(r2)
            if "/books/OL1M" in s:
                r.append(b1)
            if "/books/OL2M" in s:
                r.append(b2)
            return r

        loans = [
            {"book": "/books/ia:a", "loaned_at": 100.0},
            {"book": "/books/ia:b", "loaned_at": 200.0},
        ]
        c = _render(loans, gm)
        assert len(c.docs) == 2
        # Initial batch + one redirect hop = 2 calls (not 4)
        assert len(calls) == 2


# =========================================================================
# Missing / dedup
# =========================================================================
class TestMissingAndDedup:
    def test_missing_book_skipped(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        loans = [
            {"book": "/books/OL_GONE", "loaned_at": 10.0},
            {"book": "/books/OL1M", "loaned_at": 20.0},
        ]
        c = _render(loans, lambda k: [b] if "/books/OL1M" in k else [])
        assert len(c.docs) == 1
        assert c.docs[0].key == "/books/OL1M"

    def test_all_missing(self):
        c = _render(
            [{"book": "/books/OL_A", "loaned_at": 1.0}, {"book": "/books/OL_B", "loaned_at": 2.0}],
            lambda k: [],
        )
        assert len(c.docs) == 0

    def test_duplicate_keys_deduped_in_get_many(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            return [b]

        loans = [
            {"book": "/books/OL1M", "loaned_at": 100.0},
            {"book": "/books/OL1M", "loaned_at": 200.0},
        ]
        c = _render(loans, gm)
        assert calls[0] == ["/books/OL1M"]  # deduped
        assert len(c.docs) == 1
        assert c.docs[0].loan["loaned_at"] == 200.0  # last wins

    def test_loan_book_none_or_empty(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        calls = []

        def gm(keys):
            calls.append(list(keys))
            return [b]

        loans = [
            {"book": None, "loaned_at": 10.0},
            {"book": "", "loaned_at": 20.0},
            {"book": "/books/OL1M", "loaned_at": 30.0},
        ]
        c = _render(loans, gm)
        assert calls[0] == ["/books/OL1M"]  # None/"" filtered out
        assert len(c.docs) == 1


# =========================================================================
# Book with no works
# =========================================================================
class TestNoWorks:
    def test_empty_works_list_uses_book_key(self):
        b = _make_book("/books/OL1M")
        b.works = []
        c = _render([{"book": "/books/OL1M", "loaned_at": 1.0}], lambda k: [b])
        assert len(c.docs) == 1
        assert c.docs[0].key == "/books/OL1M"

    def test_works_none_uses_book_key(self):
        b = MagicMock()
        b.key = "/books/OL1M"
        b.type.key = "/type/edition"
        del b.works  # getattr returns None
        c = _render([{"book": "/books/OL1M", "loaned_at": 1.0}], lambda k: [b])
        assert len(c.docs) == 1


# =========================================================================
# History merge
# =========================================================================
class TestHistoryMerge:
    def test_active_overrides_history_same_work(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        h = MagicMock()
        h.key = "/books/OL2M"
        h.works = [MagicMock(key="/works/OL1W")]
        h.get.side_effect = lambda k, d=None: {"last_loan_date": "2026-08-07", "ia_only": False}.get(k, d)

        c = _render(
            [{"book": "/books/OL1M", "loaned_at": 100.0}],
            lambda k: [b],
            history_docs=[h],
        )
        assert len(c.docs) == 1
        assert c.docs[0].loan["loaned_at"] == 100.0

    def test_history_only_no_active_loans(self):
        h = MagicMock()
        h.key = "/books/OL1M"
        h.works = [MagicMock(key="/works/OL1W")]
        h.get.side_effect = lambda k, d=None: {"last_loan_date": "2026-01-01", "ia_only": False}.get(k, d)

        c = _render([], lambda k: [], history_docs=[h])
        assert len(c.docs) == 1
        assert c.docs[0].key == "/books/OL1M"

    def test_ia_only_history_filtered(self):
        h = MagicMock()
        h.key = "/books/OL1M"
        h.works = [MagicMock(key="/works/OL1W")]
        h.get.side_effect = lambda k, d=None: {"last_loan_date": "2026-01-01", "ia_only": True}.get(k, d)

        c = _render([], lambda k: [], history_docs=[h])
        assert len(c.docs) == 0

    def test_active_before_history_in_sort(self):
        b_active = _make_book("/books/OL1M", "/works/OL1W")
        h = MagicMock()
        h.key = "/books/OL2M"
        h.works = [MagicMock(key="/works/OL2W")]
        h.get.side_effect = lambda k, d=None: {"last_loan_date": "2026-09-01", "ia_only": False}.get(k, d)

        c = _render(
            [{"book": "/books/OL1M", "loaned_at": 1.0}],  # old timestamp
            lambda k: [b_active],
            history_docs=[h],  # recent timestamp
        )
        assert c.docs[0].key == "/books/OL1M"  # active wins despite older timestamp
        assert c.docs[1].key == "/books/OL2M"

    def test_two_loans_same_work_via_different_keys(self):
        b1 = _make_book("/books/OL1M", "/works/OL1W")
        b2 = _make_book("/books/OL2M", "/works/OL1W")  # same work
        c = _render(
            [
                {"book": "/books/OL1M", "loaned_at": 100.0},
                {"book": "/books/OL2M", "loaned_at": 200.0},
            ],
            lambda k: [b1, b2],
        )
        assert len(c.docs) == 1
        assert c.docs[0].loan["loaned_at"] == 200.0


# =========================================================================
# Edge cases
# =========================================================================
class TestEdgeCases:
    def test_history_fetch_failure_nonfatal(self):
        b = _make_book("/books/OL1M", "/works/OL1W")
        _req_context()
        mb = _make_mb(is_my_page=True)
        mock_site = MagicMock()
        mock_site.get_many.return_value = [b]
        mock_site_ctx = MagicMock()
        mock_site_ctx.get.return_value = mock_site
        mock_render = MagicMock()

        with (
            patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=[{"book": "/books/OL1M", "loaned_at": 100.0}]),
            patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data", side_effect=Exception("IA down")),
            patch("openlibrary.plugins.upstream.mybooks.site", mock_site_ctx),
            patch("openlibrary.plugins.upstream.mybooks.render", mock_render),
        ):
            mybooks_home().render_template(mb)

        args, _ = mock_render.__getitem__.return_value.call_args
        docs = args[1]["loans"]
        assert len(docs.docs) == 1
        assert docs.docs[0].key == "/books/OL1M"

    def test_non_owner_history_not_fetched(self):
        _req_context()
        mb = _make_mb(is_my_page=False)
        mock_site = MagicMock()
        mock_site.get_many.return_value = []
        mock_site_ctx = MagicMock()
        mock_site_ctx.get.return_value = mock_site
        mock_render = MagicMock()
        history_fn = MagicMock(return_value={"docs": []})

        with (
            patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=[]),
            patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data", history_fn),
            patch("openlibrary.plugins.upstream.mybooks.site", mock_site_ctx),
            patch("openlibrary.plugins.upstream.mybooks.render", mock_render),
        ):
            mybooks_home().render_template(mb)

        history_fn.assert_not_called()

    def test_mixed_normal_redirect_missing(self):
        """All three types in one pass."""
        b_normal = _make_book("/books/OL1M", "/works/OL1W")
        redirect = _make_book("/books/ia:olc5", is_redirect=True, redirect_target="/books/OL2M")
        resolved = _make_book("/books/OL2M", "/works/OL2W")

        loans = [
            {"book": "/books/OL1M", "loaned_at": 100.0},
            {"book": "/books/OL_GONE", "loaned_at": 150.0},
            {"book": "/books/ia:olc5", "loaned_at": 200.0},
        ]

        def gm(keys):
            s = set(keys)
            r = []
            if "/books/OL1M" in s:
                r.append(b_normal)
            if "/books/ia:olc5" in s:
                r.append(redirect)
            if "/books/OL2M" in s:
                r.append(resolved)
            return r

        c = _render(loans, gm)
        assert len(c.docs) == 2
        keys = {d.key for d in c.docs}
        assert keys == {"/books/OL1M", "/books/OL2M"}
        ol2m = next(d for d in c.docs if d.key == "/books/OL2M")
        assert ol2m.loan["book"] == "/books/ia:olc5"
