"""Tests for /works and /books lending preparation (issue #13419)."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import web

from infogami.utils import delegate, macro
from infogami.utils.app import modes
from openlibrary.core import db, lending
from openlibrary.plugins.upstream import code, recentchanges, utils


def make_edition(key, ocaid=None, availability=None, **extra):
    return web.storage(key=key, ocaid=ocaid, availability=availability or {}, **extra)


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


def make_direct_page(availability, ocaid="ia1", key="/books/OL1M"):
    """Edition page whose work lists that same edition."""
    edition = make_edition(key, ocaid=ocaid, availability=availability)
    work = make_work("/works/OL1W", [edition])
    edition.works = [work]
    return edition


def ia_provider():
    return Mock(short_name="ia")


def logged_in_user(*, loan=None, printdisabled=False):
    user = Mock()
    user.is_printdisabled.return_value = printdisabled
    user.get_loan_for.return_value = loan
    user.get_user_waiting_loans.return_value = None
    return user


class TestPrepareBookPageEditionSelection:
    @pytest.fixture(autouse=True)
    def _stub_lending_state(self, monkeypatch):
        monkeypatch.setattr(lending, "get_lending_state", lambda *a, **kw: "locate")

    def test_direct_edition_page(self):
        ed2 = make_edition("/books/OL2M", ocaid="ia2", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed2])
        page = ed2
        page.works = [work]

        context = code.prepare_book_page(page, {}, user=None)

        assert context.work is work
        assert context.edition is page
        assert context.editions == [ed2]

    def test_work_without_edition_uses_best_edition(self):
        ed1 = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open"})
        ed2 = make_edition("/books/OL2M", ocaid="ia2", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed1, ed2])

        with patch("openlibrary.book_providers.get_best_edition", return_value=(ed2, None)) as mock_best:
            context = code.prepare_book_page(work, {}, user=None)

        mock_best.assert_called_once_with([ed1, ed2])
        assert context.work is work
        assert context.edition is ed2

    def test_explicit_edition_query_param(self):
        ed9 = make_edition("/books/OL9M", ocaid="ia9", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed9])

        with patch.object(code.core.db, "get_type", return_value=ed9) as mock_get_type:
            context = code.prepare_book_page(work, {"edition": "key:/books/OL9M"}, user=None)

        mock_get_type.assert_called_once_with("/books/OL9M")
        assert context.edition is ed9

    def test_provider_id_edition_selection(self):
        ed1 = make_edition("/books/OL1M", ocaid="someid", availability={"status": "open"})
        ed2 = make_edition("/books/OL2M", ocaid="other", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed1, ed2])

        mock_provider = Mock()
        mock_provider.get_olids.return_value = ["OL1M"]
        mock_provider.get_identifiers.side_effect = lambda e: [e.ocaid]

        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_provider):
            context = code.prepare_book_page(work, {"edition": "ia:someid"}, user=None)

        assert context.edition is ed1

    def test_provider_id_with_extra_colons_does_not_crash(self):
        ed1 = make_edition("/books/OL1M", ocaid="someid", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed1])

        mock_provider = Mock()
        mock_provider.get_olids.return_value = []
        mock_provider.get_identifiers.side_effect = lambda e: [e.ocaid]

        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_provider):
            context = code.prepare_book_page(work, {"edition": "ia:someid:extra"}, user=None)

        # Splits on the first colon only, so a crafted multi-colon ?edition=
        # falls back to the best edition instead of raising ValueError.
        mock_provider.get_olids.assert_called_once_with("someid:extra")
        assert context.edition is ed1

    def test_orphan_edition_falls_back_to_synthetic_work(self):
        orphan_work = make_work("", [], edition_count=1)
        ed = make_edition("/books/OL1M", ocaid="ia1", availability={"status": "open"})
        ed.works = []
        ed.make_work_from_orphaned_edition = Mock(return_value=orphan_work)

        context = code.prepare_book_page(ed, {}, user=None)

        ed.make_work_from_orphaned_edition.assert_called_once()
        assert context.work is orphan_work
        assert context.show_observations is False
        assert context.edition is ed

    def test_merged_redirected_work(self):
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
    @pytest.fixture(autouse=True)
    def _stub_lending_state(self, monkeypatch):
        monkeypatch.setattr(lending, "get_lending_state", lambda *a, **kw: "locate")

    def test_groundtruth_not_called_when_bulk_status_ok(self):
        page = make_direct_page({"status": "open", "is_readable": True})

        with patch.object(lending, "get_cached_groundtruth_availability") as mock_gt:
            context = code.prepare_book_page(page, {}, user=None)

        mock_gt.assert_not_called()
        assert context.edition.availability["status"] == "open"

    def test_groundtruth_called_only_for_selected_edition_on_bulk_error(self):
        ed_error = make_edition("/books/OL1M", ocaid="ia-error", availability={"status": "error"})
        ed_ok = make_edition("/books/OL2M", ocaid="ia-ok", availability={"status": "open"})
        work = make_work("/works/OL1W", [ed_error, ed_ok])
        page = ed_error
        page.works = [work]

        with patch.object(
            lending,
            "get_cached_groundtruth_availability",
            return_value={"status": "borrowable", "is_lendable": True, "available_to_borrow": True},
        ) as mock_gt:
            context = code.prepare_book_page(page, {}, user=None)

        mock_gt.assert_called_once_with("ia-error")
        assert context.edition is ed_error
        assert context.edition.availability["status"] == "borrowable"
        assert ed_ok.availability == {"status": "open"}

    def test_groundtruth_exception_degrades_instead_of_crashing_the_page(self):
        page = make_direct_page({"status": "error"})

        with patch.object(lending, "get_cached_groundtruth_availability", side_effect=TimeoutError("groundtruth timed out")) as mock_gt:
            context = code.prepare_book_page(page, {}, user=None)

        mock_gt.assert_called_once_with("ia1")
        assert context.edition.availability["status"] == "error"

    def test_groundtruth_fallback_runs_before_get_lending_state(self, monkeypatch):
        page = make_direct_page({"status": "error"})
        order = []

        def fake_gt(ocaid):
            order.append("gt")
            return {"status": "open", "is_readable": True}

        def fake_gls(doc, **kw):
            order.append("gls")
            assert doc.availability["status"] == "open"
            return "open"

        monkeypatch.setattr(lending, "get_cached_groundtruth_availability", fake_gt)
        monkeypatch.setattr(lending, "get_lending_state", fake_gls)

        context = code.prepare_book_page(page, {}, user=None)

        assert order == ["gt", "gls"]
        assert context.lending_state == "open"


class TestPrepareBookPageLendingState:
    """Uses real get_lending_state() so bulk -> groundtruth -> lending_state order is exercised."""

    def _run(self, page, *, gt=None, user=None, provider=None):
        with (
            patch.object(lending, "get_cached_groundtruth_availability", return_value=gt or {}) as mock_gt,
            patch("openlibrary.book_providers.get_book_provider", return_value=provider or ia_provider()),
            patch("openlibrary.accounts.get_current_user") as mock_get_user,
        ):
            context = code.prepare_book_page(page, {}, user=user)
        return context, mock_gt, mock_get_user

    @pytest.mark.parametrize(
        ("gt_availability", "expected"),
        [
            ({"status": "open", "is_readable": True}, "open"),
            ({"status": "borrowable", "is_lendable": True, "available_to_borrow": True}, "borrowable"),
            ({"status": "waitlist", "is_lendable": True, "available_to_waitlist": True}, "waitlist"),
            ({"status": "private", "is_previewable": True}, "preview_only"),
            ({"status": "error"}, "locate"),
        ],
    )
    def test_lending_state_from_groundtruth_on_bulk_error(self, gt_availability, expected):
        context, mock_gt, mock_get_user = self._run(
            make_direct_page({"status": "error"}),
            gt=gt_availability,
            user=logged_in_user(),
        )
        mock_gt.assert_called_once_with("ia1")
        mock_get_user.assert_not_called()
        assert context.lending_state == expected

    def test_bulk_ok_skips_groundtruth_and_uses_bulk_state(self):
        page = make_direct_page({"status": "open", "is_readable": True})
        context, mock_gt, _ = self._run(page, user=logged_in_user())
        mock_gt.assert_not_called()
        assert context.lending_state == "open"

    def test_active_loan_returns_borrowed(self):
        page = make_direct_page({"status": "borrow_available", "is_lendable": True, "available_to_borrow": True})
        user = logged_in_user(loan={"expiry": "2030-01-01", "resource_type": "bookreader"})
        context, mock_gt, mock_get_user = self._run(page, user=user)
        mock_gt.assert_not_called()
        mock_get_user.assert_not_called()
        assert context.lending_state == "borrowed"

    def test_printdisabled_user_returns_printdisabled(self):
        context, mock_gt, mock_get_user = self._run(
            make_direct_page({"status": "error"}),
            gt={"status": "borrowable", "is_lendable": True, "available_to_borrow": True},
            user=logged_in_user(printdisabled=True),
        )
        mock_gt.assert_called_once_with("ia1")
        mock_get_user.assert_not_called()
        assert context.lending_state == "printdisabled"

    @pytest.mark.parametrize(
        ("user", "expect_check"),
        [
            (object(), True),
            (None, False),
        ],
    )
    def test_resolved_user_is_passed_to_get_lending_state(self, user, expect_check):
        page = make_direct_page({"status": "open", "is_readable": True})
        with patch.object(lending, "get_lending_state", return_value="open") as mock_gls:
            code.prepare_book_page(page, {}, user=user)
        mock_gls.assert_called_once()
        assert mock_gls.call_args.kwargs["user"] is user
        assert mock_gls.call_args.kwargs["check_loan_status"] is expect_check


class TestLoanStatusNoLongerDoesNetworkIO:
    def test_loan_status_template_invariants(self):
        with open("openlibrary/macros/LoanStatus.html") as f:
            source = f.read()
        assert "get_cached_groundtruth_availability" not in source
        assert "allow_expensive_availability_check" not in source
        assert "macros.BookPreview(ocaid, show_only=True)" in source

    def test_databar_work_template_has_no_expensive_check(self):
        with open("openlibrary/macros/databarWork.html") as f:
            source = f.read()
        assert "get_cached_groundtruth_availability" not in source
        assert "allow_expensive_availability_check" not in source
        assert "expensive_check" not in source

    def test_groundtruth_and_add_availability_are_not_template_globals(self):
        assert "get_cached_groundtruth_availability" not in web.template.Template.globals
        assert "add_availability" not in web.template.Template.globals
        assert callable(lending.get_cached_groundtruth_availability)


class TestViewModeRoutingIsolation:
    def test_html_view_uses_prepare_path(self):
        assert modes["view"][None] is code.view

    @pytest.mark.parametrize(
        ("mode", "encoding", "owner"),
        [
            ("edit", None, lambda: code.edit),
            ("history", None, lambda: recentchanges.history),
            ("revert", None, lambda: code.revert),
            ("diff", None, lambda: code.core.diff),
        ],
    )
    def test_other_html_modes_are_not_the_book_view(self, mode, encoding, owner):
        assert modes[mode][encoding] is owner()
        assert modes[mode][encoding] is not code.view

    def _mock_web_input(self, monkeypatch):
        monkeypatch.setattr(web, "input", lambda *a, **kw: web.storage(**kw))

    def test_non_book_work_path_skips_prepare(self, monkeypatch):
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

    @pytest.mark.parametrize(
        ("path", "type_key"),
        [
            ("/works/OL1W", "/type/work"),
            ("/books/OL1M", "/type/edition"),
        ],
    )
    def test_html_works_and_books_call_prepare_book_page(self, path, type_key, monkeypatch):
        self._mock_web_input(monkeypatch)
        page = web.storage(key=path, type=web.storage(key=type_key))
        fake_context = object()
        fake_user = Mock(name="context.user")
        mock_render = Mock(return_value="rendered")
        monkeypatch.setattr(code.context, "user", fake_user, raising=False)
        with (
            patch.object(code.core.db, "get_version", return_value=page),
            patch.object(code, "prepare_book_page", return_value=fake_context) as mock_prepare,
        ):
            monkeypatch.setattr(code.render, "viewpage", mock_render, raising=False)
            code.view().GET(path)

        mock_prepare.assert_called_once()
        assert mock_prepare.call_args[0][0] is page
        assert mock_prepare.call_args[0][2] is fake_user
        mock_render.assert_called_once_with(page, fake_context)

    def test_json_view_never_calls_prepare_book_page(self, monkeypatch):
        from infogami.plugins.api import code as api_code

        monkeypatch.setattr(web, "input", lambda *a, **kw: web.storage(**kw))
        with (
            patch.object(code, "prepare_book_page") as mock_prepare,
            patch.object(api_code, "request", return_value='{"key": "/works/OL1W"}'),
        ):
            result = api_code.view().GET("/works/OL1W")

        mock_prepare.assert_not_called()
        assert result.rawtext == '{"key": "/works/OL1W"}'


class TestIntegratedBookPageRendering:
    """Real Templetor render of view.GET() -> prepare_book_page() -> viewpage -> edition view -> LoanStatus."""

    def _load_fake_request(self, path, site, monkeypatch):
        from openlibrary.plugins.upstream import models as upstream_models

        upstream_models.setup()

        app = web.application()
        app.load({"PATH_INFO": path, "REQUEST_METHOD": "GET", "HTTP_HOST": "openlibrary.org"})
        web.ctx.site = site
        web.ctx.lang = "en"

        monkeypatch.setattr("openlibrary.core.ia.get_api_response", lambda *a, **kw: {})
        if site.get("/config/edition") is None:
            site.quicksave("/config/edition", "/type/object", classifications=[], roles=[])

        monkeypatch.setattr(delegate, "create_site", lambda: site)
        delegate.initialize_context()
        macro.load_macros("openlibrary", lazy=True)
        web.template.Template.globals["request"] = utils.Request()

        class _ZeroRow(dict):
            def __missing__(self, key):
                return 0

        fake_db = Mock()
        fake_db.query = Mock(return_value=[_ZeroRow()])
        fake_db.select = Mock(return_value=[_ZeroRow()])
        monkeypatch.setattr(db, "get_db", lambda: fake_db)

        def fake_versions(q):
            return [web.storage(key=q.get("key"), revision=1, author=None, created=datetime.now())]

        monkeypatch.setattr(site, "versions", fake_versions)

    def test_work_page_renders_open_lending_state_after_groundtruth_fallback(self, monkeypatch, mock_site, render_template, request_context_fixture):
        request_context_fixture(lang="en")
        mock_site.quicksave("/works/OL1W", "/type/work", title="Integration Test Work", edition_count=1)
        mock_site.quicksave(
            "/books/OL1M",
            "/type/edition",
            title="Integration Test Edition",
            works=[{"key": "/works/OL1W"}],
            ocaid="integrationtest001",
        )
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
        assert len(lending_state_calls) == 1
        assert 'data-lending-state="open"' in html
        assert "waitinglist-form" not in html
        assert "LocateButton" not in html

    def test_edition_page_renders_via_real_templates(self, monkeypatch, mock_site, render_template, request_context_fixture):
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

        assert groundtruth_calls == []
        assert 'data-lending-state="open"' in html
