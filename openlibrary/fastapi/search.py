from __future__ import annotations

import logging

import web
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami.utils.view import render_template
from openlibrary.fastapi.authors import get_user_from_request
from openlibrary.plugins.worksearch.code import (
    async_run_solr_query,
    async_work_search,
    get_remembered_layout,
)
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


templates = Jinja2Templates(directory="openlibrary/fastapi/templates")
templates.env.add_extension('jinja2.ext.i18n')
templates.env.install_null_translations(newstyle=True)


@router.get("/search/authors/", response_class=HTMLResponse)
async def author_page(
    request: Request,
    q: str = Query(..., description="The search query."),
):
    async def get_results(q, offset=0, limit=100, fields='*', sort=''):
        return await async_run_solr_query(
            AuthorSearchScheme(),
            {'q': q},
            offset=offset,
            rows=limit,
            fields=fields,
            sort=sort,
        )

    results = await get_results(q=q)

    u = get_user_from_request(request)

    # Needed for page banners where we call the old render function, not a new template
    web.ctx.lang = 'en'

    def dummy_get_results(q, *, offset=0, limit=100, fields='*', sort='', **kwargs):
        return results

    context = {
        # New templates use this ctx
        "ctx": {
            "title": "temp title",  # author.get("name") or olid,
            "description": "",
            "robots": "index, follow",
            "links": [],
            "metatags": [],
            "features": ["dev"],
            "path": request.url.path,
            "user": u,
        },
        "request": request,
        "page": {'name': q},
        "render_template": render_template,
        "query_param": request.query_params.get,
        "get_remembered_layout": get_remembered_layout,
        "homepath": lambda: "",
        "get_flash_messages": list,
        "get_internet_archive_id": lambda x: "@openlibrary",
        "cached_get_counts_by_mode": lambda mode: 0,
        "get_results": dummy_get_results,
    }
    return templates.TemplateResponse("search/authors.html.jinja", context)


@router.get("/_fast/search.json", response_class=JSONResponse)
async def search_json(
    q: str = Query(..., description="The search query."),
    page: int | None = Query(
        1, ge=1, description="The page number of results to return."
    ),
    limit: int = Query(
        100, ge=1, le=1000, description="The number of results per page."
    ),
    sort: str | None = Query(None, description="The sort order of results."),
    offset: int | None = Query(None, description="The offset of results to return."),
    fields: str | None = Query(None, description="The fields to return."),
    # facet: bool = Query(False, description="Whether to return facets."),
    spellcheck_count: int | None = Query(
        3, description="The number of spellcheck suggestions."
    ),
):
    """
    Performs a search for documents based on the provided query.
    """
    # Call the underlying search logic
    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    query = {"q": q, "page": page, "limit": limit}
    response = await async_work_search(
        query,
        sort=sort,
        page=page,
        offset=offset,
        limit=limit,
        fields=_fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=spellcheck_count,
    )

    # Add extra metadata to the response, similar to the original
    response['q'] = q
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
