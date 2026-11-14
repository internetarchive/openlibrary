import json
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from openlibrary import asgi_app
from openlibrary.core import infobase_async
from openlibrary.core.env import get_ol_env


@pytest.fixture
def fetch_document(monkeypatch):
    monkeypatch.setattr(asgi_app, "get_redirect_location", infobase_async.get_redirect_location)
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(infobase_async, "fetch_val", fetch)
    return fetch


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("/target", "https://testserver/target"),
        ("sibling", "https://testserver/nested/sibling"),
        ("https://example.org/slides?q=1", "https://example.org/slides?q=1"),
        ("//example.org/path", "https://testserver//example.org/path"),
    ],
)
def test_redirect_location(fastapi_client, fetch_document, method, location, expected):
    fetch_document.return_value = json.dumps({"location": location})
    response = fastapi_client.request(
        method, "/nested/short", headers={"X-Scheme": "https", "Accept": "application/json;q=0.5, text/html"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == expected
    fetch_document.assert_awaited_once()
    assert fetch_document.await_args.args[1] == {"key": "/nested/short"}


@pytest.mark.parametrize("location", ["http://example.org", "://example.org", "", None])
def test_unusable_location(fastapi_client, fetch_document, location):
    fetch_document.return_value = json.dumps({"location": location})
    response = fastapi_client.get("/short", follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers


@pytest.mark.parametrize(
    ("local_dev", "deployment", "host", "status"),
    [
        (True, "development", "localhost", 200),
        (False, "testing", "testing.openlibrary.org", 200),
        (False, "testing", "staging.openlibrary.org", 200),
        (False, "testing", "example.org", 404),
        (False, "production", "openlibrary.org", 404),
    ],
)
def test_non_redirect_fallback(monkeypatch, fetch_document, local_dev, deployment, host, status):
    monkeypatch.setattr(get_ol_env(), "LOCAL_DEV", local_dev)
    monkeypatch.setattr(asgi_app, "get_deployment_name", lambda: deployment)
    monkeypatch.setattr(asgi_app, "set_context_from_fastapi", lambda request: None)
    proxy = AsyncMock(return_value=Response("legacy page"))
    monkeypatch.setattr(asgi_app.proxy, "proxy_to_webpy", proxy)
    client = TestClient(asgi_app.create_app(), base_url=f"http://{host}")
    assert client.get("/wiki-page").status_code == status
    assert proxy.await_count == int(status == 200)
    assert client.get("/wiki-page", headers={"X-Proxied-By": "FastAPI"}).status_code == 404
    assert proxy.await_count == int(status == 200)


@pytest.mark.parametrize(
    ("method", "suffix", "headers"),
    [
        ("GET", "?m=edit", {}),
        ("GET", "?v=1", {}),
        ("POST", "", {}),
        ("GET", "", {"Accept": "text/html;q=0.5, application/json"}),
        ("HEAD", "", {"Content-Type": "application/json"}),
        ("GET", ".json", {}),
    ],
)
def test_other_modes_still_proxy(monkeypatch, fetch_document, method, suffix, headers):
    monkeypatch.setattr(get_ol_env(), "LOCAL_DEV", True)
    monkeypatch.setattr(asgi_app, "set_context_from_fastapi", lambda request: None)
    proxy = AsyncMock(return_value=Response("legacy handler"))
    monkeypatch.setattr(asgi_app.proxy, "proxy_to_webpy", proxy)
    client = TestClient(asgi_app.create_app())
    assert client.request(method, "/short" + suffix, headers=headers).status_code == 200
    proxy.assert_awaited_once()
    fetch_document.assert_not_awaited()
