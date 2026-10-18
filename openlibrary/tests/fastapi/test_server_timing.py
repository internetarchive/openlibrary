import asyncio
from unittest.mock import patch

import anyio
import httpx
import pytest
import web
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import infogami
from infogami.utils import stats
from openlibrary.asgi_app import create_app
from openlibrary.fastapi.middleware.server_timing import add_server_timing
from openlibrary.utils import server_timing
from openlibrary.utils.async_utils import async_bridge
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

    @app.get("/crash")
    def crash():
        with server_timing.timed("solr"):
            raise TimeoutError

    add_server_timing(app)
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


def test_sends_timings_to_statsd(client):
    with patch("openlibrary.core.stats.put") as put:
        client.get("/async")
        client.get("/static/x.css")  # not an app endpoint; skipped
    assert {c.args[0] for c in put.call_args_list} == {"ol.fastapi.total", "ol.fastapi.solr"}
    assert put.call_count == 2


def test_real_app_on_by_default_and_can_be_turned_off(fastapi_client):
    assert "total" in parse(fastapi_client.get("/health").headers["Server-Timing"])
    with patch.object(infogami.config, "server_timing", False, create=True), patch("openlibrary.asgi_app.set_context_from_fastapi", lambda request: None):
        resp = TestClient(create_app()).get("/health")
    assert "Server-Timing" not in resp.headers


@pytest.mark.parametrize("timing_enabled", [False, True])
@pytest.mark.parametrize("execution", ["async", "sync", "threadpool", "async-bridge"])
def test_real_app_does_not_retain_legacy_statistics(monkeypatch, timing_enabled, execution):
    monkeypatch.setattr(infogami.config, "server_timing", timing_enabled, raising=False)
    monkeypatch.setattr("openlibrary.asgi_app.set_context_from_fastapi", lambda request: None)
    app = create_app()

    def record_stats():
        before = len(web.ctx.get("stats", []))
        for _ in range(3):
            stats.begin("infobase")
            stats.end()
        return {"before": before, "after": len(web.ctx.get("stats", []))}

    async def async_record_stats():
        return record_stats()

    if execution == "sync":
        app.get("/legacy-stats")(record_stats)
    elif execution == "async-bridge":

        @app.get("/legacy-stats")
        def bridged_endpoint():
            return async_bridge.run(async_record_stats())

    else:

        @app.get("/legacy-stats")
        async def async_endpoint():
            if execution == "threadpool":
                return await anyio.to_thread.run_sync(record_stats)
            return record_stats()

    with patch("openlibrary.core.stats.put") as put, TestClient(app) as client:
        for _ in range(10):
            response = client.get("/legacy-stats")
            assert response.status_code == 200
            history = response.json()
            assert history["after"] == history["before"]
            if timing_enabled:
                assert parse(response.headers["Server-Timing"])["infobase"]["desc"] == '"3 calls"'
            else:
                assert "Server-Timing" not in response.headers
        if timing_enabled:
            assert {call.args[0] for call in put.call_args_list} == {"ol.fastapi.total", "ol.fastapi.infobase"}
        else:
            put.assert_not_called()


def test_unhandled_exception_500_has_the_header(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/crash")
    assert response.status_code == 500
    assert parse(response.headers["Server-Timing"])["solr"]["desc"] == '"1 call (1 failed)"'
