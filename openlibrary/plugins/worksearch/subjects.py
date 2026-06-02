"""Subject pages."""

from dataclasses import dataclass
from datetime import date
from typing import cast

import web

from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.core.lending import add_availability_async
from openlibrary.core.models import Subject, Tag
from openlibrary.plugins.upstream.edits import process_merge_request
from openlibrary.solr.query_utils import query_dict_to_str
from openlibrary.utils import uniq
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.solr import SolrRequestLabel

__all__ = ["SubjectEngine", "get_subject"]


DEFAULT_RESULTS = 12
MAX_RESULTS = 1000


SUBJECT_MERGE_TYPES = {"subject", "person", "place", "time"}


def normalize_subject_merge_id(record: str) -> str:
    record = record.strip().removeprefix("/subjects/")
    if record.startswith("subject:"):
        record = record.split(":", 1)[1]

    if ":" in record:
        subject_type, name = record.split(":", 1)
        if subject_type in SUBJECT_MERGE_TYPES - {"subject"}:
            return f"{subject_type}:{Tag.normalize(name)}"

    return f"subject:{Tag.normalize(record)}"


def get_subject_key_from_merge_id(record_id: str) -> str:
    subject_type, slug = record_id.split(":", 1)
    if subject_type == "subject":
        return f"/subjects/{slug}"
    return f"/subjects/{subject_type}:{slug}"


def get_subject_merge_record(record_id: str) -> web.storage:
    key = get_subject_key_from_merge_id(record_id)
    subject_type, slug = record_id.split(":", 1)
    fallback_name = slug.replace("_", " ")
    subject = get_subject(key, limit=0, request_label="SUBJECT_ENGINE_PAGE")
    name = subject.name if subject and subject.name else fallback_name
    work_count = subject.work_count if subject and subject.work_count else 0

    return web.storage(
        id=record_id,
        key=key,
        name=name,
        subject_type=subject_type,
        work_count=work_count,
    )


class merge_subjects(delegate.page):
    path = "/subjects/merge"

    def require_access(self):
        user = accounts.get_current_user()
        if user is None:
            raise web.unauthorized()
        if not (user.is_admin() or user.is_librarian() or user.is_super_librarian()):
            raise web.forbidden()
        return user

    def get_records(self, values: list[str]) -> list[web.storage]:
        record_ids = uniq(normalize_subject_merge_id(value) for value in values if value)
        return [get_subject_merge_record(record_id) for record_id in record_ids]

    def GET(self):
        self.require_access()
        i = web.input(key=[], mrid=None, records="", primary=None)
        values = list(i.key) + i.records.strip(",").split(",")
        records = self.get_records(values)
        primary = normalize_subject_merge_id(i.primary) if i.primary else None
        return render_template("merge/subjects", records, mrid=i.mrid, primary=primary)

    def POST(self):
        user = self.require_access()
        i = web.input(key=[], master=None, merge_key=[], mrid=None, comment=None)
        records = self.get_records(list(i.key))
        selected = uniq(i.merge_key)

        if i.master in selected:
            selected.remove(i.master)

        formdata = web.storage(master=i.master, selected=selected)
        if not i.master or len(selected) == 0:
            return render_template("merge/subjects", records, formdata=formdata, mrid=i.mrid)

        selected.insert(0, i.master)
        data = {
            "mr_type": CommunityEditsQueue.TYPE["SUBJECT_MERGE"],
            "action": "create-pending",
            "olids": ",".join(selected),
            "primary": i.master,
        }
        if i.comment:
            data["comment"] = i.comment

        result = process_merge_request("create-request", data)
        username = user.get("key").split("/")[-1]

        redir_url = f"/merges?submitter={username}"
        if mrid := result.get("id", None):
            redir_url = f"{redir_url}#mrid-{mrid}"
        raise web.seeother(redir_url)


class subjects(delegate.page):
    path = "(/subjects/(?!merge$)[^/]+)"

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

        if details:
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
