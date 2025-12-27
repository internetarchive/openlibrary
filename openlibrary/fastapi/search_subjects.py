from fastapi import APIRouter, Query

from openlibrary.plugins.worksearch.code import async_run_solr_query
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme

router = APIRouter()


@router.get("/search/subjects.json")
async def search_subjects_json(
    q: str = Query("", description="The search query"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=0, le=1000),
):
    response = await async_run_solr_query(
        SubjectSearchScheme(),
        {'q': q},
        offset=offset,
        rows=limit,
        sort='work_count desc',
        request_label='SUBJECT_SEARCH_API',
    )

    # Backward compatibility
    raw_resp = response.raw_resp['response']
    for doc in raw_resp['docs']:
        doc['type'] = doc.get('subject_type', 'subject')
        doc['count'] = doc.get('work_count', 0)

    return raw_resp
