"""Subject pages."""

import asyncio
import itertools
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

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

logger = logging.getLogger("openlibrary.worksearch")


DEFAULT_RESULTS = 12
MAX_RESULTS = 1000

FacetSpec = str | dict[str, int | str]
"""A bare Solr facet field name, or a {"name": ..., "sort"/"limit": ...} spec."""

# Facets requested when details=True and no facet_fields override is given.
DEFAULT_FACET_FIELDS: list[FacetSpec] = [
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

# Works sampled per signal; 8 unique authors reliably appear in the first 40 rows.
NOTABLE_AUTHORS_SAMPLE_SIZE = 40
MAX_NOTABLE_AUTHORS = 8
# Reading-log surfaces a subject's contemporary authors, syllabus assignments its
# canonical ones; neither is dense enough alone. Reading-log leads because the
# first sort owns the most visible slot.
NOTABLE_AUTHORS_SORTS = ("readinglog", "osp_count desc")
# Works with no signal at all can only be tie-broken arbitrarily. Excluding them
# shrinks the scanned corpus 3-84x depending on the subject.
NOTABLE_AUTHORS_CANDIDATE_FILTER = "osp_count:[1 TO *] OR readinglog_count:[5 TO *] OR edition_count:[5 TO *]"
# Long TTL is safe: memcache_memoize is stale-while-revalidate.
NOTABLE_AUTHORS_CACHE_TIMEOUT = 12 * 60 * 60  # 12h


class subjects(delegate.page):
    path = "(/subjects/[^/]+)"

    def GET(self, key):
        if (nkey := self.normalize_key(key)) != key:
            raise web.redirect(nkey)

        # this needs to be updated to include:
        # q=public_scan_b:true+OR+lending_edition_s:*
        # No facets, no docs: subjects.html doesn't render `works` (the on-page
        # carousel runs its own query via `page.solr_query`), and every facet it
        # used is now fetched by the PublishingHistory/RelatedSubjects partials
        # instead (see SubjectPublishingHistoryPartial/SubjectRelatedPartial).
        # This leaves just a plain work_count query.
        subj = get_subject(
            key,
            limit=0,
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
        Attaches the cached "Notable authors" list for the SubjectAuthors macro.

        Cached authors come back as plain dicts (memcache round-trips through
        JSON), so they're rehydrated into web.storage for Templetor's dot access.
        """
        subject.notable_authors = []
        engine = next((e for e in SUBJECTS if e.name == subject.subject_type), None)
        if engine is None:
            return

        path = subject.key.removeprefix(engine.prefix)
        try:
            raw_authors = get_cached_notable_authors(subject.subject_type, path)
            # Rehydration is inside the try as well: memcache entries are written
            # without an expiry under a key_prefix that's stable across deploys,
            # so a payload in an older shape can outlive the deploy that changed
            # it, and reading a missing field here would 500 the page for as long
            # as that entry survives.
            subject.notable_authors = [
                web.storage(
                    key=raw["key"],
                    name=raw["name"],
                    representative_work=(web.storage(title=rep_work["title"]) if (rep_work := raw.get("representative_work")) else None),
                )
                for raw in raw_authors
            ]
        except Exception:
            # A cold miss touches solr, memcache and infobase; none of them
            # should be able to take down a page whose main content is ready.
            logger.exception("Failed to load notable authors for %s", subject.key)


def normalize_author_name(name: str) -> str:
    """
    Collapses case, accents and punctuation, so duplicate author records for one
    person ("Lynne McTaggart" / "Lynne Mctaggart", "José Saramago" / "Jose
    Saramago") don't render as two cards.

    Deliberately script-agnostic: an ASCII-only strip would map every Cyrillic
    or CJK name to "", which the caller reads as "nothing to compare" and skips,
    silently disabling the check on exactly the subjects that need it most.

    casefold() runs before the decomposition because it can introduce combining
    marks of its own (Turkish "İ" -> "i" + combining dot).
    """
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    unaccented = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[\W_]", "", unaccented)


def merge_notable_authors(samples: list[list[dict]]) -> list[web.storage]:
    """
    Interleaves per-signal work samples by rank, so a thin signal still gets
    represented, and takes each author's highest-ranked work as their
    representative work.

    Only a work's *first* author is considered: solr's author_key carries no
    role, so later entries are as often illustrators or narrators as co-authors.
    """
    authors: dict[str, web.storage] = {}
    seen_names: set[str] = set()

    # zip_longest walks rank 0 of every sample, then rank 1, and so on.
    for docs in itertools.zip_longest(*samples):
        for doc in docs:
            if not doc:
                continue
            # Nothing to link to or display, so it can't be a representative work.
            if not doc.get("key") or not doc.get("title"):
                continue

            author_keys = doc.get("author_key") or []
            author_names = doc.get("author_name") or []
            if not author_keys or not author_names:
                continue

            olid, name = author_keys[0], author_names[0]
            # The solr updater defaults a missing author name to "", which
            # would render a nameless card.
            if not (name or "").strip() or olid in authors:
                continue

            normalized = normalize_author_name(name)
            if normalized and normalized in seen_names:
                continue

            authors[olid] = web.storage(
                key=f"/authors/{olid}",
                name=name,
                # Title only: the card links to the author, not the work, so a
                # work key would just be cached weight nothing ever reads.
                representative_work=web.storage(title=doc["title"]),
            )
            if normalized:
                seen_names.add(normalized)
            if len(authors) >= MAX_NOTABLE_AUTHORS:
                return list(authors.values())

    return list(authors.values())


def _compute_notable_authors(subject_type: str, path: str) -> list[dict]:
    """
    Sync seam for memcache_memoize, which is sync-only and needs JSON-encodable
    args (hence plain strings rather than a SubjectEngine).
    """
    if "site" not in web.ctx:
        # The background refresh thread has no request ctx. Same guard as
        # core/lending.get_user_waiting_loans.
        delegate.fakeload()

    engine = next((e for e in SUBJECTS if e.name == subject_type), None)
    if engine is None:
        return []

    return [dict(author) for author in async_bridge.run(engine.get_notable_authors_async(path))]


get_cached_notable_authors = cache.memcache_memoize(
    _compute_notable_authors,
    key_prefix="subjects.notable_authors",
    timeout=NOTABLE_AUTHORS_CACHE_TIMEOUT,
    hash_args=True,  # long subject slugs would overflow memcache's 250-char key limit
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
    details: bool = False,
    offset=0,
    sort="editions",
    limit=DEFAULT_RESULTS,
    request_label: SolrRequestLabel = "UNLABELLED",
    *,
    facet_fields: list[FacetSpec] | None = None,
    **filters: Any,
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

    Optional arguments has_fulltext and publish_year can be passed to filter the results.

    By default, details=True requests every facet in DEFAULT_FACET_FIELDS. Pass
    facet_fields to request a specific subset instead.
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
        facet_fields=facet_fields,
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
        details: bool = False,
        offset=0,
        limit=DEFAULT_RESULTS,
        sort="new",
        request_label: SolrRequestLabel = "UNLABELLED",
        *,
        facet_fields: list[FacetSpec] | None = None,
        **filters: Any,
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
            facet=(facet_fields if facet_fields is not None else details and DEFAULT_FACET_FIELDS),
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

            # A facet_fields caller may omit any of these; default rather
            # than assume every key is present.
            if has_fulltext_counts := result.facet_counts.get("has_fulltext"):
                subject.ebook_count = next(
                    (
                        count
                        for key, count in cast(  # These are fetched in a different format, we need to fix the types
                            list[tuple[str, int]], has_fulltext_counts
                        )
                        if key == "true"
                    ),
                    0,
                )

            subject.subjects = result.facet_counts.get("subject_facet", [])
            subject.places = result.facet_counts.get("place_facet", [])
            subject.people = result.facet_counts.get("person_facet", [])
            subject.times = result.facet_counts.get("time_facet", [])

            subject.authors = result.facet_counts.get("author_key", [])
            subject.publishers = result.facet_counts.get("publisher_facet", [])
            subject.languages = result.facet_counts.get("language", [])

            # Phase 1 (epic #13135): "Notable authors" is computed and
            # cached separately -- see get_cached_notable_authors and
            # subjects.decorate_with_notable_authors -- rather than fetched
            # unconditionally here on every request.

            # Ignore bad dates when computing publishing_history
            # year < 1000 or year > current_year+1 are considered bad dates
            current_year = datetime.now(tz=UTC).date().year
            subject.publishing_history = [
                [year, count]
                for year, count in cast(  # These are fetched in a different format, we need to fix the types
                    list[tuple[int, int]],
                    result.facet_counts.get("publish_year", []),
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
        # Defaults to its own label (not UNLABELLED) so this query stays
        # attributable in Solr load monitoring.
        request_label: SolrRequestLabel = "SUBJECT_NOTABLE_AUTHORS",
    ) -> list[web.storage]:
        """
        Builds a signal-ranked "Notable authors" list for a subject.

        Samples works once per signal in NOTABLE_AUTHORS_SORTS (concurrently),
        then interleaves the samples -- see merge_notable_authors. Deliberately
        ignores the reader's filters and sort, so one cached list serves every
        variant of the page.
        """
        # Circular imports are everywhere -_-
        from openlibrary.plugins.worksearch.code import (
            WorkSearchScheme,
            run_solr_query_async,
        )

        query = {"q": query_dict_to_str({self.facet_key: self.normalize_key(path)}, phrase=True)}

        async def sample(sort: str) -> list[dict]:
            result = await run_solr_query_async(
                WorkSearchScheme(),
                query,
                request_label=request_label,
                rows=NOTABLE_AUTHORS_SAMPLE_SIZE,
                sort=sort,
                facet=False,
                # q is a machine-built subject_key term, never a reader's typing,
                # and nothing reads the suggestions -- don't make Solr build them.
                spellcheck_count=0,
                fields=["key", "title", "author_key", "author_name"],
                # fq rather than part of q: it's identical for every subject, so
                # Solr's filterCache entry is shared across all of them.
                extra_params=[("fq", NOTABLE_AUTHORS_CANDIDATE_FILTER)],
            )
            return result.docs

        samples = await asyncio.gather(*(sample(sort) for sort in NOTABLE_AUTHORS_SORTS))
        return merge_notable_authors(samples)

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
