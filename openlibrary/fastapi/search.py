from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.code import work_search
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


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
    response = work_search(
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
