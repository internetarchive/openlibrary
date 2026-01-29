from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from openlibrary.plugins.openlibrary.partials import (
    BookPageListsPartial,
    SearchFacetsPartial,
)

router = APIRouter()


@router.get("/partials.json")
async def partials_endpoint(
    _component: str = Query(
        ..., description="Component name (e.g., 'SearchFacets', 'BPListsSection')"
    ),
    data: str = Query(
        ..., description="JSON-encoded data with parameters for the component"
    ),
) -> dict:
    """
    Get partial HTML for various components.

    This endpoint mirrors the legacy /partials.json endpoint but is implemented in FastAPI.

    Args:
        _component: Component name (e.g., "SearchFacets", "BPListsSection")
        data: JSON-encoded string containing parameters for the component

    Returns:
        Dictionary with component-specific data
    """
    parsed_data = json.loads(data)

    if _component == "SearchFacets":
        handler: SearchFacetsPartial | BookPageListsPartial = SearchFacetsPartial(
            data=parsed_data
        )
        return handler.generate()
    elif _component == "BPListsSection":
        handler = BookPageListsPartial(data=parsed_data)
        return handler.generate()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown component: {_component}")
