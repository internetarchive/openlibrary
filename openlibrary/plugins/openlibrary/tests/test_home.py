import datetime as dt
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import web
from bs4 import BeautifulSoup

from openlibrary.core import admin
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


def series(*values, complete=True):
    """A stat whose daily counts are `values`; `complete` is whether every doc in the window has it."""
    stat = MagicMock()
    stat.get_counts.return_value = list(enumerate(values))
    stat.has_counts.return_value = complete
    return stat


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
                    "pubdate": dt.datetime(2011, 1, 1),
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
                _id=dt.datetime.now().strftime("counts-%Y-%m-%d"),
                human_edits=1,
                bot_edits=1,
                catalog_edits=1,
                lists=1,
                list_edits=1,
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
            "catalog_edits": Stats(docs, "catalog_edits", "catalog_edits"),
            "lists": Stats(docs, "lists", "total_lists"),
            "list_edits": Stats(docs, "list_edits", "list_edits"),
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
        # The Jinja row draws its button arrow through the icon global, which reads the sprite macro.
        monkeypatch.setitem(get_jinja_env().globals, "icon", lambda *args, **kwargs: '<svg class="ol-icon"></svg>')
        html = str(render_template("home/index", test=True, library_stats=home.get_library_stats(stats)))

        assert "bookPreview" in html
        assert "In the last month" in html
        assert "A library made by the people who use it." in html
        assert 'href="/tasks"' in html
        assert "About the Project" in html

    def test_library_row_without_stats(self, render_template, monkeypatch, mock_site):
        """No admin stats: the call-out still renders, alone on its row."""
        self.setup_monkeypatch(monkeypatch)
        macros = web.template.Template.globals.setdefault("macros", web.storage())
        macros.BookPreviewFloater = lambda *args, **kwargs: '<div id="bookPreview"></div>'
        macros.LoadingIndicator = lambda *args, **kwargs: '<div class="loadingIndicator"></div>'
        # The Jinja row draws its button arrow through the icon global, which reads the sprite macro.
        monkeypatch.setitem(get_jinja_env().globals, "icon", lambda *args, **kwargs: '<svg class="ol-icon"></svg>')
        html = str(render_template("home/index", test=True))
        assert "A library made by the people who use it." in html
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

    def test_sparkline_scale_spans_at_least_12_percent_of_the_peak(self):
        # A doubling fills the box.
        assert home.sparkline_points([5, 10], width=120, height=28) == "2.0,26.0 118.0,2.0"
        # A 10% rise climbs most of a 12% span.
        assert home.sparkline_points([90, 100], width=120, height=28) == "2.0,22.0 118.0,2.0"
        assert home.sparkline_points([3, 3], width=120, height=28) == "2.0,2.0 118.0,2.0"

    def test_sparkline_skips_days_with_no_count(self):
        assert home.sparkline_points([10, 0, 10], width=120, height=28) == "2.0,2.0 118.0,2.0"
        assert home.sparkline_points([]) == ""
        assert home.sparkline_points([0, 0]) == ""

    def test_rolling_average_skips_days_with_no_count(self):
        assert home.rolling_average([2, 4, 0, 6], window=2) == [2, 3, 4, 6]
        assert home.rolling_average([0, 0, 5], window=2) == [0, 0, 5]

    def test_percent_change_runs_from_the_first_point_to_the_last(self):
        assert home.percent_change([100, 300, 150]) == 50
        assert home.percent_change([100, 50, 90]) == -10
        # Days with no count at either end don't anchor the change.
        assert home.percent_change([0, 100, 120, 0]) == 20
        assert home.percent_change([100]) is None

    def test_metrics_in_order_and_empty_series_dropped(self):
        stats = {
            "members": series(100, 200, 300),
            "catalog_edits": series(1500, 1600),
            "loans": series(None, 7),
            "list_edits": series(40, 50),
            "lists": series(0, 0, 0),
        }
        metrics = home.get_library_stats(stats)
        assert [(m["label"], m["value"], m["href"]) for m in metrics] == [
            ("New Members", "600", "/stats"),
            ("Books Read", "7", "/subjects/in_library#ebooks=true"),
            ("Catalog Edits", "3.1K", "/recentchanges"),
            ("Lists Updated", "90", "/lists"),
        ]
        assert metrics[0]["points"] == home.sparkline_points([100, 150, 200])
        assert home.get_library_stats(None) == []

    def test_older_series_stand_in_until_the_newer_ones_cover_the_window(self):
        # The newer keys have a few days of data; summing those as a month would be wrong.
        stats = {
            "catalog_edits": series(300, complete=False),
            "human_edits": series(1500, 1600),
            "list_edits": series(40, complete=False),
            "lists": series(3, 4),
        }
        assert [(m["label"], m["value"]) for m in home.get_library_stats(stats)] == [("Catalog Edits", "3.1K"), ("Lists Created", "7")]
        assert stats["catalog_edits"].has_counts.call_args.args == (34,)

    def test_has_counts_needs_the_key_in_every_doc_of_the_window(self):
        docs = [{"_key": f"counts-2026-10-{day:02d}", "members": 1} for day in range(1, 6)]
        docs[-1]["list_edits"] = 1
        assert Stats(docs, "members", "total_members").has_counts(5)
        assert not Stats(docs, "list_edits", "list_edits").has_counts(5)
        assert Stats(docs, "list_edits", "list_edits").has_counts(1)
        assert not Stats([], "members", "total_members").has_counts(5)

    def test_change_follows_the_line_not_the_monthly_average(self):
        # Busy early, quiet late: the 28-day total is high but the line, and so the change, falls.
        stat = MagicMock()
        stat.get_counts.return_value = list(enumerate([100] * 20 + [80] * 14))
        metric = home.get_library_stats({"members": stat})[0]
        assert metric["change"] == -20
        assert stat.get_counts.call_args.args == (34,)

    def test_mock_stats_cover_the_window_oldest_first(self):
        stats = admin.mock_get_stats(56)
        counts = stats["members"].get_counts(56, times=True)
        assert len(counts) == 56
        assert [day for day, _count in counts] == sorted(day for day, _count in counts)
        assert all(count > 0 for _day, count in counts)


TILE_GENRES = [
    {"name": "Horror", "slug": "horror", "query": "horror*", "kind": "genre", "subgenres": []},
    {
        "name": "History",
        "slug": "history",
        "query": "history*",
        "kind": "subject",
        "subgenres": [
            {
                "name": "World War II",
                "slug": "world-war-ii",
                "query": "world_war_1939-1945*",
                "work_count": 1146,
                "readable_count": 1146,
                "readable_by_language": {"eng": 5210, "fre": 324, "jpn": 3},
            }
        ],
    },
    {"name": "Absurd", "slug": "absurd", "query": "absurd*", "kind": "genre", "subgenres": []},
]


PICKED_COVERS = {"horror": [10, 11, 12, 13], "history": [20, 21, 22], "absurd": [30, 31, 32]}

FEATURED = home.home_genres.FEATURED
TRENDING_QUERY = home.home_genres.solr_query(FEATURED)


class TestFeaturedGenres:
    """The stacks' tiles: the vocabulary's genres with hand-picked covers, led by Featured."""

    def featured(self, picked=PICKED_COVERS, trending_covers=(1, 2, 3)):
        with (
            patch.object(home.home_genres, "load_home_genres", return_value=TILE_GENRES),
            patch.object(home.home_genres, "load_tile_covers", return_value=picked),
            patch.object(home, "get_featured_tile_covers", return_value=list(trending_covers)),
        ):
            web.ctx.env = {}
            return home.get_featured_genres()

    def test_tiles_fan_three_picked_covers(self):
        genres = self.featured()
        assert [g["slug"] for g in genres] == ["featured", "horror", "history", "absurd"]
        assert genres[1]["covers"] == [10, 11, 12]

    def test_featured_leads_with_live_covers(self):
        """Featured leads, with live covers rather than hand-picked ones."""
        genres = self.featured(trending_covers=[7, 8, 9])
        assert genres[0]["slug"] == "featured"
        assert genres[0]["kind"] == "featured"
        assert genres[0]["covers"] == [7, 8, 9]

    def test_live_trending_covers_beat_the_picked_fallback(self):
        genres = self.featured(picked={**PICKED_COVERS, "featured": [40, 41, 42]}, trending_covers=[7, 8, 9])
        assert genres[0]["covers"] == [7, 8, 9]

    def test_empty_featured_falls_back_to_picked_covers(self):
        """A Solr error or a dev index without trending data mustn't leave (and cache) a blank tile."""
        genres = self.featured(picked={**PICKED_COVERS, "featured": [40, 41, 42]}, trending_covers=[])
        assert (genres[0]["slug"], genres[0]["covers"]) == ("featured", [40, 41, 42])

    def test_featured_without_any_covers_still_gets_a_tile(self):
        genres = self.featured(trending_covers=[])
        assert (genres[0]["slug"], genres[0]["covers"]) == ("featured", [])

    def test_featured_tile_covers_come_from_its_row_query(self):
        docs = [{"cover_i": 5}, {}, {"cover_i": 6}, {"cover_i": 7}, {"cover_i": 8}]
        with patch.object(home, "work_search_async", new=AsyncMock(return_value={"docs": docs})) as search:
            assert home.get_featured_tile_covers() == [5, 6, 7]
        query, kwargs = search.call_args.args[0], search.call_args.kwargs
        assert (query["q"], query["has_fulltext"], kwargs["sort"]) == (TRENDING_QUERY, "true", "trending")

    def test_no_picked_covers_no_tile(self):
        genres = self.featured(picked={"horror": [10, 11, 12]})
        assert [g["slug"] for g in genres] == ["featured", "horror"]

    def test_names_are_localized_per_page_not_in_the_cache(self):
        genres = self.featured()
        assert [g["name"] for g in genres] == ["Featured", "Horror", "History", "Absurd"]
        with (
            patch.object(home, "get_cached_featured_genres", return_value=genres),
            patch.object(home.home_genres, "subject_tile_labels", return_value={"history": "Histoire"}),
            patch.object(home.home_genres, "subgenre_labels", return_value={"world-war-ii": "Seconde Guerre mondiale"}),
            patch.object(home.home_genres, "language_marc", return_value="fre"),
            patch.object(home.admin, "get_stats", return_value=None),
            patch.object(home, "get_blog_feeds", return_value=[]),
            patch.object(home, "render_template", return_value={}) as render,
        ):
            home.get_homepage(devmode=False)
        featured = render.call_args.kwargs["featured_genres"]
        assert [g["name"] for g in featured] == ["Featured", "Horror", "Histoire", "Absurd"]
        assert [s["name"] for s in featured[2]["subgenres"]] == ["Seconde Guerre mondiale"]

    def test_thin_subgenre_rows_are_dropped_per_page_language(self):
        genres = self.featured()
        with (
            patch.object(home, "get_cached_featured_genres", return_value=genres),
            patch.object(home.home_genres, "language_marc", return_value="jpn"),
            patch.object(home.admin, "get_stats", return_value=None),
            patch.object(home, "get_blog_feeds", return_value=[]),
            patch.object(home, "render_template", return_value={}) as render,
        ):
            home.get_homepage(devmode=False)
        assert render.call_args.kwargs["featured_genres"][2]["subgenres"] == []

    def test_solr_failure_costs_the_rail_not_the_page(self):
        with (
            patch.object(home, "get_cached_featured_genres", side_effect=RuntimeError("solr down")),
            patch.object(home.admin, "get_stats", return_value=None),
            patch.object(home, "get_blog_feeds", return_value=[]),
            patch.object(home, "render_template", return_value={}) as render,
        ):
            home.get_homepage(devmode=False)
        assert render.call_args.kwargs["featured_genres"] == []

    def test_picked_covers_file_covers_the_tiles(self):
        """Every tile has picked covers; the file may also hold covers for genres waiting on subgenres."""
        picked = home.home_genres.load_tile_covers()
        slugs = {g["slug"] for g in home.home_genres.load_home_genres()} | {FEATURED["slug"]}
        assert slugs <= set(picked)
        assert all(len(covers) == home.GENRE_TILE_COVERS for covers in picked.values())

    def test_a_genre_without_subgenres_gets_no_tile(self):
        def node(slug, readable_count, *subgenres):
            return {"name": slug.title(), "slug": slug, "query": f"{slug}*", "readable_count": readable_count, "subgenres": list(subgenres)}

        data = {
            "genres": [
                node("horror", 5000, node("gothic", 249)),
                node("western", 6873),
                node("drama", 13079, node("melodrama", 7)),
            ],
            "subjects": [],
        }
        with patch.object(home.home_genres, "GENRES_JSON_PATH", Mock(read_text=Mock(return_value=json.dumps(data)))):
            home.home_genres.load_home_genres.cache_clear()
            try:
                assert [g["slug"] for g in home.home_genres.load_home_genres()] == ["horror"]
            finally:
                home.home_genres.load_home_genres.cache_clear()


class TestShelfLanguage:
    """Shelves filter to the UI language when it's populated; subgenre rows must still be worth a row in it."""

    def marc(self, lang):
        with (
            patch("openlibrary.plugins.upstream.utils.convert_iso_to_marc", side_effect={"en": "eng", "es": "spa", "la": "lat", "pt": "por"}.get),
            patch("openlibrary.plugins.upstream.utils.get_populated_languages", return_value={"eng", "spa", "lat"}),
        ):
            return home.home_genres.language_marc(lang)

    def test_populated_languages_filter_except_latin(self):
        assert (self.marc("en"), self.marc("es"), self.marc("la"), self.marc("pt"), self.marc(None)) == ("eng", "spa", None, None, "eng")

    def test_subgenre_rows_need_books_in_the_language(self):
        def sub(slug, **by_language):
            return {"name": slug, "slug": slug, "query": slug, "work_count": 99, "readable_count": 99, "readable_by_language": by_language}

        genre = {**TILE_GENRES[0], "subgenres": [sub("a", eng=25, spa=10), sub("b", eng=19, spa=7), sub("c", eng=500, spa=0)]}
        rows = lambda marc: [s["slug"] for s in home.home_genres.subgenres_for(genre, marc)]  # noqa: E731
        assert rows(None) == ["a", "b", "c"]
        assert rows("eng") == ["a", "c"]  # English keeps the 20 bar
        assert rows("spa") == ["a"]  # other languages: 8

    def test_rows_without_language_counts_fall_back_to_the_overall_count(self):
        genre = {**TILE_GENRES[0], "subgenres": [{"name": "x", "slug": "x", "query": "x", "work_count": 30, "readable_count": 30}]}
        assert [s["slug"] for s in home.home_genres.subgenres_for(genre, "spa")] == ["x"]


class TestFeaturedStack:
    """The Featured stack isn't in the vocabulary: its rows are whole clauses across every genre."""

    def test_is_found_by_slug_but_not_a_vocabulary_genre(self):
        assert home.home_genres.find_genre("featured") is FEATURED
        assert "featured" not in {g["slug"] for g in home.home_genres.load_home_genres()}

    def test_query_is_the_clause_itself(self):
        assert home.home_genres.solr_query(FEATURED) == "trending_score_hourly_sum:[1 TO *] AND readinglog_count:[4 TO *]"
        assert (
            home.home_genres.search_url(FEATURED)
            == "/search?q=trending_score_hourly_sum%3A%5B1+TO+%2A%5D+AND+readinglog_count%3A%5B4+TO+%2A%5D&sort=trending&has_fulltext=true"
        )

    def test_name_is_translated(self):
        with patch.object(home.home_genres, "_", side_effect=lambda text: f"<{text}>"):
            assert home.home_genres.display_name(FEATURED) == "<Featured>"

    def test_rows_are_distinct_signals_with_their_own_sort(self):
        """Each row is a whole clause with its own order, not a subject within Featured; What's new starts last year."""
        rows = {s["slug"]: s for s in FEATURED["subgenres"]}
        assert list(rows) == ["whats-new", "books-we-love", "classics", "most-wanted"]
        assert [s["sort"] for s in rows.values()] == ["new", "random.daily", "trending", "want_to_read"]
        with patch.object(home.home_genres, "datetime") as now:
            now.now.return_value.year = 2026
            assert home.home_genres.solr_query(rows["whats-new"], FEATURED) == "first_publish_year:[2025 TO *] AND readinglog_count:[2 TO *]"
        assert home.home_genres.solr_query(rows["most-wanted"], FEATURED) == "want_to_read_count:[10 TO *]"
        assert "subject_key" not in home.home_genres.search_url(rows["most-wanted"], parent=FEATURED)

    def test_rows_show_in_every_language(self):
        """The rows have no per-language counts; the thin-row rule is for vocabulary subgenres."""
        assert home.home_genres.subgenres_for(FEATURED, "spa") == FEATURED["subgenres"]

    def test_row_names_are_translated(self):
        with patch.object(home.home_genres, "_", side_effect=lambda text: f"<{text}>"):
            assert [home.home_genres.subgenre_name(s) for s in FEATURED["subgenres"]] == ["<What's new>", "<Books we love>", "<Classics>", "<Most wanted>"]


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
