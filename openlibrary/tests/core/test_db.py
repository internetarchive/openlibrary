import web
from openlibrary.core.db import get_db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.booknotes import Booknotes

class TestUpdateWorkID:

    @classmethod
    def setup_class(cls):
        web.config.db_parameters = dict(dbn="sqlite", db=":memory:")
        db = get_db()
        db.query("""
        CREATE TABLE bookshelves_books (
        username text NOT NULL,
        work_id integer NOT NULL,
        bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
        edition_id integer default null,
        primary key (username, work_id, bookshelf_id)
        );""")

        db.query(
            """
            CREATE TABLE booknotes (
                username text NOT NULL,
                work_id integer NOT NULL,
                edition_id integer NOT NULL default -1,
                notes text NOT NULL,
                primary key (username, work_id, edition_id)
            );
            """
        )

    def setup_method(self, method):
        self.db = get_db()
        self.source_book = {
            "username": "@cdrini",
            "work_id": "1",
            "edition_id": "1",
            "bookshelf_id": "1"
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
            "bookshelf_id": "1"
        }
        self.db.insert("bookshelves_books", **existing_book)
        assert len(list(self.db.select("bookshelves_books"))) == 2
        Bookshelves.update_work_id(self.source_book['work_id'], existing_book['work_id'])
        assert len(list(self.db.select("bookshelves_books", where={
            "username": "@cdrini",
            "work_id": "2",
            "edition_id": "2"
        }))), "failed to update 1 to 2"
        assert not len(list(self.db.select("bookshelves_books", where={
            "username": "@cdrini",
            "work_id": "1",
            "edition_id": "1"
        }))), "old work_id 1 present"


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
