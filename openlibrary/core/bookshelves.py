import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Final, Literal, TypedDict, cast

import web

from infogami.infobase.utils import flatten
from openlibrary.i18n import gettext as _
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db

logger = logging.getLogger(__name__)

FILTER_BOOK_LIMIT: Final = 30_000


class WorkReadingLogSummary(TypedDict):
    want_to_read: int
    currently_reading: int
    already_read: int


class Bookshelves(db.CommonExtras):
    TABLENAME = "bookshelves_books"
    PRIMARY_KEY = ("username", "work_id", "bookshelf_id")
    PRESET_BOOKSHELVES: MappingProxyType[str, int] = MappingProxyType(
        {
            'Want to Read': 1,
            'Currently Reading': 2,
            'Already Read': 3,
        }
    )
    ALLOW_DELETE_ON_CONFLICT = True

    PRESET_BOOKSHELVES_JSON: MappingProxyType[str, int] = MappingProxyType(
        {
            'want_to_read': 1,
            'currently_reading': 2,
            'already_read': 3,
        }
    )

    @classmethod
    def summary(cls):
        return {
            'total_books_logged': {
                'total': Bookshelves.total_books_logged(),
                'month': Bookshelves.total_books_logged(since=DATE_ONE_MONTH_AGO),
                'week': Bookshelves.total_books_logged(since=DATE_ONE_WEEK_AGO),
            },
            'total_users_logged': {
                'total': Bookshelves.total_unique_users(),
                'month': Bookshelves.total_unique_users(since=DATE_ONE_MONTH_AGO),
                'week': Bookshelves.total_unique_users(since=DATE_ONE_WEEK_AGO),
            },
        }

    @classmethod
    def total_books_logged(
        cls, shelf_ids: list[str] | None = None, since: date | None = None
    ) -> int:
        """Returns (int) number of books logged across all Reading Log shelves (e.g. those
        specified in PRESET_BOOKSHELVES). One may alternatively specify a
        `list` of `shelf_ids` to isolate or span multiple
        shelves. `since` may be used to limit the result to those
        books logged since a specific date. Any python datetime.date
        type should work.

        :param shelf_ids: one or more bookshelf_id values, see also the default values
            specified in PRESET_BOOKSHELVES
        :param since: returns all logged books after date
        """

        oldb = db.get_db()
        query = "SELECT count(*) from bookshelves_books"
        if shelf_ids:
            query += " WHERE bookshelf_id IN ($shelf_ids)"
            if since:
                query += " AND created >= $since"
        elif since:
            query += " WHERE created >= $since"
        results = cast(
            tuple[int],
            oldb.query(query, vars={'since': since, 'shelf_ids': shelf_ids}),
        )
        return results[0]

    @classmethod
    def total_unique_users(cls, since: date | None = None) -> int:
        """Returns the total number of unique users who have logged a
        book. `since` may be provided to only return the number of users after
        a certain datetime.date.
        """
        oldb = db.get_db()
        query = "select count(DISTINCT username) from bookshelves_books"
        if since:
            query += " WHERE created >= $since"
        results = cast(tuple[int], oldb.query(query, vars={'since': since}))
        return results[0]

    @classmethod
    def patrons_who_also_read(cls, work_id: str, limit: int = 15):
        oldb = db.get_db()
        query = "select DISTINCT username from bookshelves_books where work_id=$work_id AND bookshelf_id=3 limit $limit"
        results = oldb.query(query, vars={'work_id': work_id, 'limit': limit})
        # get all patrons with public reading logs
        return [
            p
            for p in web.ctx.site.get_many(
                [f'/people/{r.username}/preferences' for r in results]
            )
            if p.dict().get('notifications', {}).get('public_readlog') == 'yes'
        ]

    @classmethod
    def most_logged_books(
        cls,
        shelf_id: int | None = None,
        limit: int = 10,
        since: date | None = None,
        page: int = 1,
        sort_by_count: bool = True,
        minimum: int = 0,
    ) -> list:
        """Returns a ranked list of work OLIDs (in the form of an integer --
        i.e. OL123W would be 123) which have been most logged by
        users. This query is limited to a specific shelf_id (e.g. 1
        for "Want to Read").
        """
        page = int(page or 1)
        offset = (page - 1) * limit
        oldb = db.get_db()

        query = f"""
            SELECT work_id, count(*) AS cnt
            FROM bookshelves_books
            WHERE
                bookshelf_id {'=$shelf_id' if shelf_id else 'IS NOT NULL'}
                {'AND created >= $since' if since else ''}
            GROUP BY work_id {'HAVING COUNT(*) > $minimum' if minimum else ''}
            {'ORDER BY cnt DESC' if sort_by_count else ''}
            LIMIT $limit
            OFFSET $offset
        """
        data = {
            'shelf_id': shelf_id,
            'limit': limit,
            'offset': offset,
            'since': since,
            'minimum': minimum,
        }

        return list(oldb.query(query, vars=data))

    @classmethod
    def add_solr_works(
        cls, readinglog_items, fields: Iterable[str] | None = None
    ) -> None:
        """Given a list of readinglog_items, such as those returned by
        Bookshelves.most_logged_books, fetch the corresponding Open Library
        book records from solr with availability. This will add a 'work' key
        to each item in readinglog_items.
        """
        from openlibrary.core.lending import add_availability  # noqa: PLC0415
        from openlibrary.plugins.worksearch.code import get_solr_works  # noqa: PLC0415

        # This gives us a dict of all the works representing
        # the logged_books, keyed by work_id
        work_index = get_solr_works(
            {f"/works/OL{i['work_id']}W" for i in readinglog_items},
            fields,
            editions=True,
        )

        add_availability(
            [
                ((w.get('editions') or {}).get('docs') or [None])[0] or w
                for w in work_index.values()
            ]
        )

        # Attach items from the work_index in the order
        # they are represented by the trending logged books
        for i, item in enumerate(readinglog_items):
            key = f"/works/OL{item['work_id']}W"
            if key in work_index:
                readinglog_items[i]['work'] = work_index[key]

    @classmethod
    def count_total_books_logged_by_user(
        cls, username: str, bookshelf_ids: list[str] | None = None
    ) -> int:
        """Counts the (int) total number of books logged by this `username`,
        with the option of limiting the count to specific bookshelves
        by `bookshelf_id`
        """
        return sum(
            cls.count_total_books_logged_by_user_per_shelf(
                username, bookshelf_ids=bookshelf_ids
            ).values()
        )

    @classmethod
    def count_user_books_on_shelf(
        cls,
        username: str,
        bookshelf_id: int,
    ) -> int:
        result = db.get_db().query(
            """
            SELECT count(*) from bookshelves_books
            WHERE bookshelf_id=$bookshelf_id AND username=$username
            """,
            vars={
                'bookshelf_id': bookshelf_id,
                'username': username,
            },
        )
        return result[0].count if result else 0

    @classmethod
    def count_total_books_logged_by_user_per_shelf(
        cls, username: str, bookshelf_ids: list[str] | None = None
    ) -> dict[int, int]:
        """Returns a dict mapping the specified user's bookshelves_ids to the
        number of number of books logged per each shelf, i.e. {bookshelf_id:
        count}. By default, we limit bookshelf_ids to those in PRESET_BOOKSHELVES

        TODO: add `since` to fetch books logged after a certain
        date. Useful for following/subscribing-to users and being
        notified of books they log. Also add to
        count_total_books_logged_by_user
        """
        oldb = db.get_db()
        data = {'username': username}
        _bookshelf_ids = ','.join(
            [str(x) for x in bookshelf_ids or cls.PRESET_BOOKSHELVES.values()]
        )
        query = (
            "SELECT bookshelf_id, count(*) from bookshelves_books WHERE "
            "bookshelf_id=ANY('{" + _bookshelf_ids + "}'::int[]) "
            "AND username=$username GROUP BY bookshelf_id"
        )
        result = oldb.query(query, vars=data)
        return {i['bookshelf_id']: i['count'] for i in result} if result else {}

    # Iterates through a list of solr docs, and for all items with a 'logged edition'
    # it will remove an item with the matching edition key from the list, and add it to
    # doc["editions"]["docs"]
    @classmethod
    def link_editions_to_works(cls, solr_docs: list[web.storage]):
        """
        :param solr_docs: Solr work/edition docs, augmented with reading log data
        """
        linked_docs: list[web.storage] = []
        editions_to_work_doc = {}
        # adds works to linked_docs, recording their edition key and index in docs_dict if present.
        for doc in solr_docs:
            if doc["key"].startswith("/works"):
                linked_docs.append(doc)
                if doc.get("logged_edition"):
                    editions_to_work_doc.update({doc["logged_edition"]: doc})
        # Attaches editions to the works, in second loop-- in case of misperformed order.
        for edition in solr_docs:
            if edition["key"].startswith("/books/"):
                if work_doc := editions_to_work_doc.get(edition["key"]):
                    work_doc.editions = [edition]
                else:
                    # raise error no matching work found
                    logger.error("Error: No work found for edition %s" % edition["key"])
        return linked_docs

    @classmethod
    def add_storage_items_for_redirects(
        cls, reading_log_keys, solr_docs: list[web.Storage]
    ):
        """
        Use reading_log_keys to fill in missing redirected items in the
        the solr_docs query results.

        Solr won't return matches for work keys that have been redirected. Because
        we use Solr to build the lists of storage items that ultimately gets passed
        to the templates, redirected items returned from the reading log DB will
        'disappear' when not returned by Solr. This remedies that by filling in
        dummy works, albeit with the correct work_id.
        """

        from openlibrary.plugins.worksearch.code import run_solr_query  # noqa: PLC0415

        fetched_keys = {doc["key"] for doc in solr_docs}
        missing_keys = {work for (work, _) in reading_log_keys} - fetched_keys

        """
        Provides a proper 1-to-1 connection between work keys and edition keys; needed, in order to fill in the appropriate 'logged_edition' data
        for the correctly pulled work later on, as well as to correctly update the post-redirect version back to the pre_redirect key.
        Without this step, processes may error due to the 'post-redirect key' not actually existing within a user's reading log.
        """
        work_to_edition_keys = {
            work: edition for (work, edition) in reading_log_keys if edition
        }
        edition_to_work_keys = {
            edition: work for (work, edition) in reading_log_keys if edition
        }

        # Here, we add in dummied works for situations in which there is no edition key present, yet the work key accesses a redirect.
        # Ideally, this will be rare, as there's no way to access the relevant information through Solr.
        for key in missing_keys.copy():
            if not work_to_edition_keys.get(key):
                missing_keys.remove(key)
                solr_docs.append(web.storage({"key": key}))

        edition_keys_to_query = [
            work_to_edition_keys[key].split("/")[2] for key in missing_keys
        ]
        fq = f'edition_key:({" OR ".join(edition_keys_to_query)})'
        if not edition_keys_to_query:
            return

        solr_resp = run_solr_query(
            scheme=WorkSearchScheme(),
            param={'q': '*:*'},
            rows=len(edition_keys_to_query),
            fields=list(
                WorkSearchScheme.default_fetched_fields
                | {'subject', 'person', 'place', 'time', 'edition_key'}
            ),
            facet=False,
            extra_params=[("fq", fq)],
        )

        """
        Now, we add the correct 'logged_edition' information to each document retrieved by the query, and substitute the work_key in
        each doc for the original one.
        """
        for doc in solr_resp.docs:
            for edition_key in doc["edition_key"]:
                if pre_redirect_key := edition_to_work_keys.get(
                    '/books/%s' % edition_key
                ):
                    doc["key"] = pre_redirect_key
                    doc["logged_edition"] = work_to_edition_keys.get(pre_redirect_key)
                    solr_docs.append(web.storage(doc))
                    break

    @classmethod
    def add_storage_items_for_deletes(
        cls, reading_log_keys, solr_docs: list[web.Storage]
    ):
        missing = {w for w, e in reading_log_keys} - {doc['key'] for doc in solr_docs}
        # Get them from the DB
        missing_docs = web.ctx.site.get_many(list(missing))

        # Push some dummy books
        for doc in missing_docs:
            if doc.type.key == '/type/delete':
                solr_docs.append(
                    web.storage(
                        {
                            'key': doc.key,
                            'title': _('[Record deleted]'),
                        }
                    )
                )
            else:
                # Should never happen?
                logger.warning(f"Missing item in Solr: {doc.key}")
                solr_docs.append(
                    web.storage(
                        {
                            'key': doc.key,
                            'title': doc.key,
                        }
                    )
                )

    @classmethod
    def get_users_logged_books(
        cls,
        username: str,
        bookshelf_id: int = 0,
        limit: int = 100,
        page: int = 1,  # Not zero-based counting!
        sort: Literal['created asc', 'created desc'] = 'created desc',
        checkin_year: int | None = None,
        q: str = "",
    ) -> Any:  # Circular imports prevent type hinting LoggedBooksData
        """
        Returns LoggedBooksData containing Reading Log database records for books that
        the user has logged. Also allows filtering/searching the reading log shelves,
        and sorting reading log shelves (when not filtering).

        The returned records ultimately come from Solr so that, as much as possible,
        these query results may be used by anything relying on logged book data.

        :param username: who logged this book
        :param bookshelf_id: the ID of the bookshelf, see: PRESET_BOOKSHELVES.
            If bookshelf_id is None, return books from all bookshelves.
        :param q: an optional query string to filter the results.
        """
        from openlibrary.core.models import LoggedBooksData  # noqa: PLC0415
        from openlibrary.plugins.worksearch.code import run_solr_query  # noqa: PLC0415

        shelf_totals = cls.count_total_books_logged_by_user_per_shelf(username)
        oldb = db.get_db()
        page = int(page or 1)
        query_params: dict[str, str | int | None] = {
            'username': username,
            'limit': limit,
            'offset': limit * (page - 1),
            'bookshelf_id': bookshelf_id,
            'checkin_year': checkin_year,
        }

        @dataclass
        class ReadingLogItem:
            """Holds the datetime a book was logged and the edition ID."""

            logged_date: datetime
            edition_id: str

        def add_reading_log_data(
            reading_log_books: list[web.storage], solr_docs: list[web.storage]
        ):
            """
            Adds data from ReadingLogItem to the Solr responses so they have the logged
            date and edition ID.
            """
            # Create a mapping of work keys to ReadingLogItem from the reading log DB.
            reading_log_store: dict[str, ReadingLogItem] = {
                f"/works/OL{book.work_id}W": ReadingLogItem(
                    logged_date=book.created,
                    edition_id=(
                        f"/books/OL{book.edition_id}M"
                        if book.edition_id is not None
                        else ""
                    ),
                )
                for book in reading_log_books
            }

            # Insert {logged_edition} if present and {logged_date} into the Solr work.
            # These dates are not used for sort-by-added-date. The DB handles that.
            # Currently only used in JSON requests.
            for doc in solr_docs:
                if reading_log_record := reading_log_store.get(doc.key):
                    doc.logged_date = reading_log_record.logged_date
                    doc.logged_edition = reading_log_record.edition_id

            return solr_docs

        def get_filtered_reading_log_books(
            q: str, query_params: dict[str, str | int | None], filter_book_limit: int
        ) -> LoggedBooksData:
            """
            Filter reading log books based an a query and return LoggedBooksData.
            This does not work with sorting.

            The reading log DB alone has access to who logged which book to their
            reading log, so we need to get work IDs and logged info from there, query
            Solr for more complete book information, and then put the logged info into
            the Solr response.
            """
            # Filtering by query needs a larger limit as we need (ideally) all of a
            # user's added works from the reading log DB. The logged work IDs are used
            # to query Solr, which searches for matches related to those work IDs.
            query_params["limit"] = filter_book_limit

            query = (
                "SELECT work_id, created, edition_id from bookshelves_books WHERE "
                "bookshelf_id=$bookshelf_id AND username=$username "
                "LIMIT $limit"
            )

            reading_log_books: list[web.storage] = list(
                oldb.query(query, vars=query_params)
            )

            assert len(reading_log_books) <= filter_book_limit

            work_to_edition_keys = {
                '/works/OL%sW' % i['work_id']: '/books/OL%sM' % i['edition_id']
                for i in reading_log_books
            }

            # Separating out the filter query from the call allows us to cleanly edit it, if editions are required.
            filter_query = 'key:(%s)' % " OR ".join(
                '"%s"' % key for key in work_to_edition_keys
            )

            solr_resp = run_solr_query(
                scheme=WorkSearchScheme(),
                param={'q': q},
                offset=query_params["offset"],
                rows=limit,
                facet=False,
                # Putting these in fq allows them to avoid user-query processing, which
                # can be (surprisingly) slow if we have ~20k OR clauses.
                extra_params=[('fq', filter_query)],
            )
            total_results = solr_resp.num_found
            solr_docs = solr_resp.docs
            edition_data = get_solr().get_many(
                [work_to_edition_keys[work["key"]] for work in solr_resp.docs],
                fields=WorkSearchScheme.default_fetched_fields
                | {'subject', 'person', 'place', 'time', 'edition_key'},
            )

            solr_docs.extend(edition_data)

            # Downstream many things expect a list of web.storage docs.
            solr_docs = [web.storage(doc) for doc in solr_resp.docs]
            solr_docs = add_reading_log_data(reading_log_books, solr_docs)
            solr_docs = cls.link_editions_to_works(solr_docs)

            return LoggedBooksData(
                username=username,
                q=q,
                page_size=limit,
                total_results=total_results,
                shelf_totals=shelf_totals,
                docs=solr_docs,
            )

        def get_sorted_reading_log_books(
            query_params: dict[str, str | int | None],
            sort: Literal['created asc', 'created desc'],
            checkin_year: int | None,
        ):
            """
            Get a page of sorted books from the reading log. This does not work with
            filtering/searching the reading log.

            The reading log DB alone has access to who logged which book to their
            reading log, so we need to get work IDs and logged info from there, query
            Solr for more complete book information, and then put the logged info into
            the Solr response.
            """
            if checkin_year:
                query = """
                SELECT b.work_id, b.created, b.edition_id
                FROM bookshelves_books b
                INNER JOIN bookshelves_events e
                ON b.work_id = e.work_id AND b.username = e.username
                WHERE b.username = $username
                AND e.event_date LIKE $checkin_year || '%'
                ORDER BY b.created DESC
                """
            else:
                query = (
                    "SELECT work_id, created, edition_id from bookshelves_books WHERE "
                    "bookshelf_id=$bookshelf_id AND username=$username "
                    f"ORDER BY created {'DESC' if sort == 'created desc' else 'ASC'} "
                    "LIMIT $limit OFFSET $offset"
                )

            if not bookshelf_id:
                query = "SELECT * from bookshelves_books WHERE username=$username"
                # XXX Removing limit, offset, etc from data looks like a bug
                # unrelated / not fixing in this PR.
                query_params = {'username': username}
            reading_log_books: list[web.storage] = list(
                oldb.query(query, vars=query_params)
            )

            reading_log_keys = [
                (
                    ['/works/OL%sW' % i['work_id'], '/books/OL%sM' % i['edition_id']]
                    if i['edition_id']
                    else ['/works/OL%sW' % i['work_id'], ""]
                )
                for i in reading_log_books
            ]

            solr_docs = get_solr().get_many(
                [key for key in flatten(reading_log_keys) if key],
                fields=WorkSearchScheme.default_fetched_fields
                | {'subject', 'person', 'place', 'time', 'edition_key'},
            )

            cls.add_storage_items_for_redirects(reading_log_keys, solr_docs)
            if len(solr_docs) < len(reading_log_keys):
                cls.add_storage_items_for_deletes(reading_log_keys, solr_docs)

            total_results = shelf_totals.get(bookshelf_id, 0)
            solr_docs = add_reading_log_data(reading_log_books, solr_docs)
            solr_docs = cls.link_editions_to_works(solr_docs)

            return LoggedBooksData(
                username=username,
                q=q,
                page_size=limit,
                total_results=total_results,
                shelf_totals=shelf_totals,
                docs=solr_docs,
            )

        if q:
            # checkin_year ignored :(
            return get_filtered_reading_log_books(
                q=q, query_params=query_params, filter_book_limit=FILTER_BOOK_LIMIT
            )
        else:
            return get_sorted_reading_log_books(
                query_params=query_params, sort=sort, checkin_year=checkin_year
            )

    @classmethod
    def iterate_users_logged_books(cls, username: str) -> Iterable[dict]:
        """
        Heavy users will have long lists of books which consume lots of memory and
        cause performance issues.  So, instead of creating a big list, let's repeatedly
        get small lists like get_users_logged_books() and yield one book at a time.
        """
        if not username or not isinstance(username, str):
            raise ValueError(f"username must be a string, not {username}.")
        oldb = db.get_db()
        block = 0
        LIMIT = 100  # Is there an ideal block size?!?

        def get_a_block_of_books() -> list:
            data = {"username": username, "limit": LIMIT, "offset": LIMIT * block}
            query = (
                "SELECT * from bookshelves_books WHERE username=$username "
                "ORDER BY created DESC LIMIT $limit OFFSET $offset"
            )
            return list(oldb.query(query, vars=data))

        while books := get_a_block_of_books():
            block += 1
            yield from books

    @classmethod
    def get_recently_logged_books(
        cls,
        bookshelf_id: str | None = None,
        limit: int = 50,
        page: int = 1,
    ) -> list:
        oldb = db.get_db()
        page = int(page or 1)
        data = {
            'bookshelf_id': bookshelf_id,
            'limit': limit,
            'offset': limit * (page - 1),
        }
        where = "WHERE bookshelf_id=$bookshelf_id " if bookshelf_id else ""
        query = (
            f"SELECT * from bookshelves_books {where} "
            "ORDER BY created DESC LIMIT $limit OFFSET $offset"
        )
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_users_read_status_of_work(cls, username: str, work_id: str) -> int | None:
        """A user can mark a book as (1) want to read, (2) currently reading,
        or (3) already read. Each of these states is mutually
        exclusive. Returns the user's read state of this work, if one
        exists.
        """
        oldb = db.get_db()
        data = {'username': username, 'work_id': int(work_id)}
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = (
            "SELECT bookshelf_id from bookshelves_books WHERE "
            "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
            "AND username=$username AND work_id=$work_id"
        )
        result = list(oldb.query(query, vars=data))
        return result[0].bookshelf_id if result else None

    @classmethod
    def user_has_read_work(cls, username: str, work_id: str) -> bool:
        user_read_status = cls.get_users_read_status_of_work(username, work_id)
        return user_read_status == cls.PRESET_BOOKSHELVES['Already Read']

    @classmethod
    def get_users_read_status_of_works(cls, username: str, work_ids: list[str]) -> list:
        oldb = db.get_db()
        data = {
            'username': username,
            'work_ids': work_ids,
        }
        query = (
            "SELECT work_id, bookshelf_id from bookshelves_books WHERE "
            "username=$username AND "
            "work_id IN $work_ids"
        )
        return list(oldb.query(query, vars=data))

    @classmethod
    def add(
        cls, username: str, bookshelf_id: str, work_id: str, edition_id=None
    ) -> None:
        """Adds a book with `work_id` to user's bookshelf designated by
        `bookshelf_id`"""
        oldb = db.get_db()
        work_id = int(work_id)  # type: ignore
        bookshelf_id = int(bookshelf_id)  # type: ignore
        data = {
            'work_id': work_id,
            'username': username,
        }

        users_status = cls.get_users_read_status_of_work(username, work_id)
        if not users_status:
            return oldb.insert(
                cls.TABLENAME,
                username=username,
                bookshelf_id=bookshelf_id,
                work_id=work_id,
                edition_id=edition_id,
            )
        else:
            where = "work_id=$work_id AND username=$username"
            return oldb.update(
                cls.TABLENAME,
                where=where,
                bookshelf_id=bookshelf_id,
                edition_id=edition_id,
                vars=data,
            )

    @classmethod
    def remove(cls, username: str, work_id: str, bookshelf_id: str | None = None):
        oldb = db.get_db()
        where = {'username': username, 'work_id': int(work_id)}
        if bookshelf_id:
            where['bookshelf_id'] = int(bookshelf_id)

        try:
            return oldb.delete(
                cls.TABLENAME,
                where=('work_id=$work_id AND username=$username'),
                vars=where,
            )
        except Exception:  # we want to catch no entry exists
            return None

    @classmethod
    def get_works_shelves(cls, work_id: str, lazy: bool = False):
        """Bookshelves this work is on"""
        oldb = db.get_db()
        query = f"SELECT * from {cls.TABLENAME} where work_id=$work_id"
        try:
            result = oldb.query(query, vars={'work_id': work_id})
            return result if lazy else list(result)
        except Exception:
            return None

    @classmethod
    def get_num_users_by_bookshelf_by_work_id(cls, work_id: str) -> dict[int, int]:
        """Returns a dict mapping a work_id to the
        number of number of users who have placed that work_id in each shelf,
        i.e. {bookshelf_id: count}.
        """
        oldb = db.get_db()
        query = (
            "SELECT bookshelf_id, count(DISTINCT username) as user_count "
            "from bookshelves_books where"
            " work_id=$work_id"
            " GROUP BY bookshelf_id"
        )
        result = oldb.query(query, vars={'work_id': int(work_id)})
        return {i['bookshelf_id']: i['user_count'] for i in result} if result else {}

    @classmethod
    def get_work_summary(cls, work_id: str) -> WorkReadingLogSummary:
        shelf_id_to_count = Bookshelves.get_num_users_by_bookshelf_by_work_id(work_id)

        result = {}
        # Make sure all the fields are present
        for shelf_name, shelf_id in Bookshelves.PRESET_BOOKSHELVES_JSON.items():
            result[shelf_name] = shelf_id_to_count.get(shelf_id, 0)

        return cast(WorkReadingLogSummary, result)

    @classmethod
    def user_with_most_books(cls) -> list:
        """
        Which super patrons have the most books logged?

        SELECT username, count(*) AS counted from bookshelves_books
          WHERE bookshelf_id=ANY('{1,3,2}'::int[]) GROUP BY username
            ORDER BY counted DESC, username LIMIT 10
        """
        oldb = db.get_db()
        _bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = (
            "SELECT username, count(*) AS counted "
            "FROM bookshelves_books WHERE "
            "bookshelf_id=ANY('{" + _bookshelf_ids + "}'::int[]) "
            "GROUP BY username "
            "ORDER BY counted DESC, username LIMIT 100"
        )
        result = oldb.query(query)
        return list(result)
