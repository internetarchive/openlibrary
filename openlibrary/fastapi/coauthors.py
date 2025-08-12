from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami import config as ig_config  # type: ignore
from infogami.infobase import client as ib_client  # type: ignore
from openlibrary.plugins.upstream.models import Author

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


def get_site() -> ib_client.Site:
    """Create an Infobase client Site using already-loaded config.

    This avoids calling back into the legacy WSGI app and uses existing Python
    facilities to load objects.
    """
    conn = ib_client.connect(**ig_config.infobase_parameters)
    return ib_client.Site(conn, ig_config.site or "openlibrary.org")


def fetch_author(olid: str) -> Author:
    site = get_site()
    author_key = f"/authors/{olid}"

    author = site.get(author_key)
    if not author:
        raise HTTPException(status_code=404, detail="author not found")
    return author


async def fetch_author_works(olid: str) -> list[dict]:
    # author = fetch_author(olid)

    # Query Solr for works by this author
    solr_url = os.environ.get("SOLR_URL", "http://solr:8983/solr/openlibrary/select")
    params = {
        "q": f"author_key:{olid}",
        "fl": "key,title,first_publish_year,edition_count,cover_i,author_key,author_name,subject_facet",
        "rows": 200,
        "wt": "json",
        "sort": "first_publish_year asc",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        s_resp = await client.get(solr_url, params=params)
    s_resp.raise_for_status()
    s_json = s_resp.json()
    docs = s_json.get("response", {}).get("docs", [])

    return docs


async def _compute_author_network(olid: str) -> dict:
    """Compute co-authors by querying Solr and author details via JSON API.

    - Fetch author details from the classic JSON API: /authors/{olid}.json
    - Query Solr for works with author_key:OL... and aggregate other authors.
    """
    import httpx  # type: ignore

    # Resolve service URLs from env with sensible defaults for docker-compose
    base_web = os.environ.get("OL_WEB_INTERNAL", "http://localhost:8080")
    solr_url = os.environ.get("SOLR_URL", "http://solr:8983/solr/openlibrary/select")

    # Query Solr for works by this author and compute co-authors
    params = {
        "q": f"author_key:{olid}",
        "fl": "key,title,author_key,author_name",
        "rows": 2000,
        "wt": "json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        s_resp = await client.get(solr_url, params=params)
    s_resp.raise_for_status()
    docs = s_resp.json().get("response", {}).get("docs", [])

    if not docs:
        raise HTTPException(
            status_code=404, detail="author not found or no works in index"
        )

    # Derive canonical author name from docs where this olid appears
    name_counts: dict[str, int] = {}
    for d in docs:
        keys: list[str] = d.get("author_key", []) or []
        names: list[str] = d.get("author_name", []) or []
        for i, k in enumerate(keys):
            if k == olid:
                nm = names[i] if i < len(names) else None
                if nm:
                    name_counts[nm] = name_counts.get(nm, 0) + 1

    author_name = max(name_counts, key=name_counts.get) if name_counts else None

    # Aggregate co-authors
    counts: dict[str, dict[str, object]] = {}
    for d in docs:
        keys: list[str] = d.get("author_key", []) or []
        names: list[str] = d.get("author_name", []) or []
        # zip may drop if lengths differ; use index lookup
        name_by_key = {
            k: names[i] if i < len(names) else None for i, k in enumerate(keys)
        }
        for k in keys:
            if k == olid:
                continue
            if k not in counts:
                counts[k] = {
                    "key": f"/authors/{k}",
                    "olid": k,
                    "name": name_by_key.get(k),
                    "shared_works": 0,
                }
            counts[k]["shared_works"] = int(counts[k]["shared_works"]) + 1

    coauthors = sorted(counts.values(), key=lambda x: -int(x["shared_works"]))

    return {
        "author": {"key": f"/authors/{olid}", "olid": olid, "name": author_name},
        "co_authors": coauthors,
        "stats": {"works_considered": len(docs), "unique_coauthors": len(coauthors)},
    }


@router.get("/_fast/coauthors/{olid}")
async def author_coauthors(olid: str):
    """Return author basic info and co-authors via Solr aggregation.

    This is intentionally JSON-first for an initial endpoint. We can add an
    HTML template later.
    """
    try:
        data = await _compute_author_network(olid)
        return JSONResponse(data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("error in author network endpoint for %s", olid)
        raise HTTPException(status_code=500, detail=str(e))
