from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Request
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.code import work_search_async
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

router = APIRouter()


def get_editions_enabled(
    # Look for an 'editions' query parameter, e.g., /search.json?editions=true
    # FastAPI automatically converts "true"/"false" strings to booleans.
    editions_from_query: Annotated[bool | None, Query(alias="editions")] = None,
    # Look for a cookie named 'SOLR_EDITIONS'.
    # We use an 'alias' because the cookie name is uppercase.
    editions_from_cookie: Annotated[str | None, Cookie(alias="SOLR_EDITIONS")] = None,
) -> bool:
    """
    Determines if SOLR editions should be enabled for the search query.

    The decision is based on the following precedence:
    1. A `editions` URL query parameter (`?editions=true`).
    2. A `SOLR_EDITIONS` cookie.
    3. Defaults to `True` if neither is provided.

    This dependency is automatically resolved for the search endpoint.
    """
    # This replaces has_solr_editions_enabled in fastapi context

    if editions_from_query is not None:
        return editions_from_query

    if editions_from_cookie is not None:
        return editions_from_cookie.lower() == 'true'

    return True


def get_print_disabled(
    print_disabled: Annotated[str | None, Cookie(alias="pd")] = None,
) -> bool:
    if print_disabled is not None:
        return print_disabled.lower() == 'true'
    return False


@router.get("/search.json", response_class=JSONResponse)
async def search_json(
    request: Request,
    editions_mode: Annotated[bool, Depends(get_editions_enabled)],
    print_disabled: Annotated[bool, Depends(get_print_disabled)],
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

    query = {"q": q, "page": page, "limit": limit}
    query.update(
        kwargs
    )  # This is a hack until we define all the params we expect above.
    response = await work_search_async(
        query,
        editions_mode=editions_mode,
        print_disabled=print_disabled,
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
    )

    # Add extra metadata to the response, similar to the original
    response['q'] = q
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
