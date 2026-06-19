from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

import web
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    computed_field,
    field_validator,
    model_validator,
)

from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.fastapi.models import (
    Pagination,
    PaginationLimit20,
    SolrInternalsParams,
    parse_comma_separated_list,
)
from openlibrary.plugins.worksearch.code import (
    default_spellcheck_count,
    run_solr_query_async,
    validate_search_json_query,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

router = APIRouter()

# Facet fields exposed by /search/facets.json — mirrors WorkSearchScheme.facet_fields
FacetField = Literal[
    "author_facet",
    "first_publish_year",
    "has_fulltext",
    "language",
    "person_facet",
    "place_facet",
    "public_scan_b",
    "publisher_facet",
    "subject_facet",
    "time_facet",
]

# process_facet_counts renames author_facet → author_key internally; map back so
# the response key always matches the caller's requested field name.
_FACET_INTERNAL_RENAME = {"author_key": "author_facet"}


class PublicQueryOptions(BaseModel):
    """
    All parameters (and Pagination) that will be passed to the query.
    """

    q: str = Field("", description="The search query string.")

    # from public_api_params in works.py
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
    # Availability filters. These are not facet_fields — they're handled by
    # WorkSearchScheme.facet_rewrites, which maps (`public_scan`, "true") and
    # (`print_disabled`, "true") to `ebook_access:*` fq clauses. Mirrors the
    # explicit whitelist in the web.py /search handler (worksearch/code.py);
    # without declaring them here, FastAPI silently drops the params and the
    # header search modal's availability filters do nothing.
    public_scan: Literal["true", "false"] | None = None
    print_disabled: Literal["true", "false"] | None = None

    # List fields (facets)
    author_key: list[str] = Field([], description="Filter by author key.", examples=["OL1394244A"])
    subject_facet: list[str] = Field([], description="Filter by subject.", examples=["Fiction", "City planning"])
    person_facet: list[str] = Field(
        [],
        description="Filter by person. Not the author but the person who is the subject of the work.",
        examples=["Jane Jacobs (1916-2006)", "Cory Doctorow"],
    )
    place_facet: list[str] = Field([], description="Filter by place.", examples=["New York", "Xiamen Shi"])
    time_facet: list[str] = Field(
        [],
        description="Filter by time. It can be formatted many ways.",
        examples=["20th century", "To 70 A.D."],
    )
    first_publish_year: list[str] = Field([], description="Filter by first publish year.", examples=["2020"])
    publisher_facet: list[str] = Field([], description="Filter by publisher.", examples=["Urban Land Institute"])
    language: list[str] = Field(
        [],
        description="Filter by language using three-letter language codes.",
        examples=[["eng"], ["spa"], ["eng", "spa"]],
    )
    author_facet: list[str] = Field(
        [],
        description="(alias for author_key) Filter by author key.",
        examples=["OL1394244A"],
    )

    isbn: str | None = None
    author: str | None = None

    @field_validator("q")
    @classmethod
    def parse_q_string(cls, v: str) -> str:
        if q_error := validate_search_json_query(v):
            raise ValueError(q_error)
        return v


class SearchRequestParams(PublicQueryOptions, Pagination):
    fields: Annotated[list[str], BeforeValidator(parse_comma_separated_list)] = Field(
        sorted(WorkSearchScheme.default_fetched_fields),
        description="The fields to return.",
    )
    query: Annotated[dict[str, Any] | None, BeforeValidator(parse_query_json)] = Field(
        None, description="A full JSON encoded solr query.", examples=['{"q": "mark"}']
    )
    sort: str | None = Field(None, description="The sort order of results.")
    spellcheck_count: int | None = Field(
        default_spellcheck_count,
        description="The number of spellcheck suggestions.",
    )

    @staticmethod
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


class FacetValue(BaseModel):
    """A single facet option returned by /search/facets.json."""

    value: str = Field(description="Filter value to pass back to /search.json (e.g. 'eng', 'OL9A')")
    label: str = Field(description="Human-readable display label — differs from value for author_facet")
    count: int = Field(description="Number of matching works")


class SearchResponse(BaseModel):
    """The response from a (books) search query."""

    model_config = ConfigDict(extra="allow")

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
    solr_internals_params: Annotated[SolrInternalsParams | None, Depends(SolrInternalsParams.from_request)],
) -> Any:
    """
    Performs a search for documents based on the provided query.
    """

    raw_response = await work_search_async(
        params.selected_query,  # type: ignore[arg-type]
        sort=params.sort,
        page=params.page,
        offset=params.offset,
        limit=params.limit,
        fields=params.fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=params.spellcheck_count,
        request_label="BOOK_SEARCH_API",
        lang=request.state.lang,
        solr_internals_params=solr_internals_params,
    )

    raw_response["q"] = params.q
    raw_response["offset"] = params.offset

    return raw_response


@router.get("/search/inside.json")
async def search_inside_json(
    pagination: Annotated[PaginationLimit20, Depends()],
    q: Annotated[str, Query(title="Search query")],
):
    return await fulltext_search_async(
        q,
        page=pagination.page,
        offset=pagination.offset,
        limit=pagination.limit,
        js=True,
        facets=True,
    )


@router.get("/search/subjects.json")
async def search_subjects_json(
    pagination: Annotated[Pagination, Depends()],
    q: Annotated[str, Query(description="The search query")] = "",
):
    response = await run_solr_query_async(
        SubjectSearchScheme(),
        {"q": q},
        offset=pagination.offset,
        page=pagination.page,
        rows=pagination.limit,
        sort="work_count desc",
        request_label="SUBJECT_SEARCH_API",
    )

    # Backward compatibility
    raw_resp = response.raw_resp["response"]
    for doc in raw_resp["docs"]:
        doc["type"] = doc.get("subject_type", "subject")
        doc["count"] = doc.get("work_count", 0)

    return raw_resp


def create_sort_option_type(sorts_map: Mapping):
    """
    Generates a Pydantic type alias that validates against the provided
    sorts_map and dynamically generates the OpenAPI Enum documentation.
    """
    # TODO: Use this for Work/Edition search above?
    # I'm just not sure if it's a good idea to have the same sort options for Works and Editions

    # The prefixes allowed dynamically
    RANDOM_PREFIXES = ("random_", "random.hourly_", "random.daily_")

    # The Validator
    def validate_sort(v: str) -> str:
        if not v or v in sorts_map or v.startswith(RANDOM_PREFIXES):
            return v

        valid_keys = ", ".join((*sorts_map.keys(), *RANDOM_PREFIXES))
        raise ValueError(f"Invalid sort option: '{v}'. Valid options are: {valid_keys}")

    # The Type Alias
    return Annotated[
        str,
        BeforeValidator(validate_sort),
        WithJsonSchema(
            {
                "type": "string",
                "enum": list(sorts_map.keys()) + [""],  # Include empty string for default
            }
        ),
    ]


ListSortOption = create_sort_option_type(ListSearchScheme.sorts)


class ListSearchRequestParams(PaginationLimit20):
    q: str = Field("", description="The search query")
    fields: str = Field("", description="Fields to return")
    sort: ListSortOption = Field("", description="Sort order")  # type: ignore[valid-type]
    api: Literal["next", ""] = Field("", description="API version: 'next' for new format, empty for old format")

    @model_validator(mode="after")
    def handle_legacy_logic(self) -> Self:
        if self.api != "next":
            if self.sort:
                raise ValueError("sort not supported in the old API")

            # 2. Modification Logic (Sanitization/Defaults for old API)
            self.limit = min(1000, self.limit or 20)
            self.fields = "key"

        return self


@router.get("/search/lists.json")
async def search_lists_json(
    params: Annotated[ListSearchRequestParams, Depends()],
):
    response = await run_solr_query_async(
        ListSearchScheme(),
        {"q": params.q},
        offset=params.offset,
        page=params.page,
        rows=params.limit,
        fields=params.fields,
        sort=params.sort,
        request_label="LIST_SEARCH_API",
    )

    if params.api == "next":
        # Match search.json
        return {
            "numFound": response.num_found,
            "num_found": response.num_found,
            "start": response.raw_resp["response"].get("start", params.offset or 0),
            "q": params.q,
            "docs": response.docs,
        }
    else:
        # Default to the old API shape for a while, then we'll flip
        lists = web.ctx.site.get_many([doc["key"] for doc in response.docs])
        return {
            "start": response.raw_resp["response"].get("start", params.offset or 0),
            "docs": [lst.preview() for lst in lists],
        }


AuthorSortOption = create_sort_option_type(AuthorSearchScheme.sorts)


class AuthorSearchRequestParams(Pagination):
    q: str = Field("", description="The search query")
    fields: str = Field("*", description="Fields to return")
    sort: AuthorSortOption = Field("", description="Sort order")  # type: ignore[valid-type]


@router.get("/search/authors.json")
async def search_authors_json(
    params: Annotated[AuthorSearchRequestParams, Depends()],
):
    response = await run_solr_query_async(
        AuthorSearchScheme(),
        {"q": params.q},
        offset=params.offset,
        page=params.page,
        rows=params.limit,
        fields=params.fields,
        sort=params.sort,
        request_label="AUTHOR_SEARCH_API",
    )

    # SIGH the public API exposes the key like this :(
    raw_resp = response.raw_resp["response"]
    for doc in raw_resp["docs"]:
        doc["key"] = doc["key"].split("/")[-1]

    return raw_resp


@router.get("/search/facets.json", tags=["search"], response_model=dict[str, list[FacetValue]])
async def search_facets_json(
    request: Request,
    params: Annotated[PublicQueryOptions, Depends()],
    field: Annotated[
        list[FacetField] | None,
        Query(description="Facet field(s) to return. Repeat for multiple."),
    ] = None,
    sfw: Annotated[str | None, Cookie()] = None,
    solr_internals_params: Annotated[SolrInternalsParams | None, Depends(SolrInternalsParams.from_request)] = None,
) -> dict[str, list[FacetValue]]:
    """
    Returns context-aware facet values for one or more search facet fields.

    Queries Solr with rows=0 alongside the current search params, returning only
    values with count > 0, ordered by count descending. Designed to power the
    OlSelectPopover components in the search results filter bar (PR #12949).

    Example: GET /search/facets.json?field=language&field=subject_facet&q=lord+of+the+rings
    """
    if not field:
        raise HTTPException(status_code=400, detail="At least one 'field' parameter is required.")

    search_response = await run_solr_query_async(
        WorkSearchScheme(lang=request.state.lang),
        params.model_dump(exclude_none=True),
        rows=0,
        page=1,
        facet=list(field),
        highlight=False,
        request_label="BOOK_SEARCH_FACETS",
        solr_internals_params=solr_internals_params,
    )

    result: dict[str, list[FacetValue]] = {f: [] for f in field}
    if search_response.facet_counts:
        for facet_field, values in search_response.facet_counts.items():
            output_key = _FACET_INTERNAL_RENAME.get(facet_field, facet_field)
            if output_key not in result:
                continue
            # values are (display_label, filter_value, count) tuples; label differs
            # from value for author_facet (name vs OL key) and "Name|key" subject fields.
            result[output_key] = [FacetValue(value=filter_val, label=display_label, count=count) for display_label, filter_val, count in values if count > 0]

    return result
