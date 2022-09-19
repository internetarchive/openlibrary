import web
from openlibrary.core.db import get_db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings

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


class TestUpdateWorkID:
    @classmethod
    def setup_class(cls):
        web.config.db_parameters = dict(dbn="sqlite", db=":memory:")
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
        web.config.db_parameters = dict(dbn="sqlite", db=":memory:")
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
