import datetime

import pytest
import web
from bs4 import BeautifulSoup

from openlibrary.core.admin import Stats
from openlibrary.core.carousels import format_book_data
from openlibrary.core.jinja import render_jinja_template
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.openlibrary import home


class MockStats:
    """Stands in for admin.Stats: a fixed list of [timestamp_ms, count] pairs."""

    def __init__(self, counts):
        self.counts = counts

    def get_counts(self, ndays=28, times=False):
        return self.counts

    def get_summary(self, ndays=28):
        return sum(count for _, count in self.counts)


class MockDoc(dict):
    def __init__(self, _id, *largs, **kargs):
        self.id = _id
        kargs["_key"] = _id
        super().__init__(*largs, **kargs)

    def __repr__(self):
        o = super().__repr__()
        return f"<{self.id} - {o}>"


class TestHomeTemplates:
    @pytest.fixture(autouse=True)
    def setup_context(self, request_context_fixture):
        """Auto-use fixture to set up request context for all tests."""
        request_context_fixture(lang="en")
        pass

    def setup_monkeypatch(self, monkeypatch):
        ctx = web.storage()
        monkeypatch.setattr(web, "ctx", ctx)
        monkeypatch.setattr(web.webapi, "ctx", web.ctx)

        self._load_fake_context()
        web.ctx.lang = "en"
        web.ctx.site = MockSite()

    def _load_fake_context(self):
        self.app = web.application()
        self.env = {
            "PATH_INFO": "/",
            "HTTP_METHOD": "GET",
        }
        self.app.load(self.env)

    def test_about_template(self, monkeypatch, render_template):
        self.setup_monkeypatch(monkeypatch)
        html = str(render_template("home/about"))
        assert "About the Project" in html

        blog = BeautifulSoup(html, "lxml").find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.find_all("li")) == 0

        posts = [
            web.storage(
                {
                    "title": "Blog-post-0",
                    "link": "https://blog.openlibrary.org/2011/01/01/blog-post-0",
                    "pubdate": datetime.datetime(2011, 1, 1),
                }
            )
        ]
        html = str(render_template("home/about", blog_posts=posts))
        assert "About the Project" in html
        assert "Blog-post-0" in html
        assert "https://blog.openlibrary.org/2011/01/01/blog-post-0" in html

        blog = BeautifulSoup(html, "lxml").find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.find_all("li")) == 1

    def test_stats_template(self):
        # Make sure that it works fine without any input (skipping section)
        assert render_jinja_template("home/stats.html.jinja", charts=None).strip() == ""

    def test_stats_charts(self, monkeypatch):
        day = 24 * 60 * 60 * 1000
        stat = MockStats([[3 * day, 4], [day, 8], [2 * day, 0]])
        monkeypatch.setattr(home, "format_date", lambda d: d.strftime("%Y-%m-%d"))
        monkeypatch.setattr(home, "commify", str)

        charts = home.get_home_stats_charts(dict.fromkeys(["visitors", "members", "human_edits", "lists", "loans"], stat))
        chart = charts["members"]
        assert chart["total"] == 12
        # Oldest first, scaled so the busiest day fills the chart height
        assert [bar["title"] for bar in chart["bars"]] == ["1970-01-02: 8", "1970-01-03: 0", "1970-01-04: 4"]
        assert [bar["height"] for bar in chart["bars"]] == [60, 0, 30]
        assert [bar["y"] for bar in chart["bars"]] == [0, 60, 30]

        html = render_jinja_template("home/stats.html.jinja", charts=charts)
        soup = BeautifulSoup(html, "lxml")
        assert len(soup.select("svg.chart-graph")) == 5
        assert len(soup.select("svg.chart-graph--members .chart-graph__bar")) == 3
        assert soup.select_one("svg.chart-graph--members title").text == "1970-01-02: 8"
        assert home.get_home_stats_charts(None) is None

    def test_home_template(self, render_template, monkeypatch, mock_site):
        self.setup_monkeypatch(monkeypatch)
        docs = [
            MockDoc(
                _id=datetime.datetime.now().strftime("counts-%Y-%m-%d"),
                human_edits=1,
                bot_edits=1,
                lists=1,
                visitors=1,
                loans=1,
                members=1,
                works=1,
                editions=1,
                ebooks=1,
                covers=1,
                authors=1,
                subjects=1,
            )
        ] * 100
        stats = {
            "human_edits": Stats(docs, "human_edits", "human_edits"),
            "bot_edits": Stats(docs, "bot_edits", "bot_edits"),
            "lists": Stats(docs, "lists", "total_lists"),
            "visitors": Stats(docs, "visitors", "visitors"),
            "loans": Stats(docs, "loans", "loans"),
            "members": Stats(docs, "members", "total_members"),
            "works": Stats(docs, "works", "total_works"),
            "editions": Stats(docs, "editions", "total_editions"),
            "ebooks": Stats(docs, "ebooks", "total_ebooks"),
            "covers": Stats(docs, "covers", "total_covers"),
            "authors": Stats(docs, "authors", "total_authors"),
            "subjects": Stats(docs, "subjects", "total_subjects"),
        }

        mock_site.quicksave("/people/foo/lists/OL1L", "/type/list")

        carousel_data = {
            "staff_picks": {
                "books": [],
                "url": "/search?q=staff_picks",
                "load_more": {
                    "queryType": "BROWSE",
                    "q": "test_query",
                    "subject": "test_subject",
                    "sorts": "test_sort",
                    "mode": "page",
                    "limit": 18,
                },
            },
            "recently_returned": {
                "books": [],
                "url": "/search?q=recently_returned",
                "load_more": {
                    "queryType": "BROWSE",
                    "q": "test_query",
                    "subject": "",
                    "sorts": "test_sort",
                    "mode": "page",
                    "limit": 18,
                },
            },
        }

        macros = web.template.Template.globals.setdefault("macros", web.storage())
        macros.BookPreview = lambda *args, **kwargs: '<div id="bookPreview"></div>'
        macros.BookPreviewFloater = lambda *args, **kwargs: '<div id="bookPreview"></div>'
        html = str(render_template("home/index", stats=stats, test=True, featured_subjects=[], carousel_data=carousel_data))

        assert "Recently Returned" in html
        assert "bookPreview" in html
        assert "Around the Library" in html
        assert "About the Project" in html


class Test_format_book_data:
    def test_all(self, mock_site, mock_ia):
        mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        mock_site.quicksave("/works/OL1W", "/type/work", title="Foo")

    def test_authors(self, mock_site, mock_ia):
        mock_site.quicksave("/authors/OL1A", "/type/author", name="A1")
        mock_site.quicksave("/authors/OL2A", "/type/author", name="A2")
        mock_site.quicksave(
            "/works/OL1W",
            "/type/work",
            title="Foo",
            authors=[{"author": {"key": "/authors/OL2A"}}],
        )

        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        assert format_book_data(book)["authors"] == []

        # when there is no work and authors, the authors field must be picked from the book
        book = mock_site.quicksave(
            "/books/OL1M",
            "/type/edition",
            title="Foo",
            authors=[{"key": "/authors/OL1A"}],
        )
        assert format_book_data(book)["authors"] == [{"key": "/authors/OL1A", "name": "A1"}]

        # when there is work, the authors field must be picked from the work
        book = mock_site.quicksave(
            "/books/OL1M",
            "/type/edition",
            title="Foo",
            authors=[{"key": "/authors/OL1A"}],
            works=[{"key": "/works/OL1W"}],
        )
        assert format_book_data(book)["authors"] == [{"key": "/authors/OL2A", "name": "A2"}]
