import json
from urllib.parse import parse_qs

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import cache
from openlibrary.core.fulltext import fulltext_search
from openlibrary.core.lending import compose_ia_url, get_available
from openlibrary.i18n import gettext as _
from openlibrary.plugins.worksearch.code import do_search, work_search
from openlibrary.plugins.worksearch.subjects import get_subject
from openlibrary.utils import dateutil
from openlibrary.views.loanstats import get_trending_books


def _get_relatedcarousels_component(workid):
    if 'env' not in web.ctx:
        delegate.fakeload()
    work = web.ctx.site.get('/works/%s' % workid) or {}
    component = render_template('books/RelatedWorksCarousel', work)
    return {0: str(component)}


def get_cached_relatedcarousels_component(*args, **kwargs):
    memoized_get_component_metadata = cache.memcache_memoize(
        _get_relatedcarousels_component,
        "book.bookspage.component.relatedcarousels",
        timeout=dateutil.HALF_DAY_SECS,
    )
    return (
        memoized_get_component_metadata(*args, **kwargs)
        or memoized_get_component_metadata.update(*args, **kwargs)[0]
    )


class CarouselCardPartial:
    MAX_VISIBLE_CARDS = 5

    def __init__(self):
        self.i = web.input(params=None)

    def generate(self) -> dict:
        # Determine query type
        params = self.i or {}
        query_type = params.get("queryType", "")

        # Do search
        search_results = self._make_book_query(query_type, params)

        # Render cards
        cards = []
        layout = params.get("layout")
        key = params.get("key") or ""

        for index, book in enumerate(search_results):
            lazy = index > self.MAX_VISIBLE_CARDS
            cards.append(
                render_template(
                    "books/custom_carousel_card",
                    web.storage(book),
                    lazy,
                    layout,
                    key=key,
                )
            )

        return {"partials": [str(template) for template in cards]}

    def _make_book_query(self, query_type: str, params: dict) -> list:
        if query_type == "SEARCH":
            return self._do_search_query(params)
        if query_type == "BROWSE":
            return self._do_browse_query(params)
        if query_type == "TRENDING":
            return self._do_trends_query(params)
        if query_type == "SUBJECTS":
            return self._do_subjects_query(params)

        raise ValueError("Unknown query type")

    def _do_search_query(self, params: dict) -> list:
        fields = [
            'key',
            'title',
            'subtitle',
            'author_name',
            'cover_i',
            'ia',
            'availability',
            'id_project_gutenberg',
            'id_project_runeberg',
            'id_librivox',
            'id_standard_ebooks',
            'id_openstax',
            'editions',
        ]
        query = params.get("q", "")
        sort = params.get("sorts", "new")  # XXX : check "new" assumption
        limit = int(params.get("limit", 20))
        page = int(params.get("page", 1))
        query_params = {
            "q": query,
            "fields": ",".join(fields),
        }
        if fulltext := params.get("hasFulltextOnly"):
            query_params['has_fulltext'] = 'true'

        results = work_search(
            query_params, sort=sort, limit=limit, facet=False, offset=page
        )
        return results.get("docs", [])

    def _do_browse_query(self, params: dict) -> list:
        query = params.get("q", "")
        subject = params.get("subject", "")
        sorts = params.get("sorts", "").split(',')
        limit = int(params.get("limit", 18))
        page = int(params.get("page", 1))
        url = compose_ia_url(
            query=query,
            limit=limit,
            page=page,
            subject=subject,
            sorts=sorts,
            advanced=True,
        )
        results = get_available(url=url)
        return results if "error" not in results else []

    def _do_trends_query(self, params: dict) -> list:
        page = int(params.get("page", 1))
        limit = int(params.get("limit", 18))
        return get_trending_books(
            minimum=3, limit=limit, page=page, books_only=True, sort_by_count=False
        )

    def _do_subjects_query(self, params: dict) -> list:
        pseudoKey = params.get("q", "")
        offset = int(params.get("page", 1))
        limit = int(params.get("limit", 18))

        subject = get_subject(pseudoKey, offset=offset, limit=limit)
        return subject.get("works", [])


class Partials(delegate.page):
    path = '/partials'
    encoding = 'json'

    def GET(self):
        # `data` is meant to be a dict with two keys: `args` and `kwargs`.
        # `data['args']` is meant to be a list of a template's positional arguments, in order.
        # `data['kwargs']` is meant to be a dict containing a template's keyword arguments.
        i = web.input(workid=None, _component=None, data=None)
        component = i.pop("_component")
        partial = {}
        if component == "RelatedWorkCarousel":
            partial = _get_relatedcarousels_component(i.workid)
        elif component == "CarouselLoadMore":
            partial = CarouselCardPartial().generate()
        elif component == "AffiliateLinks":
            data = json.loads(i.data)
            args = data.get('args', [])
            # XXX : Throw error if args length is less than 2
            macro = web.template.Template.globals['macros'].AffiliateLinks(
                args[0], args[1]
            )
            partial = {"partials": str(macro)}

        elif component == 'SearchFacets':
            data = json.loads(i.data)
            path = data.get('path')
            query = data.get('query', '')
            parsed_qs = parse_qs(query.replace('?', ''))
            param = data.get('param', {})

            sort = None
            search_response = do_search(
                param, sort, rows=0, spellcheck_count=3, facet=True
            )

            sidebar = render_template(
                'search/work_search_facets',
                param,
                facet_counts=search_response.facet_counts,
                async_load=False,
                path=path,
                query=parsed_qs,
            )

            active_facets = render_template(
                'search/work_search_selected_facets',
                param,
                search_response,
                param.get('q', ''),
                path=path,
                query=parsed_qs,
            )

            partial = {
                "sidebar": str(sidebar),
                "title": active_facets.title,
                "activeFacets": str(active_facets).strip(),
            }

        elif component == "FulltextSearchSuggestion":
            query = i.get('data', '')
            data = fulltext_search(query)
            # Add caching headers only if there were no errors in the search results
            if 'error' not in data:
                # Cache for 5 minutes (300 seconds)
                web.header('Cache-Control', 'public, max-age=300')
            hits = data.get('hits', [])
            if not hits['hits']:
                macro = '<div></div>'
            else:
                macro = web.template.Template.globals[
                    'macros'
                ].FulltextSearchSuggestion(query, data)
            partial = {"partials": str(macro)}
        elif component == "BPListsSection":
            partial = {"partials": []}

            # Get work and edition
            work_id = i.get("workId", "")
            edition_id = i.get("editionId", "")

            work = (work_id and web.ctx.site.get(work_id)) or {}
            edition = (edition_id and web.ctx.site.get(edition_id)) or {}

            # Do checks and render
            has_lists = (work and work.get_lists(limit=1)) or (
                edition and edition.get_lists(limit=1)
            )
            partial["hasLists"] = bool(has_lists)

            if not has_lists:
                partial["partials"].append(_('This work does not appear on any lists.'))
            else:
                if work and work.key:
                    work_list_template = render_template(
                        "lists/widget", work, include_header=False, include_widget=False
                    )
                    partial["partials"].append(str(work_list_template))
                if edition and edition.get("type", "") != "/type/edition":
                    edition_list_template = render_template(
                        "lists/widget",
                        edition,
                        include_header=False,
                        include_widget=False,
                    )
                    partial["partials"].append(str(edition_list_template))

        elif component == "LazyCarousel":
            i = web.input(query="", title=None, sort="new", key="", limit=20, search=False, has_fulltext_only=True, url=None, layout="carousel")
            i.search = i.search != "false"
            i.has_fulltext_only = i.has_fulltext_only != "false"
            macro = web.template.Template.globals[
                    'macros'
                ].CacheableMacro("RawQueryCarousel", i.query, lazy=False, title=i.title, sort=i.sort, key=i.key, limit=i.limit, search=i.search, has_fulltext_only=i.has_fulltext_only, url=i.url, layout=i.layout)
            partial = {"partials": str(macro)}

        return delegate.RawText(json.dumps(partial), content_type='application/json')


def setup():
    pass
