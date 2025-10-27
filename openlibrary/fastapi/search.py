from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.code import async_work_search
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

SEARCH_CACHE_MAX_AGE = 300

router = APIRouter()


@router.get("/search.json", response_class=JSONResponse)
async def search_json(
    request: Request,
    q: str | None = Query("", description="The search query."),
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

    kwargs = dict(request.query_params)
    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    query = {"q": q, "page": page, "limit": limit}
    query.update(kwargs)
    response = await async_work_search(
        query,
        sort=sort,
        page=page,
        offset=offset,
        limit=limit,
        fields=_fields,
        facet=False,
        spellcheck_count=spellcheck_count,
        lang=request.state.lang,
    )

    response['q'] = q
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"

    docs = response.pop('docs', [])
    response['docs'] = docs

    json_response = JSONResponse(content=response)
    if 'error' not in response:
        json_response.headers['Cache-Control'] = (
            f'public, max-age={SEARCH_CACHE_MAX_AGE}'
        )
    return json_response
