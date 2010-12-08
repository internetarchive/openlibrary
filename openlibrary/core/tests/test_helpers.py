import web
from openlibrary.core import helpers as h

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
    assert h.sanitize('<style type="text/css">p{color: red;}</style><p>hello</p>') == '<p>hello</p>'
    
    # script tags must be stripped
    assert h.sanitize('<script>alert("dhoom")</script>hello') == 'hello'
    
    # rel="nofollow" must be added absolute links
    assert h.sanitize('<a href="http://example.com">hello</a>') == '<a href="http://example.com" rel="nofollow">hello</a>'
    # relative links should pass through
    assert h.sanitize('<a href="relpath">hello</a>') == '<a href="relpath">hello</a>'
    
def test_datestr():
    from datetime import datetime
    then = datetime(2010, 1, 1, 0, 0, 0)
    
    #assert h.datestr(then, datetime(2010, 1, 1, 0, 0, 0, 10)) == u"just moments ago"
    assert h.datestr(then, datetime(2010, 1, 1, 0, 0, 1)) == u"1 second ago"
    assert h.datestr(then, datetime(2010, 1, 1, 0, 0, 9)) == u"9 seconds ago" 
    
    assert h.datestr(then, datetime(2010, 1, 1, 0, 1, 1)) == u"1 minute ago"
    assert h.datestr(then, datetime(2010, 1, 1, 0, 9, 1)) == u"9 minutes ago"
    
    assert h.datestr(then, datetime(2010, 1, 1, 1, 0, 1)) == u"1 hour ago"
    assert h.datestr(then, datetime(2010, 1, 1, 9, 0, 1)) == u"9 hours ago"
    
    assert h.datestr(then, datetime(2010, 1, 2, 0, 0, 1)) == u"1 day ago"
    
    assert h.datestr(then, datetime(2010, 1, 9, 0, 0, 1)) == u"January 1, 2010"    
    assert h.datestr(then, datetime(2010, 1, 9, 0, 0, 1), lang='fr') == u'1 janvier 2010'

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
    
def test_get_coverstore_url(monkeypatch):
    assert h.get_coverstore_url() == "http://covers.openlibrary.org"
    
    from infogami import config
    
    monkeypatch.setattr(config, "coverstore_url", "http://0.0.0.0:8090", raising=False)
    assert h.get_coverstore_url() == "http://0.0.0.0:8090"

    # make sure trailing / is always stripped
    monkeypatch.setattr(config, "coverstore_url", "http://0.0.0.0:8090/", raising=False)
    assert h.get_coverstore_url() == "http://0.0.0.0:8090"

def test_texsafe():
    assert h.texsafe("hello") == r"hello"
    assert h.texsafe("a_b") == r"a\_{}b"  
    assert h.texsafe("a < b") == r"a \textless{} b"