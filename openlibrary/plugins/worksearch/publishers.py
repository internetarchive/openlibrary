"""Publisher pages
"""
from infogami.utils import delegate, stats
from infogami.utils.view import render_template, safeint
import web
import logging

from . import subjects
from . import search

import urllib


logger = logging.getLogger("openlibrary.worksearch")


class publishers(subjects.subjects):
    path = '(/publishers/[^/]+)'

    def GET(self, key):
        key = key.replace("_", " ")
        page = subjects.get_subject(key, details=True)

        if not page or page.work_count == 0:
            web.ctx.status = "404 Not Found"
            return render_template('publishers/notfound.tmpl', key)

        return render_template("publishers/view", page)

    def is_enabled(self):
        return "publishers" in web.ctx.features


class publishers_json(subjects.subjects_json):
    path = '(/publishers/[^/]+)'
    encoding = "json"

    def is_enabled(self):
        return "publishers" in web.ctx.features

    def normalize_key(self, key):
        return key

    def process_key(self, key):
        return key.replace("_", " ")


class index(delegate.page):
    path = "/publishers"

    def GET(self):
        return render_template("publishers/index")

    def is_enabled(self):
        return "publishers" in web.ctx.features


class publisher_search(delegate.page):
    path = '/search/publishers'

    def GET(self):
        i = web.input(q="")
        solr = search.get_solr()
        q = {"publisher": i.q}

        result = solr.select(
            q,
            facets=["publisher_facet"],
            fields=["publisher", "publisher_facet"],
            rows=0,
        )
        result = self.process_result(result)
        return render_template('search/publishers', i.q, result)

    def process_result(self, result):
        solr = search.get_solr()

        def process(p):
            return web.storage(
                name=p.value,
                key="/publishers/" + p.value.replace(" ", "_"),
                count=solr.select({"publisher_facet": p.value}, rows=0)['num_found'],
            )

        publisher_facets = result['facets']['publisher_facet'][:25]
        return [process(p) for p in publisher_facets]


class PublisherEngine(subjects.SubjectEngine):
    def normalize_key(self, key):
        return key

    def get_ebook_count(self, name, value, publish_year):
        # Query solr for this publish_year and publish_year combination and read the has_fulltext=true facet
        solr = search.get_solr()
        q = {"publisher_facet": value}

        if isinstance(publish_year, list):
            q['publish_year'] = tuple(publish_year)  # range
        elif publish_year:
            q['publish_year'] = publish_year

        result = solr.select(q, facets=["has_fulltext"], rows=0)
        counts = {v.value: v.count for v in result["facets"]["has_fulltext"]}
        return counts.get('true')


def setup():
    d = web.storage(
        name="publisher",
        key="publishers",
        prefix="/publishers/",
        facet="publisher_facet",
        facet_key="publisher_facet",
        engine=PublisherEngine,
    )
    subjects.SUBJECTS.append(d)
