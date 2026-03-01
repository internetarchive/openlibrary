from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import Response

router = APIRouter()

ALLOWED_FILES = frozenset({"donate.js", "athena.js"})
UPSTREAM_BASE = "https://archive.org/includes/"
CACHE_MAX_AGE = 86400


@router.get("/cdn/archive.org/{filename}")
async def ia_js_cdn(filename: Annotated[str, Path()]) -> Response:
    """Proxy Internet Archive JS files."""
    if filename not in ALLOWED_FILES:
        raise HTTPException(status_code=404)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.get(UPSTREAM_BASE + filename)
            upstream.raise_for_status()  # upstream 4xx/5xx → 502 (intentional: upstream problem)
    except (httpx.HTTPStatusError, httpx.RequestError):
        # HTTPStatusError: upstream returned 4xx/5xx (including 404 — upstream problem, not bad path)
        # RequestError:    network failure — timeout, DNS error, connection refused
        raise HTTPException(status_code=502, detail="Upstream fetch failed")

    return Response(
        content=upstream.content,  # raw bytes — faithful proxy, avoids charset issues
        media_type="text/javascript",
        headers={"Cache-Control": f"max-age={CACHE_MAX_AGE}"},
    )
