from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.code import work_search_async
from openlibrary.plugins.worksearch.schemes.works import (
    WorkSearchAllFields,
    WorkSearchFacetFields,
    WorkSearchScheme,
)

router = APIRouter()


@router.get("/search.json", response_class=JSONResponse)
async def search_json(
    request: Request,
    facets: Annotated[WorkSearchFacetFields, Depends(WorkSearchFacetFields)],
    all_fields: Annotated[WorkSearchAllFields, Depends(WorkSearchAllFields)],
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
    spellcheck_count: int | None = Query(
        3, description="The number of spellcheck suggestions."
    ),
    query: str | None = Query(None, description="JSON query to search for"),
):
    """
    Performs a search for documents based on the provided query.
    """
    if query:
        final_query = json.loads(query)
    else:
        final_query = {"q": q, "page": page, "limit": limit}

    # Call the underlying search logic
    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    final_query.update(
        {key: value for key, value in facets.dict().items() if value is not None}
    )

    final_query.update(
        {key: value for key, value in all_fields.dict().items() if value is not None}
    )

    response = await work_search_async(
        query=final_query,
        sort=sort,
        page=page,
        offset=offset,
        limit=limit,
        fields=_fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=spellcheck_count,
        lang=request.state.lang,
        request_label='BOOK_SEARCH_API',
    )

    # Add extra metadata to the response, similar to the original
    response['q'] = q
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"
    response['offset'] = offset

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
