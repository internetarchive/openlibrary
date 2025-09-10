from __future__ import annotations

import logging
import time

import web
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami.utils.view import render_template
from openlibrary.core.observations import get_observation_metrics
from openlibrary.fastapi.utils import (
    get_jinja_context,
    get_site,
    get_user_from_request,
    templates,
)
from openlibrary.plugins.upstream.models import Author

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


def fetch_work(olid: str) -> Author:
    site = get_site()
    work_key = f"/works/{olid}"

    author = site.get(work_key)
    if not author:
        raise HTTPException(status_code=404, detail="work not found")
    return author


@router.get("/works/{olid}/{name}", response_class=HTMLResponse)
@router.get("/works/{olid}", response_class=HTMLResponse)
async def works_page(request: Request, olid: str):

    start = time.perf_counter()
    work = fetch_work(olid)
    duration = time.perf_counter() - start
    logger.info(f"Fetched work {olid} in {duration:.2f} seconds")

    start = time.perf_counter()
    u = get_user_from_request(request)
    duration = time.perf_counter() - start
    logger.info(f"Fetched user in {duration:.2f} seconds")

    start = time.perf_counter()
    editions = work.get_sorted_editions()
    # editions = []
    duration = time.perf_counter() - start
    logger.info(f"Fetched editions for work {olid} in {duration:.2f} seconds")

    start = time.perf_counter()
    reader_observations = get_observation_metrics(work['key'])
    duration = time.perf_counter() - start
    logger.info(
        f"Fetched reader observations for work {olid} in {duration:.2f} seconds"
    )

    start = time.perf_counter()
    authors = work.get_authors()
    duration = time.perf_counter() - start
    logger.info(f"Fetched authors for work {olid} in {duration:.2f} seconds")

    # Needed for page banners where we call the old render function, not a new template
    web.ctx.lang = 'en'

    context = get_jinja_context(
        request, user=u, page=work, title=work.get("name") or olid
    )
    start = time.perf_counter()
    context["main_content"] = render_template(
        "type/edition/view",
        page=work,
        editions=editions,
        reader_observations=reader_observations,
        authors=authors,
    )
    duration = time.perf_counter() - start
    logger.info(f"Rendered work {olid} in {duration:.2f} seconds")

    start = time.perf_counter()
    jinja_template = templates.TemplateResponse("generic_template.html.jinja", context)
    duration = time.perf_counter() - start
    logger.info(f"Rendered jinja template for work {olid} in {duration:.2f} seconds")

    return jinja_template
