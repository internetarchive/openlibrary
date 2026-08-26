"""Proxy module for forwarding requests from FastAPI to web.py during local development."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

import httpx
from fastapi.responses import StreamingResponse

from openlibrary.utils.async_utils import cache_per_event_loop

if TYPE_CHECKING:
    from fastapi import Request, Response

get_async_session = cache_per_event_loop(functools.partial(httpx.AsyncClient, follow_redirects=False, timeout=60.0))


async def proxy_to_webpy(request: Request) -> Response:
    """Forward request to web.py on http://web:8080."""
    url = f"http://web:8080{request.url.path}?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    # Stream the request body to web.py as it arrives instead of buffering it,
    # and stream the response back to the client chunk by chunk.
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

    location = resp.headers.get("location", "")
    if location:
        location = location.replace("http://web:8080", f"http://{request.headers.get('host', 'localhost:8080')}")
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
