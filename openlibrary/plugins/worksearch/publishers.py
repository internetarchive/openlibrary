"""Publisher pages
"""

import logging

import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from . import search, subjects

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
        result = search.get_solr().select(
            {"publisher": i.q, "type": "work"},
            facets=["publisher_facet"],
            facet_mincount=1,
            facet_limit=25,
            facet_contains=i.q,
            facet_contains_ignoreCase='true',
            rows=0,
        )
        result = self.process_result(result)
        return render_template('search/publishers', i.q, result)

    def process_result(self, result):
        publisher_facets = result['facets']['publisher_facet']
        return [
            web.storage(
                name=p.value,
                key="/publishers/" + p.value.replace(" ", "_"),
                count=p.count,
            )
            for p in publisher_facets
        ]


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
    subjects.SUBJECTS.append(
        subjects.SubjectMeta(
            name="publisher",
            key="publishers",
            prefix="/publishers/",
            facet="publisher_facet",
            facet_key="publisher_facet",
            Engine=PublisherEngine,
        )
    )
