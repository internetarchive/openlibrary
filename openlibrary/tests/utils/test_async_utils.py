"""Regression coverage for cache_per_event_loop (openlibrary.utils.async_utils).

A single process-wide httpx.AsyncClient is unsafe to share between
AsyncBridge's persistent background-thread event loop and a caller running on
a different event loop (e.g. FastAPI's): httpx/httpcore/anyio lazily bind a
plain asyncio.Event to whichever event loop is running the first time a
pooled connection is genuinely contended for, and reusing that connection
from another loop later raises `RuntimeError: ... is bound to a different
event loop`.

This only reproduces with a real, kept-alive HTTP/1.1 connection under
genuine read contention -- a mocked transport bypasses the real socket code
entirely -- so these tests spin up an actual local HTTP/1.1 server.
"""

import asyncio
import functools
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from openlibrary.utils.async_utils import AsyncBridge, cache_per_event_loop

# openlibrary/conftest.py's `no_sleep` autouse fixture monkeypatches `time.sleep`
# process-wide (including this handler's server thread) to catch slow tests.
# Capturing the real function at import time, before that fixture runs, lets
# the local test server use a genuine short delay to force a real cross-loop
# read race, which is the whole point of this test.
_real_sleep = time.sleep


class _KeepAliveHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # enable keep-alive so httpx pools/reuses the connection

    def do_GET(self):
        _real_sleep(0.02)  # force the client's read() to genuinely await, not just poll a buffer
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def keep_alive_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _KeepAliveHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()


async def _burst(client: httpx.AsyncClient, url: str, n: int) -> list[httpx.Response]:
    return await asyncio.gather(*[client.get(url, timeout=5) for _ in range(n)])


@pytest.mark.asyncio
async def test_sharing_one_async_client_across_loops_fails(keep_alive_server):
    """Documents the bug cache_per_event_loop exists to fix."""
    bridge = AsyncBridge()
    client = httpx.AsyncClient(limits=httpx.Limits(max_connections=2))
    try:
        # Contending for a pooled keep-alive connection on the bridge's loop
        # binds that connection's internal lock/event to it.
        bridge.run(_burst(client, keep_alive_server, 3))

        # Reusing the same (now loop-bound) pooled connection with genuine
        # contention on *this* loop trips the cross-loop RuntimeError.
        with pytest.raises(RuntimeError, match="different event loop"):
            await _burst(client, keep_alive_server, 3)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cache_per_event_loop_avoids_cross_loop_reuse(keep_alive_server):
    bridge = AsyncBridge()
    get_client = cache_per_event_loop(functools.partial(httpx.AsyncClient, limits=httpx.Limits(max_connections=2)))

    async def hit_via_cache():
        return await _burst(get_client(), keep_alive_server, 3)

    # Same sequence as the failing test above, but every call goes through
    # get_client(), so the bridge loop and this loop each get their own client.
    bridge.run(hit_via_cache())
    responses = await hit_via_cache()
    assert all(r.status_code == 200 for r in responses)


@pytest.mark.asyncio
async def test_cache_per_event_loop_returns_distinct_values_per_loop():
    get_client = cache_per_event_loop(httpx.AsyncClient)
    bridge = AsyncBridge()

    main_client = get_client()
    bridge_client = bridge.run(_call(get_client))

    assert main_client is not bridge_client
    assert get_client() is main_client  # stable within the same loop


async def _call(get_client):
    return get_client()
