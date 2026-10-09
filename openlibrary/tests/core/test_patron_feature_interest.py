"""Integration tests for the PatronFeatureInterestDB model.

Run with: pytest -m integration openlibrary/tests/core/test_patron_feature_interest.py
"""

from __future__ import annotations

import pytest

from openlibrary.core.patron_feature_interest import PatronFeatureInterest, PatronFeatureInterestDB


@pytest.mark.integration
class TestPatronFeatureInterestDB:
    """Integration tests requiring a real PostgreSQL database."""

    async def test_create_and_exists(self, pg_db):
        """Test creating an interest and checking if it exists."""
        username = "testuser"
        feature = "LibraryThing"

        # Initially should not exist
        assert await PatronFeatureInterestDB.exists(username, feature) is False

        # Create the interest
        await PatronFeatureInterestDB.create(username, feature)

        # Now should exist
        assert await PatronFeatureInterestDB.exists(username, feature) is True

    async def test_create_idempotent(self, pg_db):
        """Test that creating the same interest twice is idempotent."""
        username = "testuser"
        feature = "LibraryThing"

        await PatronFeatureInterestDB.create(username, feature)
        await PatronFeatureInterestDB.create(username, feature)  # Should not raise

        assert await PatronFeatureInterestDB.exists(username, feature) is True

    async def test_select_features_by_username(self, pg_db):
        """Test selecting all features for a user."""
        username = "testuser"
        features = ["LibraryThing", "StoryGraph", "Goodreads"]

        for feature in features:
            await PatronFeatureInterestDB.create(username, feature)

        result = await PatronFeatureInterestDB.select_features_by_username(username)
        assert set(result) == set(features)

    async def test_select_features_by_username_empty(self, pg_db):
        """Test selecting features for a user with no interests."""
        result = await PatronFeatureInterestDB.select_features_by_username("nonexistent")
        assert result == []

    async def test_select_by_username_returns_dataclass(self, pg_db):
        """Test that select_by_username returns PatronFeatureInterest dataclass instances."""
        username = "testuser"
        feature = "LibraryThing"

        await PatronFeatureInterestDB.create(username, feature)

        results = await PatronFeatureInterestDB.select_by_username(username)

        assert len(results) == 1
        record = results[0]
        assert isinstance(record, PatronFeatureInterest)
        assert record.username == username
        assert record.feature == feature
        assert record.created is not None

    async def test_count_by_feature(self, pg_db):
        """Test counting interests per feature."""
        feature = "LibraryThing"

        await PatronFeatureInterestDB.create("user1", feature)
        await PatronFeatureInterestDB.create("user2", feature)
        await PatronFeatureInterestDB.create("user3", "StoryGraph")

        count = await PatronFeatureInterestDB.count_by_feature(feature)
        assert count == 2

    async def test_count_by_feature_zero(self, pg_db):
        """Test counting a feature with no interests."""
        count = await PatronFeatureInterestDB.count_by_feature("NonExistentFeature")
        assert count == 0

    async def test_isolation_between_users(self, pg_db):
        """Test that interests are isolated per user."""
        await PatronFeatureInterestDB.create("user1", "LibraryThing")
        await PatronFeatureInterestDB.create("user2", "LibraryThing")

        assert await PatronFeatureInterestDB.exists("user1", "LibraryThing") is True
        assert await PatronFeatureInterestDB.exists("user2", "LibraryThing") is True
        assert await PatronFeatureInterestDB.exists("user1", "StoryGraph") is False
        assert await PatronFeatureInterestDB.exists("user2", "StoryGraph") is False

        user1_features = await PatronFeatureInterestDB.select_features_by_username("user1")
        user2_features = await PatronFeatureInterestDB.select_features_by_username("user2")

        assert user1_features == ["LibraryThing"]
        assert user2_features == ["LibraryThing"]