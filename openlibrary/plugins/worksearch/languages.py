"""Language pages"""

import json
import logging
from typing import Literal

import web

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary.core import cache
from openlibrary.plugins.upstream.utils import get_language_name

from . import search, subjects

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


def get_top_languages(
    limit: int,
    sort: Literal["count", "name", "ebook_edition_count"] = "count",
) -> list[web.storage]:
    available_edition_counts = dict(
        get_all_language_counts('edition', ebook_access="borrowable")
    )
    results = [
        web.storage(
            name=get_language_name(lang_key),
            key=lang_key,
            marc_code=lang_key.split('/')[-1],
            count=count,
            ebook_edition_count=available_edition_counts.get(lang_key, 0),
        )
        for (lang_key, count) in get_all_language_counts('work')
    ]
    results.sort(
        key=lambda x: x[sort], reverse=sort in ("count", "ebook_edition_count")
    )
    return results[:limit]


@cache.memoize("memcache", key='get_all_language_counts', expires=60 * 60)
def get_all_language_counts(
    solr_type: Literal['work', 'edition'],
    ebook_access: str | None = None,
) -> list[tuple[str, int]]:
    from . import search  # noqa: PLC0415

    ebook_access_query = ''
    if ebook_access:
        ebook_access_query = f' AND ebook_access:[{ebook_access} TO *]'

    result = search.get_solr().select(
        f'type:{solr_type} {ebook_access_query}',
        rows=0,
        facets=['language'],
        # There should be <500
        # See https://openlibrary.org/query.json?type=/type/language&limit=1000
        facet_limit=1_000,
        _timeout=30,  # This query can be rather slow
    )
    return [
        (f'/languages/{row.value}', row.count) for row in result['facets']['language']
    ]


class index(delegate.page):
    path = "/languages"

    def GET(self):
        sort = web.input(sort="count").sort
        if sort not in ("count", "name", "ebook_edition_count"):
            raise web.badrequest("Invalid sort parameter")

        return render_template("languages/index", get_top_languages(500, sort=sort))

    def is_enabled(self):
        return True


class index_json(delegate.page):
    path = "/languages"
    encoding = "json"

    @jsonapi
    def GET(self):
        i = web.input(limit=15, sort="count")
        limit = safeint(i.limit, 15)
        if i.sort not in ("count", "name", "ebook_edition_count"):
            raise web.badrequest("Invalid sort parameter")
        return json.dumps(get_top_languages(limit, sort=i.sort))


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
    subjects.SUBJECTS.append(
        subjects.SubjectMeta(
            name="language",
            key="languages",
            prefix="/languages/",
            facet="language",
            facet_key="language",
            Engine=LanguageEngine,
        )
    )
