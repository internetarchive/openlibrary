import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import infogami
from infogami.utils import stats
from openlibrary.fastapi.middleware.server_timing import ServerTimingMiddleware
from openlibrary.utils import server_timing
from openlibrary.utils.tests.test_server_timing import parse


@pytest.fixture(scope="module")
def app():
    server_timing.install_legacy_bridge()
    app = FastAPI()
    both_inside = asyncio.Barrier(2)

    @app.get("/async")
    async def async_endpoint():
        with server_timing.timed("solr"):
            await asyncio.sleep(0.01)
        return {}

    @app.get("/sync")
    def sync_endpoint():  # runs in the threadpool, like legacy infobase/memcache code
        stats.begin("memcache.get")
        stats.end()
        return {}

    @app.get("/concurrent/{name}")
    async def concurrent(name: str):
        with server_timing.timed(name):
            await asyncio.wait_for(both_inside.wait(), timeout=5)
        return {}

    @app.get("/existing")
    def existing():
        return Response(headers={"Server-Timing": "cdn;dur=1"})

    @app.get("/stream")
    def stream():
        return StreamingResponse(iter([b"a", b"b"]))

    app.add_middleware(ServerTimingMiddleware)
    return app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as client:
        yield client


def test_async_and_threadpool_endpoints(client):
    metrics = parse(client.get("/async").headers["Server-Timing"])
    assert float(metrics["solr"]["dur"]) >= 10
    assert float(metrics["total"]["dur"]) >= float(metrics["solr"]["dur"])
    client.get("/sync")
    assert parse(client.get("/sync").headers["Server-Timing"])["memcache"]["desc"] == '"1 call"'  # fresh per request


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_mix(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        a, b = await asyncio.gather(c.get("/concurrent/alpha"), c.get("/concurrent/beta"))
    assert set(parse(a.headers["Server-Timing"])) == {"total", "alpha"}
    assert set(parse(b.headers["Server-Timing"])) == {"total", "beta"}


def test_keeps_existing_header_and_streams(client):
    assert client.get("/existing").headers.get_list("Server-Timing")[0] == "cdn;dur=1"
    resp = client.get("/stream")
    assert resp.content == b"ab"
    assert "total" in parse(resp.headers["Server-Timing"])


def test_header_failure_does_not_break_response(client):
    with patch.object(server_timing, "format_header", side_effect=ValueError):
        resp = client.get("/async")
    assert resp.status_code == 200
    assert "Server-Timing" not in resp.headers


def test_real_app(fastapi_client):
    assert "total" in parse(fastapi_client.get("/health").headers["Server-Timing"])


def test_real_app_can_turn_it_off():
    from openlibrary.asgi_app import create_app  # noqa: PLC0415

    with patch.object(infogami.config, "server_timing", False, create=True), patch("openlibrary.asgi_app.set_context_from_fastapi", lambda request: None):
        resp = TestClient(create_app()).get("/health")
    assert "Server-Timing" not in resp.headers
