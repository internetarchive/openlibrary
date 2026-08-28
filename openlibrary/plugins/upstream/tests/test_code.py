"""
Tests for the /works and /books page lending/availability preparation
(subtask 5 of openlibrary issue #13419: remove the on-demand ground-truth
availability fetch from the LoanStatus macro).

Covers:
* prepare_book_page() edition selection (direct edition, best-edition,
  ?edition=key:, provider/id selection, merged/redirected work)
* the ground-truth availability fallback (only called when bulk
  availability status == "error", only for the selected edition, and
  only exactly once)
* the resulting lending_state for a few representative ground-truth
  outcomes
* that LoanStatus.html/get_cached_groundtruth_availability are no longer
  reachable from template rendering
* that overriding modes["view"][None] doesn't shadow edit/history/revert/diff
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
import web

from infogami.utils import app as infogami_app
from infogami.utils import delegate, macro, template
from openlibrary.core import db, lending
from openlibrary.core.processors.readableurls import ReadableUrlProcessor, get_readable_path
from openlibrary.plugins.upstream import addbook, code, utils


def make_edition(key, ocaid=None, availability=None, **extra):
    return web.storage(
        key=key,
        ocaid=ocaid,
        availability=availability or {},
        **extra,
    )


def make_work(key, editions, edition_count=None, **extra):
    work = web.storage(
        key=key,
        type=web.storage(key="/type/work"),
        works=[],
        edition_count=edition_count if edition_count is not None else len(editions),
        **extra,
    )
    work.get_sorted_editions = Mock(return_value=editions)
    return work


class TestPrepareBookPageEditionSelection:
    """Section A: correctly identifying the selected edition."""

    @pytest.fixture(autouse=True)
    def _stub_lending_state(self, monkeypatch):
        # These tests are only about edition selection, not lending_state
        # itself (that's covered separately in TestPrepareBookPageLendingState),
        # so keep them isolated from get_lending_state()'s own dependencies
        # (e.g. book_providers.get_book_provider).
        monkeypatch.setattr(lending, "get_lending_state", lambda *a, **kw: "locate")

    def test_direct_edition_page(self):
        """/books/OL2M: the edition is the page itself."""
        ed2 = make_edition("/books/OL2M", ocaid="ia2", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed2])
        page = ed2
        page.works = [work]

        context = code.prepare_book_page(page, {}, user=None)

        assert context.work is work
        assert context.edition is page
        assert context.editions == [ed2]

    def test_work_without_edition_uses_best_edition(self):
        """/works/OL1W with no ?edition=: falls back to get_best_edition()."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open"})
        ed2 = make_edition("/books/OL2M", ocaid="ia2", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed1, ed2])
        work.works = []

        with patch("openlibrary.book_providers.get_best_edition", return_value=(ed2, None)) as mock_best:
            context = code.prepare_book_page(work, {}, user=None)

        mock_best.assert_called_once_with([ed1, ed2])
        assert context.work is work
        assert context.edition is ed2

    def test_explicit_edition_query_param(self):
        """?edition=key:/books/OL9M selects that edition directly."""
        ed9 = make_edition("/books/OL9M", ocaid="ia9", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed9])
        work.works = []

        with patch.object(code.core.db, "get_type", return_value=ed9) as mock_get_type:
            context = code.prepare_book_page(work, {"edition": "key:/books/OL9M"}, user=None)

        mock_get_type.assert_called_once_with("/books/OL9M")
        assert context.edition is ed9

    def test_provider_id_edition_selection(self):
        """?edition=ia:someid selects the matching edition via the provider."""
        ed1 = make_edition("/books/OL1M", ocaid="someid", availability={"status": "open"})
        ed2 = make_edition("/books/OL2M", ocaid="other", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed1, ed2])
        work.works = []

        mock_provider = Mock()
        mock_provider.get_olids.return_value = ["OL1M"]
        mock_provider.get_identifiers.side_effect = lambda e: [e.ocaid]

        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_provider):
            context = code.prepare_book_page(work, {"edition": "ia:someid"}, user=None)

        assert context.edition is ed1

    def test_merged_redirected_work(self):
        """Viewing an old edition revision whose work has since been merged:
        get_document() is called with the redirect's own key (it follows
        redirects internally), not its .location."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open"})
        redirect_work = web.storage(key="/works/OL1W", type=web.storage(key="/type/redirect"), location="/works/OL2W")
        real_work = make_work("/works/OL2W", [ed1])

        page = ed1
        page.works = [redirect_work]

        with patch.object(code, "get_document", return_value=real_work) as mock_get_document:
            context = code.prepare_book_page(page, {}, user=None)

        mock_get_document.assert_called_once_with("/works/OL1W")
        assert context.work is real_work
        assert context.work["title"] == "↪ /works/OL1W"


class TestPrepareBookPageFailurePaths:
    """Section A2: degraded/edge-case inputs must degrade, not raise --
    an exception here would 500 the whole /works or /books page."""

    @pytest.fixture(autouse=True)
    def _stub_lending_state(self, monkeypatch):
        monkeypatch.setattr(lending, "get_lending_state", lambda *a, **kw: "locate")

    def test_orphan_edition_no_work(self):
        """An edition with no `works` reference at all must fall back to
        make_work_from_orphaned_edition() and disable observations, not
        crash on `next(iter(...))` over an empty reference."""
        orphan_work = make_work("", [], edition_count=1)
        ed = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open", "is_readable": True})
        ed.works = []
        ed.make_work_from_orphaned_edition = Mock(return_value=orphan_work)

        context = code.prepare_book_page(ed, {}, user=None)

        ed.make_work_from_orphaned_edition.assert_called_once()
        assert context.work is orphan_work
        assert context.show_observations is False
        assert context.edition is ed

    def test_work_with_no_editions_at_all(self):
        """A work with no catalogued editions must fall back to treating
        the work page itself as `edition`, not crash on an empty list."""
        work = make_work("/works/OL1W", [])
        work.works = []

        context = code.prepare_book_page(work, {}, user=None)

        assert context.editions == []
        assert context.previews == []
        assert context.edition is work
        assert context.work is work

    def test_availability_none_is_treated_as_missing(self):
        """Infobase's unset-property sentinel is falsy but not a dict --
        prepare_book_page() must treat it like an empty availability
        (`not edition.get('availability')`), not choke on a non-dict value."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1")
        ed1.availability = None
        work = make_work("/works/OL1W", [])  # bulk editions unrelated to the selected one
        work.works = []
        page = ed1
        page.works = [work]

        context = code.prepare_book_page(page, {}, user=None)

        assert context.edition.availability == {}

    def test_bulk_error_without_ocaid_skips_groundtruth(self):
        """The ground-truth fallback needs an ocaid to look anything up by;
        a bulk "error" status with no ocaid at all must not attempt the
        call (and must not crash trying)."""
        ed1 = make_edition("/books/OL1M", ocaid=None, availability={"status": "error"})
        work = make_work("/works/OL1W", [ed1])
        work.works = []
        page = ed1
        page.works = [work]

        with patch.object(lending, "get_cached_groundtruth_availability") as mock_gt:
            context = code.prepare_book_page(page, {}, user=None)

        mock_gt.assert_not_called()
        assert context.edition.availability["status"] == "error"

    def test_groundtruth_still_error_after_fallback(self):
        """The ground-truth API can itself report "error" -- applied as-is,
        not silently replaced with another status."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "error"})
        work = make_work("/works/OL1W", [ed1])
        work.works = []
        page = ed1
        page.works = [work]

        with patch.object(lending, "get_cached_groundtruth_availability", return_value={"status": "error"}):
            context = code.prepare_book_page(page, {}, user=None)

        assert context.edition.availability["status"] == "error"

    def test_invalid_provider_name_falls_back_to_best_edition(self):
        """?edition=nonexistentprovider:someid: an unrecognized provider
        must fall back to get_best_edition(), as if no ?edition= were given."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open"})
        ed2 = make_edition("/books/OL2M", ocaid="ia2", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed1, ed2])
        work.works = []

        with (
            patch("openlibrary.book_providers.get_book_provider_by_name", return_value=None),
            patch("openlibrary.book_providers.get_best_edition", return_value=(ed2, None)) as mock_best,
        ):
            context = code.prepare_book_page(work, {"edition": "nonexistentprovider:someid"}, user=None)

        mock_best.assert_called_once_with([ed1, ed2])
        assert context.edition is ed2

    def test_nonexistent_explicit_edition_key_falls_back_to_page(self):
        """?edition=key:/books/OL404M for a nonexistent edition: the page
        itself becomes `edition`, same as the no-edition-selected fallback."""
        work = make_work("/works/OL1W", [])
        work.works = []

        with patch.object(code.core.db, "get_type", return_value=None):
            context = code.prepare_book_page(work, {"edition": "key:/books/OL404M"}, user=None)

        assert context.edition is work


class TestPrepareBookPageAvailabilityFallback:
    """Section B: the ground-truth availability fallback."""

    @pytest.fixture(autouse=True)
    def _stub_lending_state(self, monkeypatch):
        # Isolate these tests from get_lending_state()'s own dependencies;
        # the lending_state value itself is covered in TestPrepareBookPageLendingState.
        monkeypatch.setattr(lending, "get_lending_state", lambda *a, **kw: "locate")

    def test_groundtruth_not_called_when_bulk_status_ok(self):
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open", "is_readable": True})
        work = make_work("/works/OL1W", [ed1])
        work.works = []

        with patch.object(lending, "get_cached_groundtruth_availability") as mock_gt:
            context = code.prepare_book_page(work, {}, user=None)

        mock_gt.assert_not_called()
        assert context.edition.availability["status"] == "open"

    def test_groundtruth_called_exactly_once_for_selected_edition_only(self):
        ed_error = make_edition("/books/OL1M", ocaid="ia-error", availability={"status": "error"})
        ed_ok_1 = make_edition("/books/OL2M", ocaid="ia-ok-1", availability={"status": "open"})
        ed_ok_2 = make_edition("/books/OL3M", ocaid="ia-ok-2", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed_error, ed_ok_1, ed_ok_2])
        work.works = []

        page = ed_error
        page.works = [work]

        with patch.object(lending, "get_cached_groundtruth_availability", return_value={"status": "open", "is_readable": True}) as mock_gt:
            context = code.prepare_book_page(page, {}, user=None)

        mock_gt.assert_called_once_with("ia-error")
        assert context.edition is ed_error
        # the other editions were never individually looked up
        assert ed_ok_1.availability == {"status": "open"}
        assert ed_ok_2.availability == {"status": "open"}

    def test_groundtruth_result_applied_to_final_availability(self):
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "error"})
        work = make_work("/works/OL1W", [ed1])
        work.works = []
        page = ed1
        page.works = [work]

        with patch.object(
            lending,
            "get_cached_groundtruth_availability",
            return_value={"status": "borrowable", "is_lendable": True, "available_to_borrow": True},
        ):
            context = code.prepare_book_page(page, {}, user=None)

        assert context.edition.availability["status"] == "borrowable"
        assert context.edition.availability["is_lendable"] is True

    def test_groundtruth_exception_degrades_instead_of_crashing_the_page(self):
        """The ground-truth call can raise (e.g. a re-raised timeout).
        Nothing upstream of prepare_book_page() catches that, so it must
        degrade to the bulk ("error") availability instead of 500ing the
        whole page."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "error"})
        work = make_work("/works/OL1W", [ed1])
        work.works = []
        page = ed1
        page.works = [work]

        with patch.object(lending, "get_cached_groundtruth_availability", side_effect=TimeoutError("groundtruth timed out")) as mock_gt:
            context = code.prepare_book_page(page, {}, user=None)

        mock_gt.assert_called_once_with("ia1")
        # Availability stays whatever bulk said (still "error") -- not
        # silently replaced with something misleading, and critically, no
        # exception escaped prepare_book_page().
        assert context.edition.availability["status"] == "error"


class TestPrepareBookPageLendingState:
    """Section C: ground truth correctly determines the final lending_state
    (using the real get_lending_state(), not a mock, so this exercises the
    fixed ordering: bulk -> groundtruth fallback -> get_lending_state)."""

    def _user(self):
        user = Mock()
        user.is_printdisabled.return_value = False
        user.get_loan_for.return_value = None
        user.get_user_waiting_loans.return_value = None
        return user

    def _page(self, bulk_status="error"):
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": bulk_status})
        work = make_work("/works/OL1W", [ed1])
        work.works = []
        page = ed1
        page.works = [work]
        return page

    def test_bulk_error_groundtruth_open(self):
        page = self._page()
        mock_provider = Mock(short_name="ia")
        with (
            patch.object(lending, "get_cached_groundtruth_availability", return_value={"status": "open", "is_readable": True}),
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user", return_value=self._user()),
        ):
            context = code.prepare_book_page(page, {}, user=self._user())

        assert context.lending_state == "open"

    def test_bulk_error_groundtruth_borrowable(self):
        page = self._page()
        mock_provider = Mock(short_name="ia")
        with (
            patch.object(
                lending,
                "get_cached_groundtruth_availability",
                return_value={"status": "borrowable", "is_lendable": True, "available_to_borrow": True},
            ),
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user", return_value=self._user()),
        ):
            context = code.prepare_book_page(page, {}, user=self._user())

        assert context.lending_state == "borrowable"

    def test_bulk_error_groundtruth_waitlist(self):
        page = self._page()
        mock_provider = Mock(short_name="ia")
        with (
            patch.object(
                lending,
                "get_cached_groundtruth_availability",
                return_value={"status": "waitlist", "is_lendable": True, "available_to_waitlist": True},
            ),
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user", return_value=self._user()),
        ):
            context = code.prepare_book_page(page, {}, user=self._user())

        assert context.lending_state == "waitlist"

    def test_bulk_ok_lending_state_matches_bulk(self):
        """Sanity check: when bulk isn't an error, lending_state is derived
        straight from it (no groundtruth call needed)."""
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open", "is_readable": True})
        work = make_work("/works/OL1W", [ed1])
        work.works = []
        page = ed1
        page.works = [work]

        mock_provider = Mock(short_name="ia")
        with (
            patch.object(lending, "get_cached_groundtruth_availability") as mock_gt,
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user", return_value=self._user()),
        ):
            context = code.prepare_book_page(page, {}, user=self._user())

        mock_gt.assert_not_called()
        assert context.lending_state == "open"

    def test_supplied_user_is_passed_to_get_lending_state(self):
        """The request user must be reused; get_lending_state must not be left
        to re-resolve the current user on its own."""
        page = self._page(bulk_status="open")
        page.availability = {"status": "open", "is_readable": True}
        user = self._user()

        with patch.object(lending, "get_lending_state", return_value="open") as mock_gls:
            code.prepare_book_page(page, {}, user=user)

        mock_gls.assert_called_once()
        assert mock_gls.call_args.kwargs["user"] is user
        assert mock_gls.call_args.kwargs["check_loan_status"] is True

    def test_logged_out_passes_user_none_without_loan_check(self):
        page = self._page(bulk_status="open")
        page.availability = {"status": "open", "is_readable": True}

        with patch.object(lending, "get_lending_state", return_value="open") as mock_gls:
            code.prepare_book_page(page, {}, user=None)

        mock_gls.assert_called_once()
        assert mock_gls.call_args.kwargs["user"] is None
        assert mock_gls.call_args.kwargs["check_loan_status"] is False

    def test_active_loan_returns_borrowed(self):
        page = self._page(
            bulk_status="borrowable",
        )
        # Non-error bulk availability so we exercise the user-loan path, not groundtruth.
        page.availability = {
            "status": "borrow_available",
            "is_lendable": True,
            "available_to_borrow": True,
        }
        user = self._user()
        user.get_loan_for.return_value = {"expiry": "2030-01-01", "resource_type": "bookreader"}
        mock_provider = Mock(short_name="ia")

        with (
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user") as mock_get_user,
        ):
            context = code.prepare_book_page(page, {}, user=user)

        mock_get_user.assert_not_called()
        assert context.lending_state == "borrowed"

    def test_printdisabled_user_returns_printdisabled(self):
        page = self._page(bulk_status="error")
        user = self._user()
        user.is_printdisabled.return_value = True
        mock_provider = Mock(short_name="ia")

        with (
            patch.object(
                lending,
                "get_cached_groundtruth_availability",
                return_value={"status": "borrowable", "is_lendable": True, "available_to_borrow": True},
            ),
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user") as mock_get_user,
        ):
            context = code.prepare_book_page(page, {}, user=user)

        mock_get_user.assert_not_called()
        assert context.lending_state == "printdisabled"

    def test_preview_only_and_locate_from_availability(self):
        mock_provider = Mock(short_name="ia")

        preview_page = self._page(bulk_status="error")
        with (
            patch.object(
                lending,
                "get_cached_groundtruth_availability",
                return_value={"status": "private", "is_previewable": True},
            ),
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user", return_value=self._user()),
        ):
            preview_ctx = code.prepare_book_page(preview_page, {}, user=self._user())
        assert preview_ctx.lending_state == "preview_only"

        locate_page = self._page(bulk_status="error")
        with (
            patch.object(
                lending,
                "get_cached_groundtruth_availability",
                return_value={"status": "error"},
            ),
            patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider),
            patch("openlibrary.accounts.get_current_user", return_value=None),
        ):
            locate_ctx = code.prepare_book_page(locate_page, {}, user=None)
        assert locate_ctx.lending_state == "locate"


class TestLoanStatusNoLongerDoesNetworkIO:
    """Section D: no template can reach the ground-truth availability fetch anymore."""

    def test_loan_status_template_has_no_groundtruth_call(self):
        with open("openlibrary/macros/LoanStatus.html") as f:
            source = f.read()
        assert "get_cached_groundtruth_availability" not in source
        assert "allow_expensive_availability_check" not in source

    def test_databar_work_template_has_no_expensive_check(self):
        with open("openlibrary/macros/databarWork.html") as f:
            source = f.read()
        assert "get_cached_groundtruth_availability" not in source
        assert "allow_expensive_availability_check" not in source
        assert "expensive_check" not in source

    def test_get_cached_groundtruth_availability_not_public(self):
        # @public registers the function in web.template.Template.globals;
        # it must no longer be there since no template calls it.
        assert "get_cached_groundtruth_availability" not in web.template.Template.globals

    def test_get_cached_groundtruth_availability_still_importable(self):
        # Still a normal, cached, importable Python function -- just not
        # exposed to Templetor anymore.
        assert callable(lending.get_cached_groundtruth_availability)


class TestViewModeRoutingIsolation:
    """Section E: overriding modes["view"][None] must not shadow other
    modes/encodings (edit, history, revert, diff, and other view encodings)."""

    def test_view_html_mode_is_overridden(self):
        from infogami.utils.app import modes

        assert modes["view"][None] is code.view

    def test_edit_mode_untouched(self):
        from infogami.utils.app import modes

        assert modes["edit"][None] is code.edit

    def test_history_mode_untouched(self):
        from infogami.utils.app import modes
        from openlibrary.plugins.upstream import recentchanges

        # modes["history"][None] (HTML) belongs to recentchanges.history;
        # code.history only overrides the "json" encoding. Neither is our view class.
        assert modes["history"][None] is recentchanges.history
        assert modes["history"]["json"] is code.history

    def test_revert_mode_untouched(self):
        from infogami.utils.app import modes

        assert modes["revert"][None] is code.revert

    def test_diff_mode_untouched(self):
        from infogami.utils.app import modes

        assert modes["diff"][None] is code.core.diff

    def _mock_web_input(self, monkeypatch):
        # web.input() needs a real WSGI request env, which doesn't exist in
        # a bare unit test. Stand in for it: fill in whatever defaults were
        # requested, exactly like a request with no matching query params.
        monkeypatch.setattr(web, "input", lambda *a, **kw: web.storage(**kw))

    def test_view_class_skips_get_version_for_non_book_work_path(self, monkeypatch):
        """A path outside /works/ and /books/ delegates to core.view.GET
        immediately, without a redundant get_version() Thing load first."""
        self._mock_web_input(monkeypatch)
        with (
            patch.object(code.core.db, "get_version") as mock_get_version,
            patch.object(code.core.view, "GET", return_value="core-view-response") as mock_core_get,
        ):
            result = code.view().GET("/authors/OL1A")

        mock_get_version.assert_not_called()
        mock_core_get.assert_called_once()
        assert mock_core_get.call_args[0][1] == "/authors/OL1A"
        assert result == "core-view-response"

    def test_view_class_falls_back_to_core_for_non_work_edition_type(self, monkeypatch):
        """A /works/ or /books/ path resolving to a non-work/edition Thing
        (e.g. deleted) still falls back to core.view.GET, but only after
        get_version() -- it needs the Thing to know that."""
        self._mock_web_input(monkeypatch)
        deleted_page = web.storage(key="/works/OL1W", type=web.storage(key="/type/delete"))
        with (
            patch.object(code.core.db, "get_version", return_value=deleted_page) as mock_get_version,
            patch.object(code.core.view, "GET", return_value="core-view-response") as mock_core_get,
        ):
            result = code.view().GET("/works/OL1W")

        mock_get_version.assert_called_once()
        mock_core_get.assert_called_once()
        assert result == "core-view-response"

    def test_view_class_prepares_book_page_context_for_work(self, monkeypatch):
        self._mock_web_input(monkeypatch)
        work_page = web.storage(key="/works/OL1W", type=web.storage(key="/type/work"))
        fake_context = object()
        fake_user = Mock(name="context.user")
        mock_render = Mock(return_value="rendered")
        # No web.ctx.site mock here at all: view.GET() must use context.user
        # (already resolved once per request by initialize_context()) rather
        # than calling web.ctx.site.get_user() itself, which is not memoized
        # and would be a second, redundant Infobase round-trip.
        monkeypatch.setattr(code.context, "user", fake_user, raising=False)
        with (
            patch.object(code.core.db, "get_version", return_value=work_page),
            patch.object(code, "prepare_book_page", return_value=fake_context) as mock_prepare,
        ):
            # render.viewpage is resolved dynamically (disk template lookup),
            # so it isn't a real static attribute to patch.object() onto.
            monkeypatch.setattr(code.render, "viewpage", mock_render, raising=False)
            code.view().GET("/works/OL1W")

        mock_prepare.assert_called_once()
        assert mock_prepare.call_args[0][0] is work_page
        assert mock_prepare.call_args[0][2] is fake_user
        mock_render.assert_called_once_with(work_page, fake_context)

    def test_view_class_does_not_call_get_user_itself(self, monkeypatch):
        """Regression test: view.GET() must not call web.ctx.site.get_user()
        (an uncached Infobase round-trip) -- it must reuse context.user,
        which initialize_context() already resolved once for this request."""
        self._mock_web_input(monkeypatch)
        work_page = web.storage(key="/works/OL1W", type=web.storage(key="/type/work"))
        mock_site = Mock()
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)
        monkeypatch.setattr(code.context, "user", None, raising=False)
        monkeypatch.setattr(code.render, "viewpage", Mock(return_value="rendered"), raising=False)
        with (
            patch.object(code.core.db, "get_version", return_value=work_page),
            patch.object(code, "prepare_book_page", return_value=object()),
        ):
            code.view().GET("/works/OL1W")

        mock_site.get_user.assert_not_called()


class TestNonHtmlModesNeverUsePreparation:
    """Section F: non-HTML encodings (json, rdf, and by the same code
    structure opds/marcxml/yml) have their own delegate.mode classes and
    never reference prepare_book_page(). Unlike TestViewModeRoutingIsolation
    above, these actually invoke GET() and prove it by call-count."""

    def test_rdf_view_never_calls_prepare_book_page(self, monkeypatch):
        """.rdf goes through openlibrary.plugins.openlibrary.code.rdf, a
        separate class that renders via typetemplate("rdf") directly."""
        from openlibrary.plugins.openlibrary import code as ol_code

        work_page = web.storage(key="/works/OL1W", type=web.storage(key="/type/work"))
        mock_site = Mock()
        mock_site.get = Mock(return_value=work_page)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        with (
            patch.object(code, "prepare_book_page") as mock_prepare,
            patch("infogami.utils.template.typetemplate", return_value=lambda page: "<rdf>ok</rdf>") as mock_typetemplate,
        ):
            result = ol_code.rdf().GET("/works/OL1W")

        mock_prepare.assert_not_called()
        mock_typetemplate.assert_called_once_with("rdf")
        assert "<rdf>ok</rdf>" in str(result)

    def test_json_view_never_calls_prepare_book_page(self, monkeypatch):
        """.json goes through infogami.plugins.api.code.view -- a raw
        Infobase '/get' with no template rendering at all."""
        from infogami.plugins.api import code as api_code

        monkeypatch.setattr(web, "input", lambda *a, **kw: web.storage(**kw))

        with (
            patch.object(code, "prepare_book_page") as mock_prepare,
            patch.object(api_code, "request", return_value='{"key": "/works/OL1W"}') as mock_request,
        ):
            result = api_code.view().GET("/works/OL1W")

        mock_prepare.assert_not_called()
        mock_request.assert_called_once()
        assert result.rawtext == '{"key": "/works/OL1W"}'


class TestEditModeRouting:
    """?m=edit routing for books/works, matching upstream/master.

    Real /books/OL...M and /works/OL...W keys are redirected to addbook's
    dedicated /edit pages. Everything else -- including fake records like
    /books/ia:foo00bar -- falls through to Infogami's core.edit.GET(),
    which never calls thingview()/type/edition/view.html (that only happens
    from POST action=preview; see TestGenericEditPreviewRouting).
    """

    def test_ia_fake_record_edit_delegates_to_core_edit(self, monkeypatch):
        """Fake records do not match editable_keys_re (no OL id) and are
        not special-cased: GET ?m=edit keeps the pre-existing fallthrough
        to core.edit.GET(). The UI already hides the Edit button for these
        (databarView.html, databarWork.html, type/edition/view.html)."""
        fake_record = web.storage(key="/books/ia:foo00bar", type=web.storage(key="/type/edition"))
        fake_record.is_fake_record = Mock(return_value=True)
        mock_site = Mock()
        mock_site.get = Mock(return_value=fake_record)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        with patch.object(code.core.edit, "GET", return_value="core-edit-response") as mock_core_get:
            result = code.edit().GET("/books/ia:foo00bar")

        mock_core_get.assert_called_once()
        assert mock_core_get.call_args[0][1] == "/books/ia:foo00bar"
        assert result == "core-edit-response"

    def test_nonexistent_books_path_still_takes_pre_existing_none_branch(self, monkeypatch):
        """Sanity check: a real (but not-yet-created) /books/OL...M key
        matches editable_keys_re and must still take the pre-existing
        `page is None` branch above the fake-record branch, unchanged."""
        mock_site = Mock()
        mock_site.get = Mock(return_value=None)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)
        monkeypatch.setattr(code.web, "seeother", lambda url: f"seeother:{url}")

        with patch.object(code.core.edit, "GET") as mock_core_get:
            result = code.edit().GET("/books/OL999999M")

        mock_core_get.assert_not_called()
        assert result == "seeother:/books/OL999999M"

    def test_real_edition_key_still_uses_addbook_edit_flow(self, monkeypatch):
        """Sanity check: a real, existing /books/OL...M key is unaffected --
        still redirected to addbook's own edit UI, not the fake-record
        branch."""
        real_edition = Mock()
        real_edition.url = Mock(return_value="/books/OL1M/edit")
        mock_site = Mock()
        mock_site.get = Mock(return_value=real_edition)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        with patch.object(code.addbook, "safe_seeother", return_value="redirected") as mock_redirect:
            result = code.edit().GET("/books/OL1M")

        mock_redirect.assert_called_once_with("/books/OL1M/edit")
        assert result == "redirected"

    def test_non_fake_record_books_key_delegates_to_core_edit(self, monkeypatch):
        """A /books/ key that isn't OL-formatted and isn't a fake record
        (page.is_fake_record() is False, e.g. an ordinary garbage/malformed
        path) must keep delegating to core.edit.GET() -- the pre-existing,
        upstream behaviour -- not be swept into the fake-record redirect."""
        not_fake = web.storage(key="/books/some-garbage-key", type=web.storage(key="/type/edition"))
        not_fake.is_fake_record = Mock(return_value=False)
        mock_site = Mock()
        mock_site.get = Mock(return_value=not_fake)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        with patch.object(code.core.edit, "GET", return_value="core-edit-response") as mock_core_get:
            result = code.edit().GET("/books/some-garbage-key")

        mock_core_get.assert_called_once()
        assert result == "core-edit-response"

    def test_works_key_has_no_is_fake_record_and_delegates_to_core_edit(self, monkeypatch):
        """/works/ pages have no fake-record concept (is_fake_record() is
        only defined on Edition); a non-OL /works/ key must not raise
        AttributeError and must keep delegating to core.edit.GET()."""
        work_page = web.storage(key="/works/not-an-olid", type=web.storage(key="/type/work"))
        mock_site = Mock()
        mock_site.get = Mock(return_value=work_page)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        with patch.object(code.core.edit, "GET", return_value="core-edit-response") as mock_core_get:
            result = code.edit().GET("/works/not-an-olid")

        mock_core_get.assert_called_once()
        assert result == "core-edit-response"

    def test_non_book_work_path_untouched(self, monkeypatch):
        """An unrelated wiki path still falls through to core.edit.GET()."""
        mock_site = Mock()
        mock_site.get = Mock(return_value=None)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        with patch.object(code.core.edit, "GET", return_value="core-edit-response") as mock_core_get:
            result = code.edit().GET("/some/wiki/page")

        mock_core_get.assert_called_once()
        assert result == "core-edit-response"


class TestIntegratedBookPageRendering:
    """Section G: a real, end-to-end render of the /works and /books HTML
    view -- view.GET() -> prepare_book_page() -> viewpage.html ->
    type/edition/view.html -> databarWork -> LoanStatus -- with Templetor
    actually rendering every template in the chain. Only genuinely external
    dependencies are stubbed: bulk and ground-truth availability (real
    outbound HTTP calls in production, and blocked anyway by the autouse
    `no_requests` fixture, openlibrary/conftest.py).
    """

    def _load_fake_request(self, path, site, monkeypatch):
        """Load a real (fake-environ) web.py request so web.ctx and
        web.input() behave like a real GET, then patch the handful of
        infrastructure gaps a bare mock_site doesn't cover, so the rest of
        the page renders instead of crashing on unrelated sections."""
        # render_template's own setup re-registers /type/work with the base
        # Work class, clobbering mock_site's upstream Work subclass that
        # prepare_book_page() needs (get_sorted_editions() etc).
        from openlibrary.plugins.upstream import models as upstream_models

        upstream_models.setup()

        app = web.application()
        app.load({"PATH_INFO": path, "REQUEST_METHOD": "GET", "HTTP_HOST": "openlibrary.org"})
        web.ctx.site = site
        web.ctx.lang = "en"  # app.load() wipes ctx.lang; databarView's datestr() needs it

        # render_download_options() hits archive.org over httpx, which the
        # no_requests autouse fixture doesn't cover (it only patches `requests`).
        monkeypatch.setattr("openlibrary.core.ia.get_api_response", lambda *a, **kw: {})

        # get_identifier_config() reads a /config/edition Thing only present
        # on a fully-seeded site; cached process-wide, so seed it once.
        if site.get("/config/edition") is None:
            site.quicksave("/config/edition", "/type/object", classifications=[], roles=[])

        # `ctx` (infogami's request-scoped template globals) is normally
        # populated by the initialize_context() loadhook, which this fake
        # request never runs.
        monkeypatch.setattr(delegate, "create_site", lambda: site)
        delegate.initialize_context()

        # render_template loads templates but not macros; `request` is a
        # separate template global that utils.setup() normally registers.
        macro.load_macros("openlibrary", lazy=True)
        web.template.Template.globals["request"] = utils.Request()

        # Unrelated Postgres-backed stats sections (ratings, "want to read"
        # counts, ...) should degrade to zero rows, not crash.
        class _ZeroRow(dict):
            def __missing__(self, key):
                return 0

        fake_db = Mock()
        fake_db.query = Mock(return_value=[_ZeroRow()])
        fake_db.select = Mock(return_value=[_ZeroRow()])
        monkeypatch.setattr(db, "get_db", lambda: fake_db)

        # MockSite.versions() always returns []; give it one so databarView's
        # "last edited" section renders instead of crashing.
        def fake_versions(q):
            return [web.storage(key=q.get("key"), revision=1, author=None, created=datetime.now())]

        monkeypatch.setattr(site, "versions", fake_versions)

    def test_work_page_renders_open_lending_state_after_groundtruth_fallback(self, monkeypatch, mock_site, render_template, request_context_fixture):
        """bulk availability errors, ground-truth returns "open": the real
        Templetor render must show data-lending-state="open" and an
        open-access CTA, with ground-truth called exactly once and
        get_lending_state() computed exactly once (LoanStatus must not
        recompute it)."""
        request_context_fixture(lang="en")
        mock_site.quicksave("/works/OL1W", "/type/work", title="Integration Test Work", edition_count=1)
        mock_site.quicksave(
            "/books/OL1M",
            "/type/edition",
            title="Integration Test Edition",
            works=[{"key": "/works/OL1W"}],
            ocaid="integrationtest001",
        )
        # get_sorted_editions() falls back to {"status": "error"} per edition
        # when bulk availability comes back empty, as it does here.
        monkeypatch.setattr(lending, "get_availability", lambda *a, **kw: {})

        groundtruth_calls = []

        def fake_groundtruth(ocaid):
            groundtruth_calls.append(ocaid)
            return {"status": "open", "identifier": ocaid, "is_readable": True}

        monkeypatch.setattr(lending, "get_cached_groundtruth_availability", fake_groundtruth)

        lending_state_calls = []
        real_get_lending_state = lending.get_lending_state

        def spy_get_lending_state(*a, **kw):
            lending_state_calls.append((a, kw))
            return real_get_lending_state(*a, **kw)

        monkeypatch.setattr(lending, "get_lending_state", spy_get_lending_state)

        self._load_fake_request("/works/OL1W", mock_site, monkeypatch)
        monkeypatch.setattr(code.context, "user", None, raising=False)

        html = str(code.view().GET("/works/OL1W"))

        assert groundtruth_calls == ["integrationtest001"]
        # LoanStatus must receive lending_state already resolved, not recompute it.
        assert len(lending_state_calls) == 1
        assert 'data-lending-state="open"' in html
        # A coherent CTA for "open" -- not leftover Locate/waitlist markup.
        assert "waitinglist-form" not in html
        assert "LocateButton" not in html

    def test_edition_page_renders_via_real_templates(self, monkeypatch, mock_site, render_template, request_context_fixture):
        """/books/OL...M direct-edition path, bulk availability already
        "open" (no ground-truth fallback needed)."""
        request_context_fixture(lang="en")
        mock_site.quicksave("/works/OL2W", "/type/work", title="Second Integration Work", edition_count=1)
        mock_site.quicksave(
            "/books/OL2M",
            "/type/edition",
            title="Second Integration Edition",
            works=[{"key": "/works/OL2W"}],
            ocaid="integrationtest002",
        )

        monkeypatch.setattr(
            lending,
            "get_availability",
            lambda kind, ids: {i: {"status": "open", "identifier": i, "is_readable": True} for i in ids},
        )

        groundtruth_calls = []
        monkeypatch.setattr(
            lending,
            "get_cached_groundtruth_availability",
            lambda ocaid: groundtruth_calls.append(ocaid) or {},
        )

        self._load_fake_request("/books/OL2M", mock_site, monkeypatch)
        monkeypatch.setattr(code.context, "user", None, raising=False)

        html = str(code.view().GET("/books/OL2M"))

        # Bulk availability already said "open" -- the ground-truth fallback
        # must not run at all (it's only for a bulk status == "error").
        assert groundtruth_calls == []
        assert 'data-lending-state="open"' in html

    def test_signature_mismatch_would_surface_as_a_real_render_error(self, monkeypatch, mock_site, render_template, request_context_fixture):
        """Negative control: proves the positive tests above are exercising
        real Templetor argument binding, not silently swallowing errors --
        rendering type/edition/view.html with no book_page_context at all
        must fail visibly, not produce a page missing lending-state markup."""
        request_context_fixture(lang="en")
        mock_site.quicksave("/works/OL3W", "/type/work", title="Third Integration Work", edition_count=1)
        edition = mock_site.quicksave(
            "/books/OL3M",
            "/type/edition",
            title="Third Integration Edition",
            works=[{"key": "/works/OL3W"}],
            ocaid="integrationtest003",
        )
        monkeypatch.setattr(lending, "get_availability", lambda *a, **kw: {})
        monkeypatch.setattr(lending, "get_cached_groundtruth_availability", lambda ocaid: {"status": "open", "identifier": ocaid})
        self._load_fake_request("/works/OL3W", mock_site, monkeypatch)
        monkeypatch.setattr(code.context, "user", None, raising=False)

        # Sanity check first: the real signature renders fine.
        assert 'data-lending-state="open"' in str(code.view().GET("/works/OL3W"))

        # Now render type/edition/view directly with no book_page_context,
        # the way a leftover thingview() caller would. saferender() catches
        # the resulting AttributeError itself (so this can't assert
        # pytest.raises()); disable the error-logging hook, which is
        # unrelated infrastructure this test doesn't depend on.
        monkeypatch.setattr(delegate, "exception_hooks", [])
        html = str(code.render.viewpage(edition))
        assert "data-lending-state" not in html
        assert "Unable to render this page" in html


class TestGenericEditPreviewRouting:
    """Prove whether Infogami's generic edit POST+preview can reach
    type/edition/view.html without BookPageContext.

    Infogami delegate order is find_page() -> find_view() -> find_mode().
    Dedicated book/work editors are delegate.page handlers on the /edit
    suffix; ?m=edit is a mode, used only when no page handler matches.
    """

    def _load_request(self, path, query="", method="GET"):
        app = web.application()
        app.load(
            {
                "PATH_INFO": path,
                "REQUEST_METHOD": method,
                "QUERY_STRING": query.lstrip("?"),
                "HTTP_HOST": "openlibrary.org",
            }
        )
        web.ctx.path = path
        web.ctx.encoding = None

    def test_dedicated_edit_pages_win_over_edit_mode_for_real_ol_keys(self):
        self._load_request("/books/OL1M/edit")
        cls, args = infogami_app.find_page()
        assert cls is addbook.book_edit
        assert args == ("/books/OL1M",)

        self._load_request("/works/OL1W/edit")
        cls, args = infogami_app.find_page()
        assert cls is addbook.work_edit
        assert args == ("/works/OL1W",)

    def test_bare_book_and_work_keys_do_not_match_a_page_handler(self):
        self._load_request("/books/OL1M")
        cls, _ = infogami_app.find_page()
        assert cls is None

        self._load_request("/works/OL1W")
        cls, _ = infogami_app.find_page()
        assert cls is None

    def test_fake_record_keys_do_not_match_book_edit_page(self):
        self._load_request("/books/ia:foo00bar")
        cls, _ = infogami_app.find_page()
        assert cls is None

        self._load_request("/books/ia:foo00bar/edit")
        cls, _ = infogami_app.find_page()
        assert cls is None

    def test_m_edit_mode_is_the_openlibrary_override(self):
        self._load_request("/books/OL1M", query="m=edit")
        cls, args = infogami_app.find_mode()
        assert cls is code.edit
        assert args == ["/books/OL1M"]

        self._load_request("/books/ia:foo00bar", query="m=edit")
        cls, args = infogami_app.find_mode()
        assert cls is code.edit
        assert args == ["/books/ia:foo00bar"]

    def test_ia_edit_suffix_is_a_readable_title_not_an_edit_handler(self, mock_site):
        """ReadableUrlProcessor treats /books/ia:.../edit as a title slug.
        The path is rewritten to /books/ia:... (view), so fake records can
        never reach addbook.book_edit via a /edit suffix."""
        mock_site.quicksave("/books/ia:foo00bar", "/type/edition", title="Some Title")
        real_path, _ = get_readable_path(
            mock_site,
            "/books/ia:foo00bar/edit",
            ReadableUrlProcessor.patterns,
        )
        assert real_path == "/books/ia:foo00bar"
        assert not real_path.endswith("/edit")

    def test_dedicated_book_edit_form_has_no_infogami_preview_button(self):
        with open("openlibrary/templates/books/edit.html") as f:
            book_edit_src = f.read()
        with open("openlibrary/macros/EditButtons.html") as f:
            buttons_src = f.read()
        assert "_preview" not in book_edit_src
        assert "_preview" not in buttons_src
        assert 'name="_save"' in buttons_src

    def test_edit_post_always_delegates_to_core_edit_for_books(self):
        """OL's edit.POST() only special-cases /people/ spam; books, works,
        and fake records all fall through to core.edit.POST(). That leftover
        Infogami endpoint is not what the production edit UI posts to
        (see dedicated /edit page handlers above)."""
        with patch.object(code.core.edit, "POST", return_value="core-post") as mock_post:
            assert code.edit().POST("/books/OL1M") == "core-post"
            assert code.edit().POST("/works/OL1W") == "core-post"
            assert code.edit().POST("/books/ia:foo00bar") == "core-post"
        assert mock_post.call_count == 3

    def test_core_edit_get_renders_editpage_without_preview(self, monkeypatch):
        page = web.storage(key="/books/ia:foo00bar", type=web.storage(key="/type/edition"))
        mock_site = Mock()
        mock_site.can_write = Mock(return_value=True)
        mock_site.get = Mock(return_value=page)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)
        monkeypatch.setattr(web, "input", lambda *a, **kw: web.storage(v=None, t=None))

        mock_editpage = Mock(return_value="edit-form")
        monkeypatch.setattr(code.core.render, "editpage", mock_editpage, raising=False)
        with patch.object(code.core.db, "get_version", return_value=page):
            result = code.core.edit().GET("/books/ia:foo00bar")

        mock_editpage.assert_called_once_with(page)
        assert result == "edit-form"

    def test_core_edit_post_preview_renders_editpage_with_preview_true(self, monkeypatch):
        page = MagicMock()
        mock_site = Mock()
        mock_site.get = Mock(return_value=page)
        monkeypatch.setattr(web.ctx, "site", mock_site, raising=False)

        posted = web.storage(_preview="Preview")
        monkeypatch.setattr(web, "input", lambda _method=None, **kw: posted if _method == "post" else web.storage())

        mock_editpage = Mock(return_value="previewed")
        monkeypatch.setattr(code.core.render, "editpage", mock_editpage, raising=False)
        with patch.object(code.core.helpers, "unflatten", side_effect=lambda i: i):
            result = code.core.edit().POST("/books/ia:foo00bar")

        mock_editpage.assert_called_once()
        assert mock_editpage.call_args[0][0] is page
        assert mock_editpage.call_args[1].get("preview") is True or mock_editpage.call_args[0][1] is True
        assert result == "previewed"

    def test_editpage_preview_of_edition_hits_thingview_without_book_page_context(self, monkeypatch, mock_site, render_template, request_context_fixture):
        """If anyone did reach render.editpage(edition, preview=True), OL's
        editpage.html calls thingview(page), which cannot render
        type/edition/view.html on this branch (no book_page_context).

        This is the leftover Infogami wiki-preview path, not the production
        /books/OL.../edit UI. Templetor saferender() degrades it to
        'Unable to render this page' rather than a 500.
        """
        request_context_fixture(lang="en")
        edition = mock_site.quicksave("/books/OL5M", "/type/edition", title="Preview Probe Edition")
        monkeypatch.setattr(delegate, "exception_hooks", [])
        template.load_templates("vendor/infogami/infogami/core")

        html = str(code.render.editpage(edition, preview=True))
        assert "data-lending-state" not in html
        assert "Unable to render this page" in html
