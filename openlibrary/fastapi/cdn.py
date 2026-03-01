from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import Response

router = APIRouter()

ALLOWED_FILES = frozenset({"donate.js", "athena.js"})
UPSTREAM_BASE = "https://archive.org/includes/"
CACHE_MAX_AGE = 86400  # 24 hours, mirrors legacy Cache-Control header


@router.get("/cdn/archive.org/{filename}")
async def ia_js_cdn(filename: Annotated[str, Path()]) -> Response:
    """Proxy Internet Archive JS files.

    Mirrors the legacy web.py ``ia_js_cdn`` handler in
    ``openlibrary/plugins/openlibrary/code.py``.

    Only ``donate.js`` and ``athena.js`` are permitted; any other filename
    returns 404.  If the upstream request fails a 502 is returned so callers
    can distinguish a bad path (404) from a transient upstream error (502).

    .. note:: Intentional improvement over legacy behavior

        The legacy ``fetch_ia_js`` function (``code.py``) does not call
        ``raise_for_status()``, so it silently returns HTTP 200 with an HTML
        error page body — even when archive.org responds 4xx/5xx — served as
        ``text/javascript``.  That is a bug, not intentional behavior.  This
        implementation returns 502 Bad Gateway on any upstream failure, which
        is semantically correct.  Happy to revert to exact parity if preferred.
    """
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
