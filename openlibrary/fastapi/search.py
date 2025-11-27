from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from openlibrary.plugins.worksearch.code import (
    default_spellcheck_count,
    validate_search_json_query,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

router = APIRouter()


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


class PublicQueryOptions(BaseModel):
    """
    This class has all the parameters that are passed as "query"
    """

    q: str = Query("", description="The search query, like keyword.")

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
    public_scan_b: bool | None = None

    author_key: list[str] = Field(Query([]))
    subject_facet: list[str] = Field(Query([]))
    person_facet: list[str] = Field(Query([]))
    place_facet: list[str] = Field(Query([]))
    time_facet: list[str] = Field(Query([]))
    first_publish_year: list[str] = Field(Query([]))
    publisher_facet: list[str] = Field(Query([]))
    language: list[str] = Field(Query([]))
    author_facet: list[str] = Field(Query([]))


@router.get("/search.json", response_class=JSONResponse)
async def search_json(
    request: Request,
    pagination: Annotated[Pagination, Depends()],
    public_query_options: Annotated[PublicQueryOptions, Depends()],
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
    query: dict[str, Any] = {}
    if query_str:
        query = json.loads(query_str)
    else:
        # In an ideal world, we would pass the model unstead of the dict but that's a big refactoring down the line
        query = public_query_options.model_dump(exclude_none=True)
        query.update({"page": pagination.page, "limit": pagination.limit})

    _fields: list[str] = list(WorkSearchScheme.default_fetched_fields)
    if fields:
        _fields = fields.split(',')

    if q_error := validate_search_json_query(public_query_options.q):
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
    response['q'] = public_query_options.q
    response['offset'] = pagination.offset

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
