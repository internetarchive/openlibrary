from __future__ import annotations

import json
from typing import Annotated, Any, Literal

import web
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)

from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.fastapi.models import Pagination, PaginationLimit20
from openlibrary.plugins.worksearch.code import (
    async_run_solr_query,
    default_spellcheck_count,
    validate_search_json_query,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.plugins.worksearch.subjects import (
    DEFAULT_RESULTS,
    MAX_RESULTS,
    date_range_to_publish_year_filter,
    get_subject_async,
)

router = APIRouter()


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

    isbn: str | None = None
    author: str | None = None

    @field_validator('q')
    @classmethod
    def parse_q_string(cls, v: str) -> str:
        if q_error := validate_search_json_query(v):
            raise ValueError(q_error)
        return v


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
    pagination: Annotated[PaginationLimit20, Depends()],
    q: str = Query(..., title="Search query"),
):
    return await fulltext_search_async(
        q, page=pagination.page, limit=pagination.limit, js=True, facets=True
    )


@router.get("/search/subjects.json")
async def search_subjects_json(
    pagination: Annotated[Pagination, Depends()],
    q: str = Query("", description="The search query"),
):
    response = await async_run_solr_query(
        SubjectSearchScheme(),
        {'q': q},
        offset=pagination.offset,
        rows=pagination.limit,
        sort='work_count desc',
        request_label='SUBJECT_SEARCH_API',
    )

    # Backward compatibility
    raw_resp = response.raw_resp['response']
    for doc in raw_resp['docs']:
        doc['type'] = doc.get('subject_type', 'subject')
        doc['count'] = doc.get('work_count', 0)

    return raw_resp


@router.get("/search/lists.json")
async def search_lists_json(
    pagination: Annotated[PaginationLimit20, Depends()],
    q: str = Query("", description="The search query"),
    fields: str = Query("", description="Fields to return"),
    sort: str = Query("", description="Sort order"),
    api: str = Query(
        "", description="API version: 'next' for new format, empty for old format"
    ),
):
    response = await async_run_solr_query(
        ListSearchScheme(),
        {'q': q},
        offset=pagination.offset,
        rows=pagination.limit,
        fields=fields,
        sort=sort,
        request_label='LIST_SEARCH_API',
    )

    if api == 'next':
        # Match search.json
        return {
            'numFound': response.num_found,
            'num_found': response.num_found,
            'start': pagination.offset,
            'q': q,
            'docs': response.docs,
        }
    else:
        # Default to the old API shape for a while, then we'll flip
        lists = web.ctx.site.get_many([doc['key'] for doc in response.docs])
        return {
            'start': pagination.offset,
            'docs': [lst.preview() for lst in lists],
        }


@router.get("/search/authors.json")
async def search_authors_json(
    pagination: Annotated[Pagination, Depends()],
    q: str = Query("", description="The search query"),
    fields: str = Query("*", description="Fields to return"),
    sort: str = Query("", description="Sort order"),
):
    response = await async_run_solr_query(
        AuthorSearchScheme(),
        {'q': q},
        offset=pagination.offset,
        rows=pagination.limit,
        fields=fields,
        sort=sort,
        request_label='AUTHOR_SEARCH_API',
    )

    # SIGH the public API exposes the key like this :(
    raw_resp = response.raw_resp['response']
    for doc in raw_resp['docs']:
        doc['key'] = doc['key'].split('/')[-1]

    return raw_resp


class SubjectsRequestParams(BaseModel):
    """Parameters for the subjects endpoint."""

    limit: int = Field(
        DEFAULT_RESULTS,
        ge=1,
        le=MAX_RESULTS,
        description="Maximum number of results to return.",
    )
    offset: int = Field(0, ge=0, description="Number of results to skip.")
    details: bool = Field(False, description="Include detailed facet information.")
    has_fulltext: bool = Field(False, description="Filter for books with fulltext.")
    sort: str = Field("editions", description="Sort order of results.")
    available: bool = Field(
        False, description="Filter for available books (currently unused)."
    )
    published_in: str | None = Field(
        None, description="Date range filter (e.g., '2000-2010' or '2000')."
    )

    @computed_field
    def filters(self) -> dict[str, str]:
        """Build filters dict based on query parameters."""
        filters: dict[str, str] = {}
        if self.has_fulltext:
            filters['has_fulltext'] = 'true'

        if publish_year_filter := date_range_to_publish_year_filter(self.published_in):
            filters['publish_year'] = publish_year_filter

        return filters


@router.get("/subjects/{subjects}.json")
async def subjects_json(
    subjects: Annotated[
        str, Path(description="Subject key (e.g., 'fiction' or 'person:harry_potter')")
    ],
    params: Annotated[SubjectsRequestParams, Query()],
) -> Any:
    """
    Returns works related to a specific subject.

    Supports various query parameters for filtering and pagination:
    - **limit**: Number of results (default: 12, max: 1000)
    - **offset**: Number of results to skip (default: 0)
    - **details**: Include facet information (default: false)
    - **has_fulltext**: Filter for books with fulltext (default: false)
    - **sort**: Sort order (default: 'editions')
    - **published_in**: Date range filter (e.g., '2000-2010' or '2000')
    """
    # Normalize the key
    subjects = subjects.lower()

    # Get subject data
    try:
        subject_results = await get_subject_async(
            subjects,
            offset=params.offset,
            limit=params.limit,
            sort=params.sort,
            details=params.details,
            request_label='SUBJECT_ENGINE_API',
            **params.filters,
        )
    except NotImplementedError:
        # No SubjectEngine for this key
        raise HTTPException(status_code=404, detail=f"Subject not found: {subjects}")

    # Adjust ebook_count if has_fulltext filter is applied
    if params.has_fulltext:
        subject_results['ebook_count'] = subject_results['work_count']

    return subject_results
