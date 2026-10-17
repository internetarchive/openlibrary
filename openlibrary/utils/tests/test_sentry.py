"""Check the tags on actual Sentry envelopes without sending them over the network."""

import asyncio
from copy import deepcopy

import httpx
import pytest
import sentry_sdk
import web
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.transport import Transport

from infogami import config
from openlibrary import asgi_app
from openlibrary.fastapi import proxy
from openlibrary.utils.sentry import InfogamiSentryProcessor, Sentry, WebPySentryProcessor


class RecordingTransport(Transport):
    def __init__(self):
        super().__init__()
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type in {"event", "transaction"}:
                self.events.append(deepcopy(item.payload.json))


@pytest.fixture
def sentry_events():
    transport = RecordingTransport()
    global_scope = sentry_sdk.get_global_scope()
    previous_client = global_scope.client
    with sentry_sdk.isolation_scope() as scope, sentry_sdk.new_scope():
        sentry_sdk.init(
            # A dummy DSN enables capture; RecordingTransport never sends to it.
            dsn="http://test@localhost/1",
            transport=transport,
            traces_sample_rate=1.0,
            default_integrations=False,
            auto_enabling_integrations=False,
            enable_backpressure_handling=False,
            integrations=[FastApiIntegration(), StarletteIntegration()],
        )
        client = global_scope.client
        scope.set_client(client)
        try:
            yield transport.events
        finally:
            client.close()
            global_scope.set_client(previous_client)


@pytest.mark.parametrize("capture_method", [None, "capture_exception_webpy", "capture_exception"])
@pytest.mark.parametrize("infogami", [True, False])
def test_webpy_server_tags(sentry_events, monkeypatch, capture_method, infogami):
    sentry = Sentry({})

    class Page:
        def GET(self):
            if capture_method:
                try:
                    raise ValueError("test error")
                except ValueError as exc:
                    if capture_method == "capture_exception_webpy":
                        sentry.capture_exception_webpy()
                    else:
                        sentry.capture_exception(exc)
                raise web.HTTPError("500 Internal Server Error", data="test error")
            return "ok"

    app = web.application(("/", "Page"), {"Page": Page})
    processor = InfogamiSentryProcessor if infogami else WebPySentryProcessor
    monkeypatch.setattr(processor, "find_route_name", lambda self: "/")
    app.add_processor(processor(app))

    response = app.request("/")

    assert response.status.startswith("500" if capture_method else "200")
    assert len(sentry_events) == (2 if capture_method else 1)
    for event in sentry_events:
        tags = event.get("tags", {})
        if infogami:
            assert tags["server"] == "webpy"
        else:
            assert "server" not in tags
    assert any(event.get("type") == "transaction" for event in sentry_events)
    assert "server" not in sentry_sdk.get_isolation_scope()._tags


@pytest.fixture
def tagged_fastapi_app(monkeypatch, sentry_events, local_dev):
    # Exercise the real startup tag calls without loading the legacy app or services.
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(asgi_app, "_setup_env", lambda: None)
    monkeypatch.setattr(asgi_app, "_load_legacy_wsgi", lambda: None)
    monkeypatch.setattr(asgi_app, "_include_routers", lambda app: None)
    monkeypatch.setattr(asgi_app, "set_context_from_fastapi", lambda request: None)
    monkeypatch.setattr(asgi_app, "setup_i18n", lambda app: None)
    monkeypatch.setattr(asgi_app, "init_sentry", lambda cfg: Sentry({}))
    monkeypatch.setattr(asgi_app, "sentry", None)
    monkeypatch.setattr(config, "server_timing", False, raising=False)
    with monkeypatch.context() as startup_patch:
        startup_patch.delitem(asgi_app.sys.modules, "pytest")
        return asgi_app.create_app()


def test_fastapi_tags_transactions_and_errors(tagged_fastapi_app, sentry_events):
    # Insert before the fallback route so this is a native FastAPI endpoint.
    router = APIRouter()

    @router.get("/error")
    async def error():
        raise ValueError("fastapi test error")

    tagged_fastapi_app.router.routes[0:0] = router.routes
    client = TestClient(tagged_fastapi_app, raise_server_exceptions=False)
    try:
        assert client.get("/health").status_code == 200
        assert client.get("/error").status_code == 500
    finally:
        client.close()

    assert len(sentry_events) == 3
    for event in sentry_events:
        assert event["tags"]["server"] == "fastapi"
        assert event["tags"]["fastapi"] is True
        assert "proxied" not in event["tags"]
    assert any("exception" in event for event in sentry_events)


@pytest.mark.asyncio
@pytest.mark.parametrize("upstream_error", [False, True])
async def test_proxy_tags_do_not_leak(tagged_fastapi_app, sentry_events, monkeypatch, upstream_error):
    async def upstream(request):
        if upstream_error:
            raise httpx.ConnectError("upstream unavailable")
        return httpx.Response(200, content=b"web.py page")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=tagged_fastapi_app, raise_app_exceptions=False), base_url="http://test") as client,
    ):
        monkeypatch.setattr(proxy, "get_async_session", lambda: upstream_client)
        assert (await client.get("/legacy")).status_code == (500 if upstream_error else 200)
        assert (await client.get("/health")).status_code == 200

    proxied_events = [event for event in sentry_events if event["transaction"] == "/{path:path}"]
    native_events = [event for event in sentry_events if event["transaction"] == "/health"]
    assert len(proxied_events) == (2 if upstream_error else 1)
    assert len(native_events) == 1
    for event in proxied_events:
        assert event["tags"]["server"] == "fastapi"
        assert event["tags"]["proxied"] is True
    assert "proxied" not in native_events[0]["tags"]


@pytest.mark.asyncio
async def test_concurrent_proxy_and_native_requests_are_isolated(tagged_fastapi_app, sentry_events, monkeypatch):
    proxy_started = asyncio.Event()
    release_proxy = asyncio.Event()

    async def upstream(request):
        proxy_started.set()
        await release_proxy.wait()
        return httpx.Response(200, content=b"web.py page")

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=tagged_fastapi_app), base_url="http://test") as client,
    ):
        monkeypatch.setattr(proxy, "get_async_session", lambda: upstream_client)
        async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
            proxied_request = tasks.create_task(client.get("/legacy"))
            await proxy_started.wait()
            try:
                assert (await client.get("/health")).status_code == 200
            finally:
                release_proxy.set()
        assert proxied_request.result().status_code == 200

    transactions = {event["transaction"]: event for event in sentry_events}
    assert transactions["/{path:path}"]["tags"]["proxied"] is True
    assert "proxied" not in transactions["/health"]["tags"]


@pytest.mark.asyncio
async def test_proxy_stream_errors_keep_request_tags(tagged_fastapi_app, sentry_events, monkeypatch):
    class FailingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial page"
            raise httpx.ReadError("upstream stream interrupted")

    async def upstream(request):
        return httpx.Response(200, stream=FailingStream())

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=tagged_fastapi_app, raise_app_exceptions=False), base_url="http://test") as client,
    ):
        monkeypatch.setattr(proxy, "get_async_session", lambda: upstream_client)
        # Headers were already sent before the upstream body failed.
        assert (await client.get("/legacy")).status_code == 200
        assert (await client.get("/health")).status_code == 200

    errors = [event for event in sentry_events if "exception" in event]
    assert len(errors) == 1
    assert errors[0]["tags"]["server"] == "fastapi"
    assert errors[0]["tags"]["proxied"] is True
    native_event = next(event for event in sentry_events if event["transaction"] == "/health")
    assert "proxied" not in native_event["tags"]


def test_rejected_fallback_is_not_tagged_as_proxied(tagged_fastapi_app, sentry_events):
    client = TestClient(tagged_fastapi_app)
    try:
        response = client.get("/legacy", headers={"X-Proxied-By": "FastAPI"})
    finally:
        client.close()

    assert response.status_code == 404
    assert len(sentry_events) == 1
    assert sentry_events[0]["tags"]["server"] == "fastapi"
    assert "proxied" not in sentry_events[0]["tags"]
