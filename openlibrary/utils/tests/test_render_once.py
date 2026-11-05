import asyncio
from contextvars import Context

import anyio
import pytest
import web
from starlette.requests import Request

from openlibrary.plugins.upstream.utils import render_once
from openlibrary.utils import request_context


@pytest.fixture
def start_request(mock_site, monkeypatch):
    old_ctx = dict(web.ctx)
    monkeypatch.setattr(request_context, "create_site", lambda: mock_site)
    monkeypatch.setattr(web, "input", lambda **kwargs: web.storage(kwargs))
    monkeypatch.setattr(web, "cookies", web.storage)

    def start(kind):
        if kind == "fastapi":
            request = Request({"type": "http", "headers": [], "query_string": b""})
            request.state.lang = "en"
            request_context.set_context_from_fastapi(request)
        else:
            web.ctx.site = mock_site
            web.ctx.env = web.storage()
            request_context.set_context_from_legacy_web_py()

    yield start
    web.ctx.clear()
    web.ctx.update(old_ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["fastapi", "webpy"])
async def test_render_once_resets_for_each_request(start_request, kind):
    for _ in range(2):
        start_request(kind)
        assert render_once("dialog") is True
        assert render_once("dialog") is False
        assert render_once("another-dialog") is True
        assert render_once("another-dialog") is False


@pytest.mark.asyncio
async def test_render_once_isolates_interleaved_requests(start_request):
    ready = asyncio.Event()

    async def first_request():
        start_request("fastapi")
        first = render_once("dialog")
        await ready.wait()
        return first, render_once("dialog")

    async def second_request():
        start_request("fastapi")
        first = render_once("dialog")
        ready.set()
        return first, render_once("dialog")

    assert await asyncio.gather(first_request(), second_request()) == [(True, False), (True, False)]


@pytest.mark.asyncio
async def test_render_once_shares_request_state_with_worker(start_request):
    start_request("fastapi")
    assert render_once("parent") is True

    def worker():
        return render_once("parent"), render_once("worker")

    assert await anyio.to_thread.run_sync(worker) == (False, True)
    assert render_once("worker") is False


@pytest.mark.asyncio
async def test_render_once_supports_calls_without_request_setup(start_request):
    def render():
        return render_once("standalone"), render_once("standalone")

    assert Context().run(render) == (True, False)
