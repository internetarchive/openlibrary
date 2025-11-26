from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, create_model

from openlibrary.plugins.worksearch.code import (
    default_spellcheck_count,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

router = APIRouter()

ListQuery = Annotated[list[str], Query(default_factory=list)]


# Ideally this will go in a models files, we'll move it for the 2nd endpoint
class Pagination(BaseModel):
    limit: int = 100
    offset: int | None = None
    page: int | None = None

    def model_post_init(self, _):
        if self.offset is not None:
            self.page = None
        else:
            self.page = self.page or 1


# Ideally this will go in a dependencies file, we'll move it for the 2nd endpoint
def pagination(
    limit: Annotated[int, Query(ge=1)] = 100,
    offset: Annotated[int | None, Query(ge=0)] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
) -> Pagination:
    return Pagination(limit=limit, offset=offset, page=page)


field_names = set(WorkSearchScheme.all_fields) | set(
    WorkSearchScheme.field_name_map.keys()
)

# Dynamically create the model
AllAllowedParams = create_model(
    'AllAllowedParams',
    __base__=BaseModel,
    **{
        field.removeprefix('_'): (str | None, Query(None, alias=field))
        for field in field_names
    },
)


@router.get("/search.json", response_class=JSONResponse)
async def search_json(  # noqa: PLR0913
    request: Request,
    author_key: ListQuery,
    subject_facet: ListQuery,
    person_facet: ListQuery,
    place_facet: ListQuery,
    time_facet: ListQuery,
    first_publish_year: ListQuery,
    publisher_facet: ListQuery,
    language: ListQuery,
    public_scan_b: ListQuery,  # tbd if this should actually be a list
    pagination: Annotated[Pagination, Depends(pagination)],
    all_allowed_params: Annotated[  # type: ignore[valid-type]
        AllAllowedParams,
        Depends(),
    ],
    q: str | None = Query("", description="The search query."),
    sort: str | None = Query(None, description="The sort order of results."),
    fields: str | None = Query(None, description="The fields to return."),
    spellcheck_count: int | None = Query(
        default_spellcheck_count, description="The number of spellcheck suggestions."
    ),
    query_str: str | None = Query(
        None, alias="query", description="A full JSON encoded solr query."
    ),
):
    """
    Performs a search for documents based on the provided query.
    """
    # return author_key
    query: dict[str, Any] = {}
    if query_str:
        query = json.loads(query_str)
    else:
        query = {"q": q, "page": pagination.page, "limit": pagination.limit}
        query.update({k: v for k, v in all_allowed_params.model_dump().items() if v is not None})  # type: ignore[attr-defined]
        query.update(
            {
                "author_key": author_key,
                "subject_facet": subject_facet,
                "person_facet": person_facet,
                "place_facet": place_facet,
                "time_facet": time_facet,
                "first_publish_year": first_publish_year,
                "publisher_facet": publisher_facet,
                "language": language,
                "public_scan_b": public_scan_b,
            }
        )

    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    response = await work_search_async(
        query,
        sort=sort,
        page=pagination.page,
        offset=pagination.offset,
        limit=pagination.limit,
        fields=_fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=spellcheck_count,
        request_label='BOOK_SEARCH_API',
        lang=request.state.lang,
    )

    # Add extra metadata to the response to match the original
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"
    response['q'] = q
    response['offset'] = pagination.offset

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
