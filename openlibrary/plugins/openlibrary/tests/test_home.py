import datetime
import web
import sys

from infogami.utils.view import render_template
from infogami.utils import template, context
from openlibrary.i18n import gettext
from openlibrary.core.admin import Stats
from BeautifulSoup import BeautifulSoup

from openlibrary import core
from openlibrary.plugins.openlibrary import home

def pytest_funcarg__olconfig(request):
    from infogami import config
    import copy

    def safecopy(data):
        if isinstance(data, list):
            return [safecopy(d) for d in data]
        elif isinstance(data, web.storage):
            return web.storage((k, safecopy(v)) for k, v in data.items())
        elif isinstance(data, dict):
            return dict((k, safecopy(v)) for k, v in data.items())
        else:
            return data

    old_config = safecopy(config.__dict__)

    def undo():
        config.__dict__.clear()
        config.__dict__.update(old_config)

    request.addfinalizer(undo)
    return config.__dict__

class MockDoc(dict):
    def __init__(self, _id, *largs, **kargs):
        self.id = _id
        kargs['_key'] = _id
        super(MockDoc,self).__init__(*largs, **kargs)

    def __repr__(self):
        o = super(MockDoc, self).__repr__()
        return "<%s - %s>"%(self.id, o)


class TestHomeTemplates:
    def test_about_template(self, render_template):
        html = unicode(render_template("home/about"))
        assert "About the Project" in html

        blog = BeautifulSoup(html).find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.findAll("li")) == 0

        posts = [web.storage({
            "title": "Blog-post-0",
            "link": "http://blog.openlibrary.org/2011/01/01/blog-post-0",
            "pubdate": datetime.datetime(2011, 01, 01)
        })]
        html = unicode(render_template("home/about", blog_posts=posts))
        assert "About the Project" in html
        assert "Blog-post-0" in html
        assert "http://blog.openlibrary.org/2011/01/01/blog-post-0" in html

        blog = BeautifulSoup(html).find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.findAll("li")) == 1

    def test_stats_template(self, render_template):
        # Make sure that it works fine without any input (skipping section)
        html = unicode(render_template("home/stats"))
        assert html == ""

    def test_read_template(self, render_template):
        # getting read-online books fails because solr is not defined.
        # Empty list should be returned when there is error.

        books = home.readonline_carousel()
        html = unicode(render_template("books/custom_carousel", books=books, title="Classic Books", url="/read",
                                       key="public_domain"))
        assert html.strip() == ""

    def test_home_template(self, render_template, mock_site, olconfig, monkeypatch):
        docs = [MockDoc(_id=datetime.datetime.now().strftime("counts-%Y-%m-%d"),
                        human_edits=1, bot_edits=1, lists=1,
                        visitors=1, loans=1, members=1,
                        works=1, editions=1, ebooks=1,
                        covers=1, authors=1, subjects=1)]* 100
        stats = dict(human_edits = Stats(docs, "human_edits", "human_edits"),
                     bot_edits   = Stats(docs, "bot_edits", "bot_edits"),
                     lists       = Stats(docs, "lists", "total_lists"),
                     visitors    = Stats(docs, "visitors", "visitors"),
                     loans       = Stats(docs, "loans", "loans"),
                     members     = Stats(docs, "members", "total_members"),
                     works       = Stats(docs, "works", "total_works"),
                     editions    = Stats(docs, "editions", "total_editions"),
                     ebooks      = Stats(docs, "ebooks", "total_ebooks"),
                     covers      = Stats(docs, "covers", "total_covers"),
                     authors     = Stats(docs, "authors", "total_authors"),
                     subjects    = Stats(docs, "subjects", "total_subjects"))

        mock_site.quicksave("/people/foo/lists/OL1L", "/type/list")
        olconfig.setdefault("home", {})['lending_list'] = "/people/foo/lists/OL1L"

        def spoofed_generic_carousel(*args, **kwargs):
            return [{
                "work": None,
                "key": "/books/OL1M",
                "url": "/books/OL1M",
                "title": "The Great Book",
                "authors": [web.storage({"key": "/authors/OL1A", "name": "Some Author"})],
                "read_url": "http://archive.org/stream/foo",
                "borrow_url": "/books/OL1M/foo/borrow",
                "inlibrary_borrow_url": "/books/OL1M/foo/borrow",
                "cover_url": ""
            }]
        monkeypatch.setattr(web.ctx, "library", {"name": "IA"}, raising=False)
        html = unicode(render_template("home/index", stats=stats, test=True))

        headers = ["Books We Love", "Recently Returned", "Kids",
                   "Thrillers", "Romance", "Classic Books", "Textbooks"]
        for h in headers:
            assert h in html

        assert "Around the Library" in html
        assert "About the Project" in html

class TestCarouselItem:
    def setup_method(self, m):
        context.context.features = []

    def render(self, book):
        if "authors" in book:
            book["authors"] = [web.storage(a) for a in book['authors']]
        return unicode(render_template("books/carousel_item", web.storage(book)))

    def link_count(self, html):
        links = BeautifulSoup(html).findAll("a") or []
        return len(links)

    def test_without_cover_url(self, render_template):
        book = {
            "work": None,
            "key": "/books/OL1M",
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "read_url": "http://archive.org/stream/foo",
            "borrow_url": "/books/OL1M/foo/borrow",
            "inlibrary_borrow_url": "/books/OL1M/foo/borrow",
            "cover_url": ""
        }
        assert book['title'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['authors']
        assert book['title'] in self.render(book)

class Test_carousel:
    def test_carousel(self, render_template):
        book = web.storage({
            "work": "/works/OL1W",
            "key": "/books/OL1M",
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [web.storage({"key": "/authors/OL1A", "name": "Some Author"})],
            "read_url": "http://archive.org/stream/foo",
            "borrow_url": "/books/OL1M/foo/borrow",
            "inlibrary_borrow_url": "/books/OL1M/foo/borrow",
            "cover_url": ""
        })

        html = unicode(render_template("books/carousel", [book]))

        assert book['title'] in html

        soup = BeautifulSoup(html)
        assert len(soup.findAll("li")) == 1
        assert len(soup.findAll("a")) == 2

class Test_format_book_data:
    def test_all(self, mock_site, mock_ia):
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo")

    def test_authors(self, mock_site, mock_ia):
        a1 = mock_site.quicksave("/authors/OL1A", "/type/author", name="A1")
        a2 = mock_site.quicksave("/authors/OL2A", "/type/author", name="A2")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo", authors=[{"author": {"key": "/authors/OL2A"}}])

        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        assert home.format_book_data(book)['authors'] == []

        # when there is no work and authors, the authors field must be picked from the book
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo", authors=[{"key": "/authors/OL1A"}])
        assert home.format_book_data(book)['authors'] == [{"key": "/authors/OL1A", "name": "A1"}]

        # when there is work, the authors field must be picked from the work
        book = mock_site.quicksave("/books/OL1M", "/type/edition",
            title="Foo",
            authors=[{"key": "/authors/OL1A"}],
            works=[{"key": "/works/OL1W"}]
        )
        assert home.format_book_data(book)['authors'] == [{"key": "/authors/OL2A", "name": "A2"}]
