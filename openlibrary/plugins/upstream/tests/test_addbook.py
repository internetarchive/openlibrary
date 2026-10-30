"""py.test tests for addbook"""

import pytest
import web

from openlibrary import accounts
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.utils.request_context import site as site_context

from .. import addbook, models


def setup_mock_site():
    web.ctx.site = MockSite()
    site_context.set(web.ctx.site)
    models.setup()


def strip_nones(d):
    return {k: v for k, v in d.items() if v is not None}


def mock_user():
    return type(
        "MockUser",
        (object,),
        {
            "is_admin": lambda slf: False,
            "is_super_librarian": lambda slf: False,
            "is_super_librarian_or_higher": lambda slf: slf.is_admin() or slf.is_super_librarian(),
            "is_librarian": lambda slf: False,
            "is_usergroup_member": lambda slf, grp: False,
        },
    )()


class TestSaveBookHelper:
    def setup_method(self, method):
        setup_mock_site()

    def test_authors(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        s = addbook.SaveBookHelper(None, None)

        def f(data):
            return strip_nones(s.process_work(web.storage(data)))

        assert f({}) == {}
        assert f({"authors": []}) == {}
        assert f({"authors": [{"type": "/type/author_role"}]}) == {}

    def test_editing_orphan_creates_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                }
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "",
                "work--title": "Original Edition Title",
                "edition--title": "Original Edition Title",
            }
        )

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 2
        assert web.ctx.site.get("/works/OL1W") is not None
        assert web.ctx.site.get("/works/OL1W").title == "Original Edition Title"

    def test_never_create_an_orphan(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")
        work = web.ctx.site.get("/works/OL1W")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)
        print(web.ctx.site.get("/books/OL1M").title)
        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL1W"

    def test_moving_orphan(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                }
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "",
                "work--title": "Original Edition Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 1
        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL1W"

    def test_moving_orphan_ignores_work_edits(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                },
            ]
        )
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "",
                "work--title": "Modified Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"

    def test_editing_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Modified Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Modified Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Original Edition Title"

    def test_editing_edition(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Modified Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Modified Edition Title"

    def test_process_edition_treats_empty_weight_and_dimensions_as_cleared(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        s = addbook.SaveBookHelper(None, None)
        edition = s.process_edition(web.storage({"weight": None, "physical_dimensions": None}))

        assert edition.weight is None
        assert edition.physical_dimensions is None

    def test_clearing_weight_and_dimensions_without_units(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                    "weight": "0.000",
                    "physical_dimensions": "9 x 6 x 1 inches",
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")
        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Modified Edition Title",
                "edition--works--0--key": "/works/OL1W",
                "edition--weight--value": "",
                "edition--physical_dimensions--height": "",
                "edition--physical_dimensions--width": "",
                "edition--physical_dimensions--depth": "",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        saved_edition = web.ctx.site.get("/books/OL1M")
        assert saved_edition.title == "Modified Edition Title"
        assert saved_edition.weight is None
        assert saved_edition.physical_dimensions is None

    def test_editing_work_and_edition(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Modified Work Title",
                "edition--title": "Modified Edition Title",
                "edition--works--0--key": "/works/OL1W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Modified Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Modified Edition Title"

    def test_moving_edition(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Original Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL2W",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL2W"

    def test_moving_edition_ignores_changes_to_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL1W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL1W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL1W",
                "work--title": "Modified Work Title",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "/works/OL2W",  # Changing work
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"

    def test_moving_edition_to_new_work(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL100W",
                    "title": "Original Work Title",
                    "authors": [{"key": "/authors/OL123A"}],
                    "subjects": [{"key": "/subjects/Horror"}],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL100W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL100W",
                "work--title": "FOO BAR",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "__new__",
            }
        )

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 3
        # Should create new work with edition data
        assert web.ctx.site.get("/works/OL1W") is not None
        new_work = web.ctx.site.get("/books/OL1M").works[0]
        assert new_work.key == "/works/OL1W"
        assert new_work.title == "Original Edition Title"
        # Should ignore edits to work data
        assert web.ctx.site.get("/works/OL100W").title == "Original Work Title"
        # Should ignore authors/subjects by default
        assert not new_work.authors
        assert not new_work.subjects

    def test_moving_edition_to_new_work_can_copy_data(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL100W",
                    "title": "Original Work Title",
                    "authors": [{"key": "/authors/OL123A"}],
                    "subjects": [{"key": "/subjects/Horror"}],
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL100W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL100W",
                "work--title": "FOO BAR",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "__new__",
                "new_work_options--copy_authors": "yes",
                "new_work_options--copy_subjects": "yes",
            }
        )
        # But if we pass in the authors/subjects, it should use them
        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 3
        old_work = web.ctx.site.get("/works/OL100W")
        new_work = web.ctx.site.get("/books/OL1M").works[0]
        assert new_work.key != old_work.key
        # Should ignore authors/subjects by default
        assert new_work.authors == old_work.authors
        assert new_work.subjects == old_work.subjects

    def test_moving_edition_to_new_work_copy_when_none(self, monkeypatch):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many(
            [
                {
                    "type": {"key": "/type/work"},
                    "key": "/works/OL100W",
                    "title": "Original Work Title",
                },
                {
                    "type": {"key": "/type/edition"},
                    "key": "/books/OL1M",
                    "title": "Original Edition Title",
                    "works": [{"key": "/works/OL100W"}],
                },
            ]
        )

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage(
            {
                "work--key": "/works/OL100W",
                "work--title": "FOO BAR",
                "edition--title": "Original Edition Title",
                "edition--works--0--key": "__new__",
                "new_work_options--copy_authors": "yes",
                "new_work_options--copy_subjects": "yes",
            }
        )
        # But if we pass in the authors/subjects, it should use them
        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 3
        old_work = web.ctx.site.get("/works/OL100W")
        new_work = web.ctx.site.get("/books/OL1M").works[0]
        assert new_work.key != old_work.key
        # Should ignore authors/subjects by default
        assert not new_work.authors
        assert not new_work.subjects


class TestDaisyPage:
    def setup_method(self, method):
        setup_mock_site()

    def test_redirects_to_archive_item_for_edition_with_ocaid(self, monkeypatch):
        web.ctx.site.save(
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Accessible Book",
                "ocaid": "testitem00archive",
            }
        )

        redirects = []

        def seeother(url):
            redirects.append(url)
            raise RuntimeError("redirect")

        monkeypatch.setattr(addbook.web, "seeother", seeother)

        with pytest.raises(RuntimeError, match="redirect"):
            addbook.daisy().GET("/books/OL1M")
        assert redirects == ["https://archive.org/details/testitem00archive"]

    def test_redirect_escapes_archive_item_identifier(self, monkeypatch):
        web.ctx.site.save(
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Accessible Book",
                "ocaid": "test item/archive",
            }
        )

        redirects = []

        def seeother(url):
            redirects.append(url)
            raise RuntimeError("redirect")

        monkeypatch.setattr(addbook.web, "seeother", seeother)

        with pytest.raises(RuntimeError, match="redirect"):
            addbook.daisy().GET("/books/OL1M")
        assert redirects == ["https://archive.org/details/test%20item%2Farchive"]


class TestMakeWork:
    def setup_method(self, method):
        setup_mock_site()

    def test_make_author_adds_the_correct_key(self):
        author_key = "OL123A"
        author_name = "Samuel Clemens"
        author = web.ctx.site.new(
            "/authors/OL123A",
            {"key": author_key, "type": {"key": "/type/author"}, "name": author_name},
        )
        assert addbook.make_author(author_key, author_name) == author

    def test_make_work_does_indeed_make_a_work(self):
        doc = {
            "author_key": ["OL123A"],
            "author_name": ["Samuel Clemens"],
            "key": "/works/OL123W",
            "type": "work",
            "language": ["eng"],
            "title": "The Celebrated Jumping Frog of Calaveras County",
        }

        author_key = "OL123A"
        author_name = "Samuel Clemens"
        author = web.ctx.site.new(
            "/authors/OL123A",
            {"key": author_key, "type": {"key": "/type/author"}, "name": author_name},
        )

        web_doc = web.Storage(
            {
                "author_key": ["OL123A"],
                "author_name": ["Samuel Clemens"],
                "key": "/works/OL123W",
                "type": "work",
                "language": ["eng"],
                "title": "The Celebrated Jumping Frog of Calaveras County",
                "authors": [author],
                "cover_url": "/static/images/icons/avatar_book-sm.png",
                "ia": [],
                "first_publish_year": None,
            }
        )

        assert addbook.make_work(doc) == web_doc

    def test_make_work_handles_no_author(self):
        doc = {
            "key": "/works/OL123W",
            "type": "work",
            "language": ["eng"],
            "title": "The Celebrated Jumping Frog of Calaveras County",
        }

        web_doc = web.Storage(
            {
                "key": "/works/OL123W",
                "type": "work",
                "language": ["eng"],
                "title": "The Celebrated Jumping Frog of Calaveras County",
                "authors": [],
                "cover_url": "/static/images/icons/avatar_book-sm.png",
                "ia": [],
                "first_publish_year": None,
            }
        )

        assert addbook.make_work(doc) == web_doc


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("", True),
        ("https://example.com/book", True),
        ("http://example.com", True),
        ("javascript:alert(1)", False),
        ("ftp://example.com/book", False),
        ("not a url", False),
        ("https://", False),
        ("//example.com/book", False),
    ],
)
def test_is_valid_web_book_url(url, expected):
    assert addbook.is_valid_web_book_url(url) is expected
