"""Exercise request setup, worker routes and real Series helpers together."""

import pytest

from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.utils.request_context import set_context_from_fastapi


@pytest.fixture
def series_client(fastapi_client, monkeypatch):
    # The shared client normally stubs context setup. Restore the real setter
    # and replace only its Infogami boundary in each test.
    monkeypatch.setattr("openlibrary.asgi_app.set_context_from_fastapi", set_context_from_fastapi)
    return fastapi_client


def save_series(current_site, title):
    series_key = "/series/OL1L"
    for key in [series_key, "/series/OL2L"]:
        current_site.save({"key": key, "type": {"key": "/type/series"}, "name": key})
    for key, position, series in [
        ("/works/OL1W", "2", series_key),
        ("/works/OL2W", "1", series_key),
        ("/works/OL3W", "0", "/series/OL2L"),
    ]:
        current_site.save(
            {
                "key": key,
                "type": {"key": "/type/work"},
                "title": f"{title} {position}",
                # An explicit no-cover marker avoids an unrelated Solr lookup.
                "covers": [-1],
                "series": [{"series": {"key": series}, "position": position}],
            }
        )


def test_series_seeds_route_uses_real_request_helpers(series_client, mock_site, monkeypatch):
    save_series(mock_site, "Current")
    monkeypatch.setattr("openlibrary.utils.request_context.create_site", lambda: mock_site)

    response = series_client.get("/series/OL1L/seeds.json")

    assert response.status_code == 200
    data = response.json()
    assert data["links"] == {"self": "/series/OL1L/seeds", "list": "/series/OL1L"}
    assert data["size"] == 2
    assert [(entry["url"], entry["title"]) for entry in data["entries"]] == [
        ("/works/OL2W", "Current 1"),
        ("/works/OL1W", "Current 2"),
    ]


def test_series_seeds_route_uses_each_requests_site(series_client, mock_site, monkeypatch):
    other_site = MockSite()
    save_series(mock_site, "First")
    save_series(other_site, "Second")
    sites = iter([mock_site, other_site])
    monkeypatch.setattr("openlibrary.utils.request_context.create_site", lambda: next(sites))

    responses = [series_client.get("/series/OL1L/seeds.json") for _ in range(2)]

    assert [response.status_code for response in responses] == [200, 200]
    assert [[entry["title"] for entry in response.json()["entries"]] for response in responses] == [
        ["First 1", "First 2"],
        ["Second 1", "Second 2"],
    ]
