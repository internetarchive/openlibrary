"""Publisher pages"""

import logging
from dataclasses import dataclass
from typing import override

import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from . import search, subjects

logger = logging.getLogger("openlibrary.worksearch")


class publishers(subjects.subjects):
    path = "(/publishers/[^/]+)"

    def GET(self, key):
        key = key.replace("_", " ")
        page = subjects.get_subject(
            key,
            details=True,
            request_label="SUBJECT_ENGINE_PAGE",
        )

        if not page or page.work_count == 0:
            web.ctx.status = "404 Not Found"
            return render_template("publishers/notfound.tmpl", key)

        return render_template("publishers/view", page)


class index(delegate.page):
    path = "/publishers"

    def GET(self):
        return render_template("publishers/index")


class publisher_search(delegate.page):
    path = "/search/publishers"

    def GET(self):
        # Local imports: openlibrary.fastapi.search imports this plugin, and this handler is temporary.
        from openlibrary.core.jinja import render_jinja_template
        from openlibrary.fastapi.search import publisher_results, publisher_search_query

        i = web.input(q="")
        result = search.get_solr().select(**publisher_search_query(i.q))
        body = render_jinja_template(
            "search/publishers.html.jinja",
            q=i.q,
            publishers=publisher_results((result.get("facets") or {}).get("publisher_facet", [])),
        )
        # web.py's layout reads the title off the result; without one it uses the path, as FastAPI does.
        return web.template.TemplateResult(__body__=body)


@dataclass
class PublisherEngine(subjects.SubjectEngine):
    name: str = "publisher"
    key: str = "publishers"
    prefix: str = "/publishers/"
    facet: str = "publisher_facet"
    facet_key: str = "publisher_facet"

    @override
    def normalize_key(self, key):
        return key

    def get_ebook_count(self, name, value, publish_year):
        # Query solr for this publish_year and publish_year combination and read the has_fulltext=true facet
        solr = search.get_solr()
        q = {"publisher_facet": value}

        if isinstance(publish_year, list):
            q["publish_year"] = tuple(publish_year)  # range
        elif publish_year:
            q["publish_year"] = publish_year

        result = solr.select(q, facets=["has_fulltext"], rows=0)
        counts = {v.value: v.count for v in result["facets"]["has_fulltext"]}
        return counts.get("true")


def setup():
    subjects.SUBJECTS.append(PublisherEngine())
