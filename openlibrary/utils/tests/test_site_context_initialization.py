"""Regression coverage for the Phase 1 site ContextVar migration (#13966)."""

from contextlib import suppress
from contextvars import Context
from queue import Queue
from threading import Thread
from unittest.mock import Mock

import pytest
import web

from infogami.utils import delegate
from openlibrary.core import carousels, lending
from openlibrary.plugins.openlibrary import code, home, lists
from openlibrary.plugins.upstream import utils
from openlibrary.plugins.worksearch import code as worksearch
from openlibrary.plugins.worksearch import subjects
from openlibrary.utils.request_context import create_context_for_script, req_context, site
from openlibrary.views import loanstats
from scripts import affiliate_server


@pytest.fixture(autouse=True)
def isolated_web_context(monkeypatch):
    # Some legacy tests replace web.ctx with a plain dict. Workers need the
    # real thread-local semantics regardless of which tests ran before them.
    context = web.utils.ThreadedDict()
    monkeypatch.setattr(web, "ctx", context)
    monkeypatch.setattr(web.webapi, "ctx", context)
    yield
    context.clear()


@pytest.mark.parametrize("first_response", ["success", "redirect", "notfound"])
def test_context_precedes_ol_processors_and_survives_layout(monkeypatch, first_response):
    processors = delegate.app.processors
    setup_index = processors.index(code.setup_contextvars)
    readable_index = next(i for i, processor in enumerate(processors) if isinstance(processor, code.processors.ReadableUrlProcessor))
    assert setup_index < readable_index

    def check_requests():
        current_sites = iter([Mock(), Mock()])
        observed = []

        def initialize(handler):
            web.ctx.site = next(current_sites)
            web.ctx.lang = "en"
            return handler()

        def render_layout(site_name, result):
            assert site.get() is web.ctx.site
            return str(result)

        def next_processor(self, handler):
            assert site.get() is web.ctx.site
            observed.append(site.get())
            return handler()

        class Page:
            def GET(self):
                assert site.get() is web.ctx.site
                if len(observed) == 1:
                    if first_response == "redirect":
                        raise web.seeother("/target")
                    if first_response == "notfound":
                        raise web.notfound("missing")
                return "ok"

        app = web.application(("/", "Page"), {"Page": Page})
        monkeypatch.setattr(delegate, "render_site", render_layout)
        monkeypatch.setattr(code.processors.ReadableUrlProcessor, "__call__", next_processor)
        for processor in [initialize, delegate.layout_processor, *processors[setup_index : readable_index + 1]]:
            app.add_processor(processor)
        response = app.request("/")
        expected_status = {"success": "200", "redirect": "303", "notfound": "404"}[first_response]
        assert response.status.startswith(expected_status)
        assert app.request("/").data == b"ok"
        assert len(observed) == 2
        assert observed[0] is not observed[1]

    Context().run(check_requests)


@pytest.mark.parametrize(
    "fetch",
    [
        lambda: lists._get_recently_modified_lists(1),
        lambda: lists._get_active_lists_in_random(limit=0),
        lambda: worksearch.rewrite_list_query("/lists/OL1L", 1, 0, 1, {}),
        lambda: subjects._compute_notable_authors("unknown", "/subjects/example"),
        lambda: carousels.get_ia_carousel_books("example"),
        lambda: utils._get_changes_v1_raw({}),
        lambda: utils._get_changes_v2_raw({}),
        utils._get_recent_changes2,
        home.get_featured_subjects,
        home.get_featured_genres,
        loanstats.reading_log_summary,
        lambda: loanstats.reading_log_leaderboard(1),
    ],
    ids=[
        "recent-lists",
        "active-lists",
        "list-query",
        "notable-authors",
        "carousel",
        "changes-v1",
        "changes-v2",
        "recent-changes",
        "featured-subjects",
        "featured-genres",
        "reading-summary",
        "reading-leaderboard",
    ],
)
def test_fakeload_callers_synchronize_context(monkeypatch, fetch):
    class Fetched(Exception):
        pass

    anonymous = Mock()

    def reached_data(*args, **kwargs):
        assert site.get() is anonymous
        assert not req_context.get().print_disabled
        raise Fetched

    for method in ["things", "get", "versions", "recentchanges"]:
        getattr(anonymous, method).side_effect = reached_data

    def fakeload():
        delegate.app.load({"REQUEST_METHOD": "GET", "PATH_INFO": "/install"})
        web.ctx.site = anonymous

    monkeypatch.setattr(delegate, "fakeload", fakeload)
    monkeypatch.setattr(carousels.lending, "get_available", reached_data)
    monkeypatch.setattr(subjects, "get_subject", reached_data)
    monkeypatch.setattr(home.home_genres, "load_tile_covers", reached_data)
    monkeypatch.setattr(loanstats.Bookshelves, "summary", reached_data)
    monkeypatch.setattr(loanstats.Bookshelves, "most_logged_books", reached_data)
    # Bypass cache hits so the tests exercise the cold context path.
    monkeypatch.setattr(worksearch.cache, "memcache_memoize", lambda fn, *args, **kwargs: fn)

    def run():
        web.ctx.clear()
        site.set(Mock(name="stale_authenticated_site"))
        with suppress(Fetched):
            fetch()
        assert site.get() is anonymous

    Context().run(run)


def test_waiting_loan_refresh_uses_anonymous_site(monkeypatch, mock_memcache):
    anonymous = Mock()
    observed = Queue()

    def fakeload():
        delegate.app.load({"REQUEST_METHOD": "GET", "PATH_INFO": "/install"})
        web.ctx.site = anonymous

    def get_account(user_key):
        observed.put((site.get(), req_context.get(), user_key))

    monkeypatch.setattr(delegate, "fakeload", fakeload)
    monkeypatch.setattr(lending.OpenLibraryAccount, "get_by_key", get_account)
    monkeypatch.setattr("openlibrary.core.waitinglist.WaitingLoan.query", lambda **kwargs: [])

    def refresh():
        # The main request is authenticated; refresh workers must not inherit it.
        site.set(Mock(name="authenticated_site"))
        req_context.set(create_context_for_script())
        lending.get_cached_user_waiting_loans.update_async("/people/test")
        lending.get_cached_user_waiting_loans.join_threads()

    Context().run(refresh)
    refreshed_site, context, user_key = observed.get_nowait()
    assert refreshed_site is anonymous
    assert context.print_disabled is False
    assert user_key == "/people/test"


def test_affiliate_worker_initializes_context(monkeypatch):
    class StopWorker(Exception):
        pass

    observed = Queue()
    worker_site = Mock()

    def stop():
        observed.put((site.get(), req_context.get()))
        raise StopWorker

    monkeypatch.setattr(affiliate_server.time, "time", stop)

    def run():
        with suppress(StopWorker):
            affiliate_server.amazon_lookup(worker_site, Mock(), Mock())

    thread = Thread(target=run, context=Context())
    thread.start()
    thread.join()
    actual_site, context = observed.get_nowait()
    assert actual_site is worker_site
    assert context == create_context_for_script()
