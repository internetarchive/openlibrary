from __future__ import annotations

import base64
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import Response

from infogami import config
from openlibrary.core import cache

router = APIRouter()

ALLOWED_FILES = frozenset({"donate.js", "athena.js"})
UPSTREAM_BASE = "https://archive.org/includes/"
CACHE_MAX_AGE = 86400

# Graphite lives inside the Internet Archive's network and is unreachable from
# the public internet, so the browser must never load it directly (see
# internetarchive/openlibrary#12823). We fetch the charts server-side instead
# and cache the result, so a Graphite outage surfaces as a quick 502 rather
# than a request that hangs in the visitor's browser.
#
# Reuse the config-driven host that the admin graphs already read
# (plugins/admin/graphs.py), keeping the historical value as the default.
GRAPHITE_BASE_URL = config.get("graphite_base_url") or "http://graphite.us.archive.org"
GRAPHITE_RENDER_URL = f"{GRAPHITE_BASE_URL.rstrip('/')}/render"
GRAPHITE_TIMEOUT = 5.0
GRAPHITE_CACHE_SECONDS = 300

# Allowlist of named charts, each pinned to a fixed upstream query. The client
# only ever supplies the name, never Graphite parameters, so this cannot be
# abused as an open proxy or an SSRF vector into the internal network.
GRAPHS: dict[str, dict[str, str]] = {
    "unique-visitors": {
        "min": "0",
        "template": "plain",
        "lineMode": "staircase",
        "areaMode": "stacked",
        "areaAlpha": "0.5",
        "yAxisSide": "right",
        "title": "openlibrary   Unique IPs per day   (uip_openlibrary)",
        "hideLegend": "true",
        "target": 'cactiStyle(alias(summarize(sumSeries(group(stats.uniqueips.openlibrary)),"1day"),"openlibrary   Unique IPs per day   (uip_openlibrary)"))',
        "colorList": "00ff00",
        "height": "200",
        "width": "900",
        "from": "-60days",
    },
    "borrows-3-months": {
        "target": 'hitcount(stats.ol.loans.bookreader,"1d")',
        "from": "-3months",
        "tz": "UTC",
        "width": "900",
    },
    "borrows-2-years": {
        "target": 'hitcount(stats.ol.loans.bookreader,"1d")',
        "from": "-24months",
        "tz": "UTC",
        "width": "900",
    },
}


async def _fetch_graphite_graph(params: dict[str, str]) -> str | None:
    """Fetch one Graphite chart as a base64 PNG, or None on failure.

    Returning None (instead of raising) lets ``singleflight_cache`` cache the
    failure too, so an outage doesn't trigger a fresh upstream fetch per request.
    """
    try:
        async with httpx.AsyncClient(timeout=GRAPHITE_TIMEOUT) as client:
            upstream = await client.get(GRAPHITE_RENDER_URL, params=params)
            upstream.raise_for_status()  # upstream 4xx/5xx → 502 (upstream problem)
    except httpx.HTTPStatusError, httpx.RequestError:
        return None
    return base64.b64encode(upstream.content).decode("ascii")


@router.get("/cdn/graphite/{name}")
async def graphite_graph(name: Annotated[str, Path()]) -> Response:
    """Proxy and cache a Graphite chart for the /stats page."""
    if name not in GRAPHS:
        raise HTTPException(status_code=404)

    encoded = await cache.singleflight_cache(
        f"cdn.graphite.{name}",
        lambda: _fetch_graphite_graph(GRAPHS[name]),
        ttl=GRAPHITE_CACHE_SECONDS,
    )
    if encoded is None:
        raise HTTPException(status_code=502, detail="Upstream fetch failed")

    return Response(
        content=base64.b64decode(encoded),
        media_type="image/png",
        headers={"Cache-Control": f"public, max-age={GRAPHITE_CACHE_SECONDS}"},
    )


@router.get("/cdn/archive.org/{filename}")
async def ia_js_cdn(filename: Annotated[str, Path()]) -> Response:
    """Proxy Internet Archive JS files."""
    if filename not in ALLOWED_FILES:
        raise HTTPException(status_code=404)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.get(UPSTREAM_BASE + filename)
            upstream.raise_for_status()  # upstream 4xx/5xx → 502 (intentional: upstream problem)
    except httpx.HTTPStatusError, httpx.RequestError:
        # HTTPStatusError: upstream returned 4xx/5xx (including 404 — upstream problem, not bad path)
        # RequestError:    network failure — timeout, DNS error, connection refused
        raise HTTPException(status_code=502, detail="Upstream fetch failed")

    return Response(
        content=upstream.content,  # raw bytes — faithful proxy, avoids charset issues
        media_type="text/javascript",
        headers={"Cache-Control": f"max-age={CACHE_MAX_AGE}"},
    )
