from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from pydantic import BaseModel, BeforeValidator

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    is_librarian,
    require_authenticated_user,
)
from openlibrary.fastapi.models import parse_comma_separated_list
from openlibrary.fastapi.shared.dependencies import get_fullpath
from openlibrary.plugins.openlibrary.partials import (
    AffiliateLinksPartial,
    BookPageListsPartial,
    CarouselCardPartial,
    CarouselLoadMoreParams,
    FullTextSuggestionsPartial,
    LazyCarouselParams,
    LazyCarouselPartial,
    MyBooksDropperListsPartial,
    ReadingGoalProgressPartial,
    ReadingStatePartial,
    SearchFacetsPartial,
    SubjectPublishingHistoryPartial,
    SubjectRelatedPartial,
)

router = APIRouter()

# Only show partials endpoints in OpenAPI schema in local dev
SHOW_PARTIALS_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


@router.get("/partials/SearchFacets.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def search_facets_partial(
    data: Annotated[str, Query(description="JSON-encoded data with search parameters")],
    sfw: Annotated[str | None, Cookie()] = None,
    is_librarian: Annotated[bool, Depends(is_librarian)] = False,
) -> dict:
    """
    Get search facets sidebar and selected facets HTML.

    The data parameter should contain:
    - param: dict with search parameters (q, author_key, subject_facet, etc.)
    - path: str (e.g., '/search')
    - query: str (e.g., '?q=python')
    """
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in data parameter")

    return await SearchFacetsPartial.generate_async(data=parsed_data, sfw=sfw == "yes", show_merge_authors=is_librarian)


@router.get("/partials/SubjectPublishingHistory.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def subject_publishing_history_partial(
    key: Annotated[str, Query(description="Subject key (e.g. /subjects/cooking)")],
) -> dict:
    """
    Get the subject page's publishing-history chart HTML.
    """
    return await SubjectPublishingHistoryPartial.generate_async(key=key)


@router.get("/partials/SubjectRelated.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def subject_related_partial(
    key: Annotated[str, Query(description="Subject key (e.g. /subjects/cooking)")],
) -> dict:
    """
    Get the subject page's related subjects/places/people/times widget HTML.
    """
    return await SubjectRelatedPartial.generate_async(key=key)


@router.get("/partials/AffiliateLinks.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def affiliate_links_partial(
    title: Annotated[str, Query(description="Book title")],
    isbn: Annotated[str | None, Query(description="ISBN-13 or ISBN-10")] = None,
    asin: Annotated[str | None, Query(description="Amazon ASIN")] = None,
    prices: Annotated[bool, Query(description="Whether to fetch live prices")] = False,
) -> dict:
    """
    Get affiliate links HTML for a book.
    """
    return await AffiliateLinksPartial.generate_async(
        title=title,
        isbn=isbn,
        asin=asin,
        # Temporarily disabled due to amazon request timing out
        prices=False,
    )


@router.get("/partials/BPListsSection.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def book_page_lists_partial(
    workId: Annotated[str, Query(description="Work ID (e.g., /works/OL53924W)")] = "",
    editionId: Annotated[str, Query(description="Edition ID (e.g., /books/OL7353617M)")] = "",
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)] = None,
) -> dict:
    """
    Get book page lists section HTML.

    At least one of workId or editionId must be provided.
    """
    return await BookPageListsPartial.generate_async(workId=workId, editionId=editionId, user=user)


@router.get("/partials/FulltextSearchSuggestion.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def fulltext_search_suggestion_partial(
    response: Response,
    data: Annotated[str, Query(description="Search query string")],
) -> dict:
    """
    Get full-text search suggestions HTML.

    The data parameter is the raw search query string.
    """
    result = await FullTextSuggestionsPartial.generate_async(query=data)

    if not result.has_error:
        response.headers["Cache-Control"] = "public, max-age=300"

    return result.body


@router.get("/partials/ReadingGoalProgress.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def reading_goal_progress_partial(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    year: Annotated[int | None, Query(description="Year for reading goal (defaults to current year)")] = None,
) -> dict:
    """
    Get reading goal progress HTML for the current user.

    The year parameter is optional; defaults to the current year.
    """
    # Despite the face we are not yet using the user, it gives us faster auth checking and api documentation.
    return ReadingGoalProgressPartial.generate(year=year or datetime.now().year)


@router.get("/partials/MyBooksDropperLists.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def my_books_dropper_lists_partial(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """
    Get the current user's lists.

    Returns:
    - listData: dict mapping list keys to their members and names
    """
    # Despite the fact we are not yet using the user directly, it gives us faster
    # auth checking and api documentation.
    return MyBooksDropperListsPartial.generate()


MAX_READING_STATE_WORKS = 100
WORK_OLID = re.compile(r"^OL\d+W$")


def parse_work_olids(v: str | list[str]) -> list[str]:
    """Comma-separated work OLIDs; anything that is not one is a 422, not a 500."""
    olids = [olid.strip() for olid in parse_comma_separated_list(v) if olid.strip()]
    if bad := [olid for olid in olids if not WORK_OLID.match(olid)]:
        raise ValueError(f"Not a work OLID: {bad[0]}")
    return olids


class ReadingStateEntry(BaseModel):
    shelf: int | None
    rating: int | None
    read_date: str | None
    event_id: int | None


class ReadingStateResponse(BaseModel):
    user_key: str
    works: dict[str, ReadingStateEntry]


@router.get("/partials/ReadingState.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
def reading_state_partial(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    work_ids: Annotated[
        list[str],
        BeforeValidator(parse_work_olids),
        Query(description="Comma-separated work OLIDs, e.g. OL1W,OL2W", max_length=MAX_READING_STATE_WORKS),
    ],
) -> ReadingStateResponse:
    """
    The current user's shelf, rating and last finish date for each work, keyed by OLID.

    Every requested work is present, with nulls where the reader has no state.
    book-state.js hydrates carousel shelf buttons from this.
    """
    states = ReadingStatePartial.generate(user.username, work_ids)
    return ReadingStateResponse(user_key=user.user_key, works={olid: ReadingStateEntry(**state) for olid, state in states.items()})


@router.get("/partials/LazyCarousel.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def lazy_carousel_partial(
    params: Annotated[LazyCarouselParams, Query()],
) -> dict:
    """
    Get lazily-loaded carousel HTML.
    """
    return await LazyCarouselPartial.generate_async(params=params)


@router.get("/partials/CarouselLoadMore.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def carousel_load_more_partial(
    params: Annotated[CarouselLoadMoreParams, Query()],
    full_path: Annotated[str, Depends(get_fullpath)],
) -> dict:
    """
    Get additional carousel card HTML for paginated carousels.

    Parameters (query string) are defined by CarouselLoadMoreParams:
    queryType (SEARCH | BROWSE | TRENDING | SUBJECTS), q, limit, page,
    sorts, subject, hasFulltextOnly, key, layout, published_in.
    """
    return await CarouselCardPartial.generate_async(params=params, full_path=full_path)
