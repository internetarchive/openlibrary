"""py.test tests for addbook"""
import web
from .. import addbook
from openlibrary import accounts

def strip_nones(d):
    return dict((k, v) for k, v in d.items() if v is not None)

class TestSaveBookHelper:
    def get_test_authors(self, monkeypatch):
        def mock_user():
            return type('MockUser', (object,), {'is_admin': lambda self: False})()

        monkeypatch.setattr(accounts, "get_current_user", mock_user)

        s = addbook.SaveBookHelper(None, None)
        def f(data):
            return strip_nones(s.process_work(web.storage(data)))

        assert f({}) == {}
        assert f({"authors": []}) == {}
        assert f({"authors": [{"type": "/type/author_role"}]}) == {}
