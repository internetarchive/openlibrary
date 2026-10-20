from __future__ import annotations

import base64
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import Response, StreamingResponse

from infogami import config
from openlibrary.core import cache
from openlibrary.utils.async_utils import cache_per_event_loop

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


# Snippets are stored by iannotate, which has no lookup by id, so the whole
# list is fetched and cached briefly. This is the same backend nginx proxies
# /api/snippets to.
SNIPPETS_API_URL = config.get("snippets_api_url") or "http://ol-home0.us.archive.org:8000/annotations"
SNIPPETS_TIMEOUT = 5.0
SNIPPETS_CACHE_SECONDS = 60
SNIPPET_IMAGE_TIMEOUT = 10.0
SNIPPET_IMAGE_MAX_REDIRECTS = 5
SNIPPET_IMAGE_MAX_AGE = 3600
# Raster only: an SVG served from our origin could run script.
SNIPPET_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})

get_snippet_image_session = cache_per_event_loop(lambda: httpx.AsyncClient(timeout=SNIPPET_IMAGE_TIMEOUT, follow_redirects=False))


def _is_archive_org_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and (host == "archive.org" or host.endswith(".archive.org"))


def snippet_image_url(annotation: dict) -> str | None:
    """The page image for a snippet: its /details/ URL on the /download/ path.

    Annotations are user-submitted and fetched server-side, so only
    archive.org URLs are accepted.
    """
    details_url = annotation.get("annotation") or annotation.get("uri") or ""
    if not _is_archive_org_url(details_url) or "/details/" not in urlsplit(details_url).path:
        return None
    return details_url.replace("/details/", "/download/", 1)


async def _fetch_snippet_image_urls() -> dict[str, str] | None:
    """Map each snippet's id (as a str) to its image URL, or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=SNIPPETS_TIMEOUT) as client:
            upstream = await client.get(SNIPPETS_API_URL)
            upstream.raise_for_status()
            annotations = upstream.json()
    except httpx.HTTPStatusError, httpx.RequestError, ValueError:
        return None
    return {str(a["id"]): url for a in annotations if "id" in a and (url := snippet_image_url(a))}


async def _open_snippet_image(url: str) -> httpx.Response | None:
    """Open a streaming GET for the image, or None if it leaves archive.org.

    /download/ redirects to the item's image server, so redirects are followed
    by hand to keep every hop on archive.org.
    """
    client = get_snippet_image_session()
    for _ in range(SNIPPET_IMAGE_MAX_REDIRECTS + 1):
        upstream = await client.send(client.build_request("GET", url), stream=True)
        if not upstream.is_redirect:
            return upstream
        await upstream.aclose()
        if upstream.next_request is None:
            return None
        url = str(upstream.next_request.url)
        if not _is_archive_org_url(url):
            return None
    return None


@router.get("/cdn/snippets/{annotation_id}")
async def snippet_image(annotation_id: Annotated[int, Path()]) -> Response:
    """Stream the page image of the snippet with this annotation id."""
    urls = await cache.singleflight_cache(
        "cdn.snippets.image_urls",
        _fetch_snippet_image_urls,
        ttl=SNIPPETS_CACHE_SECONDS,
    )
    if urls is None:
        raise HTTPException(status_code=502, detail="Upstream fetch failed")
    if (url := urls.get(str(annotation_id))) is None:
        raise HTTPException(status_code=404)

    try:
        upstream = await _open_snippet_image(url)
    except httpx.RequestError:
        upstream = None
    if upstream is None:
        raise HTTPException(status_code=502, detail="Upstream fetch failed")
    media_type = upstream.headers.get("content-type", "").split(";")[0].strip().lower()
    if upstream.status_code != 200 or media_type not in SNIPPET_IMAGE_TYPES:
        await upstream.aclose()
        raise HTTPException(status_code=502, detail="Upstream fetch failed")

    async def stream_body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        stream_body(),
        media_type=media_type,
        headers={
            "Cache-Control": f"public, max-age={SNIPPET_IMAGE_MAX_AGE}",
            "X-Content-Type-Options": "nosniff",
        },
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
