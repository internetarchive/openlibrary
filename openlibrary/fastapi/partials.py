from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from openlibrary.plugins.openlibrary.partials import (
    AffiliateLinksPartial,
    BookPageListsPartial,
    FullTextSuggestionsPartial,
    SearchFacetsPartial,
)

router = APIRouter()


@router.get("/partials.json")
async def partials_endpoint(
    _component: Literal[
        "SearchFacets", "BPListsSection", "AffiliateLinks", "FulltextSearchSuggestion"
    ] = Query(
        ...,
        description="Component name",
    ),
    data: str | None = Query(
        None, description="JSON-encoded data with parameters for the component"
    ),
    workId: str = Query("", description="Work ID (for BPListsSection component)"),
    editionId: str = Query("", description="Edition ID (for BPListsSection component)"),
) -> dict:
    """
    Get partial HTML for various components.

    This endpoint mirrors the legacy /partials.json endpoint but is implemented in FastAPI.

    For BPListsSection, accepts separate parameters:
    - ?workId=/works/OL53924W&editionId=/books/OL7353617M

    For other components, uses the data parameter (JSON).
    """
    # Parse JSON data for components that need it
    parsed_data: dict | None = None
    if data and _component in ("SearchFacets", "AffiliateLinks"):
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid JSON in data parameter"
            )

    if _component == "SearchFacets":
        if not parsed_data:
            raise HTTPException(
                status_code=400, detail="Missing required data parameter"
            )
        return SearchFacetsPartial(data=parsed_data).generate()

    elif _component == "AffiliateLinks":
        if not parsed_data:
            raise HTTPException(
                status_code=400, detail="Missing required data parameter"
            )
        return AffiliateLinksPartial(data=parsed_data).generate()

    elif _component == "BPListsSection":
        # Pass parameters directly - much simpler!
        return BookPageListsPartial(workId=workId, editionId=editionId).generate()

    elif _component == "FulltextSearchSuggestion":
        # data is just a string, not JSON
        return FullTextSuggestionsPartial(data=data or "").generate()

    else:
        raise HTTPException(status_code=400, detail=f"Unknown component: {_component}")
