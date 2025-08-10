from __future__ import annotations

import os

import httpx  # async HTTP for Solr
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami import config as ig_config  # type: ignore
from infogami.infobase import client as ib_client  # type: ignore

router = APIRouter()


def get_site() -> ib_client.Site:
    """Create an Infobase client Site using already-loaded config.

    This avoids calling back into the legacy WSGI app and uses existing Python
    facilities to load objects.
    """
    conn = ib_client.connect(**ig_config.infobase_parameters)
    return ib_client.Site(conn, ig_config.site or "openlibrary.org")


async def fetch_author_and_works(olid: str) -> tuple[dict, list[dict]]:
    site = get_site()
    author_key = f"/authors/{olid}"

    author = site.get(author_key)
    if not author:
        raise HTTPException(status_code=404, detail="author not found")

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

    return author.dict(), docs


templates = Jinja2Templates(directory="openlibrary/fastapi/templates")


@router.get("/_fast/authors/{olid}", response_class=HTMLResponse)
async def author_page(request: Request, olid: str):
    author, docs = await fetch_author_and_works(olid)

    # Aggregate top subjects
    subject_counts: dict[str, int] = {}
    for d in docs:
        for subj in d.get("subject_facet") or []:
            subject_counts[subj] = subject_counts.get(subj, 0) + 1
    top_subjects = sorted(subject_counts.items(), key=lambda x: -x[1])[:20]

    # Prepare author details
    name = author.get("name") or olid
    bio = author.get("bio")
    if isinstance(bio, dict):
        bio = bio.get("value")
    birth_date = author.get("birth_date")
    death_date = author.get("death_date")

    # Find Wikipedia link
    wikipedia = None
    for link in author.get("links", []) or []:
        title = (link.get("title") or "").lower()
        url = link.get("url")
        if "wikipedia" in title and url:
            wikipedia = url
            break

    # The context dictionary passes data to the template. [6]
    context = {
        "request": request,
        "olid": olid,
        "name": name,
        "bio": bio,
        "birth_date": birth_date,
        "death_date": death_date,
        "wikipedia": wikipedia,
        "docs": docs,
        "top_subjects": top_subjects,
    }

    return templates.TemplateResponse("author.html.jinja", context)
