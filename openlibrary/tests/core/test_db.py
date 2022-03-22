import web
from openlibrary.core.db import CommonExtras, get_db

class TestUpdateWorkID:

    def setup_method(self, method):
        web.config.db_parameters = dict(dbn="sqlite", db=":memory:")
        self.db = get_db()
        self.db.query("""
        CREATE TABLE bookshelves_books (
        username text NOT NULL,
        work_id integer NOT NULL,
        bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
        edition_id integer default null,
        primary key (username, work_id, bookshelf_id)
        );
        """)

    def test_update(self):
        CommonExtras.TABLENAME = "bookshelves_books"
        book1 = {
            "username": "@cdrini",
            "work_id": "1",
            "edition_id": "1",
            "bookshelf_id": "1"
        }
        assert not len(list(self.db.select("bookshelves_books", where=book1)))
        self.db.insert("bookshelves_books", **book1)
        assert len(list(self.db.select("bookshelves_books", where=book1))) == 1

        # [x] 1 -> 2 (no 2 exists in db) + many case
        #     1 -> 2 (2 does exist in db) + many case
        #        1 -> 2 (2 has different edition than 1)
        CommonExtras.update_work_id("1", "2")
        assert len(list(self.db.select("bookshelves_books", where={
            "username": "@cdrini",
            "work_id": "2",
            "edition_id": "1"
        }))), "failed to update 1 to 2"
        assert not len(list(self.db.select("bookshelves_books", where={
            "username": "@cdrini",
            "work_id": "1",
            "edition_id": "1"
        }))), "old value 1 present"
