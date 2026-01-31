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
    data: str = Query(
        ..., description="JSON-encoded data with parameters for the component"
    ),
) -> dict:
    """
    Get partial HTML for various components.

    This endpoint mirrors the legacy /partials.json endpoint but is implemented in FastAPI.

    """
    if _component != "FulltextSearchSuggestion":
        # For FulltextSearchSuggestion, the data query param is just a string, not a dict
        parsed_data = json.loads(data)
    else:
        parsed_data = data

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
