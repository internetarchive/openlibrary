import datetime
from unittest.mock import MagicMock

import pytest
import web
from bs4 import BeautifulSoup

from openlibrary.core.admin import Stats
from openlibrary.core.carousels import format_book_data
from openlibrary.core.jinja import get_jinja_env
from openlibrary.mocks.mock_infobase import MockSite
from openlibrary.plugins.openlibrary import home


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
        # The Jinja row draws its button arrow through the icon global, which reads the sprite macro.
        monkeypatch.setitem(get_jinja_env().globals, "icon", lambda *args, **kwargs: '<svg class="ol-icon"></svg>')
        html = str(
            render_template(
                "home/index",
                stats=stats,
                test=True,
                featured_subjects=[],
                carousel_data=carousel_data,
                library_stats=home.get_library_stats(stats),
            )
        )

        assert "Recently Returned" in html
        assert "bookPreview" in html
        assert "Around the Library" in html
        assert "A library owned by the people who use it." in html
        assert 'href="/librarians"' in html
        assert "About the Project" in html

    def test_library_row_without_stats(self, render_template, monkeypatch, mock_site):
        """No admin stats: the call-out still renders, alone on its row."""
        self.setup_monkeypatch(monkeypatch)
        macros = web.template.Template.globals.setdefault("macros", web.storage())
        macros.BookPreviewFloater = lambda *args, **kwargs: '<div id="bookPreview"></div>'
        # The Jinja row draws its button arrow through the icon global, which reads the sprite macro.
        monkeypatch.setitem(get_jinja_env().globals, "icon", lambda *args, **kwargs: '<svg class="ol-icon"></svg>')
        html = str(render_template("home/index", stats=None, test=True, featured_subjects=[], carousel_data=None))
        assert "A library owned by the people who use it." in html
        assert "Around the Library" not in html
        assert "library-row--solo" in html


class TestLibraryStats:
    """The compact stats card: a 28-day total and a sparkline per series."""

    def test_compact_number(self):
        assert [home.compact_number(n) for n in (0, 999, 1000, 1234, 9960, 18400, 96400, 412000, 1_200_000, 12_000_000)] == [
            "0",
            "999",
            "1K",
            "1.2K",
            "10K",
            "18K",
            "96K",
            "412K",
            "1.2M",
            "12M",
        ]

    def test_sparkline_fills_the_box_oldest_first(self):
        points = home.sparkline_points([0, 5, 10], width=120, height=28)
        assert points == "2.0,26.0 60.0,14.0 118.0,2.0"

    def test_sparkline_flat_series_is_a_midline(self):
        assert home.sparkline_points([3, 3], width=120, height=28) == "2.0,14.0 118.0,14.0"
        assert home.sparkline_points([]) == ""

    def test_metrics_in_order_and_empty_series_dropped(self):
        def series(*values):
            stat = MagicMock()
            stat.get_counts.return_value = list(enumerate(values))
            return stat

        stats = {
            "visitors": series(0, 0, 0),
            "members": series(100, 200, 300),
            "human_edits": series(1500, 1600),
            "loans": series(7),
        }
        metrics = home.get_library_stats(stats)
        assert [(m["label"], m["value"], m["href"]) for m in metrics] == [
            ("new members", "600", "/stats"),
            ("catalog edits", "3.1K", "/recentchanges"),
            ("ebooks borrowed", "7", "/subjects/in_library#ebooks=true"),
        ]
        assert metrics[0]["points"] == home.sparkline_points([100, 200, 300])
        assert home.get_library_stats(None) == []


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
