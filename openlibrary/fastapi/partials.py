from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
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
    SearchFacetsPartial,
)

router = APIRouter()

# Only show partials endpoints in OpenAPI schema in local dev
SHOW_PARTIALS_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


@router.get("/partials/SearchFacets.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def search_facets_partial(
    data: str = Query(..., description="JSON-encoded data with search parameters"),
    sfw: Annotated[str | None, Cookie()] = None,
) -> dict:
    """
    Get search facets sidebar and selected facets HTML.

    The data parameter should contain:
    - param: dict with search parameters (q, author_key, subject_facet, etc.)
    - path: str (e.g., '/search')
    - query: str (e.g., '?q=python')
    # TODO: Make this fully async
    """
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in data parameter")

    return SearchFacetsPartial(data=parsed_data, sfw=sfw == "yes").generate()


@router.get("/partials/AffiliateLinks.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def affiliate_links_partial(
    data: str = Query(..., description="JSON-encoded data with book information"),
) -> dict:
    """
    Get affiliate links HTML for a book.

    The data parameter should contain:
    - args: list with [title, opts] where opts is a dict with optional isbn
    """
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in data parameter")

    return AffiliateLinksPartial(data=parsed_data).generate()


@router.get("/partials/BPListsSection.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def book_page_lists_partial(
    workId: str = Query("", description="Work ID (e.g., /works/OL53924W)"),
    editionId: str = Query("", description="Edition ID (e.g., /books/OL7353617M)"),
) -> dict:
    """
    Get book page lists section HTML.

    At least one of workId or editionId must be provided.
    """
    return BookPageListsPartial(workId=workId, editionId=editionId).generate()


@router.get("/partials/FulltextSearchSuggestion.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def fulltext_search_suggestion_partial(
    response: Response,
    data: str = Query(..., description="Search query string"),
) -> dict:
    """
    Get full-text search suggestions HTML.

    The data parameter is the raw search query string.
    """
    partial = FullTextSuggestionsPartial(query=data)
    result = partial.generate()

    if not partial.has_error:
        response.headers["Cache-Control"] = "public, max-age=300"

    return result


@router.get("/partials/ReadingGoalProgress.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def reading_goal_progress_partial(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    year: int | None = Query(None, description="Year for reading goal (defaults to current year)"),
) -> dict:
    """
    Get reading goal progress HTML for the current user.

    The year parameter is optional; defaults to the current year.
    """
    # Despite the face we are not yet using the user, it gives us faster auth checking and api documentation.
    return ReadingGoalProgressPartial(year=year or datetime.now().year).generate()


@router.get("/partials/MyBooksDropperLists.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def my_books_dropper_lists_partial(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """
    Get MyBooks dropper lists HTML and list data for the current user.

    Returns:
    - dropper: HTML string for the dropper lists component
    - listData: dict mapping list keys to their members and names
    """
    # Despite the fact we are not yet using the user directly, it gives us faster
    # auth checking and api documentation.
    return MyBooksDropperListsPartial().generate()


@router.get("/partials/LazyCarousel.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def lazy_carousel_partial(
    params: Annotated[LazyCarouselParams, Query()],
) -> dict:
    """
    Get lazily-loaded carousel HTML.
    """
    return LazyCarouselPartial(params=params).generate()


@router.get("/partials/CarouselLoadMore.json", include_in_schema=SHOW_PARTIALS_IN_SCHEMA)
async def carousel_load_more_partial(
    params: Annotated[CarouselLoadMoreParams, Query()],
) -> dict:
    """
    Get additional carousel card HTML for paginated carousels.

    Parameters (query string) are defined by CarouselLoadMoreParams:
    queryType (SEARCH | BROWSE | TRENDING | SUBJECTS), q, limit, page,
    sorts, subject, hasFulltextOnly, key, layout, published_in.
    """
    return CarouselCardPartial(params=params).generate()
