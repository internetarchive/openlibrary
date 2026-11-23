"""Tests for the Book Tag Stats page."""

from datetime import date, timedelta

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from openlibrary.core import admin
from openlibrary.fastapi.stats import pages


@pytest.fixture
def client(site_page_app):
    return TestClient(site_page_app(pages))


def test_tags_stats_uses_saved_counts_and_exact_snapshot_dates(client, monkeypatch):
    today = date.today()
    docs = [{"_key": f"counts-{today - timedelta(days=days)}", "tags": 1} for days in range(365, -1, -1)]
    docs[0]["total_tagged_works"] = {"genres": 2, "awards": 0}
    docs[-29]["total_tagged_works"] = {"genres": 10, "awards": 0}
    docs[-7]["total_tagged_works"] = {"genres": 99}  # Six days ago, not the seven-day baseline.
    docs[-1].update(total_tags=500, total_tagged_works={"genres": 8, "awards": 0})
    monkeypatch.setattr(admin, "get_count_docs", lambda ndays: docs)

    response = client.get("/stats/tags")
    assert response.status_code == 200
    page = BeautifulSoup(response.text, "html.parser")
    assert [card.get_text(strip=True) for card in page.select(".tasks-stats__card-value")] == ["7", "28", "365", "500"]
    assert len(page.select(".tags-stats__chart")) == 4
    rows = {row.th.get_text(strip=True): [cell.get_text(strip=True) for cell in row.find_all("td")] for row in page.select("tbody tr")}
    assert rows["Genres"] == ["8", "—", "-2", "+6"]
    assert rows["Awards"] == ["0", "—", "0", "0"]
    assert len(rows) == 7


def test_tags_stats_handles_old_docs_and_partial_daily_counts(client, monkeypatch):
    today = date.today()
    docs = [{"_key": f"counts-{today - timedelta(days=1)}", "works": 2}, {"_key": f"counts-{today}", "tags": 0}]
    monkeypatch.setattr(admin, "get_count_docs", lambda ndays: docs)

    response = client.get("/stats/tags")
    assert response.status_code == 200
    page = BeautifulSoup(response.text, "html.parser")
    assert [value.get_text(strip=True) for value in page.select(".tasks-stats__card-value")] == ["—"] * 4
    assert [cell.get_text(strip=True) for cell in page.select(".tags-stats tbody td")] == ["—"] * 28
