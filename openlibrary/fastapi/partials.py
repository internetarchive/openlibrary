from __future__ import annotations

import json

from fastapi import APIRouter, Query

from openlibrary.plugins.openlibrary.partials import SearchFacetsPartial

router = APIRouter()


@router.get("/partials.json")
async def search_facets_partial(
    _component: str = Query(..., description="Component name (must be 'SearchFacets')"),
    data: str = Query(..., description="JSON-encoded data with param, path, and query"),
) -> dict:
    """
    Get search facets partial HTML for the sidebar and selected facets.

    This endpoint mirrors the legacy /partials.json?_component=SearchFacets endpoint
    but is implemented in FastAPI.

    Args:
        _component: Must be "SearchFacets"
        data: JSON-encoded string containing param, path, and query

    Returns:
        Dictionary with:
        - sidebar: HTML string for the facets sidebar
        - title: Page title string
        - activeFacets: HTML string for selected/active facets
    """
    if _component != "SearchFacets":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=f"Unknown component: {_component}")

    parsed_data = json.loads(data)
    handler = SearchFacetsPartial(data=parsed_data)
    return handler.generate()
