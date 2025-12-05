from __future__ import annotations

import json
from typing import Annotated, Any, Self

from fastapi import APIRouter, HTTPException, Query, Request
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
    """Reusable pagination parameters for API endpoints."""

    limit: int = Field(
        default=100, ge=0, description="Maximum number of results to return."
    )
    offset: int | None = Field(
        default=None, ge=0, description="Number of results to skip."
    )
    page: int | None = Field(default=None, ge=1, description="Page number (1-indexed).")

    @model_validator(mode='after')
    def normalize_pagination(self) -> Self:
        if self.offset is not None:
            self.page = None
        elif self.page is None:
            self.page = 1
        return self


class PublicQueryOptions(Pagination):
    """
    All parameters (and Pagination) that will be passed to the query.
    Those with exclude=True (like limit) are not serialied and therefore not passed.
    """

    # from check_params in works.py
    q: str = Field(default="", description="The search query string.")
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

    # List fields (facets)
    author_key: list[str] = []
    subject_facet: list[str] = []
    person_facet: list[str] = []
    place_facet: list[str] = []
    time_facet: list[str] = []
    first_publish_year: list[str] = []
    publisher_facet: list[str] = []
    language: list[str] = []
    author_facet: list[str] = []

    @field_validator('q')
    @classmethod
    def parse_q_string(cls, v: str) -> str:
        # Note: in other endpoints we should use a value error
        # but we can't because the way we have multiple pydantic models here
        # See: https://docs.pydantic.dev/2.2/usage/validators/
        # Also https://fastapi.tiangolo.com/tutorial/handling-errors/
        if q_error := validate_search_json_query(v):
            raise HTTPException(422, detail=q_error)
        return v


class SearchRequestParams(PublicQueryOptions):
    fields: str | None = Field(
        default=",".join(WorkSearchScheme.default_fetched_fields),
        description="The fields to return.",
    )
    query: str | None = Field(
        default=None, description="A full JSON encoded solr query."
    )
    sort: str | None = Field(default=None, description="The sort order of results.")
    spellcheck_count: int | None = Field(
        default=default_spellcheck_count,
        description="The number of spellcheck suggestions.",
    )

    @field_validator('fields')
    @classmethod
    def parse_fields_string(cls, v: str) -> list[str]:
        return [f.strip() for f in v.split(",") if f.strip()]

    @field_validator('query')
    @classmethod
    def parse_query_json(cls, v: str | None) -> dict[str, Any] | None:
        if v is None:
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError as e:
            raise HTTPException(422, detail=f"Invalid JSON in 'query' parameter: {e}")


@router.get("/search.json")
async def search_json(
    request: Request,
    params: Annotated[SearchRequestParams, Query()],
):
    """
    Performs a search for documents based on the provided query.
    """
    query: dict[str, Any]
    if params.query is not None:
        query = params.query  # type: ignore[assignment]
    else:
        query = params.model_dump(exclude_none=True)
        # TODO: remove this line, also add a test ensuring offset is not passed.
        query.update({"page": params.page, "limit": params.limit})

    response = await work_search_async(
        query,
        sort=params.sort,
        page=params.page,
        offset=params.offset,
        limit=params.limit,
        fields=params.fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=params.spellcheck_count,
        request_label='BOOK_SEARCH_API',
        lang=request.state.lang,
    )

    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"
    response['q'] = params.q
    response['offset'] = params.offset

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
