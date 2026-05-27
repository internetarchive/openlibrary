import logging
from dataclasses import dataclass
from typing import Literal, override

import web
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.plugins.upstream.utils import get_language_name
from openlibrary.utils.async_utils import async_bridge

from . import search, subjects

logger = logging.getLogger("openlibrary.worksearch")


async def get_top_languages(
    limit: int,
    user_lang: str,
    sort: Literal["count", "name", "ebook_edition_count"] = "count",
) -> list[web.storage]:

    available_edition_counts = dict(
        await get_all_language_counts("edition", ebook_access="borrowable")
    )

    results = [
        web.storage(
            name=get_language_name(lang_key, user_lang),
            key=lang_key,
            marc_code=lang_key.split("/")[-1],
            count=count,
            ebook_edition_count=available_edition_counts.get(lang_key, 0),
        )
        for (lang_key, count) in await get_all_language_counts("work")
    ]

    if sort == "name":
        from icu import Collator, Locale

        collator = Collator.createInstance(Locale(user_lang or "en"))
        collator.setStrength(Collator.PRIMARY)
        results.sort(key=lambda x: collator.getSortKey(x.name or ""))
    else:
        results.sort(
            key=lambda x: x[sort],
            reverse=sort in ("count", "ebook_edition_count"),
        )

    return results[:limit]


async def get_all_language_counts(
    solr_type: Literal["work", "edition"],
    ebook_access: str | None = None,
) -> list[tuple[str, int]]:

    from . import search

    ebook_access_query = ""

    if ebook_access:

        ebook_access_query = f" AND ebook_access:[{ebook_access} TO *]"

    result = await search.get_solr().select_async(
        f"type:{solr_type} {ebook_access_query}",
        rows=0,
        facets=["language"],
        facet_limit=1_000,
        _timeout=30,  
        time_allowed=False,  
    )

    return [
        (f"/languages/{row.value}", row.count)
        for row in result["facets"]["language"]
    ]


class index(delegate.page):

    path = "/languages"

    def GET(self):

        sort = web.input(sort="count").sort

        if sort not in ("count", "name", "ebook_edition_count"):

            raise web.badrequest("Invalid sort parameter")

        return render_template(
            "languages/index",
            async_bridge.run(
                get_top_languages(500, user_lang=web.ctx.lang, sort=sort)
            ),
        )

    def is_enabled(self):

        return True


class language_search(delegate.page):

    path = "/search/languages"

    def GET(self):

        i = web.input(q="")

        solr = search.get_solr()

        q = {"language": i.q}

        result = solr.select(q, facets=["language"], fields=["language"], rows=0)

        result = self.process_result(result)

        return render_template("search/languages", i.q, result)

    def process_result(self, result):

        solr = search.get_solr()

        def process(p):

            return web.storage(
                name=p.value,
                key="/languages/" + p.value.replace(" ", "_"),
                count=solr.select({"language": p.value}, rows=0)["num_found"],
            )

        language_facets = result["facets"]["language"][:25]

        return [process(p) for p in language_facets]


@dataclass
class LanguageEngine(subjects.SubjectEngine):

    name: str = "language"

    key: str = "languages"

    prefix: str = "/languages/"

    facet: str = "language"

    facet_key: str = "language"


@override
def normalize_key(self, key):

    return key


def get_ebook_count(self, name, value, publish_year):


    solr = search.get_solr()

    q = {"language": value}

    if isinstance(publish_year, list):

        q["publish_year"] = tuple(publish_year)  

    elif publish_year:

        q["publish_year"] = publish_year

    result = solr.select(q, facets=["has_fulltext"], rows=0)

    counts = {v.value: v.count for v in result["facets"]["has_fulltext"]}

    return counts.get("true")


def setup():

    subjects.SUBJECTS.append(LanguageEngine())