import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import cast
from urllib.parse import parse_qs

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core.fulltext import fulltext_search
from openlibrary.core.lending import compose_ia_url, get_available
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.lists import get_lists, get_user_lists
from openlibrary.plugins.upstream.yearly_reading_goals import get_reading_goals
from openlibrary.plugins.worksearch.code import do_search, work_search
from openlibrary.plugins.worksearch.subjects import (
    date_range_to_publish_year_filter,
    get_subject,
)
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


class ReadingGoalProgressPartial(PartialDataHandler):
    """Handler for reading goal progress."""

    def __init__(self):
        self.i = web.input(year=None)

    def generate(self) -> dict:
        year = self.i.year or datetime.now().year
        goal = get_reading_goals(year=year)
        component = render_template('reading_goals/reading_goal_progress', [goal])

        return {"partials": str(component)}


class MyBooksDropperListsPartial(PartialDataHandler):
    """Handler for the MyBooks dropper list component."""

    def generate(self) -> dict:
        user_lists = get_user_lists(None)

        dropper = render_template("lists/dropper_lists", user_lists)
        list_data = {
            list_data['key']: {
                'members': list_data['list_items'],
                'listName': list_data['name'],
            }
            for list_data in user_lists
        }

        return {
            'dropper': str(dropper),
            'listData': list_data,
        }


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

        for index, work in enumerate(search_results):
            lazy = index > self.MAX_VISIBLE_CARDS
            editions = work.get('editions', {})
            if not editions:
                book = work
            elif isinstance(editions, list):
                book = editions[0]
            else:
                book = editions.get('docs', [None])[0]
            book['authors'] = work.get('authors', [])

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
        query_params = {"q": query}

        if params.get("hasFulltextOnly"):
            query_params['has_fulltext'] = 'true'

        results = work_search(
            query_params,
            sort=sort,
            fields=','.join(fields),
            limit=limit,
            facet=False,
            offset=page,
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
            safe_mode=True,
        )
        results = get_available(url=url)
        return results if "error" not in results else []

    def _do_trends_query(self, params: dict) -> list:
        page = int(params.get("page", 1))
        limit = int(params.get("limit", 18))
        return get_trending_books(
            minimum=3, limit=limit, page=page, sort_by_count=False
        )

    def _do_subjects_query(self, params: dict) -> list:
        pseudoKey = params.get("q", "")
        offset = int(params.get("page", 1))
        limit = int(params.get("limit", 18))
        published_in = params.get("published_in", "")
        publish_year = date_range_to_publish_year_filter(published_in)

        subject = get_subject(
            pseudoKey, offset=offset, limit=limit, publish_year=publish_year
        )
        return subject.get("works", [])


class AffiliateLinksPartial(PartialDataHandler):
    """Handler for affiliate links"""

    def __init__(self, data: dict | None = None):
        if data is None:
            self.i = web.input(data=None)
            self.data = json.loads(self.i.data) if self.i.data else {}
        else:
            self.data = data

    def generate(self) -> dict:
        args = self.data.get("args", [])

        if len(args) < 2:
            raise PartialResolutionError("Unexpected amount of arguments")

        macro = web.template.Template.globals['macros'].AffiliateLinks(args[0], args[1])
        return {"partials": str(macro)}


class SearchFacetsPartial(PartialDataHandler):
    """Handler for search facets sidebar and "selected facets" affordances."""

    def __init__(self, data: dict | None = None):
        if data is None:
            self.i = web.input(data=None)
            self.data = json.loads(self.i.data) if self.i.data else {}
        else:
            self.data = data

    def generate(self) -> dict:
        path = self.data.get('path')
        query = self.data.get('query', '')
        parsed_qs = parse_qs(query.replace('?', ''))
        param = self.data.get('param', {})

        sort = None
        search_response = do_search(
            param,
            sort,
            rows=0,
            spellcheck_count=3,
            facet=True,
            request_label='BOOK_SEARCH_FACETS',
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

        return {
            "sidebar": str(sidebar),
            "title": active_facets.title,
            "activeFacets": str(active_facets).strip(),
        }


class FullTextSuggestionsPartial(PartialDataHandler):
    """Handler for rendering full-text search suggestions."""

    def __init__(self, data: str | None = None):
        if data is None:
            raw_input = web.input(data=None)
            self.query = raw_input.get("data", "")
        else:
            self.query = data or ""

    def generate(self) -> dict:
        query = self.query
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

    def __init__(self, data: dict | None = None):
        if data is None:
            self.i = web.input(workId="", editionId="")
            self.data = {
                "workId": self.i.workId,
                "editionId": self.i.editionId,
            }
        else:
            self.data = data

    def generate(self) -> dict:
        results: dict = {"partials": []}
        work_key = self.data.get("workId", "")
        edition_key = self.data.get("editionId", "")
        keys = [k for k in (work_key, edition_key) if k]

        # Do checks and render
        lists = get_lists(keys)
        results["hasLists"] = bool(lists)

        if not lists:
            results["partials"].append(_('This work does not appear on any lists.'))
        else:
            query = "seed_count:[2 TO *] seed:(%s)" % " OR ".join(
                f'"{k}"' for k in keys
            )
            all_url = "/search/lists?q=" + web.urlquote(query) + "&sort=last_modified"
            lists_template = render_template("lists/carousel", lists, all_url)
            results["partials"].append(str(lists_template))

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
    component_mapping = {  # noqa: RUF012
        "CarouselLoadMore": CarouselCardPartial,
        "AffiliateLinks": AffiliateLinksPartial,
        "SearchFacets": SearchFacetsPartial,
        "FulltextSearchSuggestion": FullTextSuggestionsPartial,
        "BPListsSection": BookPageListsPartial,
        "LazyCarousel": LazyCarouselPartial,
        "MyBooksDropperLists": MyBooksDropperListsPartial,
        "ReadingGoalProgress": ReadingGoalProgressPartial,
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
    path = r'/partials/([A-Za-z]+)'
    encoding = 'json'

    def GET(self, component):
        return delegate.RawText(
            json.dumps(PartialRequestResolver.resolve(component)),
            content_type='application/json',
        )


def setup():
    pass
