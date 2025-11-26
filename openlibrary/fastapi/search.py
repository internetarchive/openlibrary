from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from openlibrary.plugins.worksearch.code import (
    default_spellcheck_count,
    validate_search_json_query,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

router = APIRouter()

ListQuery = Annotated[list[str], Query(default_factory=list)]


# Ideally this will go in a models files, we'll move it for the 2nd endpoint
class Pagination(BaseModel):
    limit: Annotated[int, Query(ge=0)] = 100
    offset: Annotated[int | None, Query(ge=0)] = None
    page: Annotated[int | None, Query(ge=1)] = None

    def model_post_init(self, _):
        if self.offset is not None:
            self.page = None
        else:
            self.page = self.page or 1


class MostQueryParams(BaseModel):
    """
    This class supports most of the parameters that are passed to query
    Right now we can't get it to work with the query params that have multiple values (e.g. author_key)
    """

    # from check_params in works.py
    title: str | None = None
    publisher: str | None = None
    oclc: str | None = None
    lccn: str | None = None
    contributor: str | None = None
    subject: str | None = None
    place: str | None = None
    person: str | None = None
    time: str | None = None
    # from workscheme facet_fields
    has_fulltext: bool | None = None


@router.get("/search.json", response_class=JSONResponse)
async def search_json(  # noqa: PLR0913
    request: Request,
    pagination: Annotated[Pagination, Depends()],
    mqp: Annotated[MostQueryParams, Depends()],
    # from web.input for search.json
    author_key: ListQuery,
    subject_facet: ListQuery,
    person_facet: ListQuery,
    place_facet: ListQuery,
    time_facet: ListQuery,
    first_publish_year: ListQuery,
    publisher_facet: ListQuery,
    language: ListQuery,
    public_scan_b: ListQuery,  # tbd if this should actually be a list
    author_facet: ListQuery,  # from workscheme facet_fields
    q: str | None = Query("", description="The search query."),
    sort: str | None = Query(None, description="The sort order of results."),
    fields: str | None = Query(None, description="The fields to return."),
    spellcheck_count: int | None = Query(
        default_spellcheck_count, description="The number of spellcheck suggestions."
    ),
    query_str: str | None = Query(
        None, alias="query", description="A full JSON encoded solr query."
    ),
):
    """
    Performs a search for documents based on the provided query.
    """
    # return author_key
    query: dict[str, Any] = {}
    if query_str:
        query = json.loads(query_str)
    else:
        query = {"q": q, "page": pagination.page, "limit": pagination.limit}
        # TODO: ensure all the query params are passed down, preferably from a pydantic model
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
        query.update(mqp.model_dump())

    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    if q_error := validate_search_json_query(q):
        return JSONResponse(status_code=422, content={"error": q_error})

    response = await work_search_async(
        query,
        sort=sort,
        page=pagination.page,
        offset=pagination.offset,
        limit=pagination.limit,
        fields=_fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=spellcheck_count,
        request_label='BOOK_SEARCH_API',
        lang=request.state.lang,
    )

    # Add extra metadata to the response to match the original
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"
    response['q'] = q
    response['offset'] = pagination.offset

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
