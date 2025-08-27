from __future__ import annotations

import logging

import web
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from infogami.utils.view import render, render_template

# Use existing Infogami client to talk to Infobase using configured parameters
from openlibrary.fastapi.authors import get_user_from_request
from openlibrary.fastapi.utils import get_jinja_context, templates
from openlibrary.plugins.worksearch.code import (
    SearchResponse,
    async_run_solr_query,
    async_work_search,
    do_search,
    get_doc,
)
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.works import (
    WorkSearchScheme,
)
from openlibrary.solr.query_utils import fully_escape_query

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


@router.get("/search/authors/", response_class=HTMLResponse)
async def author_page(
    request: Request,
    q: str = Query(..., description="The search query."),
):
    async def get_results(q, offset=0, limit=100, fields='*', sort=''):
        return await async_run_solr_query(
            AuthorSearchScheme(),
            {'q': q},
            offset=offset,
            rows=limit,
            fields=fields,
            sort=sort,
        )

    results = await get_results(q=q)

    u = get_user_from_request(request)

    # Needed for page banners where we call the old render function, not a new template
    web.ctx.lang = 'en'
    # This is apparently the right way to set things that'll be accessed from web.input()
    web.ctx.env['QUERY_STRING'] = f'q={q}'

    def dummy_get_results(q, *, offset=0, limit=100, fields='*', sort='', **kwargs):
        return results

    context = get_jinja_context(request, user=u, title=q)
    context["main_content"] = render_template("search/authors", dummy_get_results)
    return templates.TemplateResponse("generic_template.html.jinja", context)


@router.get("/search/", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query(..., description="The search query."),
):

    u = get_user_from_request(request)
    # Needed for page banners where we call the old render function, not a new template
    web.ctx.lang = 'en'
    # This is apparently the right way to set things that'll be accessed from web.input()
    web.ctx.env['QUERY_STRING'] = f'q={q}'

    # Enable patrons to search for query q2 within collection q
    # q2 param gets removed and prepended to q via a redirect
    # _i = web.input(q='', q2='')
    # if _i.q.strip() and _i.q2.strip():
    #     _i.q = _i.q2.strip() + ' ' + _i.q.strip()
    #     _i.pop('q2')
    #     raise web.seeother('/search?' + urllib.parse.urlencode(_i))

    i = web.input(
        author_key=[],
        language=[],
        first_publish_year=[],
        publisher_facet=[],
        subject_facet=[],
        person_facet=[],
        place_facet=[],
        time_facet=[],
        public_scan_b=[],
    )

    # Send to full-text Search Inside if checkbox checked
    # if i.get('search-fulltext'):
    #     raise web.seeother(
    #         '/search/inside?' + urllib.parse.urlencode({'q': i.get('q', '')})
    #     )

    if i.get('wisbn'):
        i.isbn = i.wisbn

    # self.redirect_if_needed(i)

    # if 'isbn' in i:
    #     self.isbn_redirect(i.isbn)

    q_list = []
    if q := i.get('q', '').strip():
        # m = re_olid.match(q)
        # if m:
        #     raise web.seeother(f'/{OLID_URLS[m.group(1)]}/{q}')
        # m = re_isbn_field.match(q)
        # if m:
        #     self.isbn_redirect(m.group(1))
        q_list.append(q)
    for k in ('title', 'author', 'isbn', 'subject', 'place', 'person', 'publisher'):
        if k in i:
            q_list.append(f'{k}:{fully_escape_query(i[k].strip())}')

    web_input = i
    param = {}
    for p in {
        'q',
        'title',
        'author',
        'page',
        'sort',
        'isbn',
        'oclc',
        'contributor',
        'publish_place',
        'lccn',
        'ia',
        'first_sentence',
        'publisher',
        'author_key',
        'debug',
        'subject',
        'place',
        'person',
        'time',
        'editions.sort',
    } | WorkSearchScheme.facet_fields:
        if web_input.get(p):
            param[p] = web_input[p]
    if list(param) == ['has_fulltext']:
        param = {}

    page = int(param.get('page', 1))
    sort = param.get('sort', None)
    rows = 20
    if param:
        search_response = do_search(param, sort, page, rows=rows, spellcheck_count=3)
    else:
        search_response = SearchResponse(
            facet_counts={}, sort='', docs=[], num_found=0, solr_select=''
        )

    context = get_jinja_context(request, user=u, title=q)
    context["main_content"] = render.work_search(
        ' '.join(q_list),
        search_response,
        get_doc,
        param,
        page,
        rows,
    )
    return templates.TemplateResponse("generic_template.html.jinja", context)


@router.get("/search.json", response_class=JSONResponse)
async def search_json(
    q: str = Query(..., description="The search query."),
    page: int | None = Query(
        1, ge=1, description="The page number of results to return."
    ),
    limit: int = Query(
        100, ge=1, le=1000, description="The number of results per page."
    ),
    sort: str | None = Query(None, description="The sort order of results."),
    offset: int | None = Query(None, description="The offset of results to return."),
    fields: str | None = Query(None, description="The fields to return."),
    # facet: bool = Query(False, description="Whether to return facets."),
    spellcheck_count: int | None = Query(
        3, description="The number of spellcheck suggestions."
    ),
):
    """
    Performs a search for documents based on the provided query.
    """
    # Call the underlying search logic
    _fields = WorkSearchScheme.default_fetched_fields
    if fields:
        _fields = fields.split(',')  # type: ignore

    query = {"q": q, "page": page, "limit": limit}
    response = await async_work_search(
        query,
        sort=sort,
        page=page,
        offset=offset,
        limit=limit,
        fields=_fields,
        # We do not support returning facets from /search.json,
        # so disable it. This makes it much faster.
        facet=False,
        spellcheck_count=spellcheck_count,
    )

    # Add extra metadata to the response, similar to the original
    response['q'] = q
    response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"

    # Reorder keys to have 'docs' at the end, as in the original code
    docs = response.pop('docs', [])
    response['docs'] = docs

    return response
