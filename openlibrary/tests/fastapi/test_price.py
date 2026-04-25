from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.fastapi.internal.api import router


# Create a minimal FastAPI app just for testing this router
app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_price_api_missing_params():
    """Should return error when neither isbn nor asin is supplied."""
    resp = client.get("/prices.json")
    assert resp.status_code == 200
    assert resp.json()["error"] == "isbn or asin required"


def test_price_api_with_isbn(monkeypatch):
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

    resp = client.get("/prices.json?isbn=0765319853")
    assert resp.status_code == 200
    data = resp.json()
    assert data["amazon"] == fake_amazon
    assert data["betterworldbooks"] == fake_bwb


def test_price_api_with_asin(monkeypatch):
    """ASIN should skip BWB lookup entirely."""
    fake_amazon = {"price": "$15.00"}

    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_amazon_metadata",
        lambda *a, **kw: fake_amazon,
    )

    resp = client.get("/prices.json?asin=B0001234")
    assert resp.status_code == 200
    data = resp.json()
    assert data["amazon"] == fake_amazon
    assert data["betterworldbooks"] == {}


def test_price_api_isbn10_bwb_fallback(monkeypatch):
    """When isbn_10 gives no BWB price, should retry with isbn_13."""
    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_amazon_metadata",
        lambda *a, **kw: {},
    )
    # First call returns no price, second call returns a price
    bwb_mock = AsyncMock(side_effect=[{"price": None}, {"price": "$3.00 (used)"}])
    monkeypatch.setattr(
        "openlibrary.fastapi.internal.api.get_betterworldbooks_metadata_async",
        bwb_mock,
    )

    resp = client.get("/prices.json?isbn=0765319853")  # isbn-10
    assert resp.status_code == 200
    data = resp.json()
    # The fallback isbn-13 result should be used
    assert data["betterworldbooks"]["price"] == "$3.00 (used)"
