from __future__ import annotations

import logging

import httpx
import web
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami.utils.view import render_template
from openlibrary.fastapi.utils import (
    get_jinja_context,
    get_site,
    get_user_from_request,
    templates,
)
from openlibrary.plugins.upstream.models import Author
from openlibrary.plugins.worksearch.code import get_remembered_layout

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


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
    # solr_url = os.environ.get("SOLR_URL", "http://solr:8983/solr/openlibrary/select")

    from openlibrary.solr.utils import get_solr_base_url

    solr_url = get_solr_base_url() + '/select'
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


# templates = Jinja2Templates(directory="openlibrary/fastapi/templates")
# templates.env.add_extension('jinja2.ext.i18n')
# templates.env.install_null_translations(newstyle=True)


# @router.get("/authors/{olid}/{name}", response_class=HTMLResponse)
@router.get("/authors/{olid}/{name}", response_class=HTMLResponse)
@router.get("/authors/{olid}", response_class=HTMLResponse)
async def author_page(request: Request, olid: str):
    author = fetch_author(olid)

    u = get_user_from_request(request)

    # Needed for page banners where we call the old render function, not a new template
    web.ctx.lang = 'en'

    context = get_jinja_context(
        request, user=u, page=author, title=author.get("name") or olid
    )
    context["main_content"] = render_template("type/author/view", page=author)
    return templates.TemplateResponse("generic_template.html.jinja", context)


# This was an experiment to see what it would be like to just use new templates instead of rendering old ones
@router.get("/_fast/authors_simple/{olid}/{name}", response_class=HTMLResponse)
@router.get("/_fast/authors_simple/{olid}", response_class=HTMLResponse)
async def author_page2(request: Request, olid: str):
    author = fetch_author(olid)
    docs = await fetch_author_works(olid)

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

    web.ctx.lang = 'en'
    u = get_user_from_request(request)

    # logger.info(render_template("covers/author_photo.html", author))
    context = {
        "ctx": {
            "title": name,
            "description": "",
            "robots": "index, follow",
            "links": [],
            "metatags": [],
            "features": ["dev"],
            "path": request.url.path,
        },
        "request": request,
        "olid": olid,
        "name": name + str(u.is_admin()),
        "bio": bio,
        "birth_date": birth_date,
        "death_date": death_date,
        "wikipedia": wikipedia,
        "docs": docs,
        "top_subjects": top_subjects,
        "page": author,
        "render_template": render_template,
        "query_param": request.query_params.get,
        "get_remembered_layout": get_remembered_layout,
        "homepath": lambda: "",
        "get_flash_messages": list,
    }
    import time

    start = time.perf_counter()
    t = templates.TemplateResponse("author/simple_author.html.jinja", context)
    duration = time.perf_counter() - start
    logger.info(f"Rendered author page for {olid} in {duration:.2f} seconds")
    return t
