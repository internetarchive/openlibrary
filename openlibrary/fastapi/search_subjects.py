from typing import Annotated

from fastapi import APIRouter, Depends, Query

from openlibrary.fastapi.models import Pagination
from openlibrary.plugins.worksearch.code import async_run_solr_query
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme

router = APIRouter()


@router.get("/search/subjects.json")
async def search_subjects_json(
    pagination: Annotated[Pagination, Depends()],
    q: str = Query("", description="The search query"),
):
    response = await async_run_solr_query(
        SubjectSearchScheme(),
        {'q': q},
        offset=pagination.offset,
        rows=pagination.limit,
        sort='work_count desc',
        request_label='SUBJECT_SEARCH_API',
    )

    # Backward compatibility
    raw_resp = response.raw_resp['response']
    for doc in raw_resp['docs']:
        doc['type'] = doc.get('subject_type', 'subject')
        doc['count'] = doc.get('work_count', 0)

    return raw_resp
