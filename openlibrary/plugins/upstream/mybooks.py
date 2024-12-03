import json
from typing import TYPE_CHECKING, Final, Literal, cast

import web
from web.template import TemplateResult

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from infogami.utils.view import public, render, safeint
from openlibrary import accounts
from openlibrary.accounts.model import (
    OpenLibraryAccount,  # noqa: F401 side effects may be needed
)
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.follows import PubSub
from openlibrary.core.lending import (
    add_availability,
    get_loans_of_user,
)
from openlibrary.core.models import LoggedBooksData, User
from openlibrary.core.observations import Observations, convert_observation_ids
from openlibrary.core.yearly_reading_goals import YearlyReadingGoals
from openlibrary.i18n import gettext as _
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.dateutil import current_year

if TYPE_CHECKING:
    from openlibrary.core.lists.model import List
    from openlibrary.plugins.upstream.models import Work

RESULTS_PER_PAGE: Final = 25


class avatar(delegate.page):
    path = "/people/([^/]+)/avatar"

    def GET(self, username: str):
        url = User.get_avatar_url(username)
        raise web.seeother(url)


class mybooks_home(delegate.page):
    path = "/people/([^/]+)/books"

    def GET(self, username: str) -> TemplateResult:
        """Renders the template for the my books overview page

        The other way to get to this page is /account/books which is
        defined in /plugins/account.py account_my_books. But we don't
        need to update that redirect because it already just redirects
        here.
        """
        mb = MyBooksTemplate(username, key='mybooks')
        template = self.render_template(mb)
        return mb.render(header_title=_("Books"), template=template)

    def render_template(self, mb):
        # Marshal loans into homogeneous data that carousel can render
        want_to_read, currently_reading, already_read, loans = [], [], [], []

        if mb.me:
            myloans = get_loans_of_user(mb.me.key)
            loans = web.Storage({"docs": [], "total_results": len(loans)})
            # TODO: should do in one web.ctx.get_many fetch
            for loan in myloans:
                # Book will be None if no OL edition exists for the book
                if book := web.ctx.site.get(loan['book']):
                    book.loan = loan
                    loans.docs.append(book)

        if mb.me or mb.is_public:
            params = {'sort': 'created', 'limit': 6, 'sort_order': 'desc', 'page': 1}
            want_to_read = mb.readlog.get_works(key='want-to-read', **params)
            currently_reading = mb.readlog.get_works(key='currently-reading', **params)
            already_read = mb.readlog.get_works(key='already-read', **params)

            # Ideally, do all 3 lookups in one add_availability call
            want_to_read.docs = add_availability(
                [d for d in want_to_read.docs if d.get('title')]
            )[:5]
            currently_reading.docs = add_availability(
                [d for d in currently_reading.docs if d.get('title')]
            )[:5]
            already_read.docs = add_availability(
                [d for d in already_read.docs if d.get('title')]
            )[:5]

        docs = {
            'loans': loans,
            'want-to-read': want_to_read,
            'currently-reading': currently_reading,
            'already-read': already_read,
        }
        return render['account/mybooks'](
            mb.user,
            docs,
            key=mb.key,
            public=mb.is_public,
            owners_page=mb.is_my_page,
            counts=mb.counts,
            lists=mb.lists,
            component_times=mb.component_times,
        )


class mybooks_notes(delegate.page):
    path = "/people/([^/]+)/books/notes"

    def GET(self, username):
        i = web.input(page=1)
        mb = MyBooksTemplate(username, key='notes')
        if mb.is_my_page:
            docs = PatronBooknotes(mb.user).get_notes(page=int(i.page))
            template = render['account/notes'](
                docs, mb.user, mb.counts['notes'], page=int(i.page)
            )
            return mb.render(header_title=_("Notes"), template=template)
        raise web.seeother(mb.user.key)


class mybooks_reviews(delegate.page):
    path = "/people/([^/]+)/books/observations"

    def GET(self, username):
        i = web.input(page=1)
        mb = MyBooksTemplate(username, key='observations')
        if mb.is_my_page:
            docs = PatronBooknotes(mb.user).get_observations(page=int(i.page))
            template = render['account/observations'](
                docs, mb.user, mb.counts['observations'], page=int(i.page)
            )
            return mb.render(header_title=_("Reviews"), template=template)
        raise web.seeother(mb.user.key)


class mybooks_feed(delegate.page):
    path = "/people/([^/]+)/books/feed"

    def GET(self, username):
        mb = MyBooksTemplate(username, key='feed')
        if mb.is_my_page:
            docs = PubSub.get_feed(username)
            doc_count = len(docs)
            template = render['account/reading_log'](
                docs,
                mb.key,
                doc_count,
                doc_count,
                mb.is_my_page,
                current_page=1,
                user=mb.me,
            )
            return mb.render(header_title=_("My Feed"), template=template)
        raise web.seeother(mb.user.key)


class readinglog_stats(delegate.page):
    path = "/people/([^/]+)/books/(want-to-read|currently-reading|already-read)/stats"

    def GET(self, username, key='want-to-read'):
        user = web.ctx.site.get('/people/%s' % username)
        if not user:
            return render.notfound("User %s" % username, create=False)

        cur_user = accounts.get_current_user()
        if not cur_user or cur_user.key.split('/')[-1] != username:
            return render.permission_denied(web.ctx.path, 'Permission Denied')

        readlog = ReadingLog(user=user)
        works = readlog.get_works(key, page=1, limit=2000).docs
        works_json = [
            {
                # Fallback to key if it is a redirect
                'title': w.get('title') or w.key,
                'subtitle': w.get('subtitle'),
                'key': w.get('key'),
                'author_keys': ['/authors/' + key for key in w.get('author_key', [])],
                'first_publish_year': w.get('first_publish_year') or None,
                'subjects': w.get('subject'),
                'subject_people': w.get('person'),
                'subject_places': w.get('place'),
                'subject_times': w.get('time'),
            }
            for w in works
        ]
        author_keys = {a for work in works_json for a in work['author_keys']}
        authors_json = [
            {
                'key': a.key,
                'name': a.name,
                'birth_date': a.get('birth_date'),
            }
            for a in web.ctx.site.get_many(list(author_keys))
        ]
        return render['account/readinglog_stats'](
            works_json,
            authors_json,
            len(works_json),
            user.key,
            user.displayname,
            web.ctx.path.rsplit('/', 1)[0],
            key,
            lang=web.ctx.lang,
        )


class readinglog_yearly(delegate.page):
    path = "/people/([^/]+)/books/already-read/year/([0-9]+)"

    def GET(self, username, year=None):
        year = int(year or current_year())
        if year < 1000:
            # The year is used in a LIKE statement when we query for the yearly summary, so
            # ensuring that the year is at least four digits long avoids incorrect results.
            raise web.badrequest(message="Year must be four digits")
        mb = MyBooksTemplate(username, 'already-read')
        mb.selected_year = str(year)
        template = mybooks_readinglog().render_template(mb, year=year)
        return mb.render(template=template, header_title=_("Already Read"))


class mybooks_readinglog(delegate.page):
    path = r'/people/([^/]+)/books/(want-to-read|currently-reading|already-read)'

    def GET(self, username, key='want-to-read'):
        mb = MyBooksTemplate(username, key)
        if mb.is_my_page or mb.is_public:
            KEYS_TITLES = {
                'currently-reading': _(
                    "Currently Reading (%(count)d)",
                    count=mb.counts['currently-reading'],
                ),
                'want-to-read': _(
                    "Want to Read (%(count)d)", count=mb.counts['want-to-read']
                ),
                'already-read': _(
                    "Already Read (%(count)d)", count=mb.counts['already-read']
                ),
            }
            template = self.render_template(mb)
            return mb.render(header_title=KEYS_TITLES[key], template=template)
        raise web.seeother(mb.user.key)

    def render_template(self, mb, year=None):
        i = web.input(page=1, sort='desc', q="", results_per_page=RESULTS_PER_PAGE)
        # Limit reading log filtering to queries of 3+ characters
        # because filtering the reading log can be computationally expensive.
        if len(i.q) < 3:
            i.q = ""
        logged_book_data: LoggedBooksData = mb.readlog.get_works(
            key=mb.key, page=i.page, sort='created', sort_order=i.sort, q=i.q, year=year
        )
        docs = add_availability(logged_book_data.docs, mode="openlibrary_work")
        doc_count = logged_book_data.total_results

        # Add ratings to "already-read" items.
        if include_ratings := mb.key == "already-read" and mb.is_my_page:
            logged_book_data.load_ratings()

        # Add yearly reading goals to the MyBooksTemplate
        if mb.key == 'already-read' and mb.is_my_page:
            mb.reading_goals = [
                str(result.year)
                for result in YearlyReadingGoals.select_by_username(
                    mb.username, order='year DESC'
                )
            ]

        ratings = logged_book_data.ratings
        return render['account/reading_log'](
            docs,
            mb.key,
            mb.counts[mb.key],
            doc_count,
            mb.is_my_page,
            i.page,
            sort_order=i.sort,
            user=mb.user,
            include_ratings=include_ratings,
            q=i.q,
            results_per_page=i.results_per_page,
            ratings=ratings,
            checkin_year=year,
        )


class public_my_books_json(delegate.page):
    path = r"/people/([^/]+)/books/(want-to-read|currently-reading|already-read)"
    encoding = "json"

    def GET(self, username, key='want-to-read'):
        i = web.input(page=1, limit=100, q="")
        key = cast(ReadingLog.READING_LOG_KEYS, key.lower())
        if len(i.q) < 3:
            i.q = ""
        page = safeint(i.page, 1)
        limit = safeint(i.limit, 100)
        # check if user's reading log is public
        user = web.ctx.site.get('/people/%s' % username)
        if not user:
            return delegate.RawText(
                json.dumps({'error': 'User %s not found' % username}),
                content_type="application/json",
            )
        is_public = user.preferences().get('public_readlog', 'no') == 'yes'
        logged_in_user = accounts.get_current_user()
        if (
            is_public
            or logged_in_user
            and logged_in_user.key.split('/')[-1] == username
        ):
            readlog = ReadingLog(user=user)
            books = readlog.get_works(key, page, limit, q=i.q).docs
            records_json = [
                {
                    'work': {
                        'title': w.get('title'),
                        'key': w.key,
                        'author_keys': [
                            '/authors/' + key for key in w.get('author_key', [])
                        ],
                        'author_names': w.get('author_name', []),
                        'first_publish_year': w.get('first_publish_year') or None,
                        'lending_edition_s': (w.get('lending_edition_s') or None),
                        'edition_key': (w.get('edition_key') or None),
                        'cover_id': (w.get('cover_i') or None),
                        'cover_edition_key': (w.get('cover_edition_key') or None),
                    },
                    'logged_edition': w.get('logged_edition') or None,
                    'logged_date': (
                        w.get('logged_date').strftime("%Y/%m/%d, %H:%M:%S")
                        if w.get('logged_date')
                        else None
                    ),
                }
                for w in books
            ]

            if page == 1 and len(records_json) < limit:
                num_found = len(records_json)
            else:
                num_found = readlog.count_shelf(key)

            return delegate.RawText(
                json.dumps(
                    {
                        'page': page,
                        'numFound': num_found,
                        'reading_log_entries': records_json,
                    }
                ),
                content_type="application/json",
            )
        else:
            return delegate.RawText(
                json.dumps({'error': 'Shelf %s not found or not accessible' % key}),
                content_type="application/json",
            )


@public
def get_patrons_work_read_status(username: str, work_key: str) -> int | None:
    if not username:
        return None
    work_id = extract_numeric_id_from_olid(work_key)
    status_id = Bookshelves.get_users_read_status_of_work(username, work_id)
    return status_id


@public
class MyBooksTemplate:
    # Reading log shelves
    READING_LOG_KEYS = {"currently-reading", "want-to-read", "already-read"}

    # Keys that can be accessed when not logged in
    PUBLIC_KEYS = READING_LOG_KEYS | {"lists", "list"} | {"mybooks"}

    # Keys that are only accessible when logged in
    # unioned with the public keys
    ALL_KEYS = PUBLIC_KEYS | {
        "loans",
        "feed",
        "waitlist",
        "notes",
        "observations",
        "imports",
    }

    def __init__(self, username: str, key: str) -> None:
        """The following is data required by every My Books sub-template (e.g. sidebar)"""
        self.username = username
        self.user = web.ctx.site.get('/people/%s' % self.username)

        if not self.user:
            raise render.notfound("User %s" % self.username, create=False)

        self.is_public = self.user.preferences().get('public_readlog', 'no') == 'yes'
        self.user_itemname = self.user.get_account().get('internetarchive_itemname')

        self.me = accounts.get_current_user()
        self.is_my_page = self.me and self.me.key.split('/')[-1] == self.username
        self.is_subscribed = (
            self.me.is_subscribed_user(self.username)
            if self.me and self.is_public
            else -1
        )
        self.key = key.lower()

        self.readlog = ReadingLog(user=self.user)
        self.lists = self.readlog.lists
        self.counts = (
            self.readlog.reading_log_counts
            if (self.is_my_page or self.is_public)
            else {}
        )

        self.reading_goals: list = []
        self.selected_year = None

        if self.me and self.is_my_page or self.is_public:
            self.counts['followers'] = PubSub.count_followers(self.username)
            self.counts['following'] = PubSub.count_following(self.username)

        if self.me and self.is_my_page:
            self.counts.update(PatronBooknotes.get_counts(self.username))

        self.component_times: dict = {}

    def render_sidebar(self) -> TemplateResult:
        return render['account/sidebar'](
            self.username,
            self.key,
            self.is_my_page,
            self.is_public,
            self.counts,
            self.lists,
            self.component_times,
        )

    def render(
        self, template: TemplateResult, header_title: str, page: "List | None" = None
    ) -> TemplateResult:
        """
        Gather the data necessary to render the My Books template, and then
        render the template.
        """
        return render['account/view'](
            mb=self, template=template, header_title=header_title, page=page
        )


class ReadingLog:
    """Manages the user's account page books (reading log, waitlists, loans)"""

    # Constants
    PRESET_SHELVES = Literal["Want to Read", "Already Read", "Currently Reading"]
    READING_LOG_KEYS = Literal["want-to-read", "already-read", "currently-reading"]
    READING_LOG_KEY_TO_SHELF: dict[READING_LOG_KEYS, PRESET_SHELVES] = {
        "want-to-read": "Want to Read",
        "already-read": "Already Read",
        "currently-reading": "Currently Reading",
    }

    def __init__(self, user=None):
        self.user = user or accounts.get_current_user()

    @property
    def lists(self) -> list:
        return self.user.get_lists()

    @property
    def booknotes_counts(self):
        return PatronBooknotes.get_counts(self.user.get_username())

    @property
    def get_sidebar_counts(self):
        counts = self.reading_log_counts
        counts.update(self.booknotes_counts)
        return counts

    @property
    def reading_log_counts(self) -> dict[str, int]:
        counts = (
            Bookshelves.count_total_books_logged_by_user_per_shelf(
                self.user.get_username()
            )
            if self.user.get_username()
            else {}
        )
        return {
            'want-to-read': counts.get(
                Bookshelves.PRESET_BOOKSHELVES['Want to Read'], 0
            ),
            'currently-reading': counts.get(
                Bookshelves.PRESET_BOOKSHELVES['Currently Reading'], 0
            ),
            'already-read': counts.get(
                Bookshelves.PRESET_BOOKSHELVES['Already Read'], 0
            ),
        }

    def count_shelf(self, key: READING_LOG_KEYS) -> int:
        username = self.user.get_username()
        assert username
        shelf_id = Bookshelves.PRESET_BOOKSHELVES[self.READING_LOG_KEY_TO_SHELF[key]]
        return Bookshelves.count_user_books_on_shelf(username, shelf_id)

    def get_works(
        self,
        key: READING_LOG_KEYS,
        page: int = 1,
        limit: int = RESULTS_PER_PAGE,
        sort: str = 'created',
        sort_order: str = 'desc',
        q: str = "",
        year: int | None = None,
    ) -> LoggedBooksData:
        """
        Get works for want-to-read, currently-reading, and already-read as
        determined by {key}.

        See LoggedBooksData for specifics on what's returned.
        """
        shelf = self.READING_LOG_KEY_TO_SHELF[key]

        # Mypy is unhappy about the sort argument not being a literal string.
        # Although this doesn't satisfy Mypy, at least make sure sort is either
        # "created asc" or "created desc"
        if sort + " " + sort_order == "created asc":
            sort_literal = "created_asc"
        else:
            sort_literal = "created desc"

        logged_books: LoggedBooksData = Bookshelves.get_users_logged_books(
            self.user.get_username(),
            bookshelf_id=Bookshelves.PRESET_BOOKSHELVES[shelf],
            page=page,
            limit=limit,
            sort=sort_literal,  # type: ignore[arg-type]
            checkin_year=year,
            q=q,
        )

        return logged_books


@public
def get_read_status(work_key, username):
    work_id = extract_numeric_id_from_olid(work_key.split('/')[-1])
    return Bookshelves.get_users_read_status_of_work(username, work_id)


@public
def add_read_statuses(username, works):
    work_ids = [extract_numeric_id_from_olid(work.key.split('/')[-1]) for work in works]
    results = Bookshelves.get_users_read_status_of_works(username, work_ids)
    results_map = {}
    for result in results:
        results_map[f"OL{result['work_id']}W"] = result['bookshelf_id']
    for work in works:
        work_olid = work.key.split('/')[-1]
        work['readinglog'] = results_map.get(work_olid)
    return works


class PatronBooknotes:
    """Manages the patron's book notes and observations"""

    def __init__(self, user: User) -> None:
        self.user = user
        self.username = user.key.split('/')[-1]

    def get_notes(self, limit: int = RESULTS_PER_PAGE, page: int = 1) -> list:
        notes = Booknotes.get_notes_grouped_by_work(
            self.username, limit=limit, page=page
        )

        for entry in notes:
            entry['work_key'] = f"/works/OL{entry['work_id']}W"
            entry['work'] = self._get_work(entry['work_key'])
            entry['work_details'] = self._get_work_details(entry['work'])
            entry['notes'] = {i['edition_id']: i['notes'] for i in entry['notes']}
            entry['editions'] = {
                k: web.ctx.site.get(f'/books/OL{k}M')
                for k in entry['notes']
                if k != Booknotes.NULL_EDITION_VALUE
            }
        return notes

    def get_observations(self, limit: int = RESULTS_PER_PAGE, page: int = 1) -> list:
        observations = Observations.get_observations_grouped_by_work(
            self.username, limit=limit, page=page
        )

        for entry in observations:
            entry['work_key'] = f"/works/OL{entry['work_id']}W"
            entry['work'] = self._get_work(entry['work_key'])
            entry['work_details'] = self._get_work_details(entry['work'])
            ids = {}
            for item in entry['observations']:
                ids[item['observation_type']] = item['observation_values']
            entry['observations'] = convert_observation_ids(ids)
        return observations

    def _get_work(self, work_key: str) -> "Work | None":
        return web.ctx.site.get(work_key)

    def _get_work_details(
        self, work: "Work"
    ) -> dict[str, list[str] | str | int | None]:
        author_keys = [a.author.key for a in work.get('authors', [])]

        return {
            'cover_url': (
                work.get_cover_url('S')
                or 'https://openlibrary.org/images/icons/avatar_book-sm.png'
            ),
            'title': work.get('title'),
            'authors': [a.name for a in web.ctx.site.get_many(author_keys)],
            'first_publish_year': work.first_publish_year or None,
        }

    @classmethod
    def get_counts(cls, username: str) -> dict[str, int]:
        return {
            'notes': Booknotes.count_works_with_notes_by_user(username),
            'observations': Observations.count_distinct_observations(username),
        }
