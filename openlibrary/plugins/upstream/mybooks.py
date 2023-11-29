import json
import web

from typing import Final, Literal

from infogami.utils import delegate
from infogami.utils.view import public, safeint, render

from openlibrary import accounts
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.dateutil import current_year
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.lending import add_availability, get_loans_of_user
from openlibrary.core.observations import Observations, convert_observation_ids
from openlibrary.core.sponsorships import get_sponsored_editions
from openlibrary.core.models import LoggedBooksData


RESULTS_PER_PAGE: Final = 25


class my_books_home(delegate.page):
    path = "/people/([^/]+)/books"

    def GET(self, username):
        """
        The other way to get to this page is /account/books which is defined
        in /plugins/account.py account_my_books. But we don't need to update that redirect
        because it already just redirects here.
        """
        return MyBooksTemplate(username, key='mybooks').render()


class my_books_view(delegate.page):
    path = r"/people/([^/]+)/books/([a-zA-Z_-]+)"

    def GET(self, username, key):
        i = web.input(page=1, sort='desc', q="")
        # Limit reading log filtering to queries of 3+ characters because filtering the
        # reading log can be computationally expensive.
        if len(i.q) < 3:
            i.q = ""
        return MyBooksTemplate(username, key).render(page=i.page, sort=i.sort, q=i.q)


class public_my_books_json(delegate.page):
    encoding = "json"
    path = "/people/([^/]+)/books/([a-zA-Z_-]+)"

    def GET(self, username, key='want-to-read'):
        i = web.input(page=1, limit=5000, q="")
        if len(i.q) < 3:
            i.q = ""
        page = safeint(i.page, 1)
        limit = safeint(i.limit, 5000)
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
            books = readlog.get_works(key.lower(), page, limit, q=i.q).docs
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
            return delegate.RawText(
                json.dumps({'page': page, 'reading_log_entries': records_json}),
                content_type="application/json",
            )
        else:
            return delegate.RawText(
                json.dumps({'error': 'Shelf %s not found or not accessible' % key}),
                content_type="application/json",
            )


class readinglog_yearly(delegate.page):
    path = "/people/([^/]+)/books/already-read/year/([0-9]+)"

    def GET(self, username, year=None):
        year = int(year or current_year())
        if year < 1000:
            # The year is used in a LIKE statement when we query for the yearly summary, so
            # ensuring that the year is at least four digits long avoids incorrect results.
            raise web.badrequest(message="Year must be four digits")
        return MyBooksTemplate(username, 'already-read').render(year=year)


class readinglog_stats(delegate.page):
    path = "/people/([^/]+)/books/([a-zA-Z_-]+)/stats"

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


@public
def get_public_patron_account(username):
    user = web.ctx.site.get('/people/%s' % username)
    return ReadingLog(user=user)


@public
def get_patrons_work_read_status(username, work_key):
    if not username:
        return None
    work_id = extract_numeric_id_from_olid(work_key)
    status_id = Bookshelves.get_users_read_status_of_work(username, work_id)
    return status_id


class MyBooksTemplate:
    # Reading log shelves
    READING_LOG_KEYS = {"currently-reading", "want-to-read", "already-read"}

    # Keys that can be accessed when not logged in
    PUBLIC_KEYS = READING_LOG_KEYS | {"lists", "list"} | {"mybooks"}

    # Keys that are only accessible when logged in
    # unioned with the public keys
    ALL_KEYS = PUBLIC_KEYS | {
        "loans",
        "waitlist",
        "sponsorships",
        "notes",
        "observations",
        "imports",
    }

    def __init__(self, username, key):
        self.username = username
        self.user = web.ctx.site.get('/people/%s' % self.username)
        self.key = key.lower()
        self.readlog = ReadingLog(user=self.user)
        self.lists = self.readlog.lists
        self.counts = self.readlog.reading_log_counts

    def render(
        self,
        page=1,
        sort='desc',
        list=None,
        q="",
        doc_count: int = 0,
        ratings=None,
        year=None,
    ):
        """
        Gather the data necessary to render the My Books template, and then
        render the template.
        """
        if not self.user:
            return render.notfound("User %s" % self.username, create=False)
        logged_in_user = accounts.get_current_user()
        is_logged_in_user = (
            logged_in_user and logged_in_user.key.split('/')[-1] == self.username
        )
        is_public = self.user.preferences().get('public_readlog', 'no') == 'yes'

        docs = None

        if is_logged_in_user and self.key in self.ALL_KEYS:
            self.counts.update(PatronBooknotes.get_counts(self.username))
            sponsorships = get_sponsored_editions(self.user)
            self.counts['sponsorships'] = len(sponsorships)

            if self.key == 'sponsorships':
                docs = (
                    add_availability(
                        web.ctx.site.get_many(
                            [
                                '/books/%s' % doc['openlibrary_edition']
                                for doc in sponsorships
                            ]
                        )
                    )
                    if sponsorships
                    else None
                )

            # Reading log for logged in users.
            elif self.key in self.READING_LOG_KEYS:
                logged_book_data: LoggedBooksData = self.readlog.get_works(
                    key=self.key,
                    page=page,
                    sort='created',
                    sort_order=sort,
                    q=q,
                    year=year,
                )
                docs = add_availability(logged_book_data.docs, mode="openlibrary_work")
                doc_count = logged_book_data.total_results

                # Add ratings to "already-read" items.
                if self.key == "already-read" and logged_in_user:
                    logged_book_data.load_ratings()

                ratings = logged_book_data.ratings

            elif self.key == 'list':
                docs = list

            else:
                docs = self._prepare_data(logged_in_user)

        # Reading log for non-logged in users.
        elif self.key in self.READING_LOG_KEYS and is_public:
            logged_book_data: LoggedBooksData = self.readlog.get_works(  # type: ignore[no-redef]
                key=self.key, page=page, sort='created', sort_order=sort, q=q, year=year
            )
            docs = add_availability(logged_book_data.docs, mode="openlibrary_work")
            doc_count = logged_book_data.total_results
            ratings = logged_book_data.ratings

        if docs is not None:
            return render['account/books'](
                docs=docs,
                key=self.key,
                shelf_counts=self.counts,
                doc_count=doc_count,
                logged_in_user=logged_in_user,
                user=self.user,
                lists=self.lists,
                public=is_public,
                owners_page=is_logged_in_user,
                sort_order=sort,
                q=q,
                results_per_page=RESULTS_PER_PAGE,
                ratings=ratings,
                checkin_year=year,
            )

        raise web.seeother(self.user.key)

    def _prepare_data(
        self,
        logged_in_user,
        page=1,
        username=None,
    ):
        def get_shelf(name, page=1):
            return self.readlog.get_works(
                key=name, page=page, limit=6, sort='created', sort_order='asc'
            )

        if self.key == 'mybooks':
            want_to_read = get_shelf('want-to-read', page=page)
            currently_reading = get_shelf('currently-reading', page=page)
            already_read = get_shelf('already-read', page=page)

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

            # Marshal loans into homogeneous data that carousel can render
            loans = get_loans_of_user(logged_in_user.key)
            myloans = web.Storage({"docs": [], "total_results": len(loans)})
            for loan in loans:
                book = web.ctx.site.get(loan['book'])
                book.loan = loan
                myloans.docs.append(book)

            return {
                'loans': myloans,
                'want-to-read': want_to_read,
                'currently-reading': currently_reading,
                'already-read': already_read,
            }
        elif self.key == 'loans':
            return get_loans_of_user(logged_in_user.key)
        elif self.key == 'waitlist':
            return {}
        elif self.key == 'lists':
            if username:
                return web.ctx.site.get('/people/%s' % username)
            return self.user
        elif self.key == 'notes':
            return PatronBooknotes(self.user).get_notes(page=page)
        elif self.key == 'observations':
            return PatronBooknotes(self.user).get_observations(page=page)
        elif self.key == 'imports':
            return {}

        return None


@public
def get_mybooks_template(username, key, list):
    return MyBooksTemplate(username, key).render(list=list)


class ReadingLog:
    """Manages the user's account page books (reading log, waitlists, loans)"""

    # Constants
    PRESET_SHELVES = Literal["Want to Read", "Already Read", "Currently Reading"]
    READING_LOG_KEYS = Literal["want-to-read", "already-read", "currently-reading"]

    def __init__(self, user=None):
        self.user = user or accounts.get_current_user()

    @property
    def lists(self):
        return self.user.get_lists()

    @property
    def sponsorship_counts(self):
        return {'sponsorships': len(get_sponsored_editions(self.user))}

    @property
    def booknotes_counts(self):
        return PatronBooknotes.get_counts(self.user.get_username())

    @property
    def get_sidebar_counts(self):
        counts = self.reading_log_counts
        counts.update(self.sponsorship_counts)
        counts.update(self.booknotes_counts)
        return counts

    @property
    def reading_log_counts(self):
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
        if key == "want-to-read":
            shelf = "Want to Read"
        elif key == "already-read":
            shelf = "Already Read"
        elif key == "currently-reading":
            shelf = "Currently Reading"
        else:
            raise ValueError(
                "key must be want-to-read, already-read, or currently-reading"
            )
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
        work['readinglog'] = results_map.get(work_olid, None)
    return works


class PatronBooknotes:
    """Manages the patron's book notes and observations"""

    def __init__(self, user):
        self.user = user
        self.username = user.key.split('/')[-1]

    def get_notes(self, limit=RESULTS_PER_PAGE, page=1):
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

    def get_observations(self, limit=RESULTS_PER_PAGE, page=1):
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

    def _get_work(self, work_key):
        return web.ctx.site.get(work_key)

    def _get_work_details(self, work):
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
    def get_counts(cls, username):
        return {
            'notes': Booknotes.count_works_with_notes_by_user(username),
            'observations': Observations.count_distinct_observations(username),
        }
