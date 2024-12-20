"""Handlers for adding and editing books."""

import csv
import datetime
import io
import json
import logging
import urllib
from typing import Literal, NoReturn, overload

import web
from web.webapi import SeeOther

from infogami import config
from infogami.core.db import ValidationException
from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import add_flash_message, safeint
from openlibrary import accounts
from openlibrary.core.helpers import uniq
from openlibrary.i18n import gettext as _  # noqa: F401 side effects may be needed
from openlibrary.plugins.recaptcha import recaptcha
from openlibrary.plugins.upstream import spamcheck, utils
from openlibrary.plugins.upstream.account import as_admin
from openlibrary.plugins.upstream.models import Author, Edition, Work
from openlibrary.plugins.upstream.utils import fuzzy_find, render_template
from openlibrary.plugins.worksearch.search import get_solr

logger = logging.getLogger("openlibrary.book")


def get_recaptcha():
    def recaptcha_exempt() -> bool:
        """Check to see if account is an admin, or more than two years old."""
        user = web.ctx.site.get_user()
        account = user and user.get_account()

        if not (user and account):
            return False

        if account.has_tag("trusted-user") or user.is_admin() or user.is_librarian():
            return True

        create_dt = account.creation_time()
        now_dt = datetime.datetime.utcnow()
        delta = now_dt - create_dt
        return delta.days > 30

    def is_plugin_enabled(name) -> bool:
        plugin_names = delegate.get_plugins()
        return name in plugin_names or "openlibrary.plugins." + name in plugin_names

    if is_plugin_enabled('recaptcha') and not recaptcha_exempt():
        public_key = config.plugin_recaptcha.public_key
        private_key = config.plugin_recaptcha.private_key
        return recaptcha.Recaptcha(public_key, private_key)
    else:
        return None


def make_author(key: str, name: str) -> Author:
    """
    Use author_key and author_name and return an Author.

    >>> make_author("OL123A", "Samuel Clemens")
    <Author: '/authors/OL123A'>
    """
    key = "/authors/" + key
    return web.ctx.site.new(
        key, {"key": key, "type": {"key": "/type/author"}, "name": name}
    )


def make_work(doc: dict[str, str | list]) -> web.Storage:
    """
    Take a dictionary and make it a work of web.Storage format. This is used as a
    wrapper for results from solr.select() when adding books from /books/add and
    checking for existing works or editions.
    """

    w = web.storage(doc)

    w.authors = [
        make_author(key, name)
        for key, name in zip(doc.get('author_key', []), doc.get('author_name', []))
    ]

    w.cover_url = "/images/icons/avatar_book-sm.png"
    w.setdefault('ia', [])
    w.setdefault('first_publish_year', None)
    return w


@overload
def new_doc(type_: Literal["/type/author"], **data) -> Author: ...


@overload
def new_doc(type_: Literal["/type/edition"], **data) -> Edition: ...


@overload
def new_doc(type_: Literal["/type/work"], **data) -> Work: ...


def new_doc(type_: str, **data) -> Author | Edition | Work:
    """
    Create an new OL doc item.
    :param str type_: object type e.g. /type/edition
    :return: the newly created document
    """
    key = web.ctx.site.new_key(type_)
    data['key'] = key
    data['type'] = {"key": type_}
    return web.ctx.site.new(key, data)


class DocSaveHelper:
    """Simple utility to collect the saves and save them together at the end."""

    def __init__(self):
        self.docs = []

    def save(self, doc) -> None:
        """Adds the doc to the list of docs to be saved."""
        if not isinstance(doc, dict):  # thing
            doc = doc.dict()
        self.docs.append(doc)

    def commit(self, **kw) -> None:
        """Saves all the collected docs."""
        if self.docs:
            web.ctx.site.save_many(self.docs, **kw)

    def create_authors_from_form_data(
        self, authors: list[dict], author_names: list[str], _test: bool = False
    ) -> bool:
        """
        Create any __new__ authors in the provided array. Updates the authors
        dicts _in place_ with the new key.
        :param list[dict] authors: e.g. [{author: {key: '__new__'}}]
        :return: Whether new author(s) were created
        """
        created = False
        for author_dict, author_name in zip(authors, author_names):
            if author_dict['author']['key'] == '__new__':
                created = True
                if not _test:
                    doc = new_doc('/type/author', name=author_name)
                    self.save(doc)
                    author_dict['author']['key'] = doc.key
        return created


def encode_url_path(url: str) -> str:
    """Encodes the path part of the url to avoid issues with non-latin characters as
    non-latin characters was breaking `web.seeother`.

    >>> encode_url_path('/books/OL10M/Вас_ил/edit?mode=add-work')
    '/books/OL10M/%D0%92%D0%B0%D1%81_%D0%B8%D0%BB/edit?mode=add-work'
    >>> encode_url_path('')
    ''
    >>> encode_url_path('/')
    '/'
    >>> encode_url_path('/books/OL11M/进入该海域?mode=add-work')
    '/books/OL11M/%E8%BF%9B%E5%85%A5%E8%AF%A5%E6%B5%B7%E5%9F%9F?mode=add-work'
    """  # noqa: RUF002
    result = urllib.parse.urlparse(url)
    correct_path = "/".join(urllib.parse.quote(part) for part in result.path.split("/"))
    result = result._replace(path=correct_path)
    return result.geturl()


def safe_seeother(url: str) -> SeeOther:
    """Safe version of `web.seeother` which encodes the url path appropriately using
    `encode_url_path`."""
    return web.seeother(encode_url_path(url))


class addbook(delegate.page):
    path = "/books/add"

    def GET(self):
        """Main user interface for adding a book to Open Library."""

        if not self.has_permission():
            return safe_seeother(f"/account/login?redirect={self.path}")

        i = web.input(work=None, author=None)
        work = i.work and web.ctx.site.get(i.work)
        author = i.author and web.ctx.site.get(i.author)

        # pre-filling existing author(s) if adding new edition from existing work page
        authors = (work and work.authors) or []
        if work and authors:
            authors = [a.author for a in authors]
        # pre-filling existing author if adding new work from author page
        if author and author not in authors:
            authors.append(author)

        return render_template(
            'books/add', work=work, authors=authors, recaptcha=get_recaptcha()
        )

    def has_permission(self) -> bool:
        """
        Can a book be added?
        """
        return web.ctx.site.can_write("/books/add")

    def POST(self):
        i = web.input(
            title="",
            book_title="",
            publisher="",
            publish_date="",
            id_name="",
            id_value="",
            web_book_url="",
            _test="false",
        )
        i.title = i.book_title

        if spamcheck.is_spam(i, allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )

        if not web.ctx.site.get_user():
            recap = get_recaptcha()
            if recap and not recap.validate():
                return render_template(
                    'message.html',
                    'Recaptcha solution was incorrect',
                    'Please <a href="javascript:history.back()">go back</a> and try again.',
                )

        i = utils.unflatten(i)
        saveutil = DocSaveHelper()
        created_author = saveutil.create_authors_from_form_data(
            i.authors, i.author_names, _test=i._test == 'true'
        )
        match = None if created_author else self.find_matches(i)

        if i._test == 'true' and not isinstance(match, list):
            if match:
                return f'Matched <a href="{match.key}">{match.key}</a>'
            else:
                return 'No match found'

        if isinstance(match, list):
            # multiple matches
            return render_template('books/check', i, match)

        elif match and match.key.startswith('/books'):
            # work match and edition match, match is an Edition
            if i.web_book_url:
                match.provider = [{"url": i.web_book_url, "format": "web"}]
            return self.work_edition_match(match)

        elif match and match.key.startswith('/works'):
            # work match but not edition
            work = match
            return self.work_match(saveutil, work, i)
        else:
            # no match
            return self.no_match(saveutil, i)

    def find_matches(
        self, i: web.utils.Storage
    ) -> None | Work | Edition | list[web.utils.Storage]:
        """
        Tries to find an edition, or work, or multiple work candidates that match the
        given input data.

        Case#1: No match. None is returned.
        Case#2: Work match but not edition. Work is returned.
        Case#3: Work match and edition match. Edition is returned
        Case#4: Multiple work match. List of works is returned.

        :param web.utils.Storage i: addbook user supplied formdata
        :return: None or Work or Edition or list of Works (as Storage objects) that are
                 likely matches.
        """

        i.publish_year = i.publish_date and self.extract_year(i.publish_date)
        author_key = i.authors and i.authors[0].author.key

        # work is set from the templates/books/check.html page.
        work_key = i.get('work')

        # work_key is set to none-of-these when user selects none-of-these link.
        if work_key == 'none-of-these':
            return None  # Case 1, from check page

        work = work_key and web.ctx.site.get(work_key)
        if work:
            edition = self.try_edition_match(
                work=work,
                publisher=i.publisher,
                publish_year=i.publish_year,
                id_name=i.id_name,
                id_value=i.id_value,
            )
            return edition or work  # Case 3 or 2, from check page

        edition = self.try_edition_match(
            title=i.title,
            author_key=author_key,
            publisher=i.publisher,
            publish_year=i.publish_year,
            id_name=i.id_name,
            id_value=i.id_value,
        )

        if edition:
            return edition  # Case 2 or 3 or 4, from add page

        solr = get_solr()
        # Less exact solr search than try_edition_match(), search by supplied title and author only.
        result = solr.select(
            {'title': i.title, 'author_key': author_key.split("/")[-1]},
            doc_wrapper=make_work,
            q_op="AND",
        )

        if result.num_found == 0:
            return None  # Case 1, from add page
        elif result.num_found == 1:
            return result.docs[0]  # Case 2
        else:
            return result.docs  # Case 4

    def extract_year(self, value: str) -> str:
        """
        Extract just the 4 digit year from a date string.

        :param str value: A freeform string representing a publication date.
        :return: a four digit year
        """
        m = web.re_compile(r"(\d\d\d\d)").search(value)
        return m and m.group(1)

    def try_edition_match(
        self,
        work: web.Storage | None = None,
        title: str | None = None,
        author_key: str | None = None,
        publisher: str | None = None,
        publish_year: str | None = None,
        id_name: str | None = None,
        id_value: str | None = None,
    ) -> None | Edition | list[web.Storage]:
        """
        Searches solr for potential edition matches.

        :param str author_key: e.g. /author/OL1234A
        :param str publish_year: yyyy
        :param str id_name: from list of values in mapping below
        :return: None, an Edition, or a list of Works (as web.Storage objects)
        """
        # insufficient data
        if not publisher and not publish_year and not id_value:
            return None

        q: dict = {}
        work and q.setdefault('key', work.key.split("/")[-1])
        title and q.setdefault('title', title)
        author_key and q.setdefault('author_key', author_key.split('/')[-1])
        publisher and q.setdefault('publisher', publisher)
        # There are some errors indexing of publish_year. Use publish_date until it is fixed
        publish_year and q.setdefault('publish_date', publish_year)

        mapping = {
            'isbn_10': 'isbn',
            'isbn_13': 'isbn',
            'lccn': 'lccn',
            'oclc_numbers': 'oclc',
            'ocaid': 'ia',
        }
        if id_value and id_name in mapping:
            if id_name.startswith('isbn'):
                id_value = id_value.replace('-', '')
            q[mapping[id_name]] = id_value

        solr = get_solr()
        result = solr.select(q, doc_wrapper=make_work, q_op="AND")

        if len(result.docs) > 1:
            # found multiple work matches
            return result.docs
        elif len(result.docs) == 1:
            # found one work match
            work = result.docs[0]
            publisher = publisher and fuzzy_find(
                publisher, work.publisher, stopwords=("publisher", "publishers", "and")
            )

            editions = web.ctx.site.get_many(
                ["/books/" + key for key in work.edition_key]
            )
            for e in editions:
                d: dict = {}
                if publisher and (not e.publishers or e.publishers[0] != publisher):
                    continue
                if publish_year and (
                    not e.publish_date
                    or publish_year != self.extract_year(e.publish_date)
                ):
                    continue
                if id_value and id_name in mapping:  # noqa: SIM102
                    if id_name not in e or id_value not in e[id_name]:
                        continue
                # return the first good likely matching Edition
                return e

        return None

    def work_match(
        self, saveutil: DocSaveHelper, work: Work, i: web.utils.Storage
    ) -> NoReturn:
        """
        Action for when a work, but not edition, is matched.
        Saves a new edition of work, created form the formdata i.
        Redirects the user to the newly created edition page in edit
        mode to add more details.

        :param Work work: the matched work for this book
        :param web.utils.Storage i: user supplied book formdata
        """
        edition = self._make_edition(work, i)

        saveutil.save(edition)
        comment = utils.get_message("comment_add_book")
        saveutil.commit(comment=comment, action="add-book")

        raise safe_seeother(edition.url("/edit?mode=add-book"))

    def work_edition_match(self, edition: Edition) -> NoReturn:
        """
        Action for when an exact work and edition match have been found.
        Redirect user to the found item's edit page to add any missing details.
        """
        raise safe_seeother(edition.url("/edit?mode=found"))

    def no_match(self, saveutil: DocSaveHelper, i: web.utils.Storage) -> NoReturn:
        """
        Action to take when no matches are found.
        Creates and saves both a Work and Edition.
        Redirects the user to the work/edition edit page
        in `add-work` mode.
        """
        # Any new author has been created and added to
        # saveutil, and author_key added to i
        work = new_doc("/type/work", title=i.title, authors=i.authors)

        edition = self._make_edition(work, i)

        saveutil.save(work)
        saveutil.save(edition)

        comment = utils.get_message("comment_add_book")
        saveutil.commit(action="add-book", comment=comment)

        raise safe_seeother(edition.url("/edit?mode=add-work"))

    def _make_edition(self, work: Work, i: web.utils.Storage) -> Edition:
        """
        Uses formdata 'i' to create (but not save) an edition of 'work'.
        """
        edition = new_doc(
            "/type/edition",
            works=[{"key": work.key}],
            title=i.title,
            publishers=[i.publisher],
            publish_date=i.publish_date,
        )
        if i.get('web_book_url'):
            edition.set_provider_data({"url": i.web_book_url, "format": "web"})
        if i.get("id_name") and i.get("id_value"):
            edition.set_identifiers([{"name": i.id_name, "value": i.id_value}])
        return edition


# remove existing definitions of addbook and addauthor
delegate.pages.pop('/addbook', None)
delegate.pages.pop('/addauthor', None)


class addbook(delegate.page):  # type: ignore[no-redef] # noqa: F811
    def GET(self):
        raise web.redirect("/books/add")


class addauthor(delegate.page):
    def GET(self):
        raise web.redirect("/authors")


def trim_value(value):
    """Trim strings, lists and dictionaries to remove empty/None values.

    >>> trim_value("hello ")
    'hello'
    >>> trim_value("")
    >>> trim_value([1, 2, ""])
    [1, 2]
    >>> trim_value({'x': 'a', 'y': ''})
    {'x': 'a'}
    >>> trim_value({'x': [""]})
    None
    """
    if isinstance(value, str):
        value = value.strip()
        return value or None
    elif isinstance(value, list):
        value = [v2 for v in value for v2 in [trim_value(v)] if v2 is not None]
        return value or None
    elif isinstance(value, dict):
        value = {
            k: v2 for k, v in value.items() for v2 in [trim_value(v)] if v2 is not None
        }
        return value or None
    else:
        return value


def trim_doc(doc):
    """Replace empty values in the document with Nones."""
    return web.storage((k, trim_value(v)) for k, v in doc.items() if k[:1] not in "_{")


class SaveBookHelper:
    """Helper to save edition and work using the form data coming from edition edit and work edit pages.

    This does the required trimming and processing of input data before saving.
    """

    def __init__(self, work: Work | None, edition: Edition | None):
        """
        :param Work|None work: None if editing an orphan edition
        :param Edition|None edition: None if just editing work
        """
        self.work = work
        self.edition = edition

    def save(self, formdata: web.Storage) -> None:
        """
        Update work and edition documents according to the specified formdata.
        """
        comment = formdata.pop('_comment', '')

        user = accounts.get_current_user()
        delete = (
            user
            and (user.is_admin() or user.is_super_librarian())
            and formdata.pop('_delete', '')
        )

        formdata = utils.unflatten(formdata)
        work_data, edition_data = self.process_input(formdata)

        if not delete:
            self.process_new_fields(formdata)

        saveutil = DocSaveHelper()

        if delete:
            if self.edition:
                self.delete(self.edition.key, comment=comment)

            if self.work and self.work.edition_count == 0:
                self.delete(self.work.key, comment=comment)
            return

        just_editing_work = edition_data is None
        if work_data:
            # Create any new authors that were added
            saveutil.create_authors_from_form_data(
                work_data.get("authors") or [], formdata.get('authors') or []
            )

            if not just_editing_work:
                # Mypy misses that "not just_editing_work" means there is edition data.
                assert self.edition
                # Handle orphaned editions
                new_work_key = (edition_data.get('works') or [{'key': None}])[0]['key']
                if self.work is None and (
                    new_work_key is None or new_work_key == '__new__'
                ):
                    # i.e. not moving to another work, create empty work
                    self.work = self.new_work(self.edition)
                    edition_data.works = [{'key': self.work.key}]
                    work_data.key = self.work.key
                elif self.work is not None and new_work_key is None:
                    # we're trying to create an orphan; let's not do that
                    edition_data.works = [{'key': self.work.key}]

            if self.work is not None:
                self.work.update(work_data)
                saveutil.save(self.work)

        if self.edition and edition_data:
            # Create a new work if so desired
            new_work_key = (edition_data.get('works') or [{'key': None}])[0]['key']
            if new_work_key == "__new__" and self.work is not None:
                new_work = self.new_work(self.edition)
                edition_data.works = [{'key': new_work.key}]

                new_work_options = formdata.get(
                    'new_work_options',
                    {
                        'copy_authors': 'no',
                        'copy_subjects': 'no',
                    },
                )

                if (
                    new_work_options.get('copy_authors') == 'yes'
                    and 'authors' in self.work
                ):
                    new_work.authors = self.work.authors
                if new_work_options.get('copy_subjects') == 'yes':
                    for field in (
                        'subjects',
                        'subject_places',
                        'subject_times',
                        'subject_people',
                    ):
                        if field in self.work:
                            new_work[field] = self.work[field]

                self.work = new_work
                saveutil.save(self.work)

            identifiers = edition_data.pop('identifiers', [])
            self.edition.set_identifiers(identifiers)

            classifications = edition_data.pop('classifications', [])
            self.edition.set_classifications(classifications)

            self.edition.set_physical_dimensions(
                edition_data.pop('physical_dimensions', None)
            )
            self.edition.set_weight(edition_data.pop('weight', None))
            self.edition.set_toc_text(edition_data.pop('table_of_contents', None))

            if edition_data.pop('translation', None) != 'yes':
                edition_data.translation_of = None
                edition_data.translated_from = None

            if 'contributors' not in edition_data:
                self.edition.contributors = []

            providers = edition_data.pop('providers', [])
            self.edition.set_providers(providers)

            self.edition.update(edition_data)
            saveutil.save(self.edition)

        saveutil.commit(comment=comment, action="edit-book")

    @staticmethod
    def new_work(edition: Edition) -> Work:
        return new_doc(
            '/type/work',
            title=edition.get('title'),
            subtitle=edition.get('subtitle'),
            covers=edition.get('covers', []),
        )

    @staticmethod
    def delete(key, comment=""):
        doc = web.ctx.site.new(key, {"key": key, "type": {"key": "/type/delete"}})
        doc._save(comment=comment)

    def process_new_fields(self, formdata: dict):
        def f(name: str):
            val = formdata.get(name)
            return val and json.loads(val)

        new_roles = f('select-role-json')
        new_ids = f('select-id-json')
        new_classifications = f('select-classification-json')

        if new_roles or new_ids or new_classifications:
            edition_config = web.ctx.site.get('/config/edition')

            # TODO: take care of duplicate names

            if new_roles:
                edition_config.roles += [d.get('value') or '' for d in new_roles]

            if new_ids:
                edition_config.identifiers += [
                    {
                        "name": d.get('value') or '',
                        "label": d.get('label') or '',
                        "website": d.get("website") or '',
                        "notes": d.get("notes") or '',
                    }
                    for d in new_ids
                ]

            if new_classifications:
                edition_config.classifications += [
                    {
                        "name": d.get('value') or '',
                        "label": d.get('label') or '',
                        "website": d.get("website") or '',
                        "notes": d.get("notes") or '',
                    }
                    for d in new_classifications
                ]

            as_admin(edition_config._save)("add new fields")

    def process_input(self, i):
        if 'edition' in i:
            edition = self.process_edition(i.edition)
        else:
            edition = None

        if 'work' in i and self.use_work_edits(i):
            work = self.process_work(i.work)
        else:
            work = None

        return work, edition

    def process_edition(self, edition):
        """Process input data for edition."""
        edition.publishers = edition.get('publishers', '').split(';')
        edition.publish_places = edition.get('publish_places', '').split(';')

        edition = trim_doc(edition)

        if list(edition.get('physical_dimensions', [])) == ['units']:
            edition.physical_dimensions = None

        if list(edition.get('weight', [])) == ['units']:
            edition.weight = None

        for k in ['roles', 'identifiers', 'classifications']:
            edition[k] = edition.get(k) or []

        self._prevent_ocaid_deletion(edition)
        return edition

    def process_work(self, work: web.Storage) -> web.Storage:
        """
        Process input data for work.
        :param web.storage work: form data work info
        """

        def read_subject(subjects):
            """
            >>> list(read_subject("A,B,C,B")) == [u'A', u'B', u'C']   # str
            True
            >>> list(read_subject(r"A,B,C,B")) == [u'A', u'B', u'C']  # raw
            True
            >>> list(read_subject(u"A,B,C,B")) == [u'A', u'B', u'C']  # Unicode
            True
            >>> list(read_subject(""))
            []
            """
            if not subjects:
                return
            f = io.StringIO(subjects.replace('\r\n', ''))
            dedup = set()
            for s in next(csv.reader(f, dialect='excel', skipinitialspace=True)):
                if s.casefold() not in dedup:
                    yield s
                    dedup.add(s.casefold())

        work.subjects = list(read_subject(work.get('subjects', '')))
        work.subject_places = list(read_subject(work.get('subject_places', '')))
        work.subject_times = list(read_subject(work.get('subject_times', '')))
        work.subject_people = list(read_subject(work.get('subject_people', '')))
        if ': ' in work.get('title', ''):
            work.title, work.subtitle = work.title.split(': ', 1)
        else:
            work.subtitle = None

        for k in ('excerpts', 'links'):
            work[k] = work.get(k) or []

        # ignore empty authors
        work.authors = [
            a
            for a in work.get('authors', [])
            if a.get('author', {}).get('key', '').strip()
        ]

        return trim_doc(work)

    def _prevent_ocaid_deletion(self, edition) -> None:
        # Allow admins to modify ocaid
        user = accounts.get_current_user()
        if user and (user.is_admin() or user.is_super_librarian()):
            return

        # read ocaid from form data
        ocaid = next(
            (
                id_['value']
                for id_ in edition.get('identifiers', [])
                if id_['name'] == 'ocaid'
            ),
            None,
        )

        # 'self.edition' is the edition doc from the db and 'edition' is the doc from formdata
        if (
            self.edition
            and self.edition.get('ocaid')
            and self.edition.get('ocaid') != ocaid
        ):
            logger.warning(
                "Attempt to change ocaid of %s from %r to %r.",
                self.edition.key,
                self.edition.get('ocaid'),
                ocaid,
            )
            raise ValidationException("Changing Internet Archive ID is not allowed.")

    @staticmethod
    def use_work_edits(formdata: web.Storage) -> bool:
        """
        Check if the form data's work OLID matches the form data's edition's work OLID.
        If they don't, then we ignore the work edits.
        :param web.storage formdata: form data (parsed into a nested dict)
        """
        if 'edition' not in formdata:
            # No edition data -> just editing work, so work data matters
            return True

        has_edition_work = (
            'works' in formdata.edition
            and formdata.edition.works
            and formdata.edition.works[0].key
        )

        if has_edition_work:
            old_work_key = formdata.work.key
            new_work_key = formdata.edition.works[0].key
            return old_work_key == new_work_key
        else:
            # i.e. editing an orphan; so we care about the work
            return True


class book_edit(delegate.page):
    path = r"(/books/OL\d+M)/edit"

    def GET(self, key):
        i = web.input(v=None)
        v = i.v and safeint(i.v, None)

        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        edition = web.ctx.site.get(key, v)
        if edition is None:
            raise web.notfound()

        work = (
            edition.works
            and edition.works[0]
            or edition.make_work_from_orphaned_edition()
        )

        return render_template('books/edit', work, edition, recaptcha=get_recaptcha())

    def POST(self, key):
        i = web.input(v=None, work_key=None, _method="GET")

        if spamcheck.is_spam(allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )

        recap = get_recaptcha()
        if recap and not recap.validate():
            return render_template(
                "message.html",
                'Recaptcha solution was incorrect',
                'Please <a href="javascript:history.back()">go back</a> and try again.',
            )
        v = i.v and safeint(i.v, None)
        edition = web.ctx.site.get(key, v)

        if edition is None:
            raise web.notfound()
        if edition.works:
            work = edition.works[0]
        else:
            work = None

        add = (
            edition.revision == 1
            and work
            and work.revision == 1
            and work.edition_count == 1
        )

        try:
            helper = SaveBookHelper(work, edition)
            helper.save(web.input())

            if add:
                add_flash_message("info", utils.get_message("flash_book_added"))
            else:
                add_flash_message("info", utils.get_message("flash_book_updated"))

            if i.work_key and i.work_key.startswith('/works/'):
                url = i.work_key
            else:
                url = edition.url()

            raise safe_seeother(url)
        except ClientException as e:
            add_flash_message('error', e.args[-1] or e.json)
            return self.GET(key)
        except ValidationException as e:
            add_flash_message('error', str(e))
            return self.GET(key)


class work_edit(delegate.page):
    path = r"(/works/OL\d+W)/edit"

    def GET(self, key):
        i = web.input(v=None, _method="GET")
        v = i.v and safeint(i.v, None)

        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        work = web.ctx.site.get(key, v)
        if work is None:
            raise web.notfound()

        return render_template('books/edit', work, recaptcha=get_recaptcha())

    def POST(self, key):
        i = web.input(v=None, _method="GET")

        if spamcheck.is_spam(allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )

        recap = get_recaptcha()

        if recap and not recap.validate():
            return render_template(
                "message.html",
                'Recaptcha solution was incorrect',
                'Please <a href="javascript:history.back()">go back</a> and try again.',
            )

        v = i.v and safeint(i.v, None)
        work = web.ctx.site.get(key, v)
        if work is None:
            raise web.notfound()

        try:
            helper = SaveBookHelper(work, None)
            helper.save(web.input())
            add_flash_message("info", utils.get_message("flash_work_updated"))
            raise safe_seeother(work.url())
        except (ClientException, ValidationException) as e:
            add_flash_message('error', str(e))
            return self.GET(key)


class author_edit(delegate.page):
    path = r"(/authors/OL\d+A)/edit"

    def GET(self, key):
        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        author = web.ctx.site.get(key)
        if author is None:
            raise web.notfound()
        return render_template("type/author/edit", author)

    def POST(self, key):
        author = web.ctx.site.get(key)
        if author is None:
            raise web.notfound()

        i = web.input(_comment=None)
        formdata = self.process_input(i)
        try:
            if not formdata:
                raise web.badrequest()
            elif "_save" in i:
                author.update(formdata)
                author._save(comment=i._comment)
                raise safe_seeother(key)
            elif "_delete" in i:
                author = web.ctx.site.new(
                    key, {"key": key, "type": {"key": "/type/delete"}}
                )
                author._save(comment=i._comment)
                raise safe_seeother(key)
        except (ClientException, ValidationException) as e:
            add_flash_message('error', str(e))
            author.update(formdata)
            author['comment_'] = i._comment
            return render_template("type/author/edit", author)

    def process_input(self, i):
        i = utils.unflatten(i)
        if 'author' in i:
            author = trim_doc(i.author)
            alternate_names = author.get('alternate_names', None) or ''
            author.alternate_names = uniq(
                [author.name]
                + [
                    name.strip() for name in alternate_names.split('\n') if name.strip()
                ],
            )[1:]
            author.links = author.get('links') or []
            return author


class daisy(delegate.page):
    path = "(/books/.*)/daisy"

    def GET(self, key):
        page = web.ctx.site.get(key)

        if not page:
            raise web.notfound()

        return render_template("books/daisy", page)


class work_identifiers(delegate.view):
    # TODO: (cclauss) Fix typing in infogami.utils.delegate and remove type: ignore
    suffix = "identifiers"  # type: ignore[assignment]
    types = ["/type/edition"]  # type: ignore[assignment]

    def POST(self, edition):
        saveutil = DocSaveHelper()
        i = web.input(isbn="")
        isbn = i.get("isbn")
        # Need to do some simple validation here. Perhaps just check if it's a number?
        if len(isbn) == 10:
            typ = "ISBN 10"
            data = [{'name': 'isbn_10', 'value': isbn}]
        elif len(isbn) == 13:
            typ = "ISBN 13"
            data = [{'name': 'isbn_13', 'value': isbn}]
        else:
            add_flash_message("error", "The ISBN number you entered was not valid")
            raise web.redirect(web.ctx.path)
        if edition.works:
            work = edition.works[0]
        else:
            work = None
        edition.set_identifiers(data)
        saveutil.save(edition)
        saveutil.commit(comment="Added an %s identifier." % typ, action="edit-book")
        add_flash_message("info", "Thank you very much for improving that record!")
        raise web.redirect(web.ctx.path)


def setup():
    """Do required setup."""
    pass
