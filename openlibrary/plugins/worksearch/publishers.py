"""Publisher pages"""

import logging
import re
from dataclasses import dataclass
from typing import override

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import cache
from openlibrary.utils.dateutil import DAY_SECS
from openlibrary.utils.solr import Solr

from . import search, subjects

logger = logging.getLogger("openlibrary.worksearch")

# A one-off for one low-traffic field, not the pattern for new autocompletes: publisher names live only as strings on works,
# so each lookup counts facets over every matching work. Fields with their own Solr docs (authors, subjects) are far cheaper.

# Shorter than this, a query matches too much of the catalog to count. Three still reaches names like "Tor" and "DAW".
SUGGEST_MIN_CHARS = 3
# Names read from Solr per query, most used first, before they are ranked and cut to the caller's limit.
SUGGEST_POOL = 50
# Solr stops counting after this and returns what it has, so a common word can't hold a search thread for seconds.
SUGGEST_TIME_ALLOWED_MS = 500


class PartialSuggestions(Exception):
    """Solr ran out of time: the rows are still worth showing, but not worth caching for a day."""

    def __init__(self, rows: list[dict]):
        super().__init__("publisher suggestions cut short by timeAllowed")
        self.rows = rows


def normalize_suggest_query(q: str) -> str:
    """The query as the cache keys it: one case, single spaces. Matching ignores case, so the answers are the same."""
    return " ".join(q.split()).casefold()


def suggest_solr_query(q: str) -> str:
    """Works whose publisher has every word of ``q``. The last word may be half-typed, so it also matches as a prefix;
    it stays as a whole word too, since the field stems ("publishing" is indexed as "publish") and a prefix is not stemmed."""
    words = [Solr.escape(w) for w in re.findall(r"\w+", q)]
    if not words:
        return ""
    *whole, last = words
    return "publisher:(%s)" % " ".join([*whole, f"({last} OR {last}*)"])


def rank_suggestions(q: str, names: list[tuple[str, int]], limit: int) -> list[dict]:
    """``names`` (each with its count) in the order to offer them: the name typed, names that start with it, names with
    a word that starts with it, then the rest; most used first within each."""
    q = normalize_suggest_query(q)

    def tier(name: str) -> int:
        folded = name.casefold()
        if folded == q:
            return 0
        if folded.startswith(q):
            return 1
        return 2 if re.search(rf"\b{re.escape(q)}", folded) else 3

    ranked = sorted(names, key=lambda pair: (tier(pair[0]), -pair[1]))
    return [{"value": name, "count": count} for name, count in ranked[:limit]]


def _suggest_publishers(q: str, limit: int) -> list[dict]:
    if not (solr_q := suggest_solr_query(q)):
        return []
    result = search.get_solr().select(
        solr_q,
        fq="type:work",
        facets=["publisher_facet"],
        facet_mincount=1,
        facet_limit=SUGGEST_POOL,
        facet_contains=q,
        facet_contains_ignoreCase="true",
        rows=0,
        timeAllowed=SUGGEST_TIME_ALLOWED_MS,
        _pass_time_allowed=False,
    )
    names = [(facet.value, facet.count) for facet in result.get("facets", {}).get("publisher_facet", [])]
    rows = rank_suggestions(q, names, limit)
    if result.partial:
        raise PartialSuggestions(rows)
    return rows


# A day: publisher counts move slowly, and repeated prefixes are shared by everyone typing them. Stale-while-revalidate.
_cached_suggest_publishers = cache.memcache_memoize(_suggest_publishers, "publishers.suggest", timeout=DAY_SECS)


def suggest_publishers(q: str, limit: int = 8) -> list[dict]:
    """Publisher names for a half-typed ``q``, each as ``{value, count}``: the count is the works that carry the name."""
    q = normalize_suggest_query(q)
    if len(q) < SUGGEST_MIN_CHARS:
        return []
    try:
        return _cached_suggest_publishers(q, limit)
    except PartialSuggestions as e:
        return e.rows


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
        i = web.input(q="")
        result = search.get_solr().select(
            {"publisher": i.q, "type": "work"},
            facets=["publisher_facet"],
            facet_mincount=1,
            facet_limit=25,
            facet_contains=i.q,
            facet_contains_ignoreCase="true",
            rows=0,
        )
        result = self.process_result(result)
        return render_template("search/publishers", i.q, result)

    def process_result(self, result):
        publisher_facets = result["facets"]["publisher_facet"]
        return [
            web.storage(
                name=p.value,
                key="/publishers/" + p.value.replace(" ", "_"),
                count=p.count,
            )
            for p in publisher_facets
        ]


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
