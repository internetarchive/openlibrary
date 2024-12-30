import web

from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelvesEvents
from openlibrary.core.db import get_db
from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings
from openlibrary.core.yearly_reading_goals import YearlyReadingGoals

READING_LOG_DDL = """
CREATE TABLE bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
    edition_id integer default null,
    primary key (username, work_id, bookshelf_id)
);
"""

BOOKNOTES_DDL = """
CREATE TABLE booknotes (
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL default -1,
    notes text NOT NULL,
    primary key (username, work_id, edition_id)
);
"""

RATINGS_DDL = """
CREATE TABLE ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer default null,
    primary key (username, work_id)
);
"""

OBSERVATIONS_DDL = """
CREATE TABLE observations (
    work_id INTEGER not null,
    edition_id INTEGER default -1,
    username text not null,
    observation_type INTEGER not null,
    observation_value INTEGER not null,
    primary key (work_id, edition_id, username, observation_value, observation_type)
);
"""

COMMUNITY_EDITS_QUEUE_DDL = """
CREATE TABLE community_edits_queue (
    title text,
    submitter text not null,
    reviewer text default null,
    url text not null,
    status int not null default 1
);
"""

BOOKSHELVES_EVENTS_DDL = """
CREATE TABLE bookshelves_events (
    id serial primary key,
    username text not null,
    work_id integer not null,
    edition_id integer not null,
    event_type integer not null,
    event_date text not null,
    updated timestamp
);
"""

YEARLY_READING_GOALS_DDL = """
CREATE TABLE yearly_reading_goals (
    username text not null,
    year integer not null,
    target integer not null,
    current integer default 0,
    updated timestamp
);
"""


class TestUpdateWorkID:
    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        db = get_db()
        db.query(READING_LOG_DDL)
        db.query(BOOKNOTES_DDL)

    @classmethod
    def teardown_class(cls):
        db = get_db()
        db.query("delete from bookshelves_books;")
        db.query("delete from booknotes;")

    def setup_method(self, method):
        self.db = get_db()
        self.source_book = {
            "username": "@cdrini",
            "work_id": "1",
            "edition_id": "1",
            "bookshelf_id": "1",
        }
        assert not len(list(self.db.select("bookshelves_books")))
        self.db.insert("bookshelves_books", **self.source_book)

    def teardown_method(self):
        self.db.query("delete from bookshelves_books;")

    def test_update_collision(self):
        existing_book = {
            "username": "@cdrini",
            "work_id": "2",
            "edition_id": "2",
            "bookshelf_id": "1",
        }
        self.db.insert("bookshelves_books", **existing_book)
        assert len(list(self.db.select("bookshelves_books"))) == 2
        Bookshelves.update_work_id(
            self.source_book['work_id'], existing_book['work_id']
        )
        assert len(
            list(
                self.db.select(
                    "bookshelves_books",
                    where={"username": "@cdrini", "work_id": "2", "edition_id": "2"},
                )
            )
        ), "failed to update 1 to 2"
        assert not len(
            list(
                self.db.select(
                    "bookshelves_books",
                    where={"username": "@cdrini", "work_id": "1", "edition_id": "1"},
                )
            )
        ), "old work_id 1 present"

    def test_update_simple(self):
        assert len(list(self.db.select("bookshelves_books"))) == 1
        Bookshelves.update_work_id(self.source_book['work_id'], "2")

    def test_no_allow_delete_on_conflict(self):
        rows = [
            {"username": "@mek", "work_id": 1, "edition_id": 1, "notes": "Jimmeny"},
            {"username": "@mek", "work_id": 2, "edition_id": 1, "notes": "Cricket"},
        ]
        self.db.multiple_insert("booknotes", rows)
        resp = Booknotes.update_work_id("1", "2")
        assert resp == {'rows_changed': 0, 'rows_deleted': 0, 'failed_deletes': 1}
        assert [dict(row) for row in self.db.select("booknotes")] == rows


class TestUsernameUpdate:
    READING_LOG_SETUP_ROWS = [
        {
            "username": "@kilgore_trout",
            "work_id": 1,
            "edition_id": 1,
            "bookshelf_id": 1,
        },
        {
            "username": "@kilgore_trout",
            "work_id": 2,
            "edition_id": 2,
            "bookshelf_id": 1,
        },
        {
            "username": "@billy_pilgrim",
            "work_id": 1,
            "edition_id": 1,
            "bookshelf_id": 2,
        },
    ]
    BOOKNOTES_SETUP_ROWS = [
        {"username": "@kilgore_trout", "work_id": 1, "edition_id": 1, "notes": "Hello"},
        {"username": "@billy_pilgrim", "work_id": 1, "edition_id": 1, "notes": "World"},
    ]
    RATINGS_SETUP_ROWS = [
        {"username": "@kilgore_trout", "work_id": 1, "edition_id": 1, "rating": 4},
        {"username": "@billy_pilgrim", "work_id": 5, "edition_id": 1, "rating": 2},
    ]
    OBSERVATIONS_SETUP_ROWS = [
        {
            "username": "@kilgore_trout",
            "work_id": 1,
            "edition_id": 3,
            "observation_type": 1,
            "observation_value": 2,
        },
        {
            "username": "@billy_pilgrim",
            "work_id": 2,
            "edition_id": 4,
            "observation_type": 4,
            "observation_value": 1,
        },
    ]

    EDITS_QUEUE_SETUP_ROWS = [
        {
            "title": "One Fish, Two Fish, Red Fish, Blue Fish",
            "submitter": "@kilgore_trout",
            "reviewer": None,
            "url": "/works/merge?records=OL1W,OL2W,OL3W",
            "status": 1,
        },
        {
            "title": "The Lorax",
            "submitter": "@kilgore_trout",
            "reviewer": "@billy_pilgrim",
            "url": "/works/merge?records=OL4W,OL5W,OL6W",
            "status": 2,
        },
        {
            "title": "Green Eggs and Ham",
            "submitter": "@eliot_rosewater",
            "reviewer": None,
            "url": "/works/merge?records=OL10W,OL11W,OL12W,OL13W",
            "status": 1,
        },
    ]

    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        db = get_db()
        db.query(RATINGS_DDL)
        db.query(OBSERVATIONS_DDL)
        db.query(COMMUNITY_EDITS_QUEUE_DDL)

    def setup_method(self):
        self.db = get_db()
        self.db.multiple_insert("bookshelves_books", self.READING_LOG_SETUP_ROWS)
        self.db.multiple_insert("booknotes", self.BOOKNOTES_SETUP_ROWS)
        self.db.multiple_insert("ratings", self.RATINGS_SETUP_ROWS)
        self.db.multiple_insert("observations", self.OBSERVATIONS_SETUP_ROWS)

    def teardown_method(self):
        self.db.query("delete from bookshelves_books;")
        self.db.query("delete from booknotes;")
        self.db.query("delete from ratings;")
        self.db.query("delete from observations;")

    def test_delete_all_by_username(self):
        assert len(list(self.db.select("bookshelves_books"))) == 3
        Bookshelves.delete_all_by_username("@kilgore_trout")
        assert len(list(self.db.select("bookshelves_books"))) == 1

        assert len(list(self.db.select("booknotes"))) == 2
        Booknotes.delete_all_by_username('@kilgore_trout')
        assert len(list(self.db.select("booknotes"))) == 1

        assert len(list(self.db.select("ratings"))) == 2
        Ratings.delete_all_by_username("@kilgore_trout")
        assert len(list(self.db.select("ratings"))) == 1

        assert len(list(self.db.select("observations"))) == 2
        Observations.delete_all_by_username("@kilgore_trout")
        assert len(list(self.db.select("observations"))) == 1

    def test_update_username(self):
        self.db.multiple_insert("community_edits_queue", self.EDITS_QUEUE_SETUP_ROWS)
        before_where = {"username": "@kilgore_trout"}
        after_where = {"username": "@anonymous"}

        assert len(list(self.db.select("bookshelves_books", where=before_where))) == 2
        Bookshelves.update_username("@kilgore_trout", "@anonymous")
        assert len(list(self.db.select("bookshelves_books", where=before_where))) == 0
        assert len(list(self.db.select("bookshelves_books", where=after_where))) == 2

        assert len(list(self.db.select("booknotes", where=before_where))) == 1
        Booknotes.update_username("@kilgore_trout", "@anonymous")
        assert len(list(self.db.select("booknotes", where=before_where))) == 0
        assert len(list(self.db.select("booknotes", where=after_where))) == 1

        assert len(list(self.db.select("ratings", where=before_where))) == 1
        Ratings.update_username("@kilgore_trout", "@anonymous")
        assert len(list(self.db.select("ratings", where=before_where))) == 0
        assert len(list(self.db.select("ratings", where=after_where))) == 1

        assert len(list(self.db.select("observations", where=before_where))) == 1
        Observations.update_username("@kilgore_trout", "@anonymous")
        assert len(list(self.db.select("observations", where=before_where))) == 0
        assert len(list(self.db.select("observations", where=after_where))) == 1

        results = self.db.select(
            "community_edits_queue", where={"submitter": "@kilgore_trout"}
        )
        assert len(list(results)) == 2

        CommunityEditsQueue.update_submitter_name('@kilgore_trout', '@anonymous')
        results = self.db.select(
            "community_edits_queue", where={"submitter": "@kilgore_trout"}
        )
        assert len(list(results)) == 0

        results = self.db.select(
            "community_edits_queue", where={"submitter": "@anonymous"}
        )
        assert len(list(results)) == 2

        self.db.query('delete from community_edits_queue;')


class TestCheckIns:
    BOOKSHELVES_EVENTS_SETUP_ROWS = [
        {
            "id": 1,
            "username": "@kilgore_trout",
            "work_id": 1,
            "edition_id": 2,
            "event_type": 1,
            "event_date": "2022-04-17",
        },
        {
            "id": 2,
            "username": "@kilgore_trout",
            "work_id": 1,
            "edition_id": 2,
            "event_type": 2,
            "event_date": "2022-05-10",
        },
        {
            "id": 3,
            "username": "@kilgore_trout",
            "work_id": 1,
            "edition_id": 2,
            "event_type": 3,
            "event_date": "2022-06-20",
        },
        {
            "id": 4,
            "username": "@billy_pilgrim",
            "work_id": 3,
            "edition_id": 4,
            "event_type": 1,
            "event_date": "2020",
        },
        {
            "id": 5,
            "username": "@eliot_rosewater",
            "work_id": 3,
            "edition_id": 4,
            "event_type": 3,
            "event_date": "2019-08-20",
        },
        {
            "id": 6,
            "username": "@eliot_rosewater",
            "work_id": 3,
            "edition_id": 4,
            "event_type": 3,
            "event_date": "2019-10",
        },
    ]

    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        db = get_db()
        db.query(BOOKSHELVES_EVENTS_DDL)

    def setup_method(self):
        self.db = get_db()
        self.db.multiple_insert(
            'bookshelves_events', self.BOOKSHELVES_EVENTS_SETUP_ROWS
        )

    def teardown_method(self):
        self.db.query("delete from bookshelves_events;")

    def test_create_event(self):
        assert len(list(self.db.select('bookshelves_events'))) == 6
        assert (
            len(
                list(
                    self.db.select(
                        'bookshelves_events', where={"username": "@billy_pilgrim"}
                    )
                )
            )
            == 1
        )
        BookshelvesEvents.create_event('@billy_pilgrim', 5, 6, '2022-01', event_type=1)
        assert len(list(self.db.select('bookshelves_events'))) == 7
        assert (
            len(
                list(
                    self.db.select(
                        'bookshelves_events', where={"username": "@billy_pilgrim"}
                    )
                )
            )
            == 2
        )

    def test_select_all_by_username(self):
        assert len(list(self.db.select('bookshelves_events'))) == 6
        assert (
            len(
                list(
                    self.db.select(
                        'bookshelves_events', where={"username": "@kilgore_trout"}
                    )
                )
            )
            == 3
        )
        BookshelvesEvents.create_event(
            '@kilgore_trout', 7, 8, '2011-01-09', event_type=1
        )
        assert len(list(self.db.select('bookshelves_events'))) == 7
        assert (
            len(
                list(
                    self.db.select(
                        'bookshelves_events', where={"username": "@kilgore_trout"}
                    )
                )
            )
            == 4
        )

    def test_update_event_date(self):
        assert len(list(self.db.select('bookshelves_events', where={"id": 1}))) == 1
        row = self.db.select('bookshelves_events', where={"id": 1})[0]
        assert row['event_date'] == "2022-04-17"
        new_date = "1999-01-01"
        BookshelvesEvents.update_event_date(1, new_date)
        row = self.db.select('bookshelves_events', where={"id": 1})[0]
        assert row['event_date'] == new_date

    def test_delete_by_id(self):
        assert len(list(self.db.select('bookshelves_events'))) == 6
        assert len(list(self.db.select('bookshelves_events', where={"id": 1}))) == 1
        BookshelvesEvents.delete_by_id(1)
        assert len(list(self.db.select('bookshelves_events'))) == 5
        assert len(list(self.db.select('bookshelves_events', where={"id": 1}))) == 0

    def test_delete_by_username(self):
        assert len(list(self.db.select('bookshelves_events'))) == 6
        assert (
            len(
                list(
                    self.db.select(
                        'bookshelves_events', where={"username": "@kilgore_trout"}
                    )
                )
            )
            == 3
        )
        BookshelvesEvents.delete_by_username('@kilgore_trout')
        assert len(list(self.db.select('bookshelves_events'))) == 3
        assert (
            len(
                list(
                    self.db.select(
                        'bookshelves_events', where={"username": "@kilgore_trout"}
                    )
                )
            )
            == 0
        )

    def test_get_latest_event_date(self):
        assert (
            BookshelvesEvents.get_latest_event_date('@eliot_rosewater', 3, 3)[
                'event_date'
            ]
            == "2019-10"
        )
        assert (
            BookshelvesEvents.get_latest_event_date('@eliot_rosewater', 3, 3)['id'] == 6
        )
        assert BookshelvesEvents.get_latest_event_date('@eliot_rosewater', 3, 1) is None


class TestYearlyReadingGoals:
    SETUP_ROWS = [
        {
            'username': '@billy_pilgrim',
            'year': 2022,
            'target': 5,
            'current': 6,
        },
        {
            'username': '@billy_pilgrim',
            'year': 2023,
            'target': 7,
            'current': 0,
        },
        {
            'username': '@kilgore_trout',
            'year': 2022,
            'target': 4,
            'current': 4,
        },
    ]

    TABLENAME = YearlyReadingGoals.TABLENAME

    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": 'sqlite', "db": ':memory:'}
        db = get_db()
        db.query(YEARLY_READING_GOALS_DDL)

    def setup_method(self):
        self.db = get_db()
        self.db.multiple_insert(self.TABLENAME, self.SETUP_ROWS)

    def teardown_method(self):
        self.db.query('delete from yearly_reading_goals')

    def test_create(self):
        assert len(list(self.db.select(self.TABLENAME))) == 3
        assert (
            len(
                list(
                    self.db.select(self.TABLENAME, where={'username': '@kilgore_trout'})
                )
            )
            == 1
        )
        YearlyReadingGoals.create('@kilgore_trout', 2023, 5)
        assert (
            len(
                list(
                    self.db.select(self.TABLENAME, where={'username': '@kilgore_trout'})
                )
            )
            == 2
        )
        new_row = list(
            self.db.select(
                self.TABLENAME, where={'username': '@kilgore_trout', 'year': 2023}
            )
        )
        assert len(new_row) == 1
        assert new_row[0]['current'] == 0

    def test_select_by_username_and_year(self):
        assert (
            len(YearlyReadingGoals.select_by_username_and_year('@billy_pilgrim', 2022))
            == 1
        )

    def test_has_reached_goal(self):
        assert YearlyReadingGoals.has_reached_goal('@billy_pilgrim', 2022)
        assert not YearlyReadingGoals.has_reached_goal('@billy_pilgrim', 2023)
        assert YearlyReadingGoals.has_reached_goal('@kilgore_trout', 2022)

    def test_update_current_count(self):
        assert (
            next(
                iter(
                    self.db.select(
                        self.TABLENAME,
                        where={'username': '@billy_pilgrim', 'year': 2023},
                    )
                )
            )['current']
            == 0
        )
        YearlyReadingGoals.update_current_count('@billy_pilgrim', 2023, 10)
        assert (
            next(
                iter(
                    self.db.select(
                        self.TABLENAME,
                        where={'username': '@billy_pilgrim', 'year': 2023},
                    )
                )
            )['current']
            == 10
        )

    def test_update_target(self):
        assert (
            next(
                iter(
                    self.db.select(
                        self.TABLENAME,
                        where={'username': '@billy_pilgrim', 'year': 2023},
                    )
                )
            )['target']
            == 7
        )
        YearlyReadingGoals.update_target('@billy_pilgrim', 2023, 14)
        assert (
            next(
                iter(
                    self.db.select(
                        self.TABLENAME,
                        where={'username': '@billy_pilgrim', 'year': 2023},
                    )
                )
            )['target']
            == 14
        )

    def test_delete_by_username(self):
        assert (
            len(
                list(
                    self.db.select(self.TABLENAME, where={'username': '@billy_pilgrim'})
                )
            )
            == 2
        )
        YearlyReadingGoals.delete_by_username('@billy_pilgrim')
        assert (
            len(
                list(
                    self.db.select(self.TABLENAME, where={'username': '@billy_pilgrim'})
                )
            )
            == 0
        )
