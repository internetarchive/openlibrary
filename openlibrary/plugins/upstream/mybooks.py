import json
import web

from infogami.utils import delegate
from infogami.utils.view import public, safeint, render

from openlibrary import accounts
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.lending import add_availability
from openlibrary.core.observations import Observations, convert_observation_ids
from openlibrary.core.sponsorships import get_sponsored_editions
from openlibrary.plugins.upstream import borrow


RESULTS_PER_PAGE = 25


class my_books_redirect(delegate.page):
    path = "/people/([^/]+)/books"

    def GET(self, username):
        raise web.seeother('/people/%s/books/want-to-read' % username)


class my_books_view(delegate.page):
    path = r"/people/([^/]+)/books/([a-zA-Z_-]+)"

    def GET(self, username, key):
        i = web.input(page=1, sort='desc')
        return MyBooksTemplate(username, key).render(page=i.page, sort=i.sort)


class public_my_books_json(delegate.page):
    encoding = "json"
    path = "/people/([^/]+)/books/([a-zA-Z_-]+)"

    def GET(self, username, key='want-to-read'):
        i = web.input(page=1, limit=5000)
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
            books = readlog.get_works(key, page, limit)
            records_json = [
                {
                    'work': {
                        'title': w.get('title'),
                        'key': w.key,
                        'author_keys': [
                            a.author.get("key")
                            for a in w.get('authors', []) if a.author
                        ],
                        'author_names': [
                            str(a.author.name)
                            for a in w.get('authors', [])
                            if type(a.author) is not str
                        ],
                        'first_publish_year': w.first_publish_year or None,
                        'lending_edition_s': (
                            w._solr_data
                            and w._solr_data.get('lending_edition_s')
                            or None
                        ),
                        'edition_key': (
                            w._solr_data and w._solr_data.get('edition_key') or None
                        ),
                        'cover_id': (
                            w._solr_data and w._solr_data.get('cover_id') or None
                        ),
                        'cover_edition_key': (
                            w._solr_data
                            and w._solr_data.get('cover_edition_key')
                            or None
                        ),
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


class readinglog_stats(delegate.page):
    path = "/people/([^/]+)/books/([a-zA-Z_-]+)/stats"

    def GET(self, username, key='loans'):
        user = web.ctx.site.get('/people/%s' % username)
        if not user:
            return render.notfound("User %s" % username, create=False)

        cur_user = accounts.get_current_user()
        if not cur_user or cur_user.key.split('/')[-1] != username:
            return render.permission_denied(web.ctx.path, 'Permission Denied')

        readlog = ReadingLog(user=user)
        works = readlog.get_works(key, page=1, limit=2000)
        works_json = [
            {
                'title': w.get('title'),
                'key': w.key,
                'author_keys': [a.author.key for a in w.get('authors', [])],
                'first_publish_year': w.first_publish_year or None,
                'subjects': w.get('subjects'),
                'subject_people': w.get('subject_people'),
                'subject_places': w.get('subject_places'),
                'subject_times': w.get('subject_times'),
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
            json.dumps(works_json),
            json.dumps(authors_json),
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

class MyBooksTemplate:
    # Reading log shelves
    READING_LOG_KEYS = {"currently-reading", "want-to-read", "already-read"}

    # Keys that can be accessed when not logged in
    PUBLIC_KEYS = READING_LOG_KEYS | {"lists", "list"}

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
        self.key = key
        self.readlog = ReadingLog(user=self.user)
        self.lists = self.readlog.lists
        self.counts = self.readlog.reading_log_counts

    def render(self, page=1, sort='desc', list=None):
        if not self.user:
            return render.notfound("User %s" % self.username, create=False)
        logged_in_user = accounts.get_current_user()
        is_logged_in_user = (
            logged_in_user and logged_in_user.key.split('/')[-1] == self.username
        )
        is_public = self.user.preferences().get('public_readlog', 'no') == 'yes'

        data = None

        if is_logged_in_user and self.key in self.ALL_KEYS:
            self.counts.update(PatronBooknotes.get_counts(self.username))
            sponsorships = get_sponsored_editions(self.user)
            self.counts['sponsorships'] = len(sponsorships)

            if self.key == 'sponsorships':
                data = add_availability(
                    web.ctx.site.get_many([
                        '/books/%s' % doc['openlibrary_edition']
                        for doc in sponsorships
                    ])
                ) if sponsorships else None
            elif self.key in self.READING_LOG_KEYS:
                data = add_availability(
                    self.readlog.get_works(
                        self.key, page=page, sort='created', sort_order=sort
                    ),
                    mode="openlibrary_work",
                )
            elif self.key == 'list':
                data = list

            else:
                data = self._prepare_data(logged_in_user)
        elif self.key in self.READING_LOG_KEYS and is_public:
            data = add_availability(
                self.readlog.get_works(
                    self.key, page=page, sort='created', sort_order=sort
                ),
                mode="openlibrary_work",
            )

        if data is not None:
            return render['account/books'](
                data,
                self.key,
                self.counts,
                logged_in_user=logged_in_user,
                user=self.user,
                lists=self.lists,
                public=is_public,
                owners_page=is_logged_in_user,
            )

        raise web.seeother(self.user.key)

    def _prepare_data(
        self,
        logged_in_user,
        page=1,
        username=None,
    ):
        if self.key == 'loans':
            logged_in_user.update_loan_status()
            return borrow.get_loans(logged_in_user)
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

    def __init__(self, user=None):
        self.user = user or accounts.get_current_user()
        self.KEYS = {
            'waitlists': self.get_waitlisted_editions,
            'loans': self.get_loans,
            'want-to-read': self.get_want_to_read,
            'currently-reading': self.get_currently_reading,
            'already-read': self.get_already_read,
        }

    @property
    def lists(self):
        return self.user.get_lists()

    @property
    def sponsorship_counts(self):
        return {
            'sponsorships': len(get_sponsored_editions(self.user))
        }

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
        counts = Bookshelves.count_total_books_logged_by_user_per_shelf(
            self.user.get_username()
        ) if self.user.get_username() else {}
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

    def get_loans(self):
        return borrow.get_loans(self.user)

    def get_waitlist_summary(self):
        return self.user.get_waitinglist()

    def get_waitlisted_editions(self):
        """Gets a list of records corresponding to a user's waitlisted
        editions, fetches all the editions, and then inserts the data
        from each waitlist record (e.g. position in line) into the
        corresponding edition
        """
        waitlists = self.user.get_waitinglist()
        keyed_waitlists = {w['identifier']: w for w in waitlists}
        ocaids = [i['identifier'] for i in waitlists]
        edition_keys = web.ctx.site.things({"type": "/type/edition", "ocaid": ocaids})
        editions = web.ctx.site.get_many(edition_keys)
        for i in range(len(editions)):
            # insert the waitlist_entry corresponding to this edition
            editions[i].waitlist_record = keyed_waitlists[editions[i].ocaid]
        return editions

    def process_logged_books(self, logged_books):
        work_ids = ['/works/OL%sW' % i['work_id'] for i in logged_books]
        works = web.ctx.site.get_many(work_ids)
        for i in range(len(works)):
            # insert the logged edition (if present) and logged date
            works[i].logged_date = logged_books[i]['created']
            works[i].logged_edition = (
                '/books/OL%sM' % logged_books[i]['edition_id']
                if logged_books[i]['edition_id']
                else ''
            )
        return works

    def get_want_to_read(
        self, page=1, limit=RESULTS_PER_PAGE, sort='created', sort_order='desc'
    ):
        return self.process_logged_books(
            Bookshelves.get_users_logged_books(
                self.user.get_username(),
                bookshelf_id=Bookshelves.PRESET_BOOKSHELVES['Want to Read'],
                page=page,
                limit=limit,
                sort=sort + ' ' + sort_order,
            )
        )

    def get_currently_reading(
        self, page=1, limit=RESULTS_PER_PAGE, sort='created', sort_order='desc'
    ):
        return self.process_logged_books(
            Bookshelves.get_users_logged_books(
                self.user.get_username(),
                bookshelf_id=Bookshelves.PRESET_BOOKSHELVES['Currently Reading'],
                page=page,
                limit=limit,
                sort=sort + ' ' + sort_order,
            )
        )

    def get_already_read(
        self, page=1, limit=RESULTS_PER_PAGE, sort='created', sort_order='desc'
    ):
        return self.process_logged_books(
            Bookshelves.get_users_logged_books(
                self.user.get_username(),
                bookshelf_id=Bookshelves.PRESET_BOOKSHELVES['Already Read'],
                page=page,
                limit=limit,
                sort=sort + ' ' + sort_order,
            )
        )

    def get_works(
        self, key, page=1, limit=RESULTS_PER_PAGE, sort='created', sort_order='desc'
    ):
        """
        :rtype: list of openlibrary.plugins.upstream.models.Work
        """
        key = key.lower()
        if key in self.KEYS:
            return self.KEYS[key](
                page=page, limit=limit, sort=sort, sort_order=sort_order
            )
        else:  # must be a list or invalid page!
            # works = web.ctx.site.get_many([ ... ])
            raise


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
        user = user
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
