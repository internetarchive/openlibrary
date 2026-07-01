"""Subject pages."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, cast

import web

from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary.core.lending import add_availability_async
from openlibrary.core.models import Subject, Tag
from openlibrary.plugins.worksearch.subject_config import get_featured_subject
from openlibrary.solr.query_utils import query_dict_to_str
from openlibrary.utils.async_utils import async_bridge

if TYPE_CHECKING:
    from openlibrary.utils.solr import SolrRequestLabel

__all__ = ["SubjectEngine", "get_subject"]


DEFAULT_RESULTS = 12
MAX_RESULTS = 1000
NOTABLE_AUTHORS_LIMIT = 24

# Solr JSON Facet used to rank a subject's authors by aggregate *reader demand*
# (the sum of readinglog counts across their works on this subject) instead of by
# how many works they have tagged. Ranking by work-count rewards prolific
# catalogers and anthology editors; ranking by demand surfaces the authors a
# reader actually associates with the genre. ``author_facet`` is the combined
# "OLID Author Name" string field, so each bucket value carries the name too.
_NOTABLE_AUTHORS_JSON_FACET = json.dumps(
    {
        "notable_authors": {
            "type": "terms",
            "field": "author_facet",
            "limit": NOTABLE_AUTHORS_LIMIT,
            "sort": "demand desc",
            "facet": {"demand": "sum(readinglog_count)"},
        }
    }
)


def parse_notable_authors(raw_resp: dict | None) -> list:
    """Build a demand-ranked author list from a Solr JSON-facet response.

    Returns web.storage items with ``key`` (``/authors/OLID``), ``name``,
    ``count`` (works on this subject) and ``demand`` (summed readinglog count),
    sorted by demand then work count. Returns ``[]`` when the facet is absent.
    """
    buckets = (((raw_resp or {}).get("facets") or {}).get("notable_authors") or {}).get("buckets") or []
    authors = []
    for bucket in buckets:
        olid, _sep, name = (bucket.get("val") or "").partition(" ")
        if not olid:
            continue
        authors.append(
            web.storage(
                key=f"/authors/{olid}",
                name=name,
                count=bucket.get("count") or 0,
                demand=int(bucket.get("demand") or 0),
            )
        )
    # Re-sort defensively so ties (and the all-zero-demand case in sparse data)
    # fall back to work count deterministically rather than Solr's bucket order.
    authors.sort(key=lambda a: (a.demand, a.count), reverse=True)
    return authors


# Trailing catalog qualifiers stripped for display, e.g.
# "Doctor (Fictitious character)" -> "Doctor", "Mars (Planet)" -> "Mars".
_FACET_QUALIFIER_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Bare cataloging eras that make poor browse seeds — too broad and artifact-y,
# e.g. "20th century", "1950-", "1837-1901". Named eras ("Victorian era", "The
# Far Future") survive and are what make the "When it's set" group worthwhile.
_BARE_TIME_RE = re.compile(r"^(?:\d+(?:st|nd|rd|th)\s+century|\d{3,4}\s*-\s*\d{0,4})$", re.IGNORECASE)

# Generic facet values that just echo the page or carry no browse signal.
_GENERIC_FACET_NAMES = {"fiction", "fiction, general", "general", "history and criticism"}

# Bare temporal words make tautological era seeds (esp. "Future" on a sci-fi
# page); qualified eras ("Near Future", "The Far Future") still survive because
# only the bare word is listed here. Checked against the article-stripped norm.
_GENERIC_TIME_NAMES = {"future", "past", "present"}

# Leading article dropped for dedup only, so "The Future" collapses into
# "Future" and "The Moon" into "Moon" (display text keeps the original).
_LEADING_ARTICLE_RE = re.compile(r"^the\s+", re.IGNORECASE)

# Reader-facing "Keep exploring" groups, drawn from place/person/time facets.
# Related *subjects* are deliberately excluded: they overlap the curated Genres
# map already in the sidebar and are the noisiest facet.
_BROWSE_THREAD_KINDS = ("places", "people", "times")


def _clean_facet_label(name: str) -> str:
    return _FACET_QUALIFIER_RE.sub("", name).strip()


def _thread_norm(label: str) -> str:
    """Normalize for dedup, dropping a leading article ('The Future' == 'Future')."""
    return Tag.normalize(_LEADING_ARTICLE_RE.sub("", label))


def build_browse_threads(subj, *, per_group: int = 6, min_items: int = 3) -> list[dict]:
    """Curate place/person/time facets into reader-facing browse seeds.

    The facet data is already fetched for the page; this just curates it: strips
    catalog qualifiers, dedupes by cleaned name, drops self-references and
    generic noise (plus bare cataloging eras for ``times``), caps each group to
    ``per_group``, and omits any group left with fewer than ``min_items`` so
    weak facets (e.g. era data on a sci-fi page) never render a hollow group.

    Returns a list of ``{"kind", "items"}`` dicts; ``kind`` maps to a translated
    label in the SubjectThreads macro so i18n stays in the template layer.
    """
    subject_norm = _thread_norm(subj.name)
    groups: list[dict] = []
    for kind in _BROWSE_THREAD_KINDS:
        seen: set[str] = set()
        items = []
        for item in subj.get(kind) or []:
            display = _clean_facet_label(item.name)
            norm = _thread_norm(display)
            if not display or norm in seen or norm == subject_norm:
                continue
            if display.lower() in _GENERIC_FACET_NAMES:
                continue
            if kind == "times" and (norm in _GENERIC_TIME_NAMES or _BARE_TIME_RE.match(display)):
                continue
            seen.add(norm)
            items.append(web.storage(key=item.key, display_name=display, count=item.count))
            if len(items) >= per_group:
                break
        if len(items) >= min_items:
            groups.append({"kind": kind, "items": items})
    return groups


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
            # Fetch a deeper works sample than the page renders so we can map a
            # representative work onto each top author for the sidebar (below)
            # without a second query.
            limit=48,
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
            if editorial := get_featured_subject(key):
                subj.editorial = editorial
            subj.author_works = self._author_works(subj)
            self._attach_author_photos(subj.get("notable_authors") or subj.get("authors"))
            subj.browse_threads = build_browse_threads(subj)
            page = render_template("subjects", page=subj)

        return page

    @staticmethod
    def _attach_author_photos(authors) -> None:
        """Annotate each rendered author with a ``photo`` cover id.

        The sidebar serves portraits as ``/a/id/<photo>`` (a global cover-store
        id) rather than ``/a/olid/<OLID>`` so dev — which reads from the
        production CDN and carries OLIDs that don't match production — can still
        show a photo once the local record gets a real ``photos`` id (see the
        ``populate-author-photos`` shelfie command). Only the first six authors
        are rendered, so only those are loaded."""
        for author in (authors or [])[:6]:
            thing = web.ctx.site.get(author.key)
            photos = (thing and thing.get("photos")) or []
            author.photo = next((pid for pid in photos if pid and pid > 0), None)

    @staticmethod
    def _author_works(subj) -> dict:
        """Map each author key to a representative work for the sidebar.

        Reuses the works already fetched for this page (no extra query), picking
        the first (highest-ranked) work each author appears on. Authors with no
        work in the sample are simply omitted.
        """
        author_works: dict = {}
        for work in subj.get("works") or []:
            for author in work.get("authors") or []:
                if author.key not in author_works:
                    author_works[author.key] = work
        return author_works

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
                # Demand-ranked author list for the subject sidebar (see above).
                *([("json.facet", _NOTABLE_AUTHORS_JSON_FACET)] if details else []),
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

            # Authors ranked by aggregate reader demand (see the JSON facet
            # above), for the new subject-page "Notable authors" sidebar.
            subject.notable_authors = parse_notable_authors(result.raw_resp)

        return subject

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
