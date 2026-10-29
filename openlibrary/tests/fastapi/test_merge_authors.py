"""Tests for POST /authors/merge.json (FastAPI merge_authors_json endpoint)."""

from unittest.mock import MagicMock, patch

import pytest

from infogami.infobase.client import ClientException
from openlibrary.utils.request_context import RequestContextVars, req_context, site
from openlibrary.utils.retry import MaxRetriesExceeded


@pytest.fixture(autouse=True)
def _setup_request_context():
    """Set ContextVars so require_librarian -> get_current_user() works."""
    site.set(MagicMock())
    req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )


@pytest.fixture
def mock_user_factory(monkeypatch):
    """Factory fixture to create and mock users with configurable roles.

    Usage:
        mock_user_factory(is_admin=True)
    """

    def create_user(
        is_admin: bool = False,
        is_librarian: bool = False,
        is_super_librarian: bool = False,
    ):
        user = MagicMock()
        user.is_librarian_or_higher.return_value = is_admin or is_librarian or is_super_librarian
        monkeypatch.setattr(
            "openlibrary.fastapi.auth.get_current_user",
            lambda: user,
        )
        return user

    return create_user


@pytest.fixture
def mock_merge_engine():
    """Mock the AuthorMergeEngine to avoid actual DB calls."""
    with patch(
        "openlibrary.fastapi.merge_authors.AuthorMergeEngine",
        autospec=True,
    ) as mock:
        instance = mock.return_value
        instance.merge.return_value = [
            {"key": "/authors/OL1A", "revision": 2},
        ]
        yield instance


@pytest.fixture
def mock_merge_queue_update():
    """Mock the async SQL-backed merge queue update."""
    with patch(
        "openlibrary.fastapi.merge_authors.perform_merge_update",
        autospec=True,
    ) as mock:
        yield mock


class TestMergeAuthorsJson:
    def test_merge_success(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """Admin user can merge authors successfully."""
        mock_user_factory(is_admin=True)

        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A", "/authors/OL3A"],
                "comment": "merging duplicates",
            },
        )
        assert response.status_code == 200
        assert response.json() == [
            {"key": "/authors/OL1A", "revision": 2},
        ]
        mock_merge_engine.merge.assert_called_once_with(
            "/authors/OL1A",
            ["/authors/OL2A", "/authors/OL3A"],
        )
        mock_merge_queue_update.assert_called_once()

    def test_merge_success_with_mrid(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """Admin user can merge authors with an existing merge request ID."""
        mock_user_factory(is_admin=True)

        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A"],
                "mrid": "123",
                "comment": "approving merge request",
            },
        )
        assert response.status_code == 200
        mock_merge_queue_update.assert_awaited_once_with(mrid=123, olids="", comment="approving merge request")

    def test_merge_invalid_mrid_returns_422_before_merging(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """A non-numeric mrid is rejected before any authors are merged."""
        mock_user_factory(is_admin=True)

        response = fastapi_client.post(
            "/authors/merge.json",
            json={"master": "/authors/OL1A", "duplicates": ["/authors/OL2A"], "mrid": "abc"},
        )
        assert response.status_code == 422
        mock_merge_engine.merge.assert_not_called()
        mock_merge_queue_update.assert_not_called()

    def test_merge_success_without_mrid_creates_request(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """When no mrid is provided, a new merge request record is created."""
        mock_user_factory(is_admin=True)

        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A"],
                "olids": "/authors/OL1A,/authors/OL2A",
            },
        )
        assert response.status_code == 200
        mock_merge_queue_update.assert_awaited_once_with(mrid=None, olids="/authors/OL1A,/authors/OL2A", comment=None)

    def test_merge_unauthenticated(self, fastapi_client):
        """Unauthenticated request returns 401 (from require_authenticated_user)."""
        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A"],
            },
        )
        assert response.status_code == 401

    def test_merge_forbidden_non_librarian(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
    ):
        """Regular user without librarian/admin role cannot merge authors."""
        mock_user_factory(
            is_admin=False,
            is_librarian=False,
            is_super_librarian=False,
        )

        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A"],
            },
        )
        assert response.status_code == 403

    def test_merge_allowed_for_librarian(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """Librarian (not admin) can merge authors."""
        mock_user_factory(
            is_admin=False,
            is_librarian=True,
            is_super_librarian=False,
        )

        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A"],
            },
        )
        assert response.status_code == 200

    def test_merge_allowed_for_super_librarian(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """Super librarian can merge authors."""
        mock_user_factory(
            is_admin=False,
            is_librarian=False,
            is_super_librarian=True,
        )

        response = fastapi_client.post(
            "/authors/merge.json",
            json={
                "master": "/authors/OL1A",
                "duplicates": ["/authors/OL2A"],
            },
        )
        assert response.status_code == 200

    def test_merge_raises_400_on_client_exception(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
    ):
        """ClientException from AuthorMergeEngine returns 400 with parsed error body."""
        mock_user_factory(is_admin=True)
        mock_merge_engine.merge.side_effect = ClientException(
            "400 Bad Request",
            "internal error",
            '{"error": "not_found", "message": "internal error"}',
        )
        response = fastapi_client.post(
            "/authors/merge.json",
            json={"master": "/authors/OL1A", "duplicates": ["/authors/OL999A"]},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": {"error": "not_found", "message": "internal error"}}

    def test_merge_raises_400_when_retries_exhausted(
        self,
        fastapi_client,
        mock_authenticated_user,
        mock_user_factory,
        mock_merge_engine,
        mock_merge_queue_update,
        monkeytime,
    ):
        """When the merge queue update exhausts retries, the endpoint returns 400."""
        mock_user_factory(is_admin=True)
        mock_merge_queue_update.side_effect = MaxRetriesExceeded(ClientException("400 Bad Request", "retry error"))
        response = fastapi_client.post(
            "/authors/merge.json",
            json={"master": "/authors/OL1A", "duplicates": ["/authors/OL2A"]},
        )
        assert response.status_code == 400
        assert "retry error" in response.json()["detail"]
