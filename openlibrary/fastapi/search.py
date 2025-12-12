from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Query, Request
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo

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
    has_fulltext: Literal["true", "false"] | None = None
    public_scan_b: list[Literal["true", "false"]] = []

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
    author_facet: list[str] = Field(
        [],
        description="(alias for author_key) Filter by author key.",
        examples=["OL1394244A"],
    )

    @field_validator('q')
    @classmethod
    def parse_q_string(cls, v: str) -> str:
        if q_error := validate_search_json_query(v):
            raise ValueError(q_error)
        return v


def add_search_fields_to_model(model: type[PublicQueryOptions]) -> None:
    """
    Dynamically adds all search fields (from WorkSearchScheme) as optional string fields
    to the given Pydantic model (typically PublicQueryOptions).

    This should be called once at import time or in a module-level block.

    TODO: when we refactor worksearchscheme we should stop using this function and have a proper model.
    """
    # Common field definition: Optional[str] with default=None
    search_field = (str | None, Field(default=None))

    # Collect all field names we want to add (original + aliases)
    fields_to_add: dict[str, tuple[Any, FieldInfo]] = {}

    for field_name in WorkSearchScheme.all_fields:
        if field_name not in model.model_fields:
            fields_to_add[field_name] = search_field

    for alias in WorkSearchScheme.field_name_map:
        if alias not in model.model_fields:
            fields_to_add[alias] = search_field

    # Apply them all at once
    for name, (type_hint, field_info) in fields_to_add.items():
        # Update annotations for IDEs/type checkers
        model.__annotations__[name] = type_hint
        # Actually set the field on the model
        setattr(model, name, field_info)

    # Rebuild the model so Pydantic recognizes the new fields
    model.model_rebuild()


# Call it once, ideally right after PublicQueryOptions is defined
add_search_fields_to_model(PublicQueryOptions)


class SearchRequestParams(PublicQueryOptions, Pagination):
    fields: Annotated[list[str], BeforeValidator(parse_fields_string)] = Field(
        ",".join(sorted(WorkSearchScheme.default_fetched_fields)),
        description="The fields to return.",
    )
    query: Annotated[dict[str, Any], BeforeValidator(parse_query_json)] = Field(
        None, description="A full JSON encoded solr query.", examples=['{"q": "mark"}']
    )
    sort: str | None = Field(None, description="The sort order of results.")
    spellcheck_count: int | None = Field(
        default_spellcheck_count,
        description="The number of spellcheck suggestions.",
    )

    def parse_fields_string(v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            v = [v]
        return [f.strip() for item in v for f in str(item).split(",") if f.strip()]

    def parse_query_json(v: str) -> dict[str, Any]:
        try:
            return json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in 'query' parameter: {e}")

    @computed_field
    def selected_query(self) -> dict[str, Any]:
        if isinstance(self.query, dict):
            return self.query
        else:
            # Include all fields that belong to PublicQueryOptions (the search query part)
            # This automatically excludes SearchRequestParams-specific fields like fields, sort, etc.
            query_fields = set(PublicQueryOptions.model_fields.keys())
            # Add dynamically handled fields from WorkSearchScheme
            query_fields |= WorkSearchScheme.all_fields
            query_fields |= set(WorkSearchScheme.field_name_map.keys())
            q = self.model_dump(include=query_fields, exclude_none=True)
            return q


class SearchResponse(BaseModel):
    """The response from a (books) search query."""

    model_config = ConfigDict(extra='allow')

    numFound: int
    start: int
    numFoundExact: bool
    num_found: int

    documentation_url: str = "https://openlibrary.org/dev/docs/api/search"
    q: str
    offset: int | None

    # Defined last so it renders at the bottom.
    # We use dict[str, Any] to avoid documenting the internal book fields.
    docs: list[dict[str, Any]] = []


@router.get("/search.json", tags=["search"], response_model=SearchResponse)
async def search_json(
    request: Request,
    params: Annotated[SearchRequestParams, Query()],
) -> Any:
    """
    Performs a search for documents based on the provided query.
    """
    raw_response = await work_search_async(
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

    raw_response['q'] = params.q
    raw_response['offset'] = params.offset

    return raw_response


@router.get("/search/inside.json")
async def search_inside_json(
    q: str = Query(..., title="Search query"),
    page: int | None = Query(1, ge=1, description="Page number"),
    limit: int | None = Query(
        RESULTS_PER_PAGE, ge=0, le=RESULTS_PER_PAGE, description="Results per page"
    ),
):
    return await fulltext_search_async(q, page=page, limit=limit, js=True, facets=True)
