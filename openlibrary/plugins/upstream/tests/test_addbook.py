"""py.test tests for addbook"""

from unittest.mock import Mock

import pytest
import web

from infogami.utils import delegate
from openlibrary import accounts
from openlibrary.core.models import User
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.utils.request_context import site

from .. import addbook


@pytest.fixture(autouse=True)
def initialized_site(monkeypatch):
    current = MockSite()
    monkeypatch.setattr(web.ctx, "site", current, raising=False)
    token = site.set(current)
    yield
    site.reset(token)


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
            "can_edit_ocaid": User.can_edit_ocaid,
        },
    )()


class TestSaveBookHelper:
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

    @pytest.mark.parametrize(
        ("current_ocaid", "submitted_ocaid"),
        [
            (None, "newitem00arch"),
            ("olditem00arch", "newitem00arch"),
            ("olditem00arch", None),
        ],
    )
    def test_ocaid_changes_need_admin(self, monkeypatch, current_ocaid, submitted_ocaid):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        s = addbook.SaveBookHelper(None, self._edition_with_ocaid(current_ocaid))

        with pytest.raises(addbook.ValidationException):
            s._prevent_ocaid_deletion(self._ocaid_form(submitted_ocaid))

    @pytest.mark.parametrize("current_ocaid", [None, "olditem00arch"])
    def test_top_level_ocaid_field_needs_admin(self, monkeypatch, current_ocaid):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        s = addbook.SaveBookHelper(None, self._edition_with_ocaid(current_ocaid))
        form = self._ocaid_form(current_ocaid)
        form.ocaid = "newitem00arch"

        with pytest.raises(addbook.ValidationException):
            s._prevent_ocaid_deletion(form)

    @pytest.mark.parametrize("ocaid", [None, "olditem00arch"])
    def test_unchanged_ocaid_is_allowed(self, monkeypatch, ocaid):
        monkeypatch.setattr(accounts, "get_current_user", mock_user)
        s = addbook.SaveBookHelper(None, self._edition_with_ocaid(ocaid))

        s._prevent_ocaid_deletion(self._ocaid_form(ocaid))

    @pytest.mark.parametrize(("is_admin", "is_super_librarian", "allowed"), [(True, False, True), (False, True, False)])
    def test_only_admins_can_add_ocaid(self, monkeypatch, is_admin, is_super_librarian, allowed):
        def user():
            u = mock_user()
            u.is_admin = lambda: is_admin
            u.is_super_librarian = lambda: is_super_librarian
            return u

        monkeypatch.setattr(accounts, "get_current_user", user)
        s = addbook.SaveBookHelper(None, self._edition_with_ocaid(None))

        if allowed:
            s._prevent_ocaid_deletion(self._ocaid_form("newitem00arch"))
        else:
            with pytest.raises(addbook.ValidationException):
                s._prevent_ocaid_deletion(self._ocaid_form("newitem00arch"))

    @staticmethod
    def _edition_with_ocaid(ocaid):
        doc = {"type": {"key": "/type/edition"}, "key": "/books/OL1M", "title": "Edition"}
        if ocaid:
            doc["ocaid"] = ocaid
        web.ctx.site.save(doc)
        return web.ctx.site.get("/books/OL1M")

    @staticmethod
    def _ocaid_form(ocaid):
        identifiers = [{"name": "ocaid", "value": ocaid}] if ocaid else []
        return web.storage(identifiers=identifiers)


class TestAddBookOcaid:
    @pytest.fixture
    def post(self, monkeypatch):
        """POST /books/add with an ocaid; returns render_template's args, or None if it got past the ocaid check."""

        def _post(user_factory):
            monkeypatch.setattr(accounts, "get_current_user", user_factory)
            monkeypatch.setattr(web, "input", lambda **kw: web.storage(kw, book_title="Book", id_name="ocaid", id_value="newitem00arch"))
            monkeypatch.setattr(addbook.spamcheck, "is_spam", lambda *a, **kw: False)
            monkeypatch.setattr(addbook, "render_template", lambda *a, **kw: a)

            class PastOcaidCheck(Exception):
                pass

            def past_check(*a, **kw):
                raise PastOcaidCheck

            monkeypatch.setattr(addbook.utils, "unflatten", past_check)
            try:
                # `addbook.addbook` is shadowed by a later class of the same name, so look the page up by path.
                return delegate.pages["/books/add"][None]().POST()
            except PastOcaidCheck:
                return None

        return _post

    def test_non_admin_cannot_add_ocaid(self, post):
        assert post(mock_user)[0] == "message.html"

    def test_admin_can_add_ocaid(self, post):
        def admin():
            u = mock_user()
            u.is_admin = lambda: True
            return u

        assert post(admin) is None


class TestDaisyPage:
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


class TestEditSavedFlash:
    """``add_edit_saved_flash``: the thank-you every save gets, and the Tasks pitch at most once a day."""

    @pytest.fixture
    def saved(self, monkeypatch):
        seen = web.storage(flash=[], cookies={}, set_cookies={})
        monkeypatch.setattr(addbook, "add_flash_message", lambda type, message: seen.flash.append((type, message)))
        monkeypatch.setattr(web, "cookies", lambda: seen.cookies)
        monkeypatch.setattr(web, "setcookie", lambda name, value, expires="": seen.set_cookies.update({name: expires}))
        monkeypatch.setattr(addbook.pitch, "encode", lambda book_keys=(): "most-read-2026-11:485")
        return seen

    def test_pitches_tasks_and_marks_it_seen_for_a_day(self, saved):
        addbook.add_edit_saved_flash("/books/OL1M")
        assert saved.flash == [("edit-saved", "most-read-2026-11:485")]
        assert saved.set_cookies == {addbook.pitch.SEEN_COOKIE: 24 * 60 * 60}

    @pytest.mark.parametrize("cookie", [addbook.pitch.SEEN_COOKIE, addbook.pitch.dismiss_cookie()])
    def test_only_thanks_once_seen_today_or_closed(self, saved, cookie):
        saved.cookies[cookie] = "1"
        addbook.add_edit_saved_flash("/books/OL1M")
        assert saved.flash == [("edit-saved", "")]
        assert saved.set_cookies == {}

    def test_nothing_to_pitch_leaves_tomorrows_chance_alone(self, saved, monkeypatch):
        monkeypatch.setattr(addbook.pitch, "encode", lambda book_keys=(): "")
        addbook.add_edit_saved_flash()
        assert saved.flash == [("edit-saved", "")]
        assert saved.set_cookies == {}

    def test_a_broken_cache_still_thanks_the_editor(self, saved, monkeypatch):
        def broken(book_keys=()):
            raise RuntimeError("memcache is down")

        monkeypatch.setattr(addbook.pitch, "encode", broken)
        addbook.add_edit_saved_flash("/books/OL1M")
        assert saved.flash == [("edit-saved", "")]


class TestSiteContextMigration:
    @pytest.fixture(params=["missing", "different"])
    def current(self, mock_site, monkeypatch, request):
        # Normal mock_site sets both handles; separate them to catch legacy reads.
        if request.param == "missing":
            monkeypatch.delitem(web.ctx, "site")
        else:
            monkeypatch.setitem(web.ctx, "site", MockSite())
        monkeypatch.setattr(mock_site, "can_write", Mock(return_value=True), raising=False)
        monkeypatch.setattr(mock_site, "seq", Mock(next_value=Mock(return_value=17)), raising=False)
        for key, value in {"home": "http://openlibrary.org", "path": "/books/add", "fullpath": "/books/add", "lang": "en"}.items():
            monkeypatch.setitem(web.ctx, key, value)
        monkeypatch.setattr(addbook, "get_recaptcha", lambda: None)
        monkeypatch.setattr(accounts, "get_current_user", lambda: Mock(can_edit_ocaid=lambda: True))
        monkeypatch.setattr(addbook.spamcheck, "is_spam", lambda *args, **kwargs: False)
        monkeypatch.setattr(addbook, "add_edit_saved_flash", lambda *keys: None)
        monkeypatch.setattr(addbook.utils, "get_message", lambda key: "Saved book")
        return mock_site

    @pytest.mark.parametrize(
        ("type_", "key"),
        [("author", "/authors/OL1A"), ("work", "/works/OL1W"), ("edition", "/books/OL1M"), ("list", "/list/OL17L"), ("series", "/series/OL17L")],
    )
    def test_new_doc_uses_current_site(self, current, type_, key):
        doc = addbook.new_doc("/type/" + type_, title="New record")
        assert doc._site is current
        assert doc.key == key
        assert doc.title == "New record"
        if type_ in {"list", "series"}:
            current.seq.next_value.assert_called_once_with("list")

    def test_add_book_post_saves_author_work_and_edition(self, current, monkeypatch):
        form = {
            "book_title": "New book",
            "publisher": "Publisher",
            "publish_date": "2020",
            "authors--0--author--key": "__new__",
            "author_names--0": "New author",
        }
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(defaults, **form))
        with pytest.raises(web.HTTPError, match="303 See Other"):
            delegate.pages["/books/add"][None]().POST()
        assert current.get("/authors/OL1A").name == "New author"
        work = current.get("/works/OL1W")
        edition = current.get("/books/OL1M")
        assert work.title == edition.title == "New book"
        assert work.authors[0].author.key == "/authors/OL1A"
        assert edition.works[0].key == work.key
        assert current.changesets[-1]["kind"] == "add-book"
        assert current.changesets[-1]["comment"] == "Saved book"
        assert dict(web.ctx.headers)["Location"].endswith("/edit?mode=add-work")

    @pytest.mark.parametrize(
        ("handler", "key", "type_"),
        [(addbook.book_edit, "/books/OL1M", "edition"), (addbook.work_edit, "/works/OL1W", "work"), (addbook.author_edit, "/authors/OL1A", "author")],
    )
    @pytest.mark.parametrize("allowed", [False, True])
    def test_edit_get_uses_current_permissions_and_records(self, current, monkeypatch, handler, key, type_, allowed):
        current.quicksave("/works/OL2W", "/type/work", title="Parent")
        current.quicksave(key, "/type/" + type_, title="Current record", works=[{"key": "/works/OL2W"}])
        current.can_write.return_value = allowed
        get = Mock(wraps=current.get)
        monkeypatch.setattr(current, "get", get)
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(v="1"))
        render = Mock()
        monkeypatch.setattr(addbook, "render_template", render)
        handler().GET(key)
        current.can_write.assert_called_once_with(key)
        if allowed:
            if handler is addbook.author_edit:
                get.assert_called_with(key)
            else:
                get.assert_called_with(key, 1)
            assert render.call_args.args[1]._site is current
        else:
            get.assert_not_called()
            assert web.ctx.status == "403 Forbidden"
            assert render.call_args.args[0] == "permission_denied"

    @pytest.mark.parametrize(
        ("handler", "key", "type_"),
        [(addbook.book_edit, "/books/OL1M", "edition"), (addbook.work_edit, "/works/OL1W", "work"), (addbook.author_edit, "/authors/OL1A", "author")],
    )
    def test_edit_post_saves_current_record(self, current, monkeypatch, handler, key, type_):
        current.quicksave(key, "/type/" + type_, title="Before", name="Before")
        fields = {"_comment": "Edit record", "_save": "Save", f"{type_}--key": key, f"{type_}--title": "After"}
        if type_ == "author":
            fields["author--name"] = "After"
        monkeypatch.setattr(web, "input", lambda **defaults: web.storage(dict(defaults) | fields))
        with pytest.raises(web.HTTPError, match="303 See Other"):
            handler().POST(key)
        assert current.get(key).title == "After"
        assert current.changesets[-1]["comment"] == "Edit record"
