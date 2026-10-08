"""Tests for the FastAPI bestbook endpoints."""

from unittest.mock import call, patch

import pytest

from openlibrary.core.bestbook import Bestbook


@pytest.fixture
def mock_bestbook_model():
    """Prevent real DB calls for Bestbook mutation methods."""
    with (
        patch("openlibrary.plugins.openlibrary.api.Bestbook.add") as add_mock,
        patch("openlibrary.plugins.openlibrary.api.Bestbook.remove") as remove_mock,
    ):
        yield add_mock, remove_mock


class TestBestbookAwardEndpoint:
    def test_post_award_adds_award(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        add_mock.return_value = 123

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            data={
                "op": "add",
                "edition_key": "/books/OL42M",
                "topic": "Fiction",
                "comment": "Great book!",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "award": 123}
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            edition_id=42,
            comment="Great book!",
            topic="Fiction",
        )
        remove_mock.assert_not_called()

    def test_post_award_adds_award_from_query_params(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        add_mock.return_value = 123

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            params={
                "op": "add",
                "edition_key": "/books/OL42M",
                "topic": "Fiction",
                "comment": "Great book!",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "award": 123}
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            edition_id=42,
            comment="Great book!",
            topic="Fiction",
        )
        remove_mock.assert_not_called()

    def test_post_award_defaults_to_add(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        add_mock.return_value = 789

        response = fastapi_client.post("/works/OL123W/awards.json", data={})

        assert response.status_code == 200
        assert response.json() == {"success": True, "award": 789}
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            edition_id=None,
            comment="",
            topic=None,
        )
        remove_mock.assert_not_called()

    def test_post_award_form_values_override_query_values(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        add_mock.return_value = 321

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            params={
                "op": "remove",
                "edition_key": "/books/OL1M",
                "topic": "Query Topic",
                "comment": "query comment",
            },
            data={
                "op": "add",
                "edition_key": "/books/OL42M",
                "topic": "Form Topic",
                "comment": "form comment",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "award": 321}
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            edition_id=42,
            comment="form comment",
            topic="Form Topic",
        )
        remove_mock.assert_not_called()

    def test_post_award_removes_award(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        remove_mock.return_value = 1

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            data={"op": "remove"},
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "rows": 1}
        remove_mock.assert_called_once_with("testuser", work_id=123)
        add_mock.assert_not_called()

    def test_post_award_updates_award(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        add_mock.return_value = 456

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            data={
                "op": "update",
                "topic": "Science Fiction",
                "comment": "Still the one.",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "award": 456}
        assert remove_mock.call_args_list == [
            call("testuser", topic="Science Fiction"),
            call("testuser", work_id=123),
        ]
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            edition_id=None,
            comment="Still the one.",
            topic="Science Fiction",
        )

    def test_post_award_updates_award_from_query_params(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, remove_mock = mock_bestbook_model
        add_mock.return_value = 456

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            params={
                "op": "update",
                "topic": "Science Fiction",
                "comment": "Still the one.",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "award": 456}
        assert remove_mock.call_args_list == [
            call("testuser", topic="Science Fiction"),
            call("testuser", work_id=123),
        ]
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            edition_id=None,
            comment="Still the one.",
            topic="Science Fiction",
        )

    def test_post_award_returns_domain_errors(self, fastapi_client, mock_authenticated_user, mock_bestbook_model):
        add_mock, _ = mock_bestbook_model
        add_mock.side_effect = Bestbook.AwardConditionsError("Only books which have been marked as read may be given awards")

        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            data={
                "op": "add",
                "topic": "Fiction",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"errors": "Only books which have been marked as read may be given awards"}

    def test_post_award_requires_authentication(self, fastapi_client):
        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            data={
                "op": "add",
                "topic": "Fiction",
            },
        )

        assert response.status_code == 401

    def test_post_award_rejects_invalid_op(self, fastapi_client, mock_authenticated_user):
        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            data={
                "op": "invalid",
                "topic": "Fiction",
            },
        )

        assert response.status_code == 422

    def test_post_award_rejects_invalid_query_op(self, fastapi_client, mock_authenticated_user):
        response = fastapi_client.post(
            "/works/OL123W/awards.json",
            params={
                "op": "invalid",
                "topic": "Fiction",
            },
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("path", ["/works/OLnot-a-numberW/awards.json", "/works/OL0W/awards.json"])
    def test_post_award_rejects_invalid_work_id(self, fastapi_client, mock_authenticated_user, path):
        response = fastapi_client.post(path, data={"op": "add"})

        assert response.status_code == 422


class TestBestbookCountEndpoint:
    def test_count_forwards_filters(self, fastapi_client):
        with patch("openlibrary.fastapi.internal.api.Bestbook.get_count", return_value=5) as get_count_mock:
            response = fastapi_client.get(
                "/awards/count.json",
                params={
                    "work_id": "OL123W",
                    "username": "testuser",
                    "topic": "Fiction",
                },
            )

        assert response.status_code == 200
        assert response.json() == {"count": 5}
        get_count_mock.assert_called_once_with(work_id="OL123W", username="testuser", topic="Fiction")

    def test_count_works_without_filters(self, fastapi_client):
        with patch("openlibrary.fastapi.internal.api.Bestbook.get_count", return_value=0) as get_count_mock:
            response = fastapi_client.get("/awards/count.json")

        assert response.status_code == 200
        assert response.json() == {"count": 0}
        get_count_mock.assert_called_once_with(work_id=None, username=None, topic=None)
