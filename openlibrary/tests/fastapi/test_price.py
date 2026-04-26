import pytest
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.fastapi.internal.api import get_price_data, router


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient for the internal API router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Endpoint-level tests (thin HTTP wrapper)
# ---------------------------------------------------------------------------


def test_price_api_missing_params(client):
    """Should return error when neither isbn nor asin is supplied."""
    resp = client.get("/prices.json")
    assert resp.status_code == 200
    assert resp.json()["error"] == "isbn or asin required"


def test_price_api_delegates_to_get_price_data(client, monkeypatch):
    """Endpoint should delegate to get_price_data and return its result."""
    fake_result = {"amazon": {"price": "$9.99"}, "betterworldbooks": {}}
    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_price_data",
        AsyncMock(return_value=fake_result),
    )
    resp = client.get("/prices.json?isbn=0765319853")
    assert resp.status_code == 200
    assert resp.json()["amazon"] == {"price": "$9.99"}


# ---------------------------------------------------------------------------
# Business-logic tests (get_price_data directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_data_with_isbn(monkeypatch):
    """Should return amazon and bwb data keyed correctly."""
    fake_amazon = {"price": "$10.00", "title": "Test Book"}
    fake_bwb = {"price": "$5.00 (used)", "isbn": "0765319853"}

    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_amazon_metadata",
        lambda *a, **kw: fake_amazon,
    )
    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_betterworldbooks_metadata_async",
        AsyncMock(return_value=fake_bwb),
    )

    result = await get_price_data(isbn="0765319853", asin="")
    assert result["amazon"] == fake_amazon
    assert result["betterworldbooks"] == fake_bwb


@pytest.mark.asyncio
async def test_get_price_data_with_asin(monkeypatch):
    """ASIN should skip BWB lookup entirely."""
    fake_amazon = {"price": "$15.00"}

    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_amazon_metadata",
        lambda *a, **kw: fake_amazon,
    )

    result = await get_price_data(isbn="", asin="B0001234")
    assert result["amazon"] == fake_amazon
    assert result["betterworldbooks"] == {}


@pytest.mark.asyncio
async def test_get_price_data_isbn10_bwb_fallback(monkeypatch):
    """When isbn_10 gives no BWB price, should retry with isbn_13."""
    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_amazon_metadata",
        lambda *a, **kw: {},
    )
    # First call (isbn-10) returns no price; second call (isbn-13) returns a price
    bwb_mock = AsyncMock(side_effect=[{"price": None}, {"price": "$3.00 (used)"}])
    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_betterworldbooks_metadata_async",
        bwb_mock,
    )

    result = await get_price_data(isbn="0765319853", asin="")  # isbn-10
    assert result["betterworldbooks"]["price"] == "$3.00 (used)"

