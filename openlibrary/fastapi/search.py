from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.code import work_search_async
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

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
    # Call the underlying search logic
    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    if q and len(q) < 3:
        return JSONResponse(
            status_code=422,
            content={"error": "Query too short, must be at least 3 characters"},
        )

    BLOCKED_QUERIES = {'the'}
    if q and q.lower() in BLOCKED_QUERIES:
        return JSONResponse(
            status_code=422,
            content={
                "error": f"Invalid query; the following queries are not allowed: {', '.join(sorted(BLOCKED_QUERIES))}"
            },
        )

    query = {"q": q, "page": page, "limit": limit}
    query.update(
        kwargs
    )  # This is a hack until we define all the params we expect above.
    response = await work_search_async(
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
        request_label='BOOK_SEARCH_API',
        lang=request.state.lang,
    )

    # Add extra metadata to the response, similar to the original
    response['q'] = q
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
