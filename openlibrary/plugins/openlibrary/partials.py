import json
from abc import ABC, abstractmethod
from typing import cast
from urllib.parse import parse_qs

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core.fulltext import fulltext_search
from openlibrary.core.lending import compose_ia_url, get_available
from openlibrary.i18n import gettext as _
from openlibrary.plugins.worksearch.code import do_search, work_search
from openlibrary.plugins.worksearch.subjects import get_subject
from openlibrary.views.loanstats import get_trending_books


class PartialResolutionError(Exception):
    pass


class PartialDataHandler(ABC):
    """Base class for partial data handlers.

    Has a single method, `generate`, that is expected to return a
    JSON-serializable dict that contains data necessary to update
    a page.
    """

    @abstractmethod
    def generate(self) -> dict:
        pass


class CarouselCardPartial(PartialDataHandler):
    """Handler for carousel "load_more" requests"""

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


class AffiliateLinksPartial(PartialDataHandler):
    """Handler for affiliate links"""

    def __init__(self):
        self.i = web.input(data=None)

    def generate(self) -> dict:
        data = json.loads(self.i.data)
        args = data.get("args", [])

        if len(args) < 2:
            raise PartialResolutionError("Unexpected amount of arguments")

        macro = web.template.Template.globals['macros'].AffiliateLinks(args[0], args[1])
        return {"partials": str(macro)}


class SearchFacetsPartial(PartialDataHandler):
    """Handler for search facets sidebar and "selected facets" affordances."""

    def __init__(self):
        self.i = web.input(data=None)

    def generate(self) -> dict:
        data = json.loads(self.i.data)
        path = data.get('path')
        query = data.get('query', '')
        parsed_qs = parse_qs(query.replace('?', ''))
        param = data.get('param', {})

        sort = None
        search_response = do_search(param, sort, rows=0, spellcheck_count=3, facet=True)

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

        return {
            "sidebar": str(sidebar),
            "title": active_facets.title,
            "activeFacets": str(active_facets).strip(),
        }


class FullTextSuggestionsPartial(PartialDataHandler):
    """Handler for rendering full-text search suggestions."""

    def __init__(self):
        self.i = web.input(data=None)

    def generate(self) -> dict:
        query = self.i.get("data", "")
        data = fulltext_search(query)
        # Add caching headers only if there were no errors in the search results
        if 'error' not in data:
            # Cache for 5 minutes (300 seconds)
            web.header('Cache-Control', 'public, max-age=300')
        hits = data.get('hits', [])
        if not hits['hits']:
            macro = '<div></div>'
        else:
            macro = web.template.Template.globals['macros'].FulltextSearchSuggestion(
                query, data
            )
        return {"partials": str(macro)}


class BookPageListsPartial(PartialDataHandler):
    """Handler for rendering the book page "Lists" section"""

    def __init__(self):
        self.i = web.input(workId="", editionId="")

    def generate(self) -> dict:
        results: dict = {"partials": []}
        work_id = self.i.workId
        edition_id = self.i.editionId

        work = (work_id and web.ctx.site.get(work_id)) or None
        edition = (edition_id and web.ctx.site.get(edition_id)) or None

        # Do checks and render
        has_lists = (work and work.get_lists(limit=1)) or (
            edition and edition.get_lists(limit=1)
        )
        results["hasLists"] = bool(has_lists)

        if not has_lists:
            results["partials"].append(_('This work does not appear on any lists.'))
        else:
            if work and work.key:
                work_list_template = render_template(
                    "lists/widget", work, include_header=False, include_widget=False
                )
                results["partials"].append(str(work_list_template))
            if edition and edition.get("type", "") != "/type/edition":
                edition_list_template = render_template(
                    "lists/widget",
                    edition,
                    include_header=False,
                    include_widget=False,
                )
                results["partials"].append(str(edition_list_template))

        return results


class LazyCarouselPartial(PartialDataHandler):
    """Handler for lazily-loaded query carousels."""

    def __init__(self):
        self.i = web.input(
            query="",
            title=None,
            sort="new",
            key="",
            limit=20,
            search=False,
            has_fulltext_only=True,
            url=None,
            layout="carousel",
        )
        self.i.search = self.i.search != "false"
        self.i.has_fulltext_only = self.i.has_fulltext_only != "false"

    def generate(self) -> dict:
        macro = web.template.Template.globals['macros'].CacheableMacro(
            "RawQueryCarousel",
            self.i.query,
            lazy=False,
            title=self.i.title,
            sort=self.i.sort,
            key=self.i.key,
            limit=int(self.i.limit),
            search=self.i.search,
            has_fulltext_only=self.i.has_fulltext_only,
            url=self.i.url,
            layout=self.i.layout,
        )
        return {"partials": str(macro)}


class PartialRequestResolver:
    # Maps `_component` values to PartialDataHandler subclasses
    component_mapping = {
        "CarouselLoadMore": CarouselCardPartial,
        "AffiliateLinks": AffiliateLinksPartial,
        "SearchFacets": SearchFacetsPartial,
        "FulltextSearchSuggestion": FullTextSuggestionsPartial,
        "BPListsSection": BookPageListsPartial,
        "LazyCarousel": LazyCarouselPartial,
    }

    @staticmethod
    def resolve(component: str) -> dict:
        """Gets an instantiated PartialDataHandler and returns its generated dict"""
        handler = PartialRequestResolver.get_handler(component)
        return handler.generate()

    @classmethod
    def get_handler(cls, component: str) -> PartialDataHandler:
        """Instantiates and returns the requested handler"""
        if klass := cls.component_mapping.get(component):
            concrete_class = cast(type[PartialDataHandler], klass)
            return concrete_class()
        raise PartialResolutionError(f'No handler found for key "{component}"')


class Partials(delegate.page):
    path = '/partials'
    encoding = 'json'

    def GET(self):
        i = web.input(_component=None)
        component = i.pop("_component")
        return delegate.RawText(
            json.dumps(PartialRequestResolver.resolve(component)),
            content_type='application/json',
        )


def setup():
    pass
