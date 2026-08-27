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

    # Stub site.get().get to resolve the active books
    mock_site = MagicMock()
    site_map = {
        "/books/OL1M": active_loan_book_A,
        "/books/OL2M": active_loan_book_B,
    }
    mock_site.get.side_effect = site_map.get

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
    mock_site.get.side_effect = {"/books/OL1M": active_loan_book_A}.get

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
    mock_site.get.side_effect = {}.get
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
