from __future__ import annotations

import json
from typing import Annotated, Any, Self

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

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

    limit: int = Field(100, ge=0, description="Maximum number of results to return.")
    offset: int | None = Field(
        None, ge=0, description="Number of results to skip.", exclude=True
    )
    page: int | None = Field(None, ge=1, description="Page number (1-indexed).")

    @model_validator(mode='after')
    def normalize_pagination(self) -> Self:
        if self.offset is not None:
            self.page = None
        elif self.page is None:
            self.page = 1
        return self


class PublicQueryOptions(BaseModel):
    """
    All parameters (and Pagination) that will be passed to the query.
    """

    q: str = Field("", description="The search query string.")

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

    # List fields (facets)
    author_key: list[str] = Field(
        [], description="Filter by author key.", examples=["OL1394244A"]
    )
    subject_facet: list[str] = Field(
        [], description="Filter by subject.", examples=["Fiction", "City planning"]
    )
    person_facet: list[str] = Field(
        [],
        description="Filter by person. Not the author but the person who is the subject of the work.",
        examples=["Jane Jacobs (1916-2006)", "Cory Doctorow"],
    )
    place_facet: list[str] = Field(
        [], description="Filter by place.", examples=["New York", "Xiamen Shi"]
    )
    time_facet: list[str] = Field(
        [],
        description="Filter by time. It can be formatted many ways.",
        examples=["20th century", "To 70 A.D."],
    )
    first_publish_year: list[str] = Field(
        [], description="Filter by first publish year.", examples=["2020"]
    )
    publisher_facet: list[str] = Field(
        [], description="Filter by publisher.", examples=["Urban Land Institute"]
    )
    language: list[str] = Field(
        [],
        description="Filter by language using three-letter language codes.",
        examples={
            "english": {
                "summary": "English",
                "description": "Returns results in English",
                "value": ["eng"],
            },
            "spanish": {
                "summary": "Spanish",
                "description": "Returns results in Spanish",
                "value": ["spa"],
            },
            "english_and_spanish": {
                "summary": "English + Spanish",
                "description": "Bilingual results",
                "value": ["eng", "spa"],
            },
        },
    )
    author_facet: list[str] = []

    @field_validator('q')
    @classmethod
    def parse_q_string(cls, v: str) -> str:
        if q_error := validate_search_json_query(v):
            raise ValueError(q_error)
        return v


class SearchRequestParams(PublicQueryOptions, Pagination):
    fields: str | None = Field(
        ",".join(sorted(WorkSearchScheme.default_fetched_fields)),
        description="The fields to return.",
    )
    query: str | None = Field(None, description="A full JSON encoded solr query.")
    sort: str | None = Field(None, description="The sort order of results.")
    spellcheck_count: int | None = Field(
        default_spellcheck_count,
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
            raise ValueError(f"Invalid JSON in 'query' parameter: {e}")

    @computed_field
    def selected_query(self) -> dict[str, Any]:
        if isinstance(self.query, dict):
            return self.query
        else:
            q = self.model_dump(
                include=PublicQueryOptions.model_fields.keys(),
                exclude_none=True,
            )
            # only add page and limit, not offset (unclear why)
            q['page'] = self.page
            q['limit'] = self.limit
            return q


@router.get("/search.json")
async def search_json(
    request: Request,
    params: Annotated[SearchRequestParams, Query()],
):
    """
    Performs a search for documents based on the provided query.
    """
    response = await work_search_async(
        params.selected_query,
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
