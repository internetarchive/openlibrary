"""Helper functions used by the List model."""

import contextlib
import logging
from collections.abc import Iterable
from functools import cached_property
from typing import TypedDict, cast

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.infobase import client, common  # noqa: F401 side effects may be needed
from infogami.utils import stats  # noqa: F401 side effects may be needed
from openlibrary.core import cache
from openlibrary.core import helpers as h
from openlibrary.core.models import Image, Subject, Thing, ThingKey, ThingReferenceDict
from openlibrary.plugins.upstream.models import Author, Changeset, Edition, User, Work
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.plugins.worksearch.subjects import get_subject

logger = logging.getLogger("openlibrary.lists.model")


SeedSubjectString = str
"""
When a subject is added to a list, it's added as a string like:
- "subject:foo"
- "person:floyd_heywood"
"""


class AnnotatedSeedDict(TypedDict):
    """
    The JSON friendly version of an annotated seed.
    """

    thing: ThingReferenceDict
    notes: str


class AnnotatedSeed(TypedDict):
    """
    The database/`Thing` friendly version of an annotated seed.
    """

    thing: Thing
    notes: str


class AnnotatedSeedThing(Thing):
    """
    Note: This isn't a real `Thing` type! This will never be constructed
    or returned. It's just here to illustrate that when we get seeds from
    the db, they're wrapped in this weird `Thing` object, which will have
    a _data field that is the raw JSON data. That JSON data will conform
    to the `AnnotatedSeedDict` type.
    """

    key: None  # type: ignore[assignment]
    _data: AnnotatedSeed


class List(Thing):
    """Class to represent /type/list objects in OL.

    List contains the following properties, theoretically:
        * cover - id of the book cover. Picked from one of its editions.
        * tags - list of tags to describe this list.
    """

    name: str | None
    """Name of the list"""

    description: str | None
    """Detailed description of the list (markdown)"""

    seeds: list[Thing | SeedSubjectString | AnnotatedSeedThing]
    """Members of the list. Either references or subject strings."""

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.name or "unnamed"

    def get_owner(self) -> User | None:
        if match := web.re_compile(r"(/people/[^/]+)/lists/OL\d+L").match(self.key):
            key = match.group(1)
            return cast(User, self._site.get(key))
        else:
            return None

    def get_cover(self):
        """Returns a cover object."""
        return self.cover and Image(self._site, "b", self.cover)

    def get_tags(self):
        """Returns tags as objects.

        Each tag object will contain name and url fields.
        """
        return [web.storage(name=t, url=self.key + "/tags/" + t) for t in self.tags]

    def add_seed(
        self, seed: ThingReferenceDict | AnnotatedSeedDict | SeedSubjectString
    ):
        """Adds a new seed to this list."""
        seed_object = Seed.from_json(self, seed)

        if self._index_of_seed(seed_object.key) >= 0:
            return False
        else:
            self.seeds = self.seeds or []
            self.seeds.append(seed_object.to_db())
            return True

    def remove_seed(
        self, seed: ThingReferenceDict | AnnotatedSeedDict | SeedSubjectString
    ):
        """Removes a seed for the list."""
        seed_key = Seed.from_json(self, seed).key
        if (index := self._index_of_seed(seed_key)) >= 0:
            self.seeds.pop(index)
            return True
        else:
            return False

    def _index_of_seed(self, seed_key: str) -> int:
        for i, s in enumerate(self._get_seed_strings()):
            if s == seed_key:
                return i
        return -1

    def __repr__(self):
        return f"<List: {self.key} ({self.name!r})>"

    def _get_seed_strings(self) -> list[SeedSubjectString | ThingKey]:
        return [seed.key for seed in self.get_seeds()]

    @cached_property
    def last_update(self):
        last_updates = [seed.last_update for seed in self.get_seeds()]
        last_updates = [x for x in last_updates if x]
        if last_updates:
            return max(last_updates)
        else:
            return None

    @property
    def seed_count(self):
        return len(self.seeds)

    def preview(self):
        """Return data to preview this list.

        Used in the API.
        """
        return {
            "url": self.key,
            "full_url": self.url(),
            "name": self.name or "",
            "seed_count": self.seed_count,
            "last_update": (self.last_update and self.last_update.isoformat()) or None,
        }

    def get_work_keys(self) -> Iterable[ThingKey]:
        """
        Gets the keys of the works in this list, or of the works of the editions in
        this list. May return duplicates.
        """
        return (
            (seed.document.works[0].key if seed.document.works else seed.key)
            for seed in self.get_seeds()
            if seed.key.startswith(('/books/', '/works/'))
        )

    def get_editions(self) -> Iterable[Edition]:
        """Returns the editions objects belonging to this list."""
        for seed in self.get_seeds():
            if (
                isinstance(seed.document, Thing)
                and seed.document.type.key == "/type/edition"
            ):
                yield cast(Edition, seed.document)

    def get_export_list(self) -> dict[str, list[dict]]:
        """Returns all the editions, works and authors of this list in arbitrary order.

        The return value is an iterator over all the entries. Each entry is a dictionary.

        This works even for lists with too many seeds as it doesn't try to
        return entries in the order of last-modified.
        """
        # Make one db call to fetch fully loaded Thing instances. By
        # default they are 'shell' instances that dynamically get fetched
        # as you access their attributes.
        things = cast(
            list[Thing],
            web.ctx.site.get_many(
                [seed.key for seed in self.get_seeds() if seed._type != "subject"]
            ),
        )

        # Create the return dictionary
        return {
            "editions": [
                thing.dict() for thing in things if isinstance(thing, Edition)
            ],
            "works": [thing.dict() for thing in things if isinstance(thing, Work)],
            "authors": [thing.dict() for thing in things if isinstance(thing, Author)],
        }

    def _preload(self, keys):
        keys = list(set(keys))
        return self._site.get_many(keys)

    def preload_works(self, editions):
        return self._preload(w.key for e in editions for w in e.get('works', []))

    def preload_authors(self, editions):
        works = self.preload_works(editions)
        return self._preload(
            a.author.key for w in works for a in w.get("authors", []) if "author" in a
        )

    def load_changesets(self, editions):
        """Adds "recent_changeset" to each edition.

        The recent_changeset will be of the form:
            {
                "id": "...",
                "author": {
                    "key": "..",
                    "displayname", "..."
                },
                "timestamp": "...",
                "ip": "...",
                "comment": "..."
            }
        """
        for e in editions:
            if "recent_changeset" not in e:
                with contextlib.suppress(IndexError):
                    e['recent_changeset'] = self._site.recentchanges(
                        {"key": e.key, "limit": 1}
                    )[0]

    def _get_solr_query_for_subjects(self):
        terms = [seed.get_solr_query_term() for seed in self.get_seeds()]
        return " OR ".join(t for t in terms if t)

    def _get_all_subjects(self):
        solr = get_solr()
        q = self._get_solr_query_for_subjects()

        # Solr has a maxBooleanClauses constraint there too many seeds, the
        if len(self.seeds) > 500:
            logger.warning(
                "More than 500 seeds. skipping solr query for finding subjects."
            )
            return []

        facet_names = ['subject_facet', 'place_facet', 'person_facet', 'time_facet']
        try:
            result = solr.select(
                q, fields=[], facets=facet_names, facet_limit=20, facet_mincount=1
            )
        except OSError:
            logger.error(
                "Error in finding subjects of list %s", self.key, exc_info=True
            )
            return []

        def get_subject_prefix(facet_name):
            name = facet_name.replace("_facet", "")
            if name == 'subject':
                return ''
            else:
                return name + ":"

        def process_subject(facet_name, title, count):
            prefix = get_subject_prefix(facet_name)
            key = prefix + title.lower().replace(" ", "_")
            url = "/subjects/" + key
            return web.storage(
                {"title": title, "name": title, "count": count, "key": key, "url": url}
            )

        def process_all():
            facets = result['facets']
            for k in facet_names:
                for f in facets.get(k, []):
                    yield process_subject(f.name, f.value, f.count)

        return sorted(process_all(), reverse=True, key=lambda s: s["count"])

    def get_subjects(self, limit=20):
        def get_subject_type(s):
            if s.url.startswith("/subjects/place:"):
                return "places"
            elif s.url.startswith("/subjects/person:"):
                return "people"
            elif s.url.startswith("/subjects/time:"):
                return "times"
            else:
                return "subjects"

        d = web.storage(subjects=[], places=[], people=[], times=[])

        for s in self._get_all_subjects():
            kind = get_subject_type(s)
            if len(d[kind]) < limit:
                d[kind].append(s)
        return d

    def get_seeds(self, sort=False, resolve_redirects=False) -> list['Seed']:
        seeds: list[Seed] = []
        for s in self.seeds:
            seed = Seed.from_db(self, s)
            max_checks = 10
            while resolve_redirects and seed.type == 'redirect' and max_checks:
                # Preserve notes when resolving redirects
                original_notes = seed.notes
                resolved_document = web.ctx.site.get(seed.document.location)
                if original_notes:
                    # Create AnnotatedSeed with both resolved document and original notes
                    seed = Seed(
                        self, {'thing': resolved_document, 'notes': original_notes}
                    )
                else:
                    seed = Seed(self, resolved_document)
                max_checks -= 1
            seeds.append(seed)

        if sort:
            seeds = h.safesort(seeds, reverse=True, key=lambda seed: seed.last_update)

        return seeds

    def has_seed(self, seed: ThingReferenceDict | SeedSubjectString) -> bool:
        if isinstance(seed, dict):
            seed = seed['key']
        return seed in self._get_seed_strings()

    # cache the default_cover_id for 60 seconds
    @cache.memoize(
        "memcache", key=lambda self: ("d" + self.key, "default-cover-id"), expires=60
    )
    def _get_default_cover_id(self):
        for s in self.get_seeds():
            cover = s.get_cover()
            if cover:
                return cover.id

    def get_default_cover(self):
        from openlibrary.core.models import Image  # noqa: PLC0415

        cover_id = self._get_default_cover_id()
        return Image(self._site, 'b', cover_id)

        # These functions cache and retrieve the 'my lists' section for mybooks.

    @cache.memoize(
        "memcache",
        key=lambda self: 'core.patron_lists.%s' % web.safestr(self.key),
        expires=60 * 10,
    )
    def get_patron_showcase(self, limit=3):
        return self._get_uncached_patron_showcase(limit=limit)

    def _get_uncached_patron_showcase(self, limit=3):
        title = self.name or "Unnamed List"
        n_covers = []
        seeds = self.get_seeds()
        for seed in seeds[:limit]:
            if cover := seed.get_cover():
                n_covers.append(cover.url("s"))
            else:
                n_covers.append(False)

        last_modified = self.last_update
        return {
            'title': title,
            'count': self.seed_count,
            'covers': n_covers,
            'last_mod': (
                last_modified.isoformat(sep=' ', timespec="minutes")
                if self.seed_count != 0
                else ""
            ),
        }


class Seed:
    """Seed of a list.

    Attributes:
        * last_update
        * type - "edition", "work" or "subject"
        * document - reference to the edition/work document
        * title
        * url
        * cover
    """

    key: ThingKey | SeedSubjectString

    value: Thing | SeedSubjectString

    notes: str | None = None

    def __init__(
        self,
        list: List,
        value: Thing | SeedSubjectString | AnnotatedSeed,
    ):
        self._list = list
        self._type = None

        if isinstance(value, str):
            self.key = value
            self.value = value
            self._type = "subject"
        elif isinstance(value, dict):
            # AnnotatedSeed
            self.key = value['thing'].key
            self.value = value['thing']
            self.notes = value['notes']
        else:
            self.key = value.key
            self.value = value

    @staticmethod
    def from_db(list: List, seed: Thing | SeedSubjectString) -> 'Seed':
        if isinstance(seed, str):
            return Seed(list, seed)
        # If there is a cache miss, `seed` is a client.Thing.
        # See https://github.com/internetarchive/openlibrary/issues/8882#issuecomment-1983844076
        elif isinstance(seed, Thing | client.Thing):
            if seed.key is None:
                return Seed(list, cast(AnnotatedSeed, seed._data))
            else:
                return Seed(list, seed)
        else:
            raise ValueError(f"Invalid seed: {seed!r}")

    @staticmethod
    def from_json(
        list: List,
        seed_json: SeedSubjectString | ThingReferenceDict | AnnotatedSeedDict,
    ):
        if isinstance(seed_json, dict):
            if 'thing' in seed_json:
                annotated_seed = cast(AnnotatedSeedDict, seed_json)  # Appease mypy

                return Seed(
                    list,
                    {
                        'thing': Thing(
                            list._site, annotated_seed['thing']['key'], None
                        ),
                        'notes': annotated_seed['notes'],
                    },
                )
            elif 'key' in seed_json:
                thing_ref = cast(ThingReferenceDict, seed_json)  # Appease mypy
                return Seed(
                    list,
                    {
                        'thing': Thing(list._site, thing_ref['key'], None),
                        'notes': '',
                    },
                )
        return Seed(list, seed_json)

    def to_db(self) -> Thing | SeedSubjectString:
        """
        Returns a db-compatible (I.e. Thing) representation of the seed.
        """
        if isinstance(self.value, str):
            return self.value
        if self.notes:
            return Thing(
                self._list._site,
                None,
                {
                    'thing': self.value,
                    'notes': self.notes,
                },
            )
        else:
            return self.value

    def to_json(self) -> SeedSubjectString | ThingReferenceDict | AnnotatedSeedDict:
        if isinstance(self.value, str):
            return self.value
        elif self.notes:
            return {
                'thing': {'key': self.key},
                'notes': self.notes,
            }
        else:
            return {'key': self.key}

    @cached_property
    def document(self) -> Subject | Thing:
        if isinstance(self.value, str):
            return get_subject(self.get_subject_url(self.value))
        else:
            return self.value

    def get_solr_query_term(self):
        if self.type == 'subject':
            typ, value = self.key.split(":", 1)
            # escaping value as it can have special chars like : etc.
            value = get_solr().escape(value)
            return f"{typ}_key:{value}"
        else:
            doc_basekey = self.document.key.split("/")[-1]
            if self.type == 'edition':
                return f"edition_key:{doc_basekey}"
            elif self.type == 'work':
                return f'key:/works/{doc_basekey}'
            elif self.type == 'author':
                return f"author_key:{doc_basekey}"
            else:
                logger.warning(
                    f"Cannot get solr query term for seed type {self.type}",
                    extra={'list': self._list.key, 'seed': self.key},
                )
                return None

    @cached_property
    def type(self) -> str:
        if self._type:
            return self._type
        key = self.document.type.key
        if key in ("/type/author", "/type/edition", "/type/redirect", "/type/work"):
            return key.split("/")[-1]
        return "unknown"

    @property
    def title(self) -> str:
        if self.type in ("work", "edition"):
            return self.document.title or self.key
        elif self.type == "author":
            return self.document.name or self.key
        elif self.type == "subject":
            return self.key.replace("_", " ")
        else:
            return self.key

    @property
    def url(self):
        if self.document:
            return self.document.url()
        elif self.key.startswith("subject:"):
            return "/subjects/" + web.lstrips(self.key, "subject:")
        else:
            return "/subjects/" + self.key

    def get_subject_url(self, subject: SeedSubjectString) -> str:
        if subject.startswith("subject:"):
            return "/subjects/" + web.lstrips(subject, "subject:")
        else:
            return "/subjects/" + subject

    def get_cover(self):
        if self.type in ['work', 'edition']:
            doc = cast(Work | Edition, self.document)
            return doc.get_cover()
        elif self.type == 'author':
            doc = cast(Author, self.document)
            return doc.get_photo()
        elif self.type == 'subject':
            doc = cast(Subject, self.document)
            return doc.get_default_cover()
        else:
            return None

    @cached_property
    def last_update(self):
        return self.document.get('last_modified')

    def dict(self):
        if self.type == "subject":
            url = self.url
            full_url = self.url
        else:
            url = self.key
            full_url = self.url

        d = {
            "url": url,
            "full_url": full_url,
            "type": self.type,
            "title": self.title,
            "last_update": (self.last_update and self.last_update.isoformat()) or None,
        }
        if cover := self.get_cover():
            d['picture'] = {"url": cover.url("S")}
        return d

    def __repr__(self):
        return f"<seed: {self.type} {self.key}>"

    __str__ = __repr__


class ListChangeset(Changeset):
    def get_added_seed(self):
        added = self.data.get("add")
        if added and len(added) == 1:
            return self.get_seed(added[0])

    def get_removed_seed(self):
        removed = self.data.get("remove")
        if removed and len(removed) == 1:
            return self.get_seed(removed[0])

    def get_list(self) -> List:
        return self.get_changes()[0]

    def get_seed(self, seed):
        """Returns the seed object."""
        if isinstance(seed, dict):
            seed = self._site.get(seed['key'])
        return Seed.from_db(self.get_list(), seed)


def register_models():
    client.register_thing_class('/type/list', List)
    client.register_changeset_class('lists', ListChangeset)
