"""Language pages
"""

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate, stats
from infogami.utils.view import render_template, safeint
import web
import json
import logging

from openlibrary.plugins.upstream.utils import get_language_name

from . import subjects
from . import search

import urllib


logger = logging.getLogger("openlibrary.worksearch")


class languages(subjects.subjects):
    path = '(/languages/[^_][^/]*)'

    def is_enabled(self):
        return "languages" in web.ctx.features


class languages_json(subjects.subjects_json):
    path = '(/languages/[^_][^/]*)'
    encoding = "json"

    def is_enabled(self):
        return "languages" in web.ctx.features

    def normalize_key(self, key):
        return key

    def process_key(self, key):
        return key.replace("_", " ")


def get_top_languages(limit):
    from . import search

    result = search.get_solr().select(
        '*:*', rows=0, facets=['language'], facet_limit=limit
    )
    return [
        web.storage(
            name=get_language_name(f'/languages/{row.value}'),
            key=f'/languages/{row.value}',
            count=row.count,
        )
        for row in result['facets']['language']
    ]


class index(delegate.page):
    path = "/languages"

    def GET(self):
        return render_template("languages/index", get_top_languages(500))

    def is_enabled(self):
        return True


class index_json(delegate.page):
    path = "/languages"
    encoding = "json"

    @jsonapi
    def GET(self):
        return json.dumps(get_top_languages(15))


class language_search(delegate.page):
    path = '/search/languages'

    def GET(self):
        i = web.input(q="")
        solr = search.get_solr()
        q = {"language": i.q}

        result = solr.select(q, facets=["language"], fields=["language"], rows=0)
        result = self.process_result(result)
        return render_template('search/languages', i.q, result)

    def process_result(self, result):
        solr = search.get_solr()

        def process(p):
            return web.storage(
                name=p.value,
                key="/languages/" + p.value.replace(" ", "_"),
                count=solr.select({"language": p.value}, rows=0)['num_found'],
            )

        language_facets = result['facets']['language'][:25]
        return [process(p) for p in language_facets]


class LanguageEngine(subjects.SubjectEngine):
    def normalize_key(self, key):
        return key

    def get_ebook_count(self, name, value, publish_year):
        # Query solr for this publish_year and publish_year combination and read the has_fulltext=true facet
        solr = search.get_solr()
        q = {"language": value}

        if isinstance(publish_year, list):
            q['publish_year'] = tuple(publish_year)  # range
        elif publish_year:
            q['publish_year'] = publish_year

        result = solr.select(q, facets=["has_fulltext"], rows=0)
        counts = {v.value: v.count for v in result["facets"]["has_fulltext"]}
        return counts.get('true')


def setup():
    d = web.storage(
        name="language",
        key="languages",
        prefix="/languages/",
        facet="language",
        facet_key="language",
        engine=LanguageEngine,
    )
    subjects.SUBJECTS.append(d)
