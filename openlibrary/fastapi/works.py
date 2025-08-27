from __future__ import annotations

import logging

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
    work = fetch_work(olid)

    u = get_user_from_request(request)

    # Needed for page banners where we call the old render function, not a new template
    web.ctx.lang = 'en'

    context = get_jinja_context(
        request, user=u, page=work, title=work.get("name") or olid
    )
    context["main_content"] = render_template("type/edition/view", page=work)
    return templates.TemplateResponse("generic_template.html.jinja", context)
