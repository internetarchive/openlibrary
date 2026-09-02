"""Proxy module for forwarding requests from FastAPI to web.py during local development."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from fastapi.responses import StreamingResponse

from openlibrary.utils.async_utils import cache_per_event_loop

if TYPE_CHECKING:
    from fastapi import Request, Response

# This timeout would set a global OpenLibrary timeout for all requests, which this code shouldn't handle.
get_async_session = cache_per_event_loop(lambda: httpx.AsyncClient(follow_redirects=False, timeout=None))


async def proxy_to_webpy(request: Request) -> Response:
    """Forward request to web.py on http://web:8080."""
    url = f"http://web:8080{request.url.path}?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    client = get_async_session()
    resp = await client.send(
        client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=request.stream(),
            cookies=request.cookies,
        ),
        stream=True,
    )

    filtered_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "transfer-encoding", "content-length", "x-served-by")}
    filtered_headers["X-Proxied-By"] = "FastAPI"
    filtered_headers["X-Served-By"] = "web.py"

    if location := resp.headers.get("location", ""):
        # web.py builds absolute redirects from the Host header + wsgi.url_scheme
        # (X-Scheme), which we forward, so it may emit http:// or https://web:8080.
        # Rewrite both to the client-facing origin, e.g. https://testing.openlibrary.org.
        client_scheme = request.headers.get("x-forwarded-proto") or request.headers.get("x-scheme") or request.url.scheme
        client_origin = f"{client_scheme}://{request.headers.get('host', 'localhost:8080')}"
        location = location.replace("http://web:8080", client_origin).replace("https://web:8080", client_origin)
        filtered_headers["location"] = location

    async def stream_body():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            # The response is consumed after this handler returns, so it must
            # stay alive via the closure until then. The client is shared
            # (per-event-loop) and must not be closed here.
            await resp.aclose()

    return StreamingResponse(stream_body(), status_code=resp.status_code, headers=filtered_headers)
