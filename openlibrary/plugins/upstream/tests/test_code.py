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

from unittest.mock import Mock, patch

import pytest
import web

from openlibrary.core import lending
from openlibrary.plugins.upstream import code


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
        """Viewing an old edition revision whose work has since been merged.

        get_document() follows redirects internally, so it's called with the
        redirect Thing's own key (not its .location) -- matching the original
        template code exactly.
        """
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
        """A path outside /works/ and /books/ must delegate to core.view.GET
        immediately, without this override doing its own get_version() call
        first -- otherwise every non-book/work page (authors, lists,
        subjects, the home page, ...) would pay for a redundant Thing load
        on top of the one core.view.GET does itself."""
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
        """A /works/... or /books/... path that doesn't resolve to a work or
        edition (e.g. a deleted/redirected Thing) still falls back to
        core.view.GET, but only after this override's own get_version()
        call -- it needs the Thing to know that."""
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
        mock_render.assert_called_once_with(work_page, book_page_context=fake_context)

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
