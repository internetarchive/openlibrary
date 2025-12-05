from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.plugins.inside.code import RESULTS_PER_PAGE
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

    @model_validator(mode='after')
    def normalize_pagination(self) -> Pagination:
        if self.offset is not None:
            self.page = None
        elif self.page is None:
            self.page = 1
        return self


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

    """
    The day will come when someone asks, why do we have Field wrapping Query
    The answer seems to be:
    1. Depends(): Tells FastAPI to explode the Pydantic model into individual arguments (dependency injection).
    2. Field(Query([])): Overrides the default behavior for lists. It forces FastAPI to look for ?author_key=...
       in the URL query string instead of expecting a JSON array in the request body.
    The Field part is needed because FastAPI's default guess for lists inside Pydantic models is wrong for this use case.
       It guesses "JSON Body," and you have to manually correct it to "Query String."
    See: https://github.com/internetarchive/openlibrary/pull/11517#issuecomment-3584196385
    """
    author_key: list[str] = Field(Query([]))
    subject_facet: list[str] = Field(Query([]))
    person_facet: list[str] = Field(Query([]))
    place_facet: list[str] = Field(Query([]))
    time_facet: list[str] = Field(Query([]))
    first_publish_year: list[str] = Field(Query([]))
    publisher_facet: list[str] = Field(Query([]))
    language: list[str] = Field(Query([]))
    author_facet: list[str] = Field(Query([]))


class AdditionalEndpointQueryOptions(BaseModel):
    fields: str | None = Query(
        ",".join(WorkSearchScheme.default_fetched_fields),
        description="The fields to return.",
    )

    @field_validator('fields', mode='after')
    @classmethod
    def parse_fields_string(cls, v: str) -> list[str]:
        return [f.strip() for f in v.split(",") if f.strip()]


@router.get("/search.json")
async def search_json(
    request: Request,
    pagination: Annotated[Pagination, Depends()],
    public_query_options: Annotated[PublicQueryOptions, Depends()],
    additional_endpoint_query_options: Annotated[
        AdditionalEndpointQueryOptions, Depends()
    ],
    sort: str | None = Query(None, description="The sort order of results."),
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

    if q_error := validate_search_json_query(public_query_options.q):
        return JSONResponse(status_code=422, content={"error": q_error})

    response = await work_search_async(
        query,
        sort=sort,
        page=pagination.page,
        offset=pagination.offset,
        limit=pagination.limit,
        fields=additional_endpoint_query_options.fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=spellcheck_count,
        request_label='BOOK_SEARCH_API',
        lang=request.state.lang,
    )

    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"
    response['q'] = public_query_options.q
    response['offset'] = pagination.offset

    # Put docs at the end of the response
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response


@router.get("/search/inside.json")
async def search_inside_json(
    q: str = Query(..., title="Search query"),
    page: int | None = Query(1, ge=1, description="Page number"),
    limit: int | None = Query(
        RESULTS_PER_PAGE, ge=0, le=RESULTS_PER_PAGE, description="Results per page"
    ),
):
    return await fulltext_search_async(q, page=page, limit=limit, js=True, facets=True)
