from typing import Annotated

from fastapi import APIRouter, Depends, Query

from openlibrary.fastapi.models import Pagination
from openlibrary.plugins.worksearch.code import async_run_solr_query
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme

router = APIRouter()


@router.get("/search/authors.json")
async def search_authors_json(
    pagination: Annotated[Pagination, Depends()],
    q: str = Query("", description="The search query"),
    fields: str = Query("*", description="Fields to return"),
    sort: str = Query("", description="Sort order"),
):
    response = await async_run_solr_query(
        AuthorSearchScheme(),
        {'q': q},
        offset=pagination.offset,
        rows=pagination.limit,
        fields=fields,
        sort=sort,
        request_label='AUTHOR_SEARCH_API',
    )

    # SIGH the public API exposes the key like this :(
    raw_resp = response.raw_resp['response']
    for doc in raw_resp['docs']:
        doc['key'] = doc['key'].split('/')[-1]

    return raw_resp
