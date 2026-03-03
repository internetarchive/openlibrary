"""Tests for FastAPI static asset serving."""


def test_static_assets_are_served(fastapi_client):
    response = fastapi_client.get("/static/robots.txt")

    assert response.status_code == 200
    assert "User-agent" in response.text


def test_missing_static_asset_returns_404(fastapi_client):
    response = fastapi_client.get("/static/does-not-exist.txt")

    assert response.status_code == 404
