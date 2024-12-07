import web

from openlibrary.core import helpers as h
from openlibrary.mocks.mock_infobase import MockSite


def _load_fake_context():
    app = web.application()
    env = {
        "PATH_INFO": "/",
        "HTTP_METHOD": "GET",
    }
    app.load(env)


def _monkeypatch_web(monkeypatch):
    monkeypatch.setattr(web, "ctx", web.storage(x=1))
    monkeypatch.setattr(web.webapi, "ctx", web.ctx)

    _load_fake_context()
    web.ctx.lang = 'en'
    web.ctx.site = MockSite()


def test_sanitize():
    # plain html should pass through
    assert h.sanitize("hello") == "hello"
    assert h.sanitize("<p>hello</p>") == "<p>hello</p>"

    # broken html must be corrected
    assert h.sanitize("<p>hello") == "<p>hello</p>"

    # css class is fine
    assert h.sanitize('<p class="foo">hello</p>') == '<p class="foo">hello</p>'

    # style attribute must be stripped
    assert h.sanitize('<p style="color: red">hello</p>') == '<p>hello</p>'

    # style tags must be stripped
    assert (
        h.sanitize('<style type="text/css">p{color: red;}</style><p>hello</p>')
        == '<p>hello</p>'
    )

    # script tags must be stripped
    assert h.sanitize('<script>alert("dhoom")</script>hello') == 'hello'

    # rel="nofollow" must be added absolute links
    assert (
        h.sanitize('<a href="https://example.com">hello</a>')
        == '<a href="https://example.com" rel="nofollow">hello</a>'
    )
    # relative links should pass through
    assert h.sanitize('<a href="relpath">hello</a>') == '<a href="relpath">hello</a>'


def test_safesort():
    from datetime import datetime

    y2000 = datetime(2000, 1, 1)
    y2005 = datetime(2005, 1, 1)
    y2010 = datetime(2010, 1, 1)

    assert h.safesort([y2005, y2010, y2000, None]) == [None, y2000, y2005, y2010]
    assert h.safesort([y2005, y2010, y2000, None], reverse=True) == [
        y2010,
        y2005,
        y2000,
        None,
    ]

    assert h.safesort([[y2005], [None]], key=lambda x: x[0]) == [[None], [y2005]]


def test_datestr(monkeypatch):
    from datetime import datetime

    then = datetime(2010, 1, 1, 0, 0, 0)

    _monkeypatch_web(monkeypatch)
    # assert h.datestr(then, datetime(2010, 1, 1, 0, 0, 0, 10)) == u"just moments ago"
    assert h.datestr(then, datetime(2010, 1, 1, 0, 0, 1)) == "1 second ago"
    assert h.datestr(then, datetime(2010, 1, 1, 0, 0, 9)) == "9 seconds ago"

    assert h.datestr(then, datetime(2010, 1, 1, 0, 1, 1)) == "1 minute ago"
    assert h.datestr(then, datetime(2010, 1, 1, 0, 9, 1)) == "9 minutes ago"

    assert h.datestr(then, datetime(2010, 1, 1, 1, 0, 1)) == "1 hour ago"
    assert h.datestr(then, datetime(2010, 1, 1, 9, 0, 1)) == "9 hours ago"

    assert h.datestr(then, datetime(2010, 1, 2, 0, 0, 1)) == "1 day ago"

    assert h.datestr(then, datetime(2010, 1, 9, 0, 0, 1)) == "January 1, 2010"
    assert h.datestr(then, datetime(2010, 1, 9, 0, 0, 1), lang='fr') == '1 janvier 2010'


def test_sprintf():
    assert h.sprintf('hello %s', 'python') == 'hello python'
    assert h.sprintf('hello %(name)s', name='python') == 'hello python'


def test_commify():
    assert h.commify(123) == "123"
    assert h.commify(1234) == "1,234"
    assert h.commify(1234567) == "1,234,567"

    assert h.commify(123, lang="te") == "123"
    assert h.commify(1234, lang="te") == "1,234"
    assert h.commify(1234567, lang="te") == "12,34,567"


def test_truncate():
    assert h.truncate("hello", 6) == "hello"
    assert h.truncate("hello", 5) == "hello"
    assert h.truncate("hello", 4) == "hell..."


def test_urlsafe():
    assert h.urlsafe("a b") == "a_b"
    assert h.urlsafe("a?b") == "a_b"
    assert h.urlsafe("a?&b") == "a_b"

    assert h.urlsafe("?a") == "a"
    assert h.urlsafe("a?") == "a"


def test_texsafe():
    assert h.texsafe("hello") == r"hello"
    assert h.texsafe("a_b") == r"a\_{}b"
    assert h.texsafe("a < b") == r"a \textless{} b"


def test_percentage():
    assert h.percentage(1, 10) == 10.0
    assert h.percentage(0, 0) == 0
