from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import ceil
from typing import Annotated, Any, Literal, Self
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, Query, Request
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

from openlibrary.core.env import get_ol_env
from openlibrary.core.fulltext import fulltext_search_async, resolve_language
from openlibrary.core.helpers import commify, urlsafe
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.models import (
    Pagination,
    PaginationLimit20,
    SolrInternalsParams,
    parse_comma_separated_list,
)
from openlibrary.fastapi.shared.site_page import CurrentUserDep, SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.inside.code import RESULTS_PER_PAGE, hit_editions, render_inside_body
from openlibrary.plugins.upstream.mybooks import get_reading_states_async
from openlibrary.plugins.upstream.utils import get_coverstore_public_url
from openlibrary.plugins.worksearch.code import (
    default_spellcheck_count,
    run_solr_query_async,
    validate_search_json_query,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.plugins.worksearch.sort_menu import SortMenu, SortScheme
from openlibrary.utils.request_context import req_context, site

router = APIRouter()
pages = APIRouter(route_class=SitePageRoute)

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

# Whether to expose internal-only endpoints in the OpenAPI schema.
# Only shown when running with LOCAL_DEV set (e.g. docker compose).
SHOW_INTERNAL_IN_SCHEMA = get_ol_env().LOCAL_DEV


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


def create_sort_option_type(sorts_map: Mapping):
    """
    Generates a Pydantic type alias that validates against the provided
    sorts_map and dynamically generates the OpenAPI Enum documentation.
    """
    # TODO: Use this for the work-search sort parameter too?
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


EditionSortOption = create_sort_option_type(EditionSearchScheme.sorts)


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

    editions_sort: EditionSortOption | None = Field(  # type: ignore[valid-type]
        None,
        alias="editions.sort",
        description="Sort the editions nested in each work. Same values as sort on /search/editions.json.",
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
            # Not a PublicQueryOptions or WorkSearchScheme field, so copy the dotted name explicitly.
            # Skip when empty so Solr keeps its default edition ordering.
            if self.editions_sort:
                q["editions.sort"] = self.editions_sort
            return q


class FacetRequestParams(PublicQueryOptions):
    """
    Query params for /search/facets.json — the search context plus the field(s) to count.

    `field` is a model field rather than a sibling parameter because FastAPI only expands a
    Pydantic query model when nothing else in the signature is a list-typed `Query`. Declared
    separately, the model binds as one scalar named "params" and every request 422s; under
    `Depends()` it binds but the inherited list filters (language, subject_facet, ...) silently
    arrive empty, so the counts ignore them.
    """

    field: list[FacetField] = Field(
        ...,
        min_length=1,
        description="Facet field(s) to return. Repeat for multiple.",
    )


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


class SearchInsidePagination(Pagination):
    limit: int = Field(20, ge=0, le=100, description="Maximum number of results to return (max 100).")


@router.get("/search/inside.json")
async def search_inside_json(
    pagination: Annotated[SearchInsidePagination, Depends()],
    q: Annotated[str, Query(title="Search query")],
    facets: Annotated[bool, Query(description="Include facet aggregations in the response.")] = True,
    readable: Annotated[bool, Query(description="Drop matches that aren't readable (public or borrowable) scans. hits.total still counts them.")] = False,
    phrase: Annotated[
        bool,
        Query(description="Search an unquoted query as one exact phrase, falling back to all the words when it has no hits. false searches all the words."),
    ] = True,
    language: Annotated[
        list[str] | None,
        Query(description="Filter by language — a MARC code (e.g. fre) or language name. The FTS backend takes one language; extra values are ignored."),
    ] = None,
):
    resolved = resolve_language(language)
    return await fulltext_search_async(
        q,
        page=pagination.page,
        offset=pagination.offset,
        limit=pagination.limit,
        js=True,
        facets=facets,
        readable=readable,
        phrase=phrase,
        # FTS takes the language name, not the MARC code.
        language=resolved[1] if resolved else None,
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
        lists = site.get().get_many([doc["key"] for doc in response.docs])
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


class EditionSearchRequestParams(Pagination):
    q: str = Field("", description="The search query")
    work_key: str | None = Field(
        None,
        description="Filter results to editions of a specific work.",
        examples=["/works/OL82536W"],
    )
    fields: Annotated[list[str], BeforeValidator(parse_comma_separated_list)] = Field(
        sorted(EditionSearchScheme.default_fetched_fields),
        description="The fields to return.",
    )
    sort: EditionSortOption = Field("", description="Sort order")  # type: ignore[valid-type]


@router.get("/search/editions.json", tags=["search"])
async def search_editions_json(
    params: Annotated[EditionSearchRequestParams, Query()],
) -> Any:
    """
    Search for edition documents in the Solr index.

    Supports full-text search across edition fields (title, ISBN, publisher, etc.)
    and optional filtering by work key.
    """
    extra_params: list[tuple[str, Any]] = []
    if params.work_key:
        work_key = params.work_key.strip().rstrip("/").split("/")[-1]
        safe_key = work_key.replace("\\", "\\\\").replace('"', '\\"')
        extra_params.append(("fq", f'work_key:"{safe_key}"'))

    response = await run_solr_query_async(
        EditionSearchScheme(),
        {"q": params.q or "*:*"},
        offset=params.offset,
        page=params.page,
        rows=params.limit,
        fields=params.fields,
        sort=params.sort,
        facet=False,
        extra_params=extra_params or None,
        request_label="EDITION_SEARCH_API",
    )

    raw_resp = response.raw_resp.get("response", {}) if response.raw_resp else {}
    return {
        "numFound": raw_resp.get("numFound", response.num_found or 0),
        "start": raw_resp.get("start", params.offset or 0),
        "numFoundExact": raw_resp.get("numFoundExact", response.num_found_exact),
        "num_found": raw_resp.get("numFound", response.num_found or 0),
        "q": params.q,
        "offset": params.offset,
        "docs": raw_resp.get("docs", response.docs or []),
    }


@router.get(
    "/search/facets.json",
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
    response_model=dict[str, list[FacetValue]],
)
async def search_facets_json(
    request: Request,
    params: Annotated[FacetRequestParams, Query()],
    solr_internals_params: Annotated[SolrInternalsParams | None, Depends(SolrInternalsParams.from_request)] = None,
) -> dict[str, list[FacetValue]]:
    """
    Returns context-aware facet values for one or more search facet fields.

    Queries Solr with rows=0 alongside the current search params, returning only
    values with count > 0, ordered by count descending. Designed to power the
    OlSelectPopover components in the search results filter bar (PR #12949).

    Example: GET /search/facets.json?field=language&field=subject_facet&q=lord+of+the+rings
    """
    search_response = await run_solr_query_async(
        WorkSearchScheme(lang=request.state.lang, solr_editions=req_context.get().solr_editions),
        params.model_dump(exclude={"field"}, exclude_none=True),
        rows=0,
        page=1,
        fields=["key", "editions"],  # opt into the same edition block-join as /search
        facet=list(params.field),
        highlight=False,
        request_label="BOOK_SEARCH_FACETS",
        solr_internals_params=solr_internals_params,
    )

    result: dict[str, list[FacetValue]] = {f: [] for f in params.field}
    if search_response.facet_counts:
        for facet_field, values in search_response.facet_counts.items():
            output_key = _FACET_INTERNAL_RENAME.get(facet_field, facet_field)
            if output_key not in result:
                continue
            # values are (filter_value, display_label, count) tuples; label differs
            # from value for author_facet (name vs OL key) and "Name|key" subject fields.
            result[output_key] = [FacetValue(value=value, label=label, count=count) for value, label, count in values if count > 0]

    return result


@dataclass(frozen=True)
class SearchNav:
    """What the search tabs (``SearchNavigation.html.jinja``) need from the request."""

    path: str
    q_query: str  # urlencoded ``q=...``, carried over to every tab
    advanced_href: str

    @classmethod
    def from_query(cls, path: str, params: Mapping[str, str]) -> Self:
        """``params`` holds one value per key, the last if repeated, as ``web.input()`` does."""
        query = {k: v for k, v in params.items() if k != "page"}
        return cls(
            path=path,
            q_query=urlencode({"q": query.get("q", "")}),
            advanced_href="/advancedsearch" + (f"?{urlencode(query)}" if query else ""),
        )

    @classmethod
    def from_request(cls, request: Request) -> Self:
        # Starlette's query_params.items() also keeps a repeated key's last value.
        return cls.from_query(request.url.path, request.query_params)


SearchNavDep = Annotated[SearchNav, Depends(SearchNav.from_request)]


@dataclass(frozen=True)
class SortLinks:
    """What the sort menu (``SortMenu``) needs from the request: the page's path and query to build its links, and who is asking.

    ``path`` is the request path. A page with a readable URL (``/authors/OL1A/Name``) must link from that path.
    """

    path: str
    params: Mapping[str, str]  # one value per key, the last if repeated
    is_bot: bool
    is_librarian: bool  # sees the beta sorts

    @classmethod
    def from_request(cls, request: Request, user: CurrentUserDep) -> Self:
        return cls(request.url.path, dict(request.query_params), req_context.get().is_bot, bool(user and user.is_librarian))

    def menu(self, selected_sort: str | None, *, scheme: SortScheme) -> SortMenu:
        return SortMenu.build(selected_sort, path=self.path, params=self.params, scheme=scheme, can_see_beta_sorts=self.is_librarian, is_bot=self.is_bot)


SortLinksDep = Annotated[SortLinks, Depends(SortLinks.from_request)]


class AdvancedSearchForm(BaseModel):
    """Pre-fill for the /advancedsearch form. A ``*_facet`` param fills its field when that is empty."""

    q: str = ""
    title: str = ""
    author: str = ""
    isbn: str = ""
    subject: str = ""
    place: str = ""
    person: str = ""
    publisher: str = ""
    subject_facet: str = ""
    place_facet: str = ""
    person_facet: str = ""
    publisher_facet: str = ""

    @model_validator(mode="after")
    def facets_are_fallbacks(self) -> Self:
        self.subject = self.subject or self.subject_facet
        self.place = self.place or self.place_facet
        self.person = self.person or self.person_facet
        self.publisher = self.publisher or self.publisher_facet
        return self


@pages.get("/advancedsearch")
async def advancedsearch(form: Annotated[AdvancedSearchForm, Query()], nav: SearchNavDep) -> SitePage:
    return SitePage(render_jinja_template("search/advancedsearch.html.jinja", form=form, nav=nav), page=PageMeta(title=_("Advanced Search")))


def lists_search_title(q: str) -> str:
    """Page title for /search/lists: led by the query, as in Wikipedia's, so tabs and history tell searches apart."""
    return _("%(query)s - List search", query=q) if q else _("List search")


@pages.get("/search/lists")
async def search_lists(nav: SearchNavDep, user: CurrentUserDep, q: str = "", page: int = 1) -> SitePage:
    # TODO: Retire the web.py `list_search` handler (it still serves /search/lists
    # in production) once production routes /search/lists here.
    page = max(1, page)
    limit = 20  # Can't set fields or limit when rendering html
    response = await run_solr_query_async(
        ListSearchScheme(),
        {"q": q},
        offset=(page - 1) * limit,
        rows=limit,
        fields="key",
        sort="",
        request_label="LIST_SEARCH",
    )
    lists = site.get().get_many([doc["key"] for doc in response.docs])

    body = render_jinja_template(
        "search/lists.html.jinja",
        nav=nav,
        q=q,
        search_response=response,
        previews=[lst.card(user.key if user else None) for lst in lists],
        commified_num_found=commify(response.num_found),
        page=page,
        total_pages=ceil(response.num_found / limit),
    )
    return SitePage(body, page=PageMeta(title=lists_search_title(q)))


class InsideSearchParams(BaseModel):
    """Query params for /search/inside.

    Plain `str` flags, not `Literal`: web.py answers `readable=yes` by reading it
    as false, and the page has to render that rather than return a 422.
    """

    q: str = ""
    page: int = 1
    language: list[str] = Field(
        [],
        description="Filter by language — a MARC code (e.g. fre) or language name. The FTS backend takes one language; extra values are ignored.",
    )
    readable: str = Field("", description="'true' keeps only hits on readable (public or borrowable) scans.")
    phrase: str = Field("true", description="'false' searches all the words instead of the exact phrase.")


@dataclass(frozen=True)
class InsideNav:
    """The phrase toggles in the results header, each keeping the page's other filters."""

    all_words_href: str
    phrase_href: str

    @classmethod
    def from_query(cls, path: str, query: str) -> Self:
        """``query`` is the raw query string, with or without its leading "?"; repeated params are kept."""
        pairs = [(key, value) for key, value in parse_qsl(query.lstrip("?"), keep_blank_values=True) if key not in {"page", "phrase"}]
        return cls(
            all_words_href=f"{path}?{urlencode([*pairs, ('phrase', 'false')])}",
            phrase_href=f"{path}?{urlencode(pairs)}" if pairs else path,
        )

    @classmethod
    def from_request(cls, request: Request) -> Self:
        return cls.from_query(request.url.path, request.url.query)


InsideNavDep = Annotated[InsideNav, Depends(InsideNav.from_request)]


def inside_search_title(q: str) -> str:
    """Page title for /search/inside: led by the query, as on the other search pages."""
    return _("%(query)s - Full-text search", query=q) if q else _("Full-text search")


@pages.get("/search/inside")
async def search_inside(params: Annotated[InsideSearchParams, Query()], nav: SearchNavDep, inside_nav: InsideNavDep, user: CurrentUserDep) -> SitePage:
    # TODO: Retire the web.py `search_inside` handler (it still serves /search/inside
    # in production) once production routes /search/inside here.
    query = params.q
    page = max(1, params.page)
    readable = params.readable == "true"
    phrase = params.phrase != "false"
    # (code, name): FTS takes the name; generated URLs keep the code. Only look the
    # name up when a language was asked for: the table comes from the database.
    language = resolve_language(params.language) if params.language else None

    data = (
        await fulltext_search_async(
            query,
            page=page,
            limit=RESULTS_PER_PAGE,
            facets=False,
            readable=readable,
            language=language[1] if language else None,
            phrase=phrase,
        )
        if query
        else {}
    )

    # One reading-state lookup for the page, awaited rather than bridged: the sync
    # get_reading_states() waits on async_bridge's loop thread, which stalls every
    # other request this worker is serving for the round trip.
    reading_states = await get_reading_states_async(user, hit_editions(data))

    body = render_inside_body(
        nav=nav,
        inside_nav=inside_nav,
        query=query,
        page=page,
        language=language,
        readable=readable,
        phrase=phrase,
        data=data,
        reading_states=reading_states,
    )
    # The search pages size their covers and rows differently, so they set bodyclass just as the Templetor page did.
    return SitePage(body, page=PageMeta(title=inside_search_title(query), bodyclass=("search-page",)))


def subjects_search_title(q: str) -> str:
    """Page title for /search/subjects: led by the query, as in Wikipedia's, so tabs and history tell searches apart."""
    return _("%(query)s - Subject search", query=q) if q else _("Subject search")


@pages.get("/search/subjects")
async def search_subjects(nav: SearchNavDep, q: str = "", page: int = 1) -> SitePage:
    # TODO: Retire the web.py `subject_search` handler (it still serves /search/subjects
    # in production) once production routes /search/subjects here.
    q = q.strip()
    page = max(1, page)
    limit = 100
    response = (
        await run_solr_query_async(
            SubjectSearchScheme(),
            {"q": q},
            offset=(page - 1) * limit,
            rows=limit,
            sort="work_count desc",
            request_label="SUBJECT_SEARCH",
        )
        if q
        else None
    )

    body = render_jinja_template(
        "search/subjects.html.jinja",
        nav=nav,
        q=q,
        search_response=response,
        commified_num_found=commify(response.num_found) if response and response.num_found is not None else "",
        page=page,
        total_pages=ceil((response.num_found or 0) / limit) if response else 0,
    )
    return SitePage(body, page=PageMeta(title=subjects_search_title(q)))


@dataclass(frozen=True)
class PublisherResult:
    """One row of /search/publishers: a publisher's name, page link and book count."""

    name: str
    key: str
    count: int


def publisher_search_query(q: str) -> dict[str, Any]:
    """The facet-only Solr query behind /search/publishers, shared with web.py's handler.
    ``select`` and ``select_async`` take the same arguments, so this splats into either.
    """
    return {
        "query": {"publisher": q, "type": "work"},
        "facets": ["publisher_facet"],
        "facet_mincount": 1,
        "facet_limit": 25,
        "facet_contains": q,
        "facet_contains_ignoreCase": "true",
        "rows": 0,
    }


def publisher_results(facet_values: Iterable[Any]) -> list[PublisherResult]:
    """Map Solr's ``publisher_facet`` values to the page's rows."""
    return [PublisherResult(name=p.value, key="/publishers/" + p.value.replace(" ", "_"), count=p.count) for p in facet_values]


def publisher_search_title(q: str) -> str:
    """Page title for /search/publishers: led by the query, as in Wikipedia's, so tabs and history tell searches apart."""
    return _("%(query)s - Publisher search", query=q) if q else _("Publisher search")


@pages.get("/search/publishers")
async def search_publishers(q: str = "") -> SitePage:
    # TODO: Retire the web.py `publisher_search` handler (it still serves
    # /search/publishers in production) once production routes it here.
    result = await get_solr().select_async(**publisher_search_query(q))
    body = render_jinja_template(
        "search/publishers.html.jinja",
        q=q,
        publishers=publisher_results((result.get("facets") or {}).get("publisher_facet", [])),
    )
    return SitePage(body, page=PageMeta(title=publisher_search_title(q)))


def authors_search_title(q: str) -> str:
    """Page title for /search/authors: led by the query, as in Wikipedia's, so tabs and history tell searches apart."""
    return _("%(query)s - Author search", query=q) if q else _("Author search")


@pages.get("/search/authors")
async def search_authors(nav: SearchNavDep, sort_links: SortLinksDep, user: CurrentUserDep, q: str = "", page: int = 1, sort: AuthorSortOption = "") -> SitePage:  # type: ignore[valid-type]
    # TODO: Retire the web.py `author_search` handler (it still serves /search/authors
    # in production) once production routes /search/authors here.
    q = q.strip()
    page = max(1, page)
    limit = 100  # Matches web.py's author_search results_per_page
    response = (
        await run_solr_query_async(
            AuthorSearchScheme(),
            {"q": q},
            offset=(page - 1) * limit,
            rows=limit,
            fields="*",
            sort=sort,
            request_label="AUTHOR_SEARCH",
        )
        if q
        else None
    )
    # num_found is None when Solr errors; the template shows the error instead of results.
    num_found = (response.num_found or 0) if response else 0

    body = render_jinja_template(
        "search/authors.html.jinja",
        nav=nav,
        q=q,
        sort_menu=sort_links.menu(sort, scheme="authors"),
        search_response=response,
        can_merge=bool(user and user.is_librarian),
        urlsafe=urlsafe,
        coverstore_url=get_coverstore_public_url(),
        commified_num_found=commify(num_found),
        page=page,
        total_pages=ceil(num_found / limit),
    )
    return SitePage(body, page=PageMeta(title=authors_search_title(q)))
