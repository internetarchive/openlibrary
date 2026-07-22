from __future__ import annotations

"""Shared pytest fixtures for FastAPI and API contract tests."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_authenticated_user,
)
from openlibrary.plugins.worksearch.code import SearchResponse


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
def mock_fulltext_search():
    """Mock the fulltext_search (sync) function to avoid actual Solr calls.

    Used by webpy search_inside endpoint tests.
    """
    with patch("openlibrary.plugins.inside.code.fulltext_search", autospec=True) as mock:
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
                ("English", "English", 665),
                ("German", "German", 32),
                ("Spanish", "Spanish", 18),
                ("Latin", "Latin", 0),  # zero-count entry — should be filtered out
            ],
            "author_key": [
                ("J.R.R. Tolkien", "OL9A", 123),
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
