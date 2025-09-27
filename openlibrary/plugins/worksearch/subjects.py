"""Subject pages."""

import datetime
import json
from dataclasses import dataclass

import web

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary.core.lending import add_availability
from openlibrary.core.models import Subject, Tag
from openlibrary.solr.query_utils import query_dict_to_str
from openlibrary.utils import str_to_key

__all__ = ["SubjectEngine", "SubjectMeta", "get_subject"]


DEFAULT_RESULTS = 12
MAX_RESULTS = 1000


class subjects(delegate.page):
    path = '(/subjects/[^/]+)'

    def GET(self, key):
        if (nkey := self.normalize_key(key)) != key:
            raise web.redirect(nkey)

        # this needs to be updated to include:
        # q=public_scan_b:true+OR+lending_edition_s:*
        subj = get_subject(
            key,
            details=True,
            filters={'public_scan_b': 'false', 'lending_edition_s': '*'},
            sort=web.input(sort='readinglog').sort,
        )

        delegate.context.setdefault('cssfile', 'subject')
        if not subj or subj.work_count == 0:
            web.ctx.status = "404 Not Found"
            page = render_template('subjects/notfound.tmpl', key)
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
        if tag_keys := Tag.find(subject.name):
            tags = web.ctx.site.get_many(tag_keys)
            subject.disambiguations = tags

            if filtered_tags := [
                tag for tag in tags if tag.tag_type == subject.subject_type
            ]:
                subject.tag = filtered_tags[0]
                # Remove matching subject tag from disambiguated tags:
                subject.disambiguations = list(set(tags) - {subject.tag})

            for tag in subject.disambiguations:
                tag.subject_key = (
                    f"/subjects/{tag.name}"
                    if tag.tag_type == "subject"
                    else f"/subjects/{tag.tag_type}:{tag.name}"
                )


class subjects_json(delegate.page):
    path = '(/subjects/[^/]+)'
    encoding = 'json'

    @jsonapi
    def GET(self, key):
        web.header('Content-Type', 'application/json')
        # If the key is not in the normalized form, redirect to the normalized form.
        if (nkey := self.normalize_key(key)) != key:
            raise web.redirect(nkey)

        # Does the key requires any processing before passing using it to query solr?
        key = self.process_key(key)

        i = web.input(
            offset=0,
            limit=DEFAULT_RESULTS,
            details='false',
            has_fulltext='false',
            sort='editions',
            available='false',
        )
        i.limit = safeint(i.limit, DEFAULT_RESULTS)
        i.offset = safeint(i.offset, 0)
        if i.limit > MAX_RESULTS:
            msg = json.dumps(
                {'error': 'Specified limit exceeds maximum of %s.' % MAX_RESULTS}
            )
            raise web.HTTPError('400 Bad Request', data=msg)

        filters = {}
        if i.get('has_fulltext') == 'true':
            filters['has_fulltext'] = 'true'

        if publish_year_filter := date_range_to_publish_year_filter(
            i.get('published_in')
        ):
            filters['publish_year'] = publish_year_filter

        subject_results = get_subject(
            key,
            offset=i.offset,
            limit=i.limit,
            sort=i.sort,
            details=i.details.lower() == 'true',
            **filters,
        )
        if i.has_fulltext == 'true':
            subject_results['ebook_count'] = subject_results['work_count']
        return json.dumps(subject_results)

    def normalize_key(self, key):
        return key.lower()

    def process_key(self, key):
        return key


def date_range_to_publish_year_filter(published_in: str) -> str:
    if published_in:
        if '-' in published_in:
            begin, end = published_in.split('-', 1)
            if safeint(begin, None) is not None and safeint(end, None) is not None:
                return f'[{begin} TO {end}]'
        else:
            year = safeint(published_in, None)
            if year is not None:
                return published_in
    return ''


SubjectPseudoKey = str
"""
The key-like paths for a subject, eg:
- `/subjects/foo`
- `/subjects/person:harry_potter`
"""


def get_subject(
    key: SubjectPseudoKey,
    details=False,
    offset=0,
    sort='editions',
    limit=DEFAULT_RESULTS,
    **filters,
) -> Subject:
    """Returns data related to a subject.

    By default, it returns a storage object with key, name, work_count and works.
    The offset and limit arguments are used to get the works.

        >>> get_subject("/subjects/Love") #doctest: +SKIP
        {
            "key": "/subjects/Love",
            "name": "Love",
            "work_count": 5129,
            "works": [...]
        }

    When details=True, facets and ebook_count are additionally added to the result.

    >>> get_subject("/subjects/Love", details=True) #doctest: +SKIP
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
    EngineClass = next(
        (d.Engine for d in SUBJECTS if key.startswith(d.prefix)), SubjectEngine
    )
    return EngineClass().get_subject(
        key,
        details=details,
        offset=offset,
        sort=sort,
        limit=limit,
        **filters,
    )


class SubjectEngine:
    def get_subject(
        self,
        key,
        details=False,
        offset=0,
        limit=DEFAULT_RESULTS,
        sort='new',
        **filters,
    ):
        # Circular imports are everywhere -_-
        from openlibrary.plugins.worksearch.code import (  # noqa: RUF100, PLC0415
            WorkSearchScheme,
            run_solr_query,
        )

        meta = self.get_meta(key)
        subject_type = meta.name
        path = web.lstrips(key, meta.prefix)
        name = path.replace("_", " ")

        unescaped_filters = {}
        if 'publish_year' in filters:
            # Don't want this escaped or used in fq for perf reasons
            unescaped_filters['publish_year'] = filters.pop('publish_year')
        result = run_solr_query(
            WorkSearchScheme(),
            {
                'q': query_dict_to_str(
                    {meta.facet_key: self.normalize_key(path)},
                    unescaped=unescaped_filters,
                    phrase=True,
                ),
                **filters,
            },
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
                "ia_collection_s",
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
                ('facet.mincount', 1),
                ('facet.limit', 25),
            ],
            allowed_filter_params={
                'has_fulltext',
                'publish_year',
            },
        )

        subject = Subject(
            key=key,
            name=name,
            subject_type=subject_type,
            solr_query=query_dict_to_str(
                {meta.facet_key: self.normalize_key(path)},
                phrase=True,
            ),
            work_count=result.num_found,
            works=add_availability([self.work_wrapper(d) for d in result.docs]),
        )

        if details:
            result.facet_counts = {
                facet_field: [
                    self.facet_wrapper(facet_field, key, label, count)
                    for key, label, count in facet_counts
                ]
                for facet_field, facet_counts in result.facet_counts.items()
            }

            subject.ebook_count = next(
                (
                    count
                    for key, count in result.facet_counts["has_fulltext"]
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
            subject.languages = result.facet_counts['language']

            # Ignore bad dates when computing publishing_history
            # year < 1000 or year > current_year+1 are considered bad dates
            current_year = datetime.datetime.utcnow().year
            subject.publishing_history = [
                [year, count]
                for year, count in result.facet_counts["publish_year"]
                if 1000 < year <= current_year + 1
            ]

            # strip self from subjects and use that to find exact name
            for i, s in enumerate(subject[meta.key]):
                if "key" in s and s.key.lower() == key.lower():
                    subject.name = s.name
                    subject[meta.key].pop(i)
                    break

        return subject

    def get_meta(self, key) -> 'SubjectMeta':
        prefix = self.parse_key(key)[0]
        meta = next((d for d in SUBJECTS if d.prefix == prefix), None)
        assert meta is not None, "Invalid subject key: {key}"
        return meta

    def parse_key(self, key):
        """Returns prefix and path from the key."""
        for d in SUBJECTS:
            if key.startswith(d.prefix):
                return d.prefix, key[len(d.prefix) :]
        return None, None

    def normalize_key(self, key):
        return str_to_key(key).lower()

    def facet_wrapper(self, facet: str, value: str, label: str, count: int):
        if facet == "publish_year":
            return [int(value), count]
        elif facet == "publisher_facet":
            return web.storage(
                name=value, count=count, key="/publishers/" + value.replace(" ", "_")
            )
        elif facet == "author_key":
            return web.storage(name=label, key=f"/authors/{value}", count=count)
        elif facet in ["subject_facet", "person_facet", "place_facet", "time_facet"]:
            meta = next((d for d in SUBJECTS if d.facet == facet), None)
            assert meta is not None, "Invalid subject facet: {facet}"
            return web.storage(
                key=meta.prefix + str_to_key(value).replace(" ", "_"),
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
        ia_collection = w.get('ia_collection_s', '').split(';')
        return web.storage(
            key=w['key'],
            title=w["title"],
            edition_count=w["edition_count"],
            cover_id=w.get('cover_i'),
            cover_edition_key=w.get('cover_edition_key'),
            subject=w.get('subject', []),
            ia_collection=ia_collection,
            printdisabled='printdisabled' in ia_collection,
            lending_edition=w.get('lending_edition_s', ''),
            lending_identifier=w.get('lending_identifier_s', ''),
            authors=[
                web.storage(key=f'/authors/{olid}', name=name)
                for olid, name in zip(w.get('author_key', []), w.get('author_name', []))
            ],
            first_publish_year=w.get('first_publish_year'),
            ia=w.get('ia', [None])[0],
            public_scan=w.get('public_scan_b', bool(w.get('ia'))),
            has_fulltext=w.get('has_fulltext', False),
        )


@dataclass
class SubjectMeta:
    name: str
    key: str
    prefix: str
    facet: str
    facet_key: str
    Engine: type['SubjectEngine'] = SubjectEngine


SUBJECTS = [
    SubjectMeta(
        name="person",
        key="people",
        prefix="/subjects/person:",
        facet="person_facet",
        facet_key="person_key",
    ),
    SubjectMeta(
        name="place",
        key="places",
        prefix="/subjects/place:",
        facet="place_facet",
        facet_key="place_key",
    ),
    SubjectMeta(
        name="time",
        key="times",
        prefix="/subjects/time:",
        facet="time_facet",
        facet_key="time_key",
    ),
    SubjectMeta(
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
