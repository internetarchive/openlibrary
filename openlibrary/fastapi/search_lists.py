from typing import Annotated

import web
from fastapi import APIRouter, Depends, Query

from openlibrary.fastapi.models import PaginationLimit20
from openlibrary.plugins.worksearch.code import async_run_solr_query
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme

router = APIRouter()


@router.get("/search/lists.json")
async def search_lists_json(
    pagination: Annotated[PaginationLimit20, Depends()],
    q: str = Query("", description="The search query"),
    fields: str = Query("", description="Fields to return"),
    sort: str = Query("", description="Sort order"),
    api: str = Query(
        "", description="API version: 'next' for new format, empty for old format"
    ),
):
    response = await async_run_solr_query(
        ListSearchScheme(),
        {'q': q},
        offset=pagination.offset,
        rows=pagination.limit,
        fields=fields,
        sort=sort,
        request_label='LIST_SEARCH_API',
    )

    if api == 'next':
        # Match search.json
        return {
            'numFound': response.num_found,
            'num_found': response.num_found,
            'start': pagination.offset,
            'q': q,
            'docs': response.docs,
        }
    else:
        # Default to the old API shape for a while, then we'll flip
        lists = web.ctx.site.get_many([doc['key'] for doc in response.docs])
        return {
            'start': pagination.offset,
            'docs': [lst.preview() for lst in lists],
        }
