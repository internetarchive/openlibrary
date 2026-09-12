from unittest.mock import MagicMock, patch

from openlibrary.plugins.upstream.mybooks import MyBooksTemplate, mybooks_home
from openlibrary.utils.request_context import RequestContextVars, req_context


def test_unified_loans_carousel_merges_active_and_history():
    # Setup req_context to prevent LookupError
    req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False, is_bot=False))

    # Setup mock active loans
    active_loan_book_A = MagicMock()
    active_loan_book_A.key = "/books/OL1M"
    active_work_A = MagicMock()
    active_work_A.key = "/works/OL1W"
    active_loan_book_A.works = [active_work_A]

    active_loan_book_B = MagicMock()
    active_loan_book_B.key = "/books/OL2M"
    active_work_B = MagicMock()
    active_work_B.key = "/works/OL2W"
    active_loan_book_B.works = [active_work_B]

    # Define mock active loans: A (older) and B (newer)
    mock_active_loans = [
        {"book": "/books/OL1M", "loaned_at": 1000.0},
        {"book": "/books/OL2M", "loaned_at": 2000.0},
    ]

    # Setup mock resolved history edition A (re-opened)
    mock_history_book_A = MagicMock()
    mock_history_book_A.key = "/books/OL1M"
    mock_history_book_A.works = [active_work_A]
    mock_history_book_A.get.side_effect = lambda k, default=None: {
        "last_loan_date": "2026-08-07 12:00:00",
        "ia_only": False,
    }.get(k, default)

    # Mock template container
    mock_mb = MagicMock(spec=MyBooksTemplate)
    mock_mb.me = MagicMock()
    mock_mb.me.key = "/people/testuser"
    mock_mb.username = "testuser"  # instance attr not in spec; set explicitly
    mock_mb.user = MagicMock()
    mock_mb.is_public = False
    mock_mb.key = "mybooks"
    mock_mb.counts = {}
    mock_mb.lists = []
    mock_mb.component_times = {}
    mock_mb.is_my_page = True
    mock_mb.current_goal = None

    # Setup readlog mock to prevent AttributeError
    mock_mb.readlog = MagicMock()
    mock_mb.readlog.get_works.return_value = MagicMock(docs=[])

    # Stub site.get().get_many to batch-resolve the active books
    mock_site = MagicMock()
    mock_site.get_many.return_value = [active_loan_book_A, active_loan_book_B]

    mock_site_context = MagicMock()
    mock_site_context.get.return_value = mock_site

    mock_render = MagicMock()

    # Patch the necessary functions
    with (
        patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=mock_active_loans),
        patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data") as mock_history_data,
        patch("openlibrary.plugins.upstream.mybooks.site", mock_site_context),
        patch("openlibrary.plugins.upstream.mybooks.render", mock_render),
    ):
        mock_history_data.return_value = {"docs": [mock_history_book_A]}

        # Execute
        home = mybooks_home()
        home.render_template(mock_mb)

        # Retrieve the docs dictionary passed to render["account/mybooks"](...)
        mock_render_func = mock_render.__getitem__.return_value
        assert mock_render_func.called
        args, _kwargs = mock_render_func.call_args
        docs = args[1]

        loans_carousel = docs["loans"]
        assert loans_carousel is not None

        # Should contain active_loan_book_A and active_loan_book_B
        assert len(loans_carousel.docs) == 2

        # Sort order check:
        # Since active loans are processed first and their timestamps are not overridden by history,
        # they sort by their active loan timestamps: Book B (2000.0) first, Book A (1000.0) second.
        assert loans_carousel.docs[0].key == "/books/OL2M"
        assert loans_carousel.docs[1].key == "/books/OL1M"

        # Both must have their `.loan` attribute attached as they are active loans
        assert loans_carousel.docs[0].loan == {"book": "/books/OL2M", "loaned_at": 2000.0}
        assert loans_carousel.docs[1].loan == {"book": "/books/OL1M", "loaned_at": 1000.0}


def test_active_loan_ranks_above_recently_returned():
    """A currently-borrowed book must appear before a recently-returned one,
    even when the return timestamp is more recent than the active loan's loaned_at."""
    req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False, is_bot=False))

    # Book A: still actively borrowed (loaned_at = old timestamp)
    active_loan_book_A = MagicMock()
    active_loan_book_A.key = "/books/OL1M"
    active_work_A = MagicMock()
    active_work_A.key = "/works/OL1W"
    active_loan_book_A.works = [active_work_A]

    # Book B: returned — present only in history with a very recent updatedate
    returned_book_B = MagicMock()
    returned_book_B.key = "/books/OL2M"
    active_work_B = MagicMock()
    active_work_B.key = "/works/OL2W"
    returned_book_B.works = [active_work_B]
    returned_book_B.get.side_effect = lambda k, default=None: {
        "last_loan_date": "2026-08-07 12:00:00",  # very recent return timestamp
        "ia_only": False,
    }.get(k, default)

    mock_active_loans = [{"book": "/books/OL1M", "loaned_at": 1000.0}]  # only A is active

    mock_mb = MagicMock(spec=MyBooksTemplate)
    mock_mb.me = MagicMock()
    mock_mb.me.key = "/people/testuser"
    mock_mb.username = "testuser"
    mock_mb.user = MagicMock()
    mock_mb.is_public = False
    mock_mb.key = "mybooks"
    mock_mb.counts = {}
    mock_mb.lists = []
    mock_mb.component_times = {}
    mock_mb.is_my_page = True
    mock_mb.current_goal = None
    mock_mb.readlog = MagicMock()
    mock_mb.readlog.get_works.return_value = MagicMock(docs=[])

    mock_site = MagicMock()
    mock_site.get_many.return_value = [active_loan_book_A]

    mock_site_context = MagicMock()
    mock_site_context.get.return_value = mock_site

    mock_render = MagicMock()

    with (
        patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=mock_active_loans),
        patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data") as mock_history_data,
        patch("openlibrary.plugins.upstream.mybooks.site", mock_site_context),
        patch("openlibrary.plugins.upstream.mybooks.render", mock_render),
    ):
        # History contains both A (old date) and B (recently returned)
        mock_history_book_A = MagicMock()
        mock_history_book_A.works = [active_work_A]
        mock_history_book_A.get.side_effect = lambda k, default=None: {
            "last_loan_date": "2024-01-01 00:00:00",
            "ia_only": False,
        }.get(k, default)
        mock_history_data.return_value = {"docs": [mock_history_book_A, returned_book_B]}

        home = mybooks_home()
        home.render_template(mock_mb)

        mock_render_func = mock_render.__getitem__.return_value
        args, _kwargs = mock_render_func.call_args
        loans_carousel = args[1]["loans"]

        assert len(loans_carousel.docs) == 2
        # Active loan A must appear first, returned B second — regardless of B's newer timestamp
        assert loans_carousel.docs[0].key == "/books/OL1M"
        assert loans_carousel.docs[1].key == "/books/OL2M"
        # A must still carry its loan attribute
        assert loans_carousel.docs[0].loan == {"book": "/books/OL1M", "loaned_at": 1000.0}


def _mb_for_viewer(*, is_my_page: bool):
    """A MyBooksTemplate stand-in for a logged-in viewer looking at the profile
    of `someoneelse`."""
    mb = MagicMock(spec=MyBooksTemplate)
    mb.me = MagicMock()
    mb.me.key = "/people/viewer"
    mb.username = "someoneelse"  # instance attr not in spec; set explicitly
    mb.user = MagicMock()
    mb.is_public = True
    mb.key = "mybooks"
    mb.counts = {}
    mb.lists = []
    mb.component_times = {}
    mb.is_my_page = is_my_page
    mb.current_goal = None
    mb.readlog = MagicMock()
    mb.readlog.get_works.return_value = MagicMock(docs=[])
    return mb


def _run_render(mb, mock_history_data):
    mock_site = MagicMock()
    mock_site.get_many.return_value = []
    mock_site_context = MagicMock()
    mock_site_context.get.return_value = mock_site
    with (
        patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=[]),
        patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data", mock_history_data),
        patch("openlibrary.plugins.upstream.mybooks.site", mock_site_context),
        patch("openlibrary.plugins.upstream.mybooks.render", MagicMock()),
    ):
        mybooks_home().render_template(mb)


def test_loan_history_not_fetched_for_another_patrons_profile():
    """/people/<someone-else>/books must not fetch that patron's loan history.

    The carousel is only *rendered* for the owner, but the fetch itself must be
    gated on ownership too: get_loan_history_data() resolves S3 credentials for
    the username it is handed, so calling it with a URL-supplied username lets
    any logged-in visitor drive a borrow-history lookup against another account.
    """
    req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False, is_bot=False))
    mock_history_data = MagicMock(return_value={"docs": []})

    _run_render(_mb_for_viewer(is_my_page=False), mock_history_data)

    mock_history_data.assert_not_called()


def test_loan_history_still_fetched_on_own_profile():
    """The owner's own page must keep fetching history (guards against fixing
    the above by disabling the feature outright)."""
    req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False, is_bot=False))
    mock_history_data = MagicMock(return_value={"docs": []})

    mb = _mb_for_viewer(is_my_page=True)
    mb.username = "viewer"
    _run_render(mb, mock_history_data)

    mock_history_data.assert_called_once()
    assert mock_history_data.call_args.args[0] == "viewer"


def _run_carousel_render(loans, get_many_side_effect, is_my_page=True, history_docs=None):
    """Helper: run mybooks_home.render_template and return the loans carousel docs."""
    req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False, is_bot=False))

    mock_mb = MagicMock(spec=MyBooksTemplate)
    mock_mb.me = MagicMock()
    mock_mb.me.key = "/people/testuser"
    mock_mb.username = "testuser"
    mock_mb.user = MagicMock()
    mock_mb.is_public = False
    mock_mb.key = "mybooks"
    mock_mb.counts = {}
    mock_mb.lists = []
    mock_mb.component_times = {}
    mock_mb.is_my_page = is_my_page
    mock_mb.current_goal = None
    mock_mb.readlog = MagicMock()
    mock_mb.readlog.get_works.return_value = MagicMock(docs=[])

    mock_site = MagicMock()
    mock_site.get_many.side_effect = get_many_side_effect

    mock_site_context = MagicMock()
    mock_site_context.get.return_value = mock_site

    mock_render = MagicMock()
    history_docs = history_docs or []

    with (
        patch("openlibrary.plugins.upstream.mybooks.get_loans_of_user", return_value=loans),
        patch("openlibrary.plugins.upstream.mybooks.get_loan_history_data", return_value={"docs": history_docs}),
        patch("openlibrary.plugins.upstream.mybooks.site", mock_site_context),
        patch("openlibrary.plugins.upstream.mybooks.render", mock_render),
    ):
        mybooks_home().render_template(mock_mb)

    args, _kwargs = mock_render.__getitem__.return_value.call_args
    return args[1]["loans"]


def test_missing_book_keys_skipped():
    """Loan pointing to a nonexistent edition is silently dropped."""
    mock_book = MagicMock()
    mock_book.key = "/books/OL1M"
    mock_book.works = [MagicMock(key="/works/OL1W")]

    loans = [
        {"book": "/books/OL999M", "loaned_at": 100.0},  # missing
        {"book": "/books/OL1M", "loaned_at": 200.0},  # present
    ]

    # First get_many call (initial batch) — only OL1M resolves
    carousel = _run_carousel_render(
        loans,
        get_many_side_effect=lambda keys: [mock_book] if "/books/OL1M" in keys else [],
    )

    assert len(carousel.docs) == 1
    assert carousel.docs[0].key == "/books/OL1M"


def test_duplicate_book_keys_deduplicated():
    """Two loans for the same key produce one get_many call, last loan wins."""
    mock_book = MagicMock()
    mock_book.key = "/books/OL1M"
    mock_book.works = [MagicMock(key="/works/OL1W")]

    loans = [
        {"book": "/books/OL1M", "loaned_at": 100.0},
        {"book": "/books/OL1M", "loaned_at": 200.0},
    ]

    get_many_calls = []

    def track_get_many(keys):
        get_many_calls.append(list(keys))
        return [mock_book]

    carousel = _run_carousel_render(loans, get_many_side_effect=track_get_many)

    # get_many should be called once with the deduplicated key
    assert len(get_many_calls) == 1
    assert get_many_calls[0] == ["/books/OL1M"]

    assert len(carousel.docs) == 1
    # Last loan wins in merged_books
    assert carousel.docs[0].loan == {"book": "/books/OL1M", "loaned_at": 200.0}


def test_redirect_chain_resolved():
    """A loan pointing to a /type/redirect is followed to its final target."""
    redirect_book = MagicMock()
    redirect_book.key = "/books/ia:olc123"
    redirect_book.type.key = "/type/redirect"
    redirect_book.location = "/books/OL2M"

    resolved_book = MagicMock()
    resolved_book.key = "/books/OL2M"
    resolved_book.works = [MagicMock(key="/works/OL2W")]

    loans = [{"book": "/books/ia:olc123", "loaned_at": 500.0}]

    get_many_calls = []

    def track_get_many(keys):
        get_many_calls.append(list(keys))
        if "/books/ia:olc123" in keys:
            return [redirect_book]
        if "/books/OL2M" in keys:
            return [resolved_book]
        return []

    carousel = _run_carousel_render(loans, get_many_side_effect=track_get_many)

    # Two get_many calls: initial batch + redirect hop
    assert len(get_many_calls) == 2
    assert get_many_calls[0] == ["/books/ia:olc123"]
    assert get_many_calls[1] == ["/books/OL2M"]

    assert len(carousel.docs) == 1
    assert carousel.docs[0].key == "/books/OL2M"
    assert carousel.docs[0].loan == {"book": "/books/ia:olc123", "loaned_at": 500.0}


def test_multi_hop_redirect_resolves():
    """Redirect → redirect → real book: up to 5 hops are followed."""
    hop1 = MagicMock()
    hop1.key = "/books/ia:abc"
    hop1.type.key = "/type/redirect"
    hop1.location = "/books/OL10M"

    hop2 = MagicMock()
    hop2.key = "/books/OL10M"
    hop2.type.key = "/type/redirect"
    hop2.location = "/books/OL20M"

    final = MagicMock()
    final.key = "/books/OL20M"
    final.works = [MagicMock(key="/works/OL20W")]

    loans = [{"book": "/books/ia:abc", "loaned_at": 300.0}]

    get_many_calls = []

    def track_get_many(keys):
        get_many_calls.append(list(keys))
        key_set = set(keys)
        results = []
        if "/books/ia:abc" in key_set:
            results.append(hop1)
        if "/books/OL10M" in key_set:
            results.append(hop2)
        if "/books/OL20M" in key_set:
            results.append(final)
        return results

    carousel = _run_carousel_render(loans, get_many_side_effect=track_get_many)

    # Initial + hop1 + hop2 = 3 get_many calls
    assert len(get_many_calls) == 3
    assert carousel.docs[0].key == "/books/OL20M"


def test_redirect_to_nonexistent_target_drops_loan():
    """If a redirect target doesn't exist, the loan is silently dropped."""
    redirect_book = MagicMock()
    redirect_book.key = "/books/ia:olc999"
    redirect_book.type.key = "/type/redirect"
    redirect_book.location = "/books/OL_NOPE"

    loans = [{"book": "/books/ia:olc999", "loaned_at": 100.0}]

    carousel = _run_carousel_render(
        loans,
        # Initial fetch returns the redirect; follow-up returns nothing for the target
        get_many_side_effect=lambda keys: [redirect_book] if "/books/ia:olc999" in keys else [],
    )

    assert len(carousel.docs) == 0


def test_mixed_loans_redirects_and_missing():
    """Mix of normal, redirect, and missing loans all handled in one pass."""
    normal_book = MagicMock()
    normal_book.key = "/books/OL1M"
    normal_book.works = [MagicMock(key="/works/OL1W")]

    redirect_book = MagicMock()
    redirect_book.key = "/books/ia:olc5"
    redirect_book.type.key = "/type/redirect"
    redirect_book.location = "/books/OL2M"

    resolved_book = MagicMock()
    resolved_book.key = "/books/OL2M"
    resolved_book.works = [MagicMock(key="/works/OL2W")]

    loans = [
        {"book": "/books/OL1M", "loaned_at": 100.0},  # normal
        {"book": "/books/OL_MISSING", "loaned_at": 200.0},  # missing
        {"book": "/books/ia:olc5", "loaned_at": 300.0},  # redirect
    ]

    def track_get_many(keys):
        key_set = set(keys)
        # Initial batch (contains all three keys)
        if "/books/OL_MISSING" in key_set:
            return [b for b in [normal_book, redirect_book] if b.key in key_set]
        # Redirect hop (only /books/OL2M)
        if "/books/OL2M" in key_set:
            return [resolved_book]
        return []

    carousel = _run_carousel_render(loans, get_many_side_effect=track_get_many)

    # Missing loan dropped; normal + resolved redirect remain
    assert len(carousel.docs) == 2
    keys_in_carousel = {doc.key for doc in carousel.docs}
    assert keys_in_carousel == {"/books/OL1M", "/books/OL2M"}
