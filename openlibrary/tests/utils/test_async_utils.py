"""Regression coverage for cache_per_event_loop.

Sharing one httpx.AsyncClient between AsyncBridge's loop and another loop
fails once a pooled keep-alive connection faces real read contention. The
connection binds to the first loop and later reuse raises RuntimeError. These
tests need a real local HTTP/1.1 server. A mocked transport skips the socket
code and never reproduces it.
"""

import asyncio
import functools
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from openlibrary.utils.async_utils import AsyncBridge, cache_per_event_loop

# ``no_sleep`` patches time.sleep process-wide. Save the real one so the test server can delay reads.
_real_sleep = time.sleep


class _KeepAliveHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        _real_sleep(0.02)
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
    bridge = AsyncBridge()
    client = httpx.AsyncClient(limits=httpx.Limits(max_connections=2))
    try:
        bridge.run(_burst(client, keep_alive_server, 3))

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


def test_bridge_rejects_nested_run_from_its_own_loop():
    bridge = AsyncBridge()

    async def nested_run():
        with pytest.raises(RuntimeError, match="own event loop"):
            bridge.run(asyncio.sleep(0))

    bridge.run(nested_run())


async def _call(get_client):
    return get_client()
