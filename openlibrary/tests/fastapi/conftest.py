"""Shared pytest fixtures for FastAPI and API contract tests."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fastapi_client():
    """Create a test client for the FastAPI app."""
    from openlibrary.asgi_app import create_app

    app = create_app()
    return TestClient(app)


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


def _default_subjects_response():
    """Default mock response for subjects search."""
    from openlibrary.plugins.worksearch.code import SearchResponse

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
