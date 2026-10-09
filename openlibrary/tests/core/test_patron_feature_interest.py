"""Tests for the PatronFeatureInterestDB model using async_db fakes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from openlibrary.core.patron_feature_interest import PatronFeatureInterest, PatronFeatureInterestDB
from openlibrary.tests.core.async_db_fakes import FakeConnection, FakeConnectionContext


def _patched_connection(conn: FakeConnection):
    return patch("openlibrary.core.async_db.connection", return_value=FakeConnectionContext(conn))


@pytest.mark.asyncio
async def test_exists_true():
    conn = FakeConnection(rows=[{"?column?": 1}])
    with _patched_connection(conn):
        assert await PatronFeatureInterestDB.exists("testuser", "LibraryThing") is True


@pytest.mark.asyncio
async def test_exists_false():
    conn = FakeConnection(rows=[])
    with _patched_connection(conn):
        assert await PatronFeatureInterestDB.exists("testuser", "LibraryThing") is False


@pytest.mark.asyncio
async def test_create():
    conn = FakeConnection()
    with _patched_connection(conn):
        await PatronFeatureInterestDB.create("testuser", "LibraryThing")
    assert conn.committed
    ((query, params),) = conn.executions
    assert "INSERT INTO patron_feature_interest" in query
    assert params == {"username": "testuser", "feature": "LibraryThing"}


@pytest.mark.asyncio
async def test_select_features_by_username():
    conn = FakeConnection(rows=[{"feature": "LibraryThing"}, {"feature": "StoryGraph"}])
    with _patched_connection(conn):
        features = await PatronFeatureInterestDB.select_features_by_username("testuser")
    assert features == ["LibraryThing", "StoryGraph"]


@pytest.mark.asyncio
async def test_select_by_username_returns_dataclass():
    columns = ("username", "feature", "created")
    conn = FakeConnection(rows=[("testuser", "LibraryThing", None)], columns=columns)
    with _patched_connection(conn):
        results = await PatronFeatureInterestDB.select_by_username("testuser")
    assert len(results) == 1
    assert isinstance(results[0], PatronFeatureInterest)
    assert results[0].username == "testuser"
    assert results[0].feature == "LibraryThing"


@pytest.mark.asyncio
async def test_count_by_feature():
    conn = FakeConnection(rows=[{"count": 5}])
    with _patched_connection(conn):
        count = await PatronFeatureInterestDB.count_by_feature("LibraryThing")
    assert count == 5
