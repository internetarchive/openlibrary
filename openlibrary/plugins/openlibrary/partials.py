import json
from urllib.parse import parse_qs

import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import cache
from openlibrary.core.fulltext import fulltext_search
from openlibrary.plugins.worksearch.code import do_search
from openlibrary.utils import dateutil


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

        return delegate.RawText(json.dumps(partial))

def setup():
    pass
