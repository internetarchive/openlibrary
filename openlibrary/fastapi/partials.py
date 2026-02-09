from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from openlibrary.plugins.openlibrary.partials import (
    AffiliateLinksPartial,
    BookPageListsPartial,
    FullTextSuggestionsPartial,
    SearchFacetsPartial,
)

router = APIRouter()


@router.get("/partials/SearchFacets.json")
async def search_facets_partial(
    data: str = Query(..., description="JSON-encoded data with search parameters"),
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

    return SearchFacetsPartial(data=parsed_data).generate()


@router.get("/partials/AffiliateLinks.json")
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


@router.get("/partials/BPListsSection.json")
async def book_page_lists_partial(
    workId: str = Query("", description="Work ID (e.g., /works/OL53924W)"),
    editionId: str = Query("", description="Edition ID (e.g., /books/OL7353617M)"),
) -> dict:
    """
    Get book page lists section HTML.

    At least one of workId or editionId must be provided.
    """
    # TODO: make this work when user is logged in. Blocked on #11816
    return BookPageListsPartial(workId=workId, editionId=editionId).generate()


@router.get("/partials/FulltextSearchSuggestion.json")
async def fulltext_search_suggestion_partial(
    data: str = Query(..., description="Search query string"),
) -> dict:
    """
    Get full-text search suggestions HTML.

    The data parameter is the raw search query string.
    """
    return FullTextSuggestionsPartial(query=data).generate()
