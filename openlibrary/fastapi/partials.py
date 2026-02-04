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
    # Handle BPListsSection with separate query parameters
    if _component == "BPListsSection":
        parsed_data = {"workId": workId, "editionId": editionId}
    elif _component == "FulltextSearchSuggestion":
        # For FulltextSearchSuggestion, the data query param is just a string, not a dict
        parsed_data = data if data else ""
    elif data:
        # For other components, parse JSON data
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid JSON in data parameter"
            )
    else:
        raise HTTPException(status_code=400, detail="Missing required data parameter")

    if _component == "SearchFacets":
        return SearchFacetsPartial(data=parsed_data).generate()
    elif _component == "BPListsSection":
        return BookPageListsPartial(data=parsed_data).generate()
    elif _component == "AffiliateLinks":
        return AffiliateLinksPartial(data=parsed_data).generate()
    elif _component == "FulltextSearchSuggestion":
        return FullTextSuggestionsPartial(data=parsed_data).generate()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown component: {_component}")
