"""Subject pages."""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, cast

import web
from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary.core import cache
from openlibrary.core.lending import add_availability_async
from openlibrary.core.models import Subject, Tag
from openlibrary.solr.query_utils import query_dict_to_str
from openlibrary.utils.async_utils import async_bridge

if TYPE_CHECKING:
    from openlibrary.utils.solr import SolrRequestLabel

__all__ = ["SubjectEngine", "get_subject"]


DEFAULT_RESULTS = 12
MAX_RESULTS = 1000

# Signal-ranked "Notable authors"
# Bounded sample of works (sorted by a popularity signal) scanned to build
# the notable-authors list. Keeps this to a single extra Solr query instead
# of one query per author. Trimmed from 100->40 per review: with
# MAX_NOTABLE_AUTHORS=8 over a readinglog-sorted list, 8 unique authors are
# almost always found within the first ~20-30 rows, so 40 cuts scan/payload
# with no realistic quality loss.
NOTABLE_AUTHORS_SAMPLE_SIZE = 40
MAX_NOTABLE_AUTHORS = 8
# Long TTL: this list changes infrequently, and memcache_memoize is
# stale-while-revalidate, so a stale value is served instantly while a
# background thread recomputes -- no request ever blocks on a refresh.
NOTABLE_AUTHORS_CACHE_TIMEOUT = 12 * 60 * 60  # 12h


class subjects(delegate.page):
    path = "(/subjects/[^/]+)"

    def GET(self, key):
        if (nkey := self.normalize_key(key)) != key:
            raise web.redirect(nkey)

        # this needs to be updated to include:
        # q=public_scan_b:true+OR+lending_edition_s:*
        subj = get_subject(
            key,
            details=True,
            filters={"public_scan_b": "false", "lending_edition_s": "*"},
            sort=web.input(sort="readinglog").sort,
            request_label="SUBJECT_ENGINE_PAGE",
        )

        delegate.context.setdefault("cssfile", "subject")
        if not subj or subj.work_count == 0:
            web.ctx.status = "404 Not Found"
            page = render_template("subjects/notfound.tmpl", key)
        else:
            self.decorate_with_tags(subj)
            self.decorate_with_notable_authors(subj)
            page = render_template("subjects", page=subj)

        return page

    def normalize_key(self, key):
        key = key.lower()

        # temporary code to handle url change from /people/ to /person:
        if key.count("/") == 3:
            key = key.replace("/people/", "/person:")
            key = key.replace("/places/", "/place:")
            key = key.replace("/times/", "/time:")
        return key

    def decorate_with_tags(self, subject) -> None:
        name = subject.name
        # Split prefixed subjects: "genre:thriller" → tag_type="genre", slug="thriller"
        if ":" in name:
            tag_type, slug_raw = name.split(":", 1)
            slug = Tag.normalize(slug_raw)
        else:
            tag_type = subject.subject_type
            slug = Tag.normalize(name)

        if tag_keys := Tag.find(slug):
            tags = web.ctx.site.get_many(tag_keys)
            subject.disambiguations = tags

            if filtered_tags := [tag for tag in tags if tag.tag_type == tag_type]:
                subject.tag = filtered_tags[0]
                # Remove matching subject tag from disambiguated tags:
                subject.disambiguations = list(set(tags) - {subject.tag})

            for tag in subject.disambiguations:
                slug = tag.slugs[0] if tag.get("slugs") else Tag.normalize(tag.name)
                tag.subject_key = f"/subjects/{slug}" if tag.tag_type == "subject" else f"/subjects/{tag.tag_type}:{slug}"

    def decorate_with_notable_authors(self, subject) -> None:
        """
        Phase 1 (epic #13135): fetches the cached "Notable authors" list
        (ranking + representative works + photos, all computed together in
        _compute_notable_authors_with_photos and memoized -- see that
        function's docstring) and attaches it to the subject for the
        SubjectAuthors macro.

        Two things happen here rather than in the cached function itself:
        - Rehydration: memcache round-trips through JSON, so cached authors
          come back as plain dicts, not web.storage. The Templetor macro
          does $author.key / $author.representative_work.title, which fails
          on a bare dict -- so we rebuild web.storage here, on every read.
        - Exact count merge: subject.authors (the author_key facet) is
          already computed fresh on *every* request as part of the main
          query, so merging it in here (rather than caching it) keeps
          displayed counts accurate even while the cached ranking/
          representative-work data is intentionally left stale for up to
          NOTABLE_AUTHORS_CACHE_TIMEOUT.
        """
        engine = next((e for e in SUBJECTS if e.name == subject.subject_type), None)
        if engine is None:
            return

        path = subject.key.removeprefix(engine.prefix)
        raw_authors = get_cached_notable_authors(subject.subject_type, path)
        if not raw_authors:
            subject.notable_authors = []
            return

        exact_counts = {a.key: a.count for a in subject.get("authors") or []}
        notable_authors = []
        for raw in raw_authors:
            rep_work = raw.get("representative_work")
            author = web.storage(
                key=raw["key"],
                name=raw["name"],
                photo_url=raw.get("photo_url"),
                representative_work=(
                    web.storage(
                        key=rep_work["key"],
                        title=rep_work["title"],
                        cover_id=rep_work.get("cover_id"),
                    )
                    if rep_work
                    else None
                ),
                count=exact_counts.get(raw["key"], raw.get("count", 1)),
            )
            notable_authors.append(author)
        subject.notable_authors = notable_authors


def _compute_notable_authors_with_photos(subject_type: str, path: str) -> list[dict]:
    """
    Sync seam for cache.memcache_memoize (memcache_memoize is sync-only;
    SubjectEngine.get_notable_authors_async is async). Bridges via
    async_bridge, then folds in author-photo decoration here too, so
    photos are cached alongside the ranking/representative-work data
    instead of being re-fetched from the site store on every cache hit.

    Args are plain strings (subject_type + path) rather than a
    SubjectEngine instance or dict, since memcache_memoize needs
    JSON-encodable args to build a stable, cacheable key. subject_type is
    used here to re-look-up the right SubjectEngine from SUBJECTS.

    Returns a list of plain dicts -- see decorate_with_notable_authors for
    why (memcache round-trips through JSON) and where rehydration happens.
    """
    if "site" not in web.ctx:
        # The stale-while-revalidate background refresh
        # (memcache_memoize.update_async) runs this on its own thread,
        # which doesn't have a normal request's web.ctx.site set up.
        # Mirrors the identical guard in core/lending.get_user_waiting_loans
        # for the same reason.
        delegate.fakeload()

    engine = next((e for e in SUBJECTS if e.name == subject_type), None)
    if engine is None:
        return []

    authors = async_bridge.run(engine.get_notable_authors_async(path, {}))
    if not authors:
        return []

    authors_by_key = {thing.key: thing for thing in web.ctx.site.get_many([a.key for a in authors])}
    for author in authors:
        thing = authors_by_key.get(author.key)
        author.photo_url = thing.get_photo_url("M") if thing else None

    return [dict(a) for a in authors]


get_cached_notable_authors = cache.memcache_memoize(
    _compute_notable_authors_with_photos,
    key_prefix="subjects.notable_authors",
    timeout=NOTABLE_AUTHORS_CACHE_TIMEOUT,
)


def date_range_to_publish_year_filter(published_in: str) -> str:
    if published_in:
        if "-" in published_in:
            begin, end = published_in.split("-", 1)
            if safeint(begin, None) is not None and safeint(end, None) is not None:
                return f"[{begin} TO {end}]"
        else:
            year = safeint(published_in, None)
            if year is not None:
                return published_in
    return ""


SubjectPseudoKey = str
"""
The key-like paths for a subject, eg:
- `/subjects/foo`
- `/subjects/person:harry_potter`
"""


async def get_subject_async(
    key: SubjectPseudoKey,
    details=False,
    offset=0,
    sort="editions",
    limit=DEFAULT_RESULTS,
    request_label: SolrRequestLabel = "UNLABELLED",
    **filters,
) -> Subject:
    """Returns data related to a subject.

    By default, it returns a storage object with key, name, work_count and works.
    The offset and limit arguments are used to get the works.

        >>> await get_subject_async("/subjects/Love") #doctest: +SKIP
        {
            "key": "/subjects/Love",
            "name": "Love",
            "work_count": 5129,
            "works": [...]
        }

    When details=True, facets and ebook_count are additionally added to the result.

    >>> await get_subject_async("/subjects/Love", details=True) #doctest: +SKIP
    {
        "key": "/subjects/Love",
        "name": "Love",
        "work_count": 5129,
        "works": [...],
        "ebook_count": 94,
        "authors": [
            {
                "count": 11,
                "name": "Plato.",
                "key": "/authors/OL12823A"
            },
            ...
        ],
        "subjects": [
            {
                "count": 1168,
                "name": "Religious aspects",
                "key": "/subjects/religious aspects"
            },
            ...
        ],
        "times": [...],
        "places": [...],
        "people": [...],
        "publishing_history": [[1492, 1], [1516, 1], ...],
        "publishers": [
            {
                "count": 57,
                "name": "Sine nomine"
            },
            ...
        ]
    }

    Optional arguments limit and offset can be passed to limit the number of works returned and starting offset.

    Optional arguments has_fulltext and published_in can be passed to filter the results.
    """
    engine = next((e for e in SUBJECTS if key.startswith(e.prefix)), None)

    if not engine:
        raise NotImplementedError(f"No SubjectEngine for key: {key}")

    return await engine.get_subject_async(
        key,
        details=details,
        offset=offset,
        sort=sort,
        limit=limit,
        request_label=request_label,
        **filters,
    )


get_subject = async_bridge.wrap(get_subject_async)


@dataclass
class SubjectEngine:
    name: str
    key: str
    prefix: str
    facet: str
    facet_key: str

    async def get_subject_async(
        self,
        key,
        details=False,
        offset=0,
        limit=DEFAULT_RESULTS,
        sort="new",
        request_label: SolrRequestLabel = "UNLABELLED",
        **filters,
    ):
        # Circular imports are everywhere -_-
        from openlibrary.plugins.worksearch.code import (
            WorkSearchScheme,
            run_solr_query_async,
        )

        subject_type = self.name
        path = key.removeprefix(self.prefix)
        name = path.replace("_", " ")

        unescaped_filters = {}
        if "publish_year" in filters:
            # Don't want this escaped or used in fq for perf reasons
            unescaped_filters["publish_year"] = filters.pop("publish_year")
        result = await run_solr_query_async(
            WorkSearchScheme(),
            {
                "q": query_dict_to_str(
                    {self.facet_key: self.normalize_key(path)},
                    unescaped=unescaped_filters,
                    phrase=True,
                ),
                **filters,
            },
            request_label=request_label,
            offset=offset,
            rows=limit,
            sort=sort,
            fields=[
                "key",
                "author_name",
                "author_key",
                "title",
                "edition_count",
                "ia",
                "cover_i",
                "first_publish_year",
                "cover_edition_key",
                "has_fulltext",
                "subject",
                "ia_collection",
                "public_scan_b",
                "lending_edition_s",
                "lending_identifier_s",
            ],
            facet=(
                details
                and [
                    {"name": "author_facet", "sort": "count"},
                    "language",
                    "publisher_facet",
                    {"name": "publish_year", "limit": -1},
                    "subject_facet",
                    "person_facet",
                    "place_facet",
                    "time_facet",
                    "has_fulltext",
                ]
            ),
            extra_params=[
                ("facet.mincount", 1),
                ("facet.limit", 25),
            ],
            allowed_filter_params={
                "has_fulltext",
                "publish_year",
            },
        )

        subject = Subject(
            key=key,
            name=name,
            subject_type=subject_type,
            solr_query=query_dict_to_str(
                {self.facet_key: self.normalize_key(path)},
                phrase=True,
            ),
            work_count=result.num_found,
            works=await add_availability_async([self.work_wrapper(d) for d in result.docs]),
        )

        if details and result.facet_counts:
            result.facet_counts = {
                facet_field: [self.facet_wrapper(facet_field, key, label, count) for key, label, count in facet_counts]
                for facet_field, facet_counts in result.facet_counts.items()
            }

            subject.ebook_count = next(
                (
                    count
                    for key, count in cast(  # These are fetched in a different format, we need to fix the types
                        list[tuple[str, int]], result.facet_counts["has_fulltext"]
                    )
                    if key == "true"
                ),
                0,
            )

            subject.subjects = result.facet_counts["subject_facet"]
            subject.places = result.facet_counts["place_facet"]
            subject.people = result.facet_counts["person_facet"]
            subject.times = result.facet_counts["time_facet"]

            subject.authors = result.facet_counts["author_key"]
            subject.publishers = result.facet_counts["publisher_facet"]
            subject.languages = result.facet_counts["language"]

            # Phase 1 (epic #13135): "Notable authors" is computed and
            # cached separately -- see get_cached_notable_authors and
            # subjects.decorate_with_notable_authors -- rather than fetched
            # unconditionally here on every request. It still uses
            # subject.authors (the facet above) for exact per-author counts.

            # Ignore bad dates when computing publishing_history
            # year < 1000 or year > current_year+1 are considered bad dates
            current_year = date.today().year
            subject.publishing_history = [
                [year, count]
                for year, count in cast(  # These are fetched in a different format, we need to fix the types
                    list[tuple[int, int]],
                    result.facet_counts["publish_year"],
                )
                if 1000 < year <= current_year + 1
            ]

            # strip self from subjects and use that to find exact name
            for i, s in enumerate(subject[self.key]):
                if "key" in s and s.key.lower() == key.lower():
                    subject.name = s.name
                    subject[self.key].pop(i)
                    break

        return subject

    async def get_notable_authors_async(
        self,
        path: str,
        filters: dict,
        request_label: SolrRequestLabel = "UNLABELLED",
    ) -> list[web.storage]:
        """
        Builds a signal-ranked "Notable authors" list for a subject.

        Runs one extra Solr query (no facets needed — those are already
        computed by the main query) over a bounded, popularity-sorted sample
        of works, then walks the sample once to pick each author's first
        (i.e. highest-signal) work as their representative work. The `count`
        on each returned author is a placeholder (1); callers should backfill
        exact per-subject book counts from the author_key facet the main
        query already computes -- see decorate_with_notable_authors.
        """
        # Circular imports are everywhere -_-
        from openlibrary.plugins.worksearch.code import (
            WorkSearchScheme,
            run_solr_query_async,
        )

        unescaped_filters = {}
        if "publish_year" in filters:
            unescaped_filters["publish_year"] = filters.pop("publish_year")

        result = await run_solr_query_async(
            WorkSearchScheme(),
            {
                "q": query_dict_to_str(
                    {self.facet_key: self.normalize_key(path)},
                    unescaped=unescaped_filters,
                    phrase=True,
                ),
                **filters,
            },
            request_label=request_label,
            rows=NOTABLE_AUTHORS_SAMPLE_SIZE,
            # Reuses the same popularity signal (readinglog_count) that
            # already drives the page's default work ordering — no new
            # infra, per the epic's Phase 1 scope note.
            sort="readinglog",
            facet=False,
            fields=["key", "title", "author_key", "author_name", "cover_i"],
        )

        notable_authors: dict[str, web.storage] = {}
        for doc in result.docs:
            # Defensive guard: a work doc without a key or title can't be a
            # representative work (nothing to link to / display) -- skip it
            # rather than let a malformed/incomplete Solr doc propagate into
            # the template or crash on the dict-index below.
            if not doc.get("key") or not doc.get("title"):
                continue

            author_keys = doc.get("author_key") or []
            author_names = doc.get("author_name") or []
            for olid, name in zip(author_keys, author_names):
                if olid not in notable_authors:
                    notable_authors[olid] = web.storage(
                        key=f"/authors/{olid}",
                        name=name,
                        representative_work=web.storage(
                            key=doc["key"],
                            title=doc["title"],
                            cover_id=doc.get("cover_i"),
                        ),
                        # Backfilled below from the exact facet count; falls
                        # back to 1 (this work) if the author is somehow
                        # missing from the facet, which shouldn't normally
                        # happen.
                        count=1,
                    )
                    # Check the cap right after each *addition*, not just
                    # once per doc: a single work can have several
                    # co-authors, and without this inner check a work that
                    # pushes us from e.g. 7 to 10 unique authors would blow
                    # past MAX_NOTABLE_AUTHORS before the outer per-doc
                    # check below ever runs.
                    if len(notable_authors) >= MAX_NOTABLE_AUTHORS:
                        break
            if len(notable_authors) >= MAX_NOTABLE_AUTHORS:
                break

        return list(notable_authors.values())

    def normalize_key(self, key):
        return Tag.normalize(key)

    def facet_wrapper(self, facet: str, value: str, label: str, count: int):
        if facet == "publish_year":
            return [int(value), count]
        elif facet == "publisher_facet":
            return web.storage(name=value, count=count, key="/publishers/" + value.replace(" ", "_"))
        elif facet == "author_key":
            return web.storage(name=label, key=f"/authors/{value}", count=count)
        elif facet in ["subject_facet", "person_facet", "place_facet", "time_facet"]:
            engine = next((d for d in SUBJECTS if d.facet == facet), None)
            assert engine is not None, f"Invalid subject facet: {facet}"
            return web.storage(
                key=engine.prefix + Tag.normalize(value),
                name=value,
                count=count,
            )
        elif facet == "has_fulltext":
            return [value, count]
        else:
            return web.storage(name=value, count=count)

    @staticmethod
    def work_wrapper(w: dict) -> web.storage:
        """
        Convert a solr document into the doc returned by the /subjects APIs.
        These docs are weird :/ We should be using more standardized results
        across our search APIs, but that would be a big breaking change.
        """
        ia_collection = w.get("ia_collection") or []
        return web.storage(
            key=w["key"],
            title=w["title"],
            edition_count=w["edition_count"],
            cover_id=w.get("cover_i"),
            cover_edition_key=w.get("cover_edition_key"),
            subject=w.get("subject", []),
            ia_collection=ia_collection,
            printdisabled="printdisabled" in ia_collection,
            lending_edition=w.get("lending_edition_s", ""),
            lending_identifier=w.get("lending_identifier_s", ""),
            authors=[web.storage(key=f"/authors/{olid}", name=name) for olid, name in zip(w.get("author_key", []), w.get("author_name", []))],
            first_publish_year=w.get("first_publish_year"),
            ia=w.get("ia", [None])[0],
            public_scan=w.get("public_scan_b", bool(w.get("ia"))),
            has_fulltext=w.get("has_fulltext", False),
        )


SUBJECTS = [
    SubjectEngine(
        name="person",
        key="people",
        prefix="/subjects/person:",
        facet="person_facet",
        facet_key="person_key",
    ),
    SubjectEngine(
        name="place",
        key="places",
        prefix="/subjects/place:",
        facet="place_facet",
        facet_key="place_key",
    ),
    SubjectEngine(
        name="time",
        key="times",
        prefix="/subjects/time:",
        facet="time_facet",
        facet_key="time_key",
    ),
    SubjectEngine(
        name="subject",
        key="subjects",
        prefix="/subjects/",
        facet="subject_facet",
        facet_key="subject_key",
    ),
]


def setup():
    """Placeholder for doing any setup required.

    This function is called from code.py.
    """
    pass
