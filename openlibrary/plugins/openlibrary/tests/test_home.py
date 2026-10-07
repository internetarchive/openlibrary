import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote_plus

import pytest
import web
from bs4 import BeautifulSoup

from openlibrary.core.admin import Stats
from openlibrary.core.carousels import format_book_data
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

    def test_stats_template(self, render_template):
        # Make sure that it works fine without any input (skipping section)
        html = str(render_template("home/stats"))
        assert html == ""

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

        macros = web.template.Template.globals.setdefault("macros", web.storage())
        macros.BookPreview = lambda *args, **kwargs: '<div id="bookPreview"></div>'
        macros.BookPreviewFloater = lambda *args, **kwargs: '<div id="bookPreview"></div>'
        macros.LoadingIndicator = lambda *args, **kwargs: '<div class="loadingIndicator"></div>'
        html = str(render_template("home/index", stats=stats, test=True))

        assert "bookPreview" in html
        assert "Around the Library" in html
        assert "About the Project" in html


TILE_GENRES = [
    {"name": "Horror", "slug": "horror", "query": "horror*", "kind": "genre", "subgenres": []},
    {"name": "History", "slug": "history", "query": "history*", "kind": "subject", "subgenres": []},
    {"name": "Absurd", "slug": "absurd", "query": "absurd*", "kind": "genre", "subgenres": []},
]


PICKED_COVERS = {"horror": [10, 11, 12, 13], "history": [20, 21, 22], "absurd": [30, 31, 32]}

TRENDING = home.home_genres.TRENDING
TRENDING_QUERY = home.home_genres.solr_query(TRENDING)


class TestFeaturedGenres:
    """The stacks' tiles come from one faceted Solr query, one facet query per genre, led by Trending."""

    def featured(self, counts, picked=PICKED_COVERS, trending_covers=(1, 2, 3)):
        solr = MagicMock()
        solr.raw_request = AsyncMock(return_value=MagicMock(json=lambda: {"facet_counts": {"facet_queries": {TRENDING_QUERY: 900, **counts}}}))
        with (
            patch.object(home.home_genres, "load_home_genres", return_value=TILE_GENRES),
            patch.object(home.home_genres, "load_tile_covers", return_value=picked),
            patch.object(home, "get_trending_tile_covers", return_value=list(trending_covers)),
            patch.object(home.search, "get_solr", return_value=solr),
        ):
            web.ctx.env = {}
            return home.get_featured_genres(), solr.raw_request.call_args.args[1]

    def test_one_query_for_every_tile(self):
        genres, payload = self.featured({"subject_key:horror*": 1200, "subject_key:history*": 5, "subject_key:absurd*": 0})
        assert payload.count("facet.query=") == 4
        # Counts only: no grouping, which sorted every genre's matches and timed out on the full index.
        assert "group" not in payload
        # Counted, and nothing readable means no tile.
        assert [(g["slug"], g["readable_count"]) for g in genres] == [("trending", 900), ("horror", 1200), ("history", 5)]
        # The fan takes three of the picked covers.
        assert genres[1]["covers"] == [10, 11, 12]

    def test_trending_leads_with_live_covers(self):
        """Trending is the first tile, always: the template keeps it there while shuffling the rest.
        Its fan is the covers its shelf would open with, not hand-picked ones."""
        genres, payload = self.featured({"subject_key:horror*": 1200, "subject_key:history*": 5, "subject_key:absurd*": 0}, trending_covers=[7, 8, 9])
        assert genres[0]["slug"] == "trending"
        assert genres[0]["kind"] == "trending"
        assert genres[0]["covers"] == [7, 8, 9]
        # Its count is a whole Solr clause, not a subject_key facet.
        assert "subject_key" not in TRENDING_QUERY
        assert f"facet.query={quote_plus(TRENDING_QUERY)}" in payload

    def test_trending_without_covers_still_gets_a_tile(self):
        genres, _ = self.featured({"subject_key:horror*": 1200, "subject_key:history*": 5, "subject_key:absurd*": 0}, trending_covers=[])
        assert (genres[0]["slug"], genres[0]["covers"]) == ("trending", [])

    def test_trending_tile_covers_come_from_its_row_query(self):
        docs = [{"cover_i": 5}, {}, {"cover_i": 6}, {"cover_i": 7}, {"cover_i": 8}]
        with patch.object(home, "work_search_async", new=AsyncMock(return_value={"docs": docs})) as search:
            assert home.get_trending_tile_covers() == [5, 6, 7]
        query, kwargs = search.call_args.args[0], search.call_args.kwargs
        # The same books the shelf shows: readable, in trending order.
        assert (query["q"], query["has_fulltext"], kwargs["sort"]) == (TRENDING_QUERY, "true", "trending")

    def test_no_picked_covers_no_tile(self):
        genres, payload = self.featured({"subject_key:horror*": 1200}, picked={"horror": [10, 11, 12]})
        # Genres without covers aren't even counted.
        assert payload.count("facet.query=") == 2
        assert [g["slug"] for g in genres] == ["trending", "horror"]

    def test_names_and_counts_are_localized_per_page_not_in_the_cache(self):
        # The cache is shared across languages, so a subject tile's name is translated, and its
        # count formatted (commify reads the request language), after it.
        genres, _ = self.featured({"subject_key:horror*": 1200, "subject_key:history*": 5, "subject_key:absurd*": 0})
        assert [g["name"] for g in genres] == ["Trending", "Horror", "History"]
        assert all("readable_count_str" not in g for g in genres)
        with (
            patch.object(home, "get_cached_featured_genres", return_value=genres),
            patch.object(home.home_genres, "subject_tile_labels", return_value={"history": "Histoire"}),
            patch.object(home.admin, "get_stats", return_value=None),
            patch.object(home, "get_blog_feeds", return_value=[]),
            patch.object(home, "render_template", return_value={}) as render,
        ):
            home.get_homepage(devmode=False)
        featured = render.call_args.kwargs["featured_genres"]
        assert [g["name"] for g in featured] == ["Trending", "Horror", "Histoire"]
        assert [g["readable_count_str"] for g in featured] == ["900", "1,200", "5"]

    def test_solr_failure_costs_the_rail_not_the_page(self):
        with (
            patch.object(home, "get_cached_featured_genres", side_effect=RuntimeError("solr down")),
            patch.object(home.admin, "get_stats", return_value=None),
            patch.object(home, "get_blog_feeds", return_value=[]),
            patch.object(home, "render_template", return_value={}) as render,
        ):
            home.get_homepage(devmode=False)
        assert render.call_args.kwargs["featured_genres"] == []

    def test_picked_covers_file_matches_the_tiles(self):
        picked = home.home_genres.load_tile_covers()
        slugs = {g["slug"] for g in home.home_genres.load_home_genres()}
        assert set(picked) == slugs
        assert all(len(covers) == home.GENRE_TILE_COVERS for covers in picked.values())


class TestTrendingStack:
    """The Trending stack isn't in the vocabulary: it's one clause across every genre."""

    def test_is_found_by_slug_but_not_a_vocabulary_genre(self):
        assert home.home_genres.find_genre("trending") is TRENDING
        assert "trending" not in {g["slug"] for g in home.home_genres.load_home_genres()}

    def test_query_is_the_clause_itself(self):
        assert home.home_genres.solr_query(TRENDING) == "trending_score_hourly_sum:[1 TO *] AND readinglog_count:[4 TO *]"
        assert (
            home.home_genres.search_url(TRENDING)
            == "/search?q=trending_score_hourly_sum%3A%5B1+TO+%2A%5D+AND+readinglog_count%3A%5B4+TO+%2A%5D&sort=trending&has_fulltext=true"
        )

    def test_name_is_translated(self):
        with patch.object(home.home_genres, "_", side_effect=lambda text: f"<{text}>"):
            assert home.home_genres.display_name(TRENDING) == "<Trending>"


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
