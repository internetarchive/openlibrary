"""Proxy module for forwarding requests from FastAPI to web.py during local development."""

import httpx
from fastapi import Request, Response


async def proxy_to_webpy(request: Request) -> Response:
    """Forward request to web.py on http://web:8080."""
    url = f"http://web:8080{request.url.path}?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    content = await request.body()

    async with httpx.AsyncClient(follow_redirects=False, timeout=60.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=content,
            cookies=request.cookies,
        )

    filtered_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "transfer-encoding", "content-length", "x-served-by")}
    filtered_headers["X-Proxied-By"] = "FastAPI"
    filtered_headers["X-Served-By"] = "web.py"

    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("location", "")
        location = location.replace("http://web:8080", f"http://{request.headers.get('host', 'localhost:8080')}")
        filtered_headers["location"] = location

    return Response(content=resp.content, status_code=resp.status_code, headers=filtered_headers)
