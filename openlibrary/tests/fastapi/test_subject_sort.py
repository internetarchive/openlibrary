from __future__ import annotations

"""Sort validation for /subjects/*.json and /publishers/*.json (issue #13988).

An unknown ``sort`` must return a 422 listing the valid options rather than a
500. Validation happens in ``BaseSubjectRequestParams`` before any Solr call,
so the invalid-sort cases need no Solr mock.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def client(fastapi_client):
    return fastapi_client


@pytest.mark.parametrize(
    "url",
    [
        "/subjects/love.json?sort=ranking",  # 'ranking' was wrongly documented as valid
        "/subjects/love.json?sort=bogus",
        "/subjects/love.json?limit=1&sort=title%20desc",
        "/publishers/Penguin.json?sort=bogus",
        "/publishers/Penguin.json?sort=new,bogus",
    ],
)
def test_invalid_sort_returns_422(client, url):
    response = client.get(url)
    assert response.status_code == 422
    assert "Invalid sort option" in response.text


@pytest.mark.parametrize(
    ("module", "url"),
    [
        ("openlibrary.fastapi.subjects", "/subjects/love.json?sort=new"),
        ("openlibrary.fastapi.subjects", "/subjects/love.json?sort=editions"),
        ("openlibrary.fastapi.subjects", "/subjects/love.json?sort=editions,"),  # empty component dropped, not 500
        ("openlibrary.fastapi.publishers", "/publishers/Penguin.json?sort=new"),
    ],
)
def test_valid_sort_is_not_rejected(client, module, url):
    """A valid sort passes validation and reaches the (mocked) data fetch."""
    with patch(f"{module}.fetch_subject_data", new=AsyncMock(return_value={"key": "/subjects/love"})) as mock:
        response = client.get(url)
    assert response.status_code == 200
    mock.assert_awaited_once()
