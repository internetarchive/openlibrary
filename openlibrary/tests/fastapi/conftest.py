from __future__ import annotations

"""Shared pytest fixtures for FastAPI and API contract tests."""

import asyncio
import datetime as dt
from collections.abc import Callable
from unittest.mock import patch

import httpx
import pytest
import web
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient

from infogami.utils import context as infogami_context_module
from openlibrary.core.jinja import get_jinja_env
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_authenticated_user,
)
from openlibrary.plugins.worksearch.code import SearchResponse
from openlibrary.utils.request_context import RequestContextVars, req_context, site


@pytest.fixture(scope="session")
def fastapi_client():
    """Create a test client for the FastAPI app (session-scoped for speed)."""
    with patch("openlibrary.asgi_app.set_context_from_fastapi", autospec=True):
        from openlibrary.asgi_app import create_app  # noqa: PLC0415

        app = create_app()
        client = TestClient(app)
        try:
            yield client
        finally:
            client.close()


@pytest.fixture
def mock_authenticated_user(fastapi_client):
    """Provide an authenticated test user using FastAPI's dependency_overrides.

    This is the correct FastAPI way to override dependencies in tests.
    Patching the function directly does not work because FastAPI's dependency
    injection system has already wired up the dependency when the app starts.
    So instead we tell the app: 'for this test, replace require_authenticated_user
    with a function that just returns our fake user'.
    """
    fake_user = AuthenticatedUser(
        username="testuser",
        user_key="/people/testuser",
        timestamp="2026-01-01T00:00:00",
    )
    fastapi_client.app.dependency_overrides[require_authenticated_user] = lambda: fake_user
    yield fake_user
    fastapi_client.app.dependency_overrides.clear()


@pytest.fixture
def mock_optional_authenticated_user(fastapi_client):
    """Override get_authenticated_user for endpoints that use optional auth.

    Use this fixture for endpoints that depend on get_authenticated_user
    (which returns AuthenticatedUser | None) and handle the unauthenticated
    case themselves — typically by returning a redirect to /account/login —
    rather than raising 401. The fixture only clears the override it set.
    """
    fake_user = AuthenticatedUser(
        username="testuser",
        user_key="/people/testuser",
        timestamp="2026-01-01T00:00:00",
    )
    fastapi_client.app.dependency_overrides[get_authenticated_user] = lambda: fake_user
    yield fake_user
    fastapi_client.app.dependency_overrides.pop(get_authenticated_user, None)


@pytest.fixture
def mock_work_search_async():
    """Mock the work_search_async function to avoid actual Solr calls.

    Used by FastAPI endpoint tests.
    """
    with patch("openlibrary.fastapi.search.work_search_async", autospec=True) as mock:
        mock.return_value = _default_search_response()
        yield mock


@pytest.fixture
def mock_work_search():
    """Mock the work_search (sync) function to avoid actual Solr calls.

    Used by webpy endpoint tests.
    """
    with patch("openlibrary.plugins.worksearch.code.work_search", autospec=True) as mock:
        mock.return_value = _default_search_response()
        yield mock


@pytest.fixture
def mock_fulltext_search_async():
    """Mock fulltext_search_async function to avoid actual Solr calls.

    Used by FastAPI search/inside endpoint tests.
    """
    with patch("openlibrary.fastapi.search.fulltext_search_async", autospec=True) as mock:
        mock.return_value = {"docs": [], "numFound": 0}
        yield mock


@pytest.fixture
def mock_async_run_solr_query():
    """Mock async_run_solr_query function to avoid actual Solr calls.

    Used by FastAPI search/subjects endpoint tests.
    """
    with patch("openlibrary.fastapi.search.async_run_solr_query", autospec=True) as mock:
        mock.return_value = _default_subjects_response()
        yield mock


@pytest.fixture
def mock_run_solr_query():
    """Mock run_solr_query (sync) function to avoid actual Solr calls.

    Used by webpy search/subjects endpoint tests.
    """
    with patch("openlibrary.plugins.worksearch.code.run_solr_query", autospec=True) as mock:
        mock.return_value = _default_subjects_response()
        yield mock


def _default_search_response():
    """Default mock response shared by both sync and async mocks."""
    return {
        "numFound": 2,
        "numFoundExact": True,
        "num_found": 2,
        "start": 0,
        "docs": [
            {"key": "/works/OL1W", "title": "Test Work 1"},
            {"key": "/works/OL2W", "title": "Test Work 2"},
        ],
        "q": "",
        "offset": None,
    }


@pytest.fixture
def mock_run_solr_query_async():
    """Mock run_solr_query_async to avoid actual Solr calls.

    Used by FastAPI search/facets endpoint tests.
    Returns a SearchResponse with sample facet_counts.
    """
    with patch("openlibrary.fastapi.search.run_solr_query_async", autospec=True) as mock:
        mock.return_value = _default_facets_response()
        yield mock


def _default_facets_response():
    """Default mock SearchResponse for facets tests."""
    return SearchResponse(
        # process_facet_counts renames author_facet → author_key in this dict
        facet_counts={
            "language": [
                ("eng", "English", 665),
                ("deu", "German", 32),
                ("spa", "Spanish", 18),
                ("lat", "Latin", 0),  # zero-count entry — should be filtered out
            ],
            "author_key": [
                ("OL9A", "J.R.R. Tolkien", 123),
            ],
            "subject_facet": [
                ("Fantasy", "Fantasy", 89),
            ],
        },
        sort="",
        docs=[],
        num_found=0,
        raw_resp={"response": {"docs": []}},
        solr_select="mock",
    )


def _default_subjects_response():
    """Default mock response for subjects search."""

    return SearchResponse(
        facet_counts=None,
        sort="work_count desc",
        docs=[
            {
                "key": "/subjects/subject1",
                "name": "Subject 1",
                "subject_type": "subject",
                "work_count": 10,
            }
        ],
        num_found=1,
        raw_resp={
            "response": {
                "docs": [
                    {
                        "key": "/subjects/subject1",
                        "name": "Subject 1",
                        "subject_type": "subject",
                        "work_count": 10,
                    }
                ]
            }
        },
        solr_select="mock",
    )


@pytest.fixture
def mock_edition_solr_query():
    """Mock run_solr_query_async for edition search tests."""
    with patch("openlibrary.fastapi.search.run_solr_query_async", autospec=True) as mock:
        mock.return_value = _default_edition_solr_response()
        yield mock


def _default_edition_solr_response():
    """Default mock SearchResponse for edition search tests."""
    docs = [
        {
            "key": "/books/OL1M",
            "title": "Test Edition 1",
            "work_key": ["OL1W"],
            "publish_date": ["2023"],
        }
    ]
    return SearchResponse(
        facet_counts=None,
        sort="publish_year desc",
        docs=docs,
        num_found=1,
        raw_resp={
            "response": {
                "numFound": 1,
                "numFoundExact": True,
                "start": 0,
                "docs": docs,
            }
        },
        solr_select="mock",
    )


# --- HTML pages (SitePageRoute) ---------------------------------------------

#: In every value ``webpy_leftovers`` leaves behind. A page showing it read state that isn't its own request's.
LEFTOVER = "LEFTOVER"


class FakeUser:
    created = dt.datetime(2013, 3, 20)

    def __init__(self, name: str):
        self.key = f"/people/{name}"

    def is_librarian_or_higher(self):
        return False

    def is_super_librarian_or_higher(self):
        return False


class FakeSite:
    """``site.get()`` for one request: logged in as ``username``, or anonymous."""

    def __init__(self, username: str | None):
        self.username = username

    def get_user(self):
        return FakeUser(self.username) if self.username else None


@pytest.fixture
def site_page_app(monkeypatch) -> Callable[..., FastAPI]:
    """Build an app serving the given page routers, with no infobase or static assets.

    Its middleware sets the per-request ContextVars, as ``asgi_app``'s does. The
    request is logged in as its ``x-user`` header (``FakeUser``), if any, and is
    from a recognized crawler if it sends ``x-recognized-bot: 1``.
    """
    monkeypatch.setitem(get_jinja_env().globals, "static_url", lambda p: f"/static/{p}")
    monkeypatch.setitem(get_jinja_env().globals, "icon", lambda *a, **kw: "")
    # A linked archive.org account, so the header shows the account title (with the joined date).
    monkeypatch.setattr("openlibrary.core.shell.user.get_internet_archive_id", lambda key: "@ia")

    def make(*routers: APIRouter) -> FastAPI:
        app = FastAPI()

        @app.middleware("http")
        async def set_context(request: Request, call_next):
            site.set(FakeSite(request.headers.get("x-user")))  # type: ignore[arg-type]
            req_context.set(RequestContextVars(None, "test", "en", True, False, is_recognized_bot=request.headers.get("x-recognized-bot") == "1"))
            await asyncio.sleep(0)  # let concurrent requests interleave between here and the page
            return await call_next(request)

        for router in routers:
            app.include_router(router)
        return app

    return make


@pytest.fixture
def webpy_leftovers(monkeypatch) -> str:
    """Leave another request's state in ``web.ctx`` and infogami's ``context``; returns ``LEFTOVER``.

    FastAPI never resets these thread-locals, so on FastAPI they hold whatever the
    last request on that thread left. Code that reads them can show one user's
    path, flash message or language in another user's page. Every value set here
    contains ``LEFTOVER`` (and the language is ``fr``), so a page that reads any
    of them shows it. They're plain objects rather than thread-locals, so every
    thread sees them, including the worker thread that loads the user.
    """
    leftovers = web.storage(
        path=f"/{LEFTOVER}-path",
        readable_path=f"/{LEFTOVER}-path",
        host=f"{LEFTOVER}.example",
        homepath=f"/{LEFTOVER}-home",
        query=f"?q={LEFTOVER}-q",
        lang="fr",
        flash=[web.storage(type="info", message=f"{LEFTOVER}-flash")],
        env={"HTTP_COOKIE": f"session={LEFTOVER}-session", "QUERY_STRING": f"q={LEFTOVER}-q&debug=1&dev_host={LEFTOVER}"},
        stats=[web.storage(name=LEFTOVER, data={}, t_start=0.0, time=0.0)],
    )
    infogami_leftovers = web.storage(bodyclass=[LEFTOVER], cssfile=LEFTOVER, experiments={LEFTOVER: 1}, metatags=[LEFTOVER], stats=leftovers.stats)
    monkeypatch.setattr(web, "ctx", leftovers)
    monkeypatch.setattr(infogami_context_module, "context", infogami_leftovers)
    return LEFTOVER


@pytest.fixture
def fetch_concurrently() -> Callable[[FastAPI, list[tuple[str, dict[str, str]]]], list[httpx.Response]]:
    """GET each ``(url, headers)`` from ``app`` at once, so the requests interleave; responses in order."""

    def fetch(app: FastAPI, requests: list[tuple[str, dict[str, str]]]) -> list[httpx.Response]:
        async def main():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                return await asyncio.gather(*(client.get(url, headers=headers) for url, headers in requests))

        return asyncio.run(main())

    return fetch
