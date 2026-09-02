"""Proxy module for forwarding requests from FastAPI to web.py during local development."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi.responses import StreamingResponse

from openlibrary.utils.async_utils import cache_per_event_loop

if TYPE_CHECKING:
    from fastapi import Request, Response

# web.py's host as the proxy addresses it (see the upstream URL below).
WEBPY_NETLOC = "web:8080"

# This timeout would set a global OpenLibrary timeout for all requests, which this code shouldn't handle.
get_async_session = cache_per_event_loop(lambda: httpx.AsyncClient(follow_redirects=False, timeout=None))


def _rebase_redirect(location: str, client_scheme: str, client_netloc: str) -> str:
    """Rebase a Location that points at web.py's internal origin onto the public one.

    Only the scheme and netloc are swapped, so URLs whose authority is not exactly
    web.py's are returned untouched. In particular, "web:8080" appearing in a path
    or query param is left alone, as are lookalike hosts like web:8080.evil.com
    (rebasing those would hand out a redirect to an attacker's domain).
    """
    parts = urlsplit(location)
    if parts.netloc.lower() != WEBPY_NETLOC or parts.scheme not in ("http", "https"):
        return location
    return urlunsplit(parts._replace(scheme=client_scheme, netloc=client_netloc))


async def proxy_to_webpy(request: Request) -> Response:
    """Forward request to web.py on http://web:8080."""
    url = f"http://{WEBPY_NETLOC}{request.url.path}?{request.url.query}"

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
        # Rebase both onto the client-facing origin, e.g. https://testing.openlibrary.org.
        client_scheme = request.headers.get("x-forwarded-proto") or request.headers.get("x-scheme") or request.url.scheme
        location = _rebase_redirect(location, client_scheme, request.headers.get("host", "localhost:8080"))
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
