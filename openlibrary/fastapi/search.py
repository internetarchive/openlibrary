from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.code import work_search_async
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

router = APIRouter()

ListQuery = Annotated[list[str], Query(default_factory=list)]


@router.get("/search.json", response_class=JSONResponse)
async def search_json(  # noqa: PLR0913
    request: Request,
    author_key: ListQuery,
    subject_facet: ListQuery,
    person_facet: ListQuery,
    place_facet: ListQuery,
    time_facet: ListQuery,
    first_publish_year: ListQuery,
    publisher_facet: ListQuery,
    language: ListQuery,
    public_scan_b: ListQuery,  # tbd if this should actually be a query
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
    # return author_key

    kwargs = dict(request.query_params)
    # Call the underlying search logic
    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    query: dict[str, Any] = {"q": q, "page": page, "limit": limit}
    query.update(
        kwargs
    )  # This is a hack until we define all the params we expect above.
    query.update(
        {
            "author_key": author_key,
            "subject_facet": subject_facet,
            "person_facet": person_facet,
            "place_facet": place_facet,
            "time_facet": time_facet,
            "first_publish_year": first_publish_year,
            "publisher_facet": publisher_facet,
            "language": language,
            "public_scan_b": public_scan_b,
        }
    )
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
