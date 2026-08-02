"""Tests for the social activity feed endpoint."""

from datetime import datetime
from unittest.mock import patch

import pytest

from openlibrary.core.activity import ListEvent, RatingEvent, ShelfEvent

JAN = datetime(2026, 1, 10, 12, 0, 0)


def shelf_event(username="ada", work_id=59800, shelf_id=1, rating=None):
    event = ShelfEvent(
        username=username,
        created=JAN,
        work_id=work_id,
        work_key=f"/works/OL{work_id}W",
        shelf_id=shelf_id,
        rating=rating,
    )
    event.work = {
        "key": f"/works/OL{work_id}W",
        "title": "The Left Hand of Darkness",
        "author_name": ["Ursula K. Le Guin"],
        "author_key": ["OL31353A"],
        "cover_i": 10618463,
        "first_publish_year": 1969,
        "ebook_access": "borrowable",
    }
    return event


@pytest.fixture
def mock_avatar():
    with patch("openlibrary.fastapi.activity.User.get_avatar_url", return_value="https://archive.org/services/img/@ada"):
        yield


class TestActivityFeedEndpoint:
    def test_returns_normalised_shelf_events(self, fastapi_client, mock_avatar):
        with (
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[shelf_event()]),
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=False),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        assert response.status_code == 200
        body = response.json()
        assert body["scope"] == "public"
        assert body["following"] is False
        (item,) = body["activity"]
        assert item["type"] == "shelf_change"
        assert item["username"] == "ada"
        assert item["label"] == "added to Want to Read"
        assert item["shelf_url"] == "/people/ada/books/want-to-read"
        assert item["work"]["title"] == "The Left Hand of Darkness"
        assert item["work"]["cover_id"] == 10618463
        assert item["work"]["author"] == "Ursula K. Le Guin"
        assert item["work"]["author_key"] == "/authors/OL31353A"

    def test_rating_rides_along_on_a_shelf_event(self, fastapi_client, mock_avatar):
        with (
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[shelf_event(shelf_id=3, rating=5)]),
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=False),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        (item,) = response.json()["activity"]
        assert item["rating"] == 5
        assert item["label"] == "finished reading"

    def test_drops_events_whose_work_is_missing_from_solr(self, fastapi_client, mock_avatar):
        # A work that Solr has no record of would render as a blank card.
        orphan = shelf_event()
        orphan.work = None

        with (
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[orphan]),
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=False),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        assert response.json()["activity"] == []

    def test_serialises_list_events(self, fastapi_client, mock_avatar):
        event = ListEvent(
            username="ada",
            created=JAN,
            list_key="/people/ada/lists/OL1L",
            name="Books that rewired my brain",
            book_count=4,
            cover_ids=[1, 2, 3],
        )
        with (
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[event]),
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=False),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        (item,) = response.json()["activity"]
        assert item["type"] == "list_update"
        assert item["list"]["name"] == "Books that rewired my brain"
        assert item["list"]["book_count"] == 4
        assert item["list"]["cover_ids"] == [1, 2, 3]
        assert item["work"] is None

    def test_rating_only_event_serialises_without_a_shelf(self, fastapi_client, mock_avatar):
        event = RatingEvent(username="ada", created=JAN, work_id=1, work_key="/works/OL1W", rating=4)
        event.work = {"key": "/works/OL1W", "title": "Trust", "author_name": [], "cover_i": None}

        with (
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[event]),
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=False),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        (item,) = response.json()["activity"]
        assert item["type"] == "rating"
        assert item["shelf_url"] is None
        assert item["work"]["author"] is None

    def test_authenticated_follower_gets_the_following_feed(self, fastapi_client, mock_optional_authenticated_user, mock_avatar):
        with (
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=True),
            patch("openlibrary.fastapi.activity.ActivityStream.following_feed", return_value=[shelf_event()]) as following_mock,
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed") as public_mock,
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        assert response.json()["scope"] == "following"
        following_mock.assert_called_once()
        public_mock.assert_not_called()

    def test_scope_can_be_forced_to_public(self, fastapi_client, mock_optional_authenticated_user, mock_avatar):
        # The design gallery needs to show the public feed regardless of who is
        # logged in, so scope is overridable.
        with (
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=True),
            patch("openlibrary.fastapi.activity.ActivityStream.following_feed") as following_mock,
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[]) as public_mock,
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json?scope=public")

        assert response.json()["scope"] == "public"
        public_mock.assert_called_once()
        following_mock.assert_not_called()

    def test_following_feed_falls_back_to_public_when_it_is_empty(self, fastapi_client, mock_optional_authenticated_user, mock_avatar):
        # Following someone who has not logged anything recently should not
        # produce a dead page.
        with (
            patch("openlibrary.fastapi.activity.PubSub.is_following", return_value=True),
            patch("openlibrary.fastapi.activity.ActivityStream.following_feed", return_value=[]),
            patch("openlibrary.fastapi.activity.ActivityStream.public_feed", return_value=[shelf_event()]) as public_mock,
            patch("openlibrary.fastapi.activity.ActivityStream.attach_works"),
        ):
            response = fastapi_client.get("/api/internal/activity/feed.json")

        body = response.json()
        assert body["scope"] == "public"
        assert body["following"] is True
        assert len(body["activity"]) == 1
        public_mock.assert_called_once()

    @pytest.mark.parametrize("limit", [0, 51])
    def test_rejects_out_of_range_limits(self, fastapi_client, limit):
        response = fastapi_client.get(f"/api/internal/activity/feed.json?limit={limit}")
        assert response.status_code == 422
