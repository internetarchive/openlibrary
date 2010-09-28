"""py.test tests for addbook"""
import web
from .. import addbook

def strip_nones(d):
    return dict((k, v) for k, v in d.items() if v is not None)

class TestSaveBookHelper:
    def test_authors(self):
        s = addbook.SaveBookHelper(None, None)
        def f(data):
            return strip_nones(s.process_work(web.storage(data)))
        
        assert f({}) == {}
        assert f({"authors": []}) == {}
        assert f({"authors": [{"type": "/type/author_role"}]}) == {}    