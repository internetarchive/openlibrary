"""py.test tests for addbook"""
import web
from collections import namedtuple

from openlibrary import accounts
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.upstream import addbook, utils


def strip_nones(d):
    return dict((k, v) for k, v in d.items() if v is not None)

class TestSaveBookHelper:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_authors(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        s = addbook.SaveBookHelper(None, None)
        def f(data):
            return strip_nones(s.process_work(web.storage(data)))

        assert f({}) == {}
        assert f({"authors": []}) == {}
        assert f({"authors": [{"type": "/type/author_role"}]}) == {}

    def test_editing_orphan_creates_work(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
            }])
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "",
            "work--title": "Original Edition Title",
            "edition--title": "Original Edition Title"
        })

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 2
        assert web.ctx.site.get("/works/OL1W") is not None
        assert web.ctx.site.get("/works/OL1W").title == "Original Edition Title"

    def test_never_create_an_orphan(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL1W"}]
            }])
        edition = web.ctx.site.get("/books/OL1M")
        work = web.ctx.site.get("/works/OL1W")

        formdata = web.storage({
            "work--key": "/works/OL1W",
            "work--title": "Original Work Title",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "",
        })

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)
        print(web.ctx.site.get("/books/OL1M").title)
        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL1W"

    def test_moving_orphan(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
            }])
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "",
            "work--title": "Original Edition Title",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "/works/OL1W",
        })

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert len(web.ctx.site.docs) == 1
        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL1W"

    def test_moving_orphan_ignores_work_edits(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
            }])
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "",
            "work--title": "Modified Work Title",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "/works/OL1W",
        })

        s = addbook.SaveBookHelper(None, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"

    def test_editing_work(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL1W"}],
            }])

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "/works/OL1W",
            "work--title": "Modified Work Title",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "/works/OL1W",
        })

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Modified Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Original Edition Title"

    def test_editing_edition(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()

        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL1W"}],
            }])

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "/works/OL1W",
            "work--title": "Original Work Title",
            "edition--title": "Modified Edition Title",
            "edition--works--0--key": "/works/OL1W",
        })

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Modified Edition Title"

    def test_editing_work_and_edition(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()

        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL1W"}],
            }])

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "/works/OL1W",
            "work--title": "Modified Work Title",
            "edition--title": "Modified Edition Title",
            "edition--works--0--key": "/works/OL1W",
        })

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Modified Work Title"
        assert web.ctx.site.get("/books/OL1M").title == "Modified Edition Title"

    def test_moving_edition(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL1W"}],
            }])

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "/works/OL1W",
            "work--title": "Original Work Title",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "/works/OL2W",
        })

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/books/OL1M").works[0].key == "/works/OL2W"

    def test_moving_edition_ignores_changes_to_work(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()
        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL1W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL1W"}],
            }])

        work = web.ctx.site.get("/works/OL1W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "/works/OL1W",
            "work--title": "Modified Work Title",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "/works/OL2W",  # Changing work
        })

        s = addbook.SaveBookHelper(work, edition)
        s.save(formdata)

        assert web.ctx.site.get("/works/OL1W").title == "Original Work Title"

    def test_moving_edition_to_new_work(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda slf: False})()

        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        web.ctx.site.save_many([
            {
                "type": {"key": "/type/work"},
                "key": "/works/OL100W",
                "title": "Original Work Title"
            },
            {
                "type": {"key": "/type/edition"},
                "key": "/books/OL1M",
                "title": "Original Edition Title",
                "works": [{"key": "/works/OL100W"}],
            }])

        work = web.ctx.site.get("/works/OL100W")
        edition = web.ctx.site.get("/books/OL1M")

        formdata = web.storage({
            "work--key": "/works/OL100W",
            "work--title": "FOO BAR",
            "edition--title": "Original Edition Title",
            "edition--works--0--key": "__new__",
        })

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


class TestAddBook:
    def setup_method(self, method):
        web.ctx.site = MockSite()

    def test_unpermitted_logged_in_user_cannot_add_book(self, monkeypatch):
        nonlocal = {'render_template_permission_denied': False}

        def mock_user():
            return True

        def mock_render_template(*args):
            if len(args) > 0:
                denied = (args[0] == "permission_denied")
                nonlocal['render_template_permission_denied'] = denied

        def mock_seeother(*args):
            assert False

        def mock_can_write(key):
            return False

        monkeypatch.setattr(web.ctx.site, "can_write", mock_can_write)
        monkeypatch.setattr(web.ctx.site, "get_user", mock_user)
        monkeypatch.setattr(addbook, "render_template", mock_render_template)
        monkeypatch.setattr(web, "seeother", mock_seeother)

        s = addbook.addbook()
        s.GET()

        assert nonlocal['render_template_permission_denied']

    def test_unpermitted_anonymous_user_cannot_add_book(self, monkeypatch):
        nonlocal = {'seeother_redirect_login_called_correctly': False}

        def mock_anonymous_user():
            return None

        def mock_render_template(*args):
            assert False, "should be unreachable given test setup"

        def mock_seeother(*args):
            if len(args) > 0:
                path = addbook.addbook.path
                denied = (args[0] == "/account/login?redirect={}".format(path))
                nonlocal['seeother_redirect_login_called_correctly'] = denied

        def mock_can_write(key):
            return False

        monkeypatch.setattr(web.ctx.site, "can_write", mock_can_write)
        monkeypatch.setattr(web.ctx.site, "get_user", mock_anonymous_user)
        monkeypatch.setattr(addbook, "render_template", mock_render_template)
        monkeypatch.setattr(web, "seeother", mock_seeother)

        s = addbook.addbook()
        s.GET()

        assert nonlocal['seeother_redirect_login_called_correctly']

    def test_permitted_user_may_add_books(self, monkeypatch):
        nonlocal = {'render_template_permission_granted': False}

        def mock_anonymous_user():
            assert False, "should be unreachable given test setup"

        def mock_can_write(key):
            return True

        def mock_input(**kwargs):
            return namedtuple("input", kwargs.keys())

        def mock_recaptcha():
            assert True, "called when rendering page"

        def mock_render_template(path_arg, **kwargs):
            #FIXME: this seems silly
            path = addbook.addbook.path[1:]
            nonlocal['render_template_permission_granted'] = (path == path_arg)

        def mock_seeother(*args):
            assert False, "should be unreachable given test setup"
        
        monkeypatch.setattr(web.ctx.site, "can_write", mock_can_write)
        monkeypatch.setattr(web.ctx.site, "get_user", mock_anonymous_user)
        monkeypatch.setattr(addbook, "render_template", mock_render_template)
        monkeypatch.setattr(addbook, "get_recaptcha", mock_recaptcha)
        monkeypatch.setattr(web, "input", mock_input)
        monkeypatch.setattr(web, "seeother", mock_seeother)

        s = addbook.addbook()
        s.GET()

        assert nonlocal['render_template_permission_granted']
