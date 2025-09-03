import logging
import re
import sys
from collections import defaultdict
from functools import cached_property
from typing import cast

import web
from isbnlib import NotValidISBNError, canonical, mask

from infogami import config  # noqa: F401 side effects may be needed
from infogami.infobase import client
from infogami.utils import stats
from infogami.utils.view import safeint  # noqa: F401 side effects may be needed
from openlibrary.core import ia, lending, models
from openlibrary.core.models import Image
from openlibrary.plugins.upstream import (
    account,  # noqa: F401 side effects may be needed
    borrow,
)
from openlibrary.plugins.upstream.table_of_contents import TableOfContents
from openlibrary.plugins.upstream.utils import MultiDict, get_identifier_config
from openlibrary.plugins.worksearch.code import works_by_author
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils import dateutil  # noqa: F401 side effects may be needed
from openlibrary.utils.isbn import (
    isbn_10_to_isbn_13,
    isbn_13_to_isbn_10,
    normalize_isbn,
)
from openlibrary.utils.lccn import normalize_lccn


def follow_redirect(doc):
    if isinstance(doc, str) and doc.startswith("/a/"):
        # Some edition records have authors as ["/a/OL1A""] instead of [{"key": "/a/OL1A"}].
        # Hack to fix it temporarily.
        doc = web.ctx.site.get(doc.replace("/a/", "/authors/"))

    if doc and doc.type.key == "/type/redirect":
        key = doc.location
        return web.ctx.site.get(key)
    else:
        return doc


class Edition(models.Edition):
    def get_title(self):
        if self['title_prefix']:
            return self['title_prefix'] + ' ' + self['title']
        else:
            return self['title']

    def get_title_prefix(self):
        return ''

    # let title be title_prefix + title
    title = property(get_title)
    title_prefix = property(get_title_prefix)

    def get_authors(self):
        """Added to provide same interface for work and edition"""
        work_authors = self.works[0].get_authors() if self.works else []
        authors = [follow_redirect(a) for a in self.authors]
        authors = [a for a in authors if a and a.type.key == "/type/author"]
        return work_authors + authors

    def get_covers(self):
        """
        This methods excludes covers that are -1 or None, which are in the data
        but should not be.
        """
        return [Image(self._site, 'b', c) for c in self.covers if c and c > 0]

    def get_cover(self):
        covers = self.get_covers()
        return covers[0] if covers else None

    def get_cover_url(self, size):
        if cover := self.get_cover():
            return cover.url(size)
        elif self.ocaid:
            return self.get_ia_cover(self.ocaid, size)

    def get_cover_aspect_ratio(self) -> float | None:
        if cover := self.get_cover():
            return cover.get_aspect_ratio()
        return None

    def get_ia_cover(self, itemid, size):
        image_sizes = {"S": (116, 58), "M": (180, 360), "L": (500, 500)}
        w, h = image_sizes[size.upper()]
        return f"https://archive.org/download/{itemid}/page/cover_w{w}_h{h}.jpg"

    def get_isbn10(self):
        """Fetches either isbn_10 or isbn_13 from record and returns canonical
        isbn_10
        """
        isbn_10 = self.isbn_10 and canonical(self.isbn_10[0])
        if not isbn_10:
            isbn_13 = self.get_isbn13()
            return isbn_13 and isbn_13_to_isbn_10(isbn_13)
        return isbn_10

    def get_isbn13(self):
        """Fetches either isbn_13 or isbn_10 from record and returns canonical
        isbn_13
        """
        isbn_13 = self.isbn_13 and canonical(self.isbn_13[0])
        if not isbn_13:
            isbn_10 = self.isbn_10 and self.isbn_10[0]
            return isbn_10 and isbn_10_to_isbn_13(isbn_10)
        return isbn_13

    def get_worldcat_url(self):
        url = 'https://search.worldcat.org/'
        if self.get('oclc_numbers'):
            return f'{url}/title/{self.oclc_numbers[0]}'
        elif self.get_isbn13():
            # Handles both isbn13 & 10
            return f'{url}/isbn/{self.get_isbn13()}'
        return f'{url}/search?q={self.title}'

    def get_isbnmask(self):
        """Returns a masked (hyphenated) ISBN if possible."""
        isbns = self.get('isbn_13', []) + self.get('isbn_10', [None])
        if isbn := normalize_isbn(isbns[0]):
            try:
                isbn = mask(isbns[0])
            except NotValidISBNError:
                return isbn
        return isbn

    def get_identifiers(self):
        """Returns (name, value) pairs of all available identifiers."""
        names = ['ocaid', 'isbn_10', 'isbn_13', 'lccn', 'oclc_numbers']
        return self._process_identifiers(
            get_identifier_config('edition').identifiers, names, self.identifiers
        )

    def get_ia_meta_fields(self):
        # Check for cached value
        # $$$ we haven't assigned _ia_meta_fields the first time around but there's apparently
        #     some magic that lets us check this way (and breaks using hasattr to check if defined)
        if self._ia_meta_fields:
            return self._ia_meta_fields

        if not self.get('ocaid', None):
            meta = {}
        else:
            meta = ia.get_metadata(self.ocaid)
            meta.setdefault('external-identifier', [])
            meta.setdefault('collection', [])

        self._ia_meta_fields = meta
        return self._ia_meta_fields

    def is_daisy_encrypted(self):
        meta_fields = self.get_ia_meta_fields()
        if not meta_fields:
            return
        v = meta_fields['collection']
        return 'printdisabled' in v

    def get_lending_resources(self):
        """Returns the loan resource identifiers (in meta.xml format for ACS4 resources) for books hosted on archive.org

        Returns e.g. ['bookreader:lettertoannewarr00west',
                      'acs:epub:urn:uuid:0df6f344-7ce9-4038-885e-e02db34f2891',
                      'acs:pdf:urn:uuid:7f192e62-13f5-4a62-af48-be4bea67e109']
        """

        # The entries in meta.xml look like this:
        # <external-identifier>
        #     acs:epub:urn:uuid:0df6f344-7ce9-4038-885e-e02db34f2891
        # </external-identifier>

        if not self.ocaid:
            return []
        return self.get_ia_meta_fields()['external-identifier']

    def get_lending_resource_id(self, type):
        if type == 'bookreader':
            desired = 'bookreader:'
        else:
            desired = 'acs:%s:' % type

        for urn in self.get_lending_resources():
            if urn.startswith(desired):
                # Got a match
                # $$$ a little icky - prune the acs:type if present
                if urn.startswith('acs:'):
                    urn = urn[len(desired) :]

                return urn

        return None

    def get_current_and_available_loans(self):
        current_loans = borrow.get_edition_loans(self)
        current_and_available_loans = (
            current_loans,
            self._get_available_loans(current_loans),
        )
        return current_and_available_loans

    def get_current_loans(self):
        return borrow.get_edition_loans(self)

    def get_available_loans(self):
        """
        Get the resource types currently available to be loaned out for this edition.  Does NOT
        take into account the user's status (e.g. number of books out, in-library status, etc).
        This is like checking if this book is on the shelf.

        Returns [{'resource_id': uuid, 'resource_type': type, 'size': bytes}]

        size may be None"""
        # no ebook
        if not self.ocaid:
            return []

        # already checked out
        if lending.is_loaned_out(self.ocaid):
            return []

        # find available loans. there are no current loans
        return self._get_available_loans([])

    def _get_available_loans(self, current_loans):
        default_type = 'bookreader'

        loans = []

        # Check if we have a possible loan - may not yet be fulfilled in ACS4
        if current_loans:
            # There is a current loan or offer
            return []

        # Create list of possible loan formats
        resource_pattern = r'acs:(\w+):(.*)'
        for resource_urn in self.get_lending_resources():
            if resource_urn.startswith('acs:'):
                (type, resource_id) = re.match(resource_pattern, resource_urn).groups()
                loans.append(
                    {'resource_id': resource_id, 'resource_type': type, 'size': None}
                )
            elif resource_urn.startswith('bookreader'):
                loans.append(
                    {
                        'resource_id': resource_urn,
                        'resource_type': 'bookreader',
                        'size': None,
                    }
                )

        # Put default type at start of list, then sort by type name
        def loan_key(loan):
            if loan['resource_type'] == default_type:
                return '1-%s' % loan['resource_type']
            else:
                return '2-%s' % loan['resource_type']

        loans = sorted(loans, key=loan_key)

        # For each possible loan, check if it is available We
        # shouldn't be out of sync (we already checked
        # get_edition_loans for current loans) but we fail safe, for
        # example the book may have been borrowed in a dev instance
        # against the live ACS4 server
        for loan in loans:
            if borrow.is_loaned_out(loan['resource_id']):
                # Only a single loan of an item is allowed
                # $$$ log out of sync state
                return []

        return loans

    def update_loan_status(self):
        """Update the loan status"""
        if self.ocaid:
            lending.sync_loan(self.ocaid)

    def _process_identifiers(self, config_, names, values):
        id_map = {}
        for id in config_:
            id_map[id.name] = id
            id.setdefault("label", id.name)
            id.setdefault("url_format", None)

        d = MultiDict()

        def process(name, value):
            if value:
                if not isinstance(value, list):
                    value = [value]

                id = id_map.get(name) or web.storage(
                    name=name, label=name, url_format=None
                )
                for v in value:
                    d[id.name] = web.storage(
                        name=id.name,
                        label=id.label,
                        value=v,
                        url=id.get('url') and id.url.replace('@@@', v.replace(' ', '')),
                    )

        for name in names:
            process(name, self[name])

        for name in values:
            process(name, values[name])

        return d

    def set_identifiers(self, identifiers):
        """Updates the edition from identifiers specified as (name, value) pairs."""
        names = (
            'isbn_10',
            'isbn_13',
            'lccn',
            'oclc_numbers',
            'ocaid',
            'dewey_decimal_class',
            'lc_classifications',
        )

        d = {}
        for id in identifiers:
            # ignore bad values
            if 'name' not in id or 'value' not in id:
                continue
            name, value = id['name'], id['value']
            if name == 'lccn':
                value = normalize_lccn(value)
            # `None` in this field causes errors. See #7999.
            if value is not None:
                d.setdefault(name, []).append(value)

        # clear existing value first
        for name in names:
            self._getdata().pop(name, None)

        self.identifiers = {}

        for name, value in d.items():
            # ocaid is not a list
            if name == 'ocaid':
                self.ocaid = value[0]
            elif name in names:
                self[name] = value
            else:
                self.identifiers[name] = value

        if not d.items():
            self.identifiers = None

    def get_classifications(self):
        names = ["dewey_decimal_class", "lc_classifications"]
        return self._process_identifiers(
            get_identifier_config('edition').classifications,
            names,
            self.classifications,
        )

    def set_classifications(self, classifications):
        names = ["dewey_decimal_class", "lc_classifications"]
        d = defaultdict(list)
        for c in classifications:
            if (
                'name' not in c
                or 'value' not in c
                or not web.re_compile("[a-z0-9_]*").match(c['name'])
            ):
                continue
            d[c['name']].append(c['value'])

        for name in names:
            self._getdata().pop(name, None)
        self.classifications = {}

        for name, value in d.items():
            if name in names:
                self[name] = value
            else:
                self.classifications[name] = value

        if not self.classifications.items():
            self.classifications = None

    def get_weight(self):
        """returns weight as a storage object with value and units fields."""
        w = self.weight
        return w and UnitParser(["value"]).parse(w)

    def set_weight(self, w):
        self.weight = w and UnitParser(["value"]).format(w)

    def get_physical_dimensions(self):
        d = self.physical_dimensions
        return d and UnitParser(["height", "width", "depth"]).parse(d)

    def set_physical_dimensions(self, d):
        # don't overwrite physical dimensions if nothing was passed in - there
        # may be dimensions in the database that don't conform to the d x d x d format
        if d:
            self.physical_dimensions = UnitParser(["height", "width", "depth"]).format(
                d
            )

    def get_toc_text(self) -> str:
        if toc := self.get_table_of_contents():
            return toc.to_markdown()
        return ""

    def get_table_of_contents(self) -> TableOfContents | None:
        if not self.table_of_contents:
            return None

        return TableOfContents.from_db(self.table_of_contents)

    def set_toc_text(self, text: str | None):
        if text:
            self.table_of_contents = TableOfContents.from_markdown(text).to_db()
        else:
            self.table_of_contents = None

    def get_links(self):
        links1 = [
            web.storage(url=url, title=title)
            for url, title in zip(self.uris, self.uri_descriptions)
        ]
        links2 = list(self.links)
        return links1 + links2

    def get_olid(self):
        return self.key.split('/')[-1]

    @property
    def wp_citation_fields(self):
        """
        Builds a Wikipedia book citation as defined by https://en.wikipedia.org/wiki/Template:Cite_book
        """
        citation = {}
        authors = [ar.author for ar in self.works[0].authors]
        if len(authors) == 1:
            citation['author'] = authors[0].name
        else:
            for i, a in enumerate(authors, 1):
                citation[f'author{i}'] = a.name

        citation.update(
            {
                'date': self.get('publish_date'),
                'orig-date': self.works[0].get('first_publish_date'),
                'title': self.title.replace("[", "&#91").replace("]", "&#93"),
                'url': (
                    f'https://archive.org/details/{self.ocaid}' if self.ocaid else None
                ),
                'publication-place': self.get('publish_places', [None])[0],
                'publisher': self.get('publishers', [None])[0],
                'isbn': self.get_isbnmask(),
                'issn': self.get('identifiers', {}).get('issn', [None])[0],
            }
        )

        if self.lccn and (lccn := normalize_lccn(self.lccn[0])):
            citation['lccn'] = lccn
        if self.get('oclc_numbers'):
            citation['oclc'] = self.oclc_numbers[0]
        citation['ol'] = str(self.get_olid())[2:]
        # TODO: add 'ol-access': 'free' if the item is free to read.
        if citation['date'] == citation['orig-date']:
            citation.pop('orig-date')
        return citation

    def is_fake_record(self):
        """Returns True if this is a record is not a real record from database,
        but created on the fly.

        The /books/ia:foo00bar records are not stored in the database, but
        created at runtime using the data from archive.org metadata API.
        """
        return "/ia:" in self.key

    def set_provider_data(self, data):
        if not self.providers:
            self.providers = []
        self.providers.append(data)

    def set_providers(self, providers):
        self.providers = providers


class Author(models.Author):
    def get_photos(self):
        return [Image(self._site, "a", id) for id in self.photos if id > 0]

    def get_photo(self):
        photos = self.get_photos()
        return photos[0] if photos else None

    def get_photo_url(self, size):
        photo = self.get_photo()
        return photo and photo.url(size)

    def get_photo_aspect_ratio(self) -> float | None:
        if photo := self.get_photo():
            return photo.get_aspect_ratio()
        return None

    def get_olid(self):
        return self.key.split('/')[-1]

    def get_books(self, q=''):
        i = web.input(sort='editions', page=1, rows=20, mode="")
        try:
            # safeguard from passing zero/negative offsets to solr
            page = max(1, int(i.page))
        except ValueError:
            page = 1
        return works_by_author(
            self.get_olid(),
            sort=i.sort,
            page=page,
            rows=i.rows,
            has_fulltext=i.mode == "ebooks",
            query=q,
            facet=True,
        )

    def get_work_count(self):
        """Returns the number of works by this author."""
        # TODO: avoid duplicate works_by_author calls
        result = works_by_author(self.get_olid(), rows=0)
        return result.num_found

    def as_fake_solr_record(self):
        record = {
            'key': self.key,
            'name': self.name,
            'top_subjects': [],
            'work_count': 0,
            'type': 'author',
        }
        if self.death_date:
            record['death_date'] = self.death_date
        if self.birth_date:
            record['birth_date'] = self.birth_date
        return record


re_year = re.compile(r'(\d{4})$')


class Work(models.Work):
    def get_olid(self):
        return self.key.split('/')[-1]

    def get_covers(self, use_solr=True) -> list[Image]:
        if self.covers:
            return [Image(self._site, "w", id) for id in self.covers if id > 0]
        elif use_solr:
            return self.get_covers_from_solr()
        else:
            return []

    def get_covers_from_solr(self) -> list[Image]:
        try:
            w = self._solr_data
        except Exception:
            logging.getLogger("openlibrary").exception(
                'Unable to retrieve covers from solr'
            )
            return []
        if w:
            if 'cover_id' in w:
                return [Image(self._site, "w", int(w['cover_id']))]
            elif 'cover_edition_key' in w:
                cover_edition = cast(
                    Edition, web.ctx.site.get("/books/" + w['cover_edition_key'])
                )
                cover = cover_edition and cover_edition.get_cover()
                if cover:
                    return [cover]
        return []

    @cached_property
    def _solr_data(self):
        from openlibrary.book_providers import get_solr_keys  # noqa: PLC0415

        fields = [
            "key",
            "cover_edition_key",
            "cover_id",
            "edition_key",
            "first_publish_year",
            "has_fulltext",
            "lending_edition_s",
            "public_scan_b",
        ] + get_solr_keys()
        solr = get_solr()
        stats.begin("solr", get=self.key, fields=fields)
        try:
            return solr.get(self.key, fields=fields)
        except Exception:
            logging.getLogger("openlibrary").exception("Failed to get solr data")
            return None
        finally:
            stats.end()

    def get_cover(self, use_solr=True):
        covers = self.get_covers(use_solr=use_solr)
        return covers[0] if covers else None

    def get_cover_url(self, size, use_solr=True):
        cover = self.get_cover(use_solr=use_solr)
        return cover and cover.url(size)

    def get_author_names(self, blacklist=None):
        author_names = []
        for author in self.get_authors():
            author_name = author if isinstance(author, str) else author.name
            if not blacklist or author_name.lower() not in blacklist:
                author_names.append(author_name)
        return author_names

    def get_authors(self):
        authors = [a.author for a in self.authors]
        authors = [follow_redirect(a) for a in authors]
        authors = [a for a in authors if a and a.type.key == "/type/author"]
        return authors

    def get_subjects(self):
        """Return subject strings."""
        subjects = self.subjects

        def flip(name):
            if name.count(",") == 1:
                a, b = name.split(",")
                return b.strip() + " " + a.strip()
            return name

        if subjects and not isinstance(subjects[0], str):
            subjects = [flip(s.name) for s in subjects]
        return subjects

    @staticmethod
    def filter_problematic_subjects(subjects, filter_unicode=True):
        def is_ascii(s):
            try:
                return s.isascii()
            except AttributeError:
                return all(ord(c) < 128 for c in s)

        blacklist = [
            'accessible_book',
            'protected_daisy',
            'in_library',
            'overdrive',
            'large_type_books',
            'internet_archive_wishlist',
            'fiction',
            'popular_print_disabled_books',
            'fiction_in_english',
            'open_library_staff_picks',
            'inlibrary',
            'printdisabled',
            'browserlending',
            'biographies',
            'open_syllabus_project',
            'history',
            'long_now_manual_for_civilization',
            'Popular works',
        ]
        blacklist_chars = ['(', ',', '\'', ':', '&', '-', '.']
        ok_subjects = []
        for subject in subjects:
            _subject = subject.lower().replace(' ', '_')
            subject = subject.replace('_', ' ')
            if (
                _subject not in blacklist
                and (
                    not filter_unicode
                    or (subject.replace(' ', '').isalnum() and is_ascii(subject))
                )
                and all(char not in subject for char in blacklist_chars)
            ):
                ok_subjects.append(subject)
        return ok_subjects

    def get_related_books_subjects(self, filter_unicode=True):
        return self.filter_problematic_subjects(self.get_subjects(), filter_unicode)

    def get_sorted_editions(
        self,
        ebooks_only: bool = False,
        limit: int | None = None,
        keys: list[str] | None = None,
    ) -> list[Edition]:
        """
        Get this work's editions sorted by publication year
        :param list[str] keys: ensure keys included in fetched editions
        """
        db_query = {"type": "/type/edition", "works": self.key}
        db_query['limit'] = limit or 10000  # type: ignore[assignment]

        edition_keys = []
        if ebooks_only:
            if self._solr_data:
                from openlibrary.book_providers import (  # noqa: PLC0415
                    get_book_providers,
                )

                # Always use solr data whether it's up to date or not
                # to determine which providers this book has
                # We only make additional queries when a
                # trusted book provider identifier is present
                for provider in get_book_providers(self._solr_data):
                    query = {**db_query, **provider.editions_query}
                    edition_keys += web.ctx.site.things(query)
            else:
                db_query["ocaid~"] = "*"

        if not edition_keys:
            solr_is_up_to_date = (
                self._solr_data
                and self._solr_data.get('edition_key')
                and len(self._solr_data.get('edition_key')) == self.edition_count
            )
            if solr_is_up_to_date:
                edition_keys += [
                    "/books/" + olid for olid in self._solr_data.get('edition_key')
                ]
            else:
                # given librarians are probably doing this, show all editions
                edition_keys += web.ctx.site.things(db_query)

        edition_keys.extend(keys or [])
        editions = web.ctx.site.get_many(list(set(edition_keys)))
        editions.sort(
            key=lambda ed: ed.get_publish_year() or -sys.maxsize, reverse=True
        )

        # 2022-03 Once we know the availability-type of editions (e.g. open)
        # via editions-search, we can sidestep get_availability to only
        # check availability for borrowable editions
        ocaids = [ed.ocaid for ed in editions if ed.ocaid]
        availability = lending.get_availability('identifier', ocaids)
        for ed in editions:
            ed.availability = availability.get(ed.ocaid) or {"status": "error"}

        return editions

    def has_ebook(self):
        w = self._solr_data or {}
        return w.get("has_fulltext", False)

    first_publish_year = property(
        lambda self: self._solr_data.get("first_publish_year")
    )

    def get_edition_covers(self):
        editions = web.ctx.site.get_many(
            web.ctx.site.things(
                {"type": "/type/edition", "works": self.key, "limit": 1000}
            )
        )
        existing = {int(c.id) for c in self.get_covers()}
        covers = [e.get_cover() for e in editions]
        return [c for c in covers if c and int(c.id) not in existing]

    def as_fake_solr_record(self):
        record = {
            'key': self.key,
            'title': self.get('title'),
        }
        if self.subtitle:
            record['subtitle'] = self.subtitle
        return record

    def get_identifiers(self):
        """Returns (name, value) pairs of all available identifiers."""
        names = []
        return self._process_identifiers(
            get_identifier_config('work').identifiers, names, self.identifiers
        )

    def set_identifiers(self, identifiers):
        """Updates the work from identifiers specified as (name, value) pairs."""

        d = {}
        if identifiers:
            for id in identifiers:
                if 'name' not in id or 'value' not in id:
                    continue
                name, value = id['name'], id['value']
                if value is not None:
                    d.setdefault(name, []).append(value)

        self.identifiers = {}

        for name, value in d.items():
            self.identifiers[name] = value

        if not d.items():
            self.identifiers = None

    def _process_identifiers(self, config_, names, values):
        id_map = {}
        for id in config_:
            id_map[id.name] = id
            id.setdefault("label", id.name)
            id.setdefault("url_format", None)

        d = MultiDict()

        def process(name, value):
            if value:
                if not isinstance(value, list):
                    value = [value]

                id = id_map.get(name) or web.storage(
                    name=name, label=name, url_format=None
                )
                for v in value:
                    d[id.name] = web.storage(
                        name=id.name,
                        label=id.label,
                        value=v,
                        url=id.get('url') and id.url.replace('@@@', v.replace(' ', '')),
                    )

        for name in names:
            process(name, self[name])

        for name in values:
            process(name, values[name])

        return d


class Subject(client.Thing):
    pass


class SubjectPlace(Subject):
    pass


class SubjectPerson(Subject):
    pass


class User(models.User):
    displayname: str | None

    def get_name(self) -> str:
        return self.displayname or self.key.split('/')[-1]

    name = property(get_name)

    def get_edit_history(self, limit: int = 10, offset: int = 0):
        return web.ctx.site.versions(
            {"author": self.key, "limit": limit, "offset": offset}
        )

    def get_users_settings(self):
        settings = web.ctx.site.get('%s/preferences' % self.key)
        return settings.dict().get('notifications') if settings else {}

    def get_creation_info(self):
        if web.ctx.path.startswith("/admin"):
            d = web.ctx.site.versions(
                {'key': self.key, "sort": "-created", "limit": 1}
            )[0]
            return web.storage({"ip": d.ip, "member_since": d.created})

    def get_edit_count(self) -> int:
        if web.ctx.path.startswith("/admin"):
            return web.ctx.site._request('/count_edits_by_user', data={"key": self.key})
        else:
            return 0

    def get_loan_count(self) -> int:
        return len(borrow.get_loans(self))

    def get_loans(self):
        self.update_loan_status()
        return lending.get_loans_of_user(self.key)

    def update_loan_status(self):
        """Update the status of this user's loans."""
        loans = lending.get_loans_of_user(self.key)
        for loan in loans:
            lending.sync_loan(loan['ocaid'])

    def get_safe_mode(self):
        return (self.get_users_settings() or {}).get('safe_mode', "").lower()


class UnitParser:
    """Parsers values like dimensions and weight.

    >>> p = UnitParser(["height", "width", "depth"])
    >>> parsed = p.parse("9 x 3 x 2 inches")
    >>> isinstance(parsed, web.utils.Storage)
    True
    >>> sorted(parsed.items())
    [('depth', '2'), ('height', '9'), ('units', 'inches'), ('width', '3')]
    >>> p.format({"height": "9", "width": 3, "depth": 2, "units": "inches"})
    '9 x 3 x 2 inches'
    """

    def __init__(self, fields):
        self.fields = fields

    def format(self, d):
        return (
            " x ".join(str(d.get(k, '')) for k in self.fields)
            + ' '
            + d.get('units', '')
        )

    def parse(self, s):
        """Parse the string and return storage object with specified fields and units."""
        pattern = "^" + " *x *".join("([0-9.]*)" for f in self.fields) + " *(.*)$"
        rx = web.re_compile(pattern)
        m = rx.match(s)
        return m and web.storage(zip(self.fields + ["units"], m.groups()))


class Changeset(client.Changeset):
    def can_undo(self):
        return False

    def _get_doc(self, key, revision):
        if revision == 0:
            return {"key": key, "type": {"key": "/type/delete"}}
        else:
            d = web.ctx.site.get(key, revision).dict()
            return d

    def process_docs_before_undo(self, docs):
        """Hook to process docs before saving for undo.

        This is called by _undo method to allow subclasses to check
        for validity or redirects so that undo doesn't fail.

        The subclasses may overwrite this as required.
        """
        return docs

    def _undo(self):
        """Undo this transaction."""
        docs = [self._get_doc(c['key'], c['revision'] - 1) for c in self.changes]
        docs = self.process_docs_before_undo(docs)

        data = {"parent_changeset": self.id}
        comment = 'undo ' + self.comment
        return web.ctx.site.save_many(docs, action="undo", data=data, comment=comment)

    def get_undo_changeset(self):
        """Returns the changeset that undone this transaction if one exists, None otherwise."""
        try:
            return self._undo_changeset
        except AttributeError:
            pass

        changesets = web.ctx.site.recentchanges(
            {"kind": "undo", "data": {"parent_changeset": self.id}}
        )
        # return the first undo changeset
        self._undo_changeset = (changesets and changesets[-1]) or None
        return self._undo_changeset


class NewAccountChangeset(Changeset):
    def get_user(self):
        keys = [c.key for c in self.get_changes()]
        user_key = "/people/" + keys[0].split("/")[2]
        return web.ctx.site.get(user_key)


class MergeAuthors(Changeset):
    def can_undo(self):
        return self.get_undo_changeset() is None

    def get_master(self):
        master = self.data.get("master")
        return master and web.ctx.site.get(master, lazy=True)

    def get_duplicates(self):
        duplicates = self.data.get("duplicates")
        changes = {c['key']: c['revision'] for c in self.changes}

        return duplicates and [
            web.ctx.site.get(key, revision=changes[key] - 1, lazy=True)
            for key in duplicates
            if key in changes
        ]


class MergeWorks(Changeset):
    def can_undo(self):
        return self.get_undo_changeset() is None

    def get_master(self):
        master = self.data.get("master")
        return master and web.ctx.site.get(master, lazy=True)

    def get_duplicates(self):
        duplicates = self.data.get("duplicates")
        changes = {c['key']: c['revision'] for c in self.changes}

        return duplicates and [
            web.ctx.site.get(key, revision=changes[key] - 1, lazy=True)
            for key in duplicates
            if key in changes
        ]


class Undo(Changeset):
    def can_undo(self):
        return False

    def get_undo_of(self):
        undo_of = self.data['undo_of']
        return web.ctx.site.get_change(undo_of)

    def get_parent_changeset(self):
        parent = self.data['parent_changeset']
        return web.ctx.site.get_change(parent)


class AddBookChangeset(Changeset):
    def get_work(self):
        book = self.get_edition()
        return (book and book.works and book.works[0]) or None

    def get_edition(self):
        for doc in self.get_changes():
            if doc.key.startswith("/books/"):
                return doc

    def get_author(self):
        for doc in self.get_changes():
            if doc.key.startswith("/authors/"):
                return doc


class Tag(models.Tag):
    """Class to represent /type/tag objects in Open Library."""

    pass


def setup():
    models.register_models()

    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/work', Work)

    client.register_thing_class('/type/subject', Subject)
    client.register_thing_class('/type/place', SubjectPlace)
    client.register_thing_class('/type/person', SubjectPerson)
    client.register_thing_class('/type/user', User)
    client.register_thing_class('/type/tag', Tag)

    client.register_changeset_class(None, Changeset)  # set the default class
    client.register_changeset_class('merge-authors', MergeAuthors)
    client.register_changeset_class('merge-works', MergeWorks)
    client.register_changeset_class('undo', Undo)

    client.register_changeset_class('add-book', AddBookChangeset)
    client.register_changeset_class('new-account', NewAccountChangeset)
