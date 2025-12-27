import web
from fastapi import APIRouter, Query

from openlibrary.plugins.worksearch.code import async_run_solr_query
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme

router = APIRouter()


@router.get("/search/lists.json")
async def search_lists_json(
    q: str = Query("", description="The search query"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=0, le=1000),
    fields: str = Query("", description="Fields to return"),
    sort: str = Query("", description="Sort order"),
    api: str = Query(
        "", description="API version: 'next' for new format, empty for old format"
    ),
):
    # Handle page parameter
    page = offset // limit + 1 if offset > 0 else 1
    offset = offset if offset > 0 else limit * (page - 1)

    response = await async_run_solr_query(
        ListSearchScheme(),
        {'q': q},
        offset=offset,
        rows=limit,
        fields=fields,
        sort=sort,
        request_label='LIST_SEARCH_API',
    )

    if api == 'next':
        # Match search.json
        return {
            'numFound': response.num_found,
            'num_found': response.num_found,
            'start': offset,
            'q': q,
            'docs': response.docs,
        }
    else:
        # Default to the old API shape for a while, then we'll flip
        lists = web.ctx.site.get_many([doc['key'] for doc in response.docs])
        return {
            'start': offset,
            'docs': [lst.preview() for lst in lists],
        }
