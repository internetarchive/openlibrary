"""Tests for partials.py functionality."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import web
from pydantic import ValidationError

from openlibrary.core.vendors import betterworldbooks_fmt
from openlibrary.plugins.openlibrary import code, home_genres  # noqa: F401  # code.setup() imports partials; import it first
from openlibrary.plugins.openlibrary.partials import (
    AffiliateOffer,
    AffiliateStoreBuildContext,
    BookPageListsPartial,
    CarouselPartial,
    HomeGenreParams,
    HomeGenrePartial,
    LazyCarouselParams,
    NearbyBooksParams,
    NearbyBooksPartial,
    ReadingGoalProgressPartial,
    _carousel_card_book,
    _solr_query_to_subject_key,
    build_nearby_books_placeholder_config,
    build_stores,
    gather_nearby_books_async,
)
from openlibrary.plugins.upstream.yearly_reading_goals import YearlyGoal
from openlibrary.utils.solr import Solr

HORROR = {
    "name": "Horror",
    "slug": "horror",
    "query": "(horror* OR fiction_horror*)",
    "kind": "genre",
    "subgenres": [
        {"name": "Gothic", "slug": "gothic", "query": "gothic_fiction*"},
        {"name": "Psychological", "slug": "psychological", "query": "psychological_fiction*", "requiresIntersection": True},
    ],
}


class TestHomeGenreNarrow:
    """A subgenre row searches the subgenre alone, unless it's ambiguous and must be scoped to its genre."""

    def narrow(self, subgenre=None, sort="trending"):
        params = LazyCarouselParams(query="stale", genre="horror", subgenre=subgenre, sort=sort, safe_mode=False)
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_request_lang", return_value=None),
            patch("openlibrary.plugins.openlibrary.home_genres.user_language_clause", return_value=""),
        ):
            return HomeGenrePartial.narrow(params, HORROR)

    def test_genre_row_is_titled_for_its_sort(self):
        params = self.narrow()
        assert params.query == "subject_key:(horror* OR fiction_horror*)"
        assert params.subgenre is None
        assert params.title == "Trending in Horror"
        assert self.narrow(sort="new").title == "Newest in Horror"
        assert self.narrow(sort="rating").title == "Top rated in Horror"

    def test_subgenre_row_searches_the_subgenre_alone(self):
        params = self.narrow("gothic")
        assert params.query == "subject_key:gothic_fiction*"
        assert "gothic_fiction" in params.url
        assert params.title == "Gothic"
        assert self.narrow("gothic", sort="new").title == "Gothic"

    def test_ambiguous_subgenre_is_scoped_to_its_genre(self):
        """Psychological on its own is mostly "psychological aspects"; requiresIntersection keeps it in Horror."""
        params = self.narrow("psychological")
        assert params.query == "subject_key:(horror* OR fiction_horror*) AND subject_key:psychological_fiction*"
        assert "horror" in params.url
        assert params.title == "Psychological"

    def test_every_row_links_with_the_shelf_sort(self):
        """A subgenre row's link follows the shelf's sort."""
        for subgenre in (None, "gothic"):
            params = self.narrow(subgenre, sort="rating")
            assert "sort=rating" in params.url
            assert "sort=trending" not in params.url

    def test_trending_stack_rows_say_only_their_order(self):
        """The Trending shelf's row isn't "Trending in Trending"."""
        trending = home_genres.TRENDING
        with patch("openlibrary.plugins.openlibrary.home_genres.user_language_clause", return_value=" language:eng"):
            params = HomeGenrePartial.narrow(LazyCarouselParams(query="stale", genre="trending", sort="trending", safe_mode=False), trending)
        assert params.query == f"{trending['query']} language:eng"
        assert "language%3Aeng" in params.url
        assert params.title == "Trending now"
        assert HomeGenrePartial.jump_links(trending) == []

    def test_unknown_subgenre_falls_back_to_the_genre(self):
        params = self.narrow("romance")
        assert params.query == "subject_key:(horror* OR fiction_horror*)"
        assert params.subgenre is None

    def test_jump_links_go_to_the_subgenre_rows(self):
        assert HomeGenrePartial.jump_links(HORROR) == [
            {"name": "Gothic", "href": "#genre-horror-gothic"},
            {"name": "Psychological", "href": "#genre-horror-psychological"},
        ]


class TestHomeGenreShelf:
    """One request renders the header, the loaded genre row and a lazy placeholder per subgenre."""

    @pytest.fixture(autouse=True)
    def setup_context(self, request_context_fixture):
        request_context_fixture(lang="en")

    async def shelf(self, genre=HORROR):
        render = AsyncMock(return_value={"partials": "<ol-carousel></ol-carousel>"})
        with (
            patch("openlibrary.plugins.openlibrary.home_genres.find_genre", return_value=genre),
            patch("openlibrary.plugins.openlibrary.home_genres.user_language_clause", return_value=""),
            patch.object(CarouselPartial, "generate_async", render),
            # Stub the macro, not the Jinja global: imported macros snapshot globals on first import.
            patch.dict(web.template.Template.globals, {"macros": {"icon": lambda *a, **kw: ""}}),
        ):
            html = (await HomeGenrePartial.generate_async(HomeGenreParams(genre=genre["slug"])))["partials"]
        return html, render.call_args.args[0]

    @pytest.mark.asyncio
    async def test_genre_row_is_rendered_and_subgenre_rows_are_lazy(self):
        html, row = await self.shelf()
        assert (row.genre, row.subgenre, row.key, row.layout, row.sort, row.see_all) == (
            "horror",
            None,
            "genre-horror",
            "ol-carousel",
            "trending",
            True,
        )
        assert "<ol-carousel></ol-carousel>" in html
        assert 'class="lazy-carousel-loaded"' in html
        assert html.count('class="lazy-carousel"') == 2
        assert 'data-sort="trending"' in html
        assert html.count("genre-shelf__sort") == 1
        assert 'class="genre-shelf__sort" label="Sort by" heading="Sort by" value="trending"' in html
        assert "carousel-sort" not in html
        assert html.count("carousel-skeleton__see-all") == 2
        assert 'id="genre-horror-gothic"' in html
        assert 'id="genre-horror-psychological"' in html
        assert "subgenre&#34;: &#34;gothic" in html or "subgenre&quot;: &quot;gothic" in html

    @pytest.mark.asyncio
    async def test_header_names_the_genre_and_links_to_its_rows(self):
        html, _row = await self.shelf()
        assert '<h2 class="genre-shelf__title">Horror</h2>' in html
        assert 'href="#genre-horror-gothic"\n                               data-ol-link-track="BrowseStacks|JumpTo|genre-horror-gothic">Gothic</a>' in html
        assert 'data-ol-link-track="BrowseStacks|JumpTo|genre-horror-psychological">Psychological</a>' in html
        assert "Browse all" not in html
        assert html.index("genre-shelf__header") < html.index("genre-shelf__sort") < html.index("lazy-carousel-loaded")

    @pytest.mark.asyncio
    async def test_trending_shelf_has_no_sort(self):
        html, _row = await self.shelf(home_genres.TRENDING)
        assert 'data-genre="trending"' in html
        assert "genre-shelf__sort" not in html

    @pytest.mark.asyncio
    async def test_unknown_genre_is_empty(self):
        with patch("openlibrary.plugins.openlibrary.home_genres.find_genre", return_value=None):
            assert await HomeGenrePartial.generate_async(HomeGenreParams(genre="nope")) == {"partials": ""}


class TestCarouselCardBook:
    def test_edition_takes_the_works_byline_and_year(self):
        work = {
            "key": "/works/OL1W",
            "author_name": ["Robert A. Heinlein"],
            "first_publish_year": 1959,
            "editions": {"docs": [{"key": "/books/OL1M", "title": "Starship Troopers"}]},
        }
        card = _carousel_card_book(work)
        assert card.key == "/books/OL1M"
        assert card.work_key == "/works/OL1W"
        assert card.author_name == ["Robert A. Heinlein"]
        assert card.first_publish_year == 1959

    def test_work_without_editions_is_its_own_card(self):
        work = {"key": "/works/OL1W", "author_name": ["A"], "first_publish_year": 2000}
        card = _carousel_card_book(work)
        assert card.key == "/works/OL1W"
        assert card.author_name == ["A"]
        assert "work_key" not in card


class TestSolrQueryToSubjectKey:
    """Tests for _solr_query_to_subject_key conversion."""

    def test_subject_key_format(self):
        """Test subject_key: format conversion."""
        assert _solr_query_to_subject_key("subject_key:science") == "/subjects/science"

    def test_person_key_format(self):
        """Test person_key: format conversion."""
        assert _solr_query_to_subject_key("person_key:harry_potter") == "/subjects/person:harry_potter"

    def test_place_key_format(self):
        """Test place_key: format conversion."""
        assert _solr_query_to_subject_key("place_key:france") == "/subjects/place:france"

    def test_time_key_format(self):
        """Test time_key: format conversion."""
        assert _solr_query_to_subject_key("time_key:19th_century") == "/subjects/time:19th_century"

    def test_subject_seed_format(self):
        """Test subject: format conversion."""
        assert _solr_query_to_subject_key("subject:science") == "/subjects/science"

    def test_already_in_correct_format(self):
        """Test /subjects/ format passes through."""
        assert _solr_query_to_subject_key("/subjects/science") == "/subjects/science"

    def test_invalid_format_raises_error(self):
        """Test invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unable to convert query to subject key"):
            _solr_query_to_subject_key("invalid:format")


def _solr_result(docs):
    result = Mock()
    result.docs = docs
    return result


# Bypass the memcache memoization so results don't leak between tests.
_gather_nearby_books = gather_nearby_books_async.__wrapped__


class TestGatherNearbyBooksAsync:
    """Tests for the "Nearby Books" (DDC shelf-adjacency) Solr queries."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_work_has_no_ddc_sort(self):
        mock_solr = Mock()
        mock_solr.escape = Solr.escape
        mock_solr.select_async = AsyncMock(return_value=_solr_result([{"key": "/works/OL1W"}]))

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await _gather_nearby_books("/works/OL1W", language=None, limit=20)

        assert docs == []
        mock_solr.select_async.assert_awaited_once_with('key:"/works/OL1W"', fields=["ddc_sort"], rows=1)

    @pytest.mark.asyncio
    async def test_returns_empty_for_non_numeric_ddc_sort(self):
        """[Fic]/[E] etc. sort after every number and aren't a real shelf position."""
        mock_solr = Mock()
        mock_solr.escape = Solr.escape
        mock_solr.select_async = AsyncMock(return_value=_solr_result([{"ddc_sort": "[Fic]"}]))

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await _gather_nearby_books("/works/OL1W", language=None, limit=20)

        assert docs == []

    @pytest.mark.asyncio
    async def test_returns_none_when_solr_fails(self):
        """None (unlike []) is not memoized, so a Solr blip isn't pinned for 5 minutes."""
        mock_solr = Mock()
        mock_solr.escape = Solr.escape
        mock_solr.select_async = AsyncMock(side_effect=RuntimeError("solr down"))

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await _gather_nearby_books("/works/OL1W", language=None, limit=20)

        assert docs is None

    @pytest.mark.asyncio
    async def test_anchors_on_the_works_indexed_ddc_sort_with_strict_bounds(self):
        """The anchor is the work's own ddc_sort (fetched from Solr), not a
        value recomputed from whichever edition happens to be viewed."""
        mock_solr = Mock()
        mock_solr.escape = Solr.escape
        mock_solr.select_async = AsyncMock(
            side_effect=[
                _solr_result([{"ddc_sort": "813.54"}]),  # anchor
                _solr_result([{"key": "/works/OL2W"}]),  # exact
                _solr_result([{"key": "/works/OL3W"}]),  # before
                _solr_result([{"key": "/works/OL4W"}]),  # after
            ]
        )

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await _gather_nearby_books("/works/OL1W", language="eng", limit=20)

        assert [d["key"] for d in docs] == ["/works/OL3W", "/works/OL2W", "/works/OL4W"]

        queries = [c.args[0] for c in mock_solr.select_async.call_args_list][1:]
        assert 'ddc_sort:"813.54"' in queries[0]
        assert 'ddc_sort:["000" TO "813.54"}' in queries[1]
        assert 'ddc_sort:{"813.54" TO "999.99999"]' in queries[2]
        assert all('-key:"/works/OL1W"' in q for q in queries)
        assert all('language:"eng"' in q for q in queries)
        assert all("content_warning:cover" in q for q in queries)
        assert all(" AND ebook_access:[borrowable TO *]" in q for q in queries)
        assert all("type:work" in q for q in queries)

    @pytest.mark.asyncio
    async def test_escapes_solr_syntax_in_params(self):
        mock_solr = Mock()
        mock_solr.escape = Solr.escape
        mock_solr.select_async = AsyncMock(return_value=_solr_result([]))

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            await _gather_nearby_books('/works/OL1W" OR key:"', language=None, limit=20)

        assert mock_solr.select_async.call_args.args[0] == 'key:"/works/OL1W\\" OR key\\:\\""'


class TestNearbyBooksParams:
    @pytest.mark.parametrize(
        "params",
        [
            {"work_key": "/works/OL1W", "language": 'eng" OR title:*'},
            {"work_key": '/works/OL1W" OR key:"'},
            {"work_key": "/books/OL1M"},
            {"work_key": "/works/OL1W", "limit": 0},
            {"work_key": "/works/OL1W", "limit": 999},
        ],
    )
    def test_rejects_unsafe_or_out_of_range_params(self, params):
        with pytest.raises(ValidationError):
            NearbyBooksParams(**params)

    def test_accepts_valid_params(self):
        params = NearbyBooksParams(work_key="/works/OL1W", language="eng")
        assert params.limit == 20


class TestNearbyBooksPartial:
    @pytest.mark.asyncio
    async def test_generate_async_returns_empty_partial_when_no_neighbours(self):
        with patch(
            "openlibrary.plugins.openlibrary.partials.gather_nearby_books_async",
            AsyncMock(return_value=[]),
        ):
            params = Mock(work_key="/works/OL1W", language=None, limit=20)
            result = await NearbyBooksPartial.generate_async(params)

        assert result == {"partials": ""}

    @pytest.mark.asyncio
    async def test_generate_async_attaches_availability_to_the_solr_docs(self):
        """Raw Solr docs carry no lending state; the card badge needs it."""
        docs = [{"key": "/works/OL2W", "title": "Neighbour", "ia": ["neighbour"]}]
        with (
            patch("openlibrary.plugins.openlibrary.partials.gather_nearby_books_async", AsyncMock(return_value=docs)),
            patch("openlibrary.plugins.openlibrary.partials.add_availability_async", AsyncMock()) as add_availability,
            patch("openlibrary.plugins.openlibrary.partials.get_book_carousel_data", return_value={}),
            patch("openlibrary.plugins.openlibrary.partials.render_jinja_template", return_value="<div/>"),
        ):
            params = Mock(work_key="/works/OL1W", language=None, limit=20)
            result = await NearbyBooksPartial.generate_async(params)

        add_availability.assert_awaited_once_with(docs)
        assert result == {"partials": "<div/>"}


def test_build_nearby_books_placeholder_config_targets_the_nearby_books_partial():
    config = build_nearby_books_placeholder_config("/works/OL1W", "eng")
    assert json.loads(config["lazy_config_json"]) == {"partial": "NearbyBooks", "work_key": "/works/OL1W", "language": "eng"}
    assert config["fallback"] is None
    # The skeleton stands in for NearbyBooksPartial's slick row and its unlinked heading.
    assert (config["layout"], config["title_link"]) == ("carousel", False)


def _community_card(title: str) -> dict:
    """A card for a list with no owner, so the template needs no follow-button bridge."""
    return {
        "url": "/lists/OL1L",
        "showcase": {"title": title, "count": 2, "covers": [False], "last_mod": ""},
        "owner": None,
        "own_list": False,
        "is_public": False,
        "is_subscribed": 0,
    }


LISTS = [web.storage(key=f"/people/u/lists/OL{n}L", owner=None) for n in (1, 2, 3)]


class TestReadingGoalProgressPartial:
    """The async path renders the same component the sync path did."""

    @pytest.fixture(autouse=True)
    def setup_context(self, request_context_fixture):
        # gettext reads req_context.lang while rendering.
        request_context_fixture(lang="en")

    @pytest.mark.asyncio
    async def test_generate_async_renders_goal(self):
        goal = YearlyGoal(2026, 25, 10)
        with patch(
            "openlibrary.plugins.openlibrary.partials.get_reading_goals_async",
            new_callable=AsyncMock,
            return_value=goal,
        ) as mock_get:
            result = await ReadingGoalProgressPartial.generate_async("testuser", 2026)

        mock_get.assert_awaited_once_with("testuser", 2026)
        html = result["partials"]
        assert "reading-goal-progress__completed" in html
        assert "width: 40%" in html
        assert ">10</span>/<span" in html
        assert ">25</span>" in html

    @pytest.mark.asyncio
    async def test_generate_async_without_goal_renders_empty(self):
        with patch(
            "openlibrary.plugins.openlibrary.partials.get_reading_goals_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await ReadingGoalProgressPartial.generate_async("testuser", 2026)

        assert '<div class="reading-goal-progress">' not in result["partials"]


class TestBookPageListsPartial:
    """The Jinja render must degrade the way the Templetor render did, not 500."""

    @pytest.fixture(autouse=True)
    def setup_context(self, request_context_fixture):
        # Set in the sync fixture, not inside the async test: pytest-asyncio runs
        # the coroutine in a copied context, so a token created there cannot be
        # reset by the fixture's teardown.
        request_context_fixture(lang="en")

    @pytest.mark.asyncio
    async def test_broken_card_is_skipped(self):
        good = _community_card("Fine list")
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_lists_async", AsyncMock(return_value=LISTS)),
            patch.object(
                BookPageListsPartial,
                "get_list_card",
                side_effect=[good, AttributeError("'Thing' object has no attribute 'get_users_settings'"), good],
            ),
        ):
            result = await BookPageListsPartial.generate_async(workId="/works/OL1W", editionId="", user=None)

        assert result["hasLists"] is True
        html = result["partials"][0]
        assert html.count('class="list-follow-card"') == 2
        assert "Unable to render" not in html

    @pytest.mark.asyncio
    async def test_render_failure_keeps_old_fallback(self):
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_lists_async", AsyncMock(return_value=LISTS)),
            patch.object(BookPageListsPartial, "get_list_card", return_value=_community_card("Fine list")),
            patch(
                "openlibrary.plugins.openlibrary.partials.render_jinja_template",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await BookPageListsPartial.generate_async(workId="/works/OL1W", editionId="", user=None)

        assert result["hasLists"] is True
        assert result["partials"] == [BookPageListsPartial.RENDER_FALLBACK]


def _stores(bwb=None, amz=None, title="A Title", isbn="9780190906764", asin="0190906766", author=None) -> dict:
    ctx = AffiliateStoreBuildContext(title, isbn, asin, bwb, amz, author)
    return {store.key: store for store in build_stores(ctx)}


class TestBuildStores:
    def test_bwb_new_and_used(self):
        bwb = betterworldbooks_fmt("9780190906764", new_price="9.99", new_qty=3, used_price="4.28", used_qty=12) | {"market_price": "$12.49"}
        stores = _stores(bwb=bwb)
        assert stores["betterworldbooks"].offers == (
            AffiliateOffer(price="$9.99", amount=9.99, condition="new", quantity=3),
            AffiliateOffer(price="$4.28", amount=4.28, condition="used", quantity=12),
        )
        assert stores["betterworldbooks"].lowest_offer.price == "$4.28"
        assert stores["amazon"].offers == (AffiliateOffer(price="$12.49", amount=12.49),)

    def test_bwb_skips_condition_with_no_copies(self):
        bwb = betterworldbooks_fmt("9780190906764", new_price="9.99", new_qty=0, used_price="4.28", used_qty=1)
        assert [offer.condition for offer in _stores(bwb=bwb)["betterworldbooks"].offers] == ["used"]

    def test_bwb_legacy_metadata_falls_back_to_single_price(self):
        bwb = betterworldbooks_fmt("9780190906764", qlt="used", price="5.99") | {"new_price": None, "used_price": None}
        assert _stores(bwb=bwb)["betterworldbooks"].offers == (AffiliateOffer(price="$5.99", amount=5.99, condition="used"),)

    def test_out_of_stock_needs_explicit_zero_counts(self):
        assert _stores(bwb=betterworldbooks_fmt("9780190906764", new_qty=0, used_qty=0))["betterworldbooks"].out_of_stock
        assert not _stores(bwb=betterworldbooks_fmt("9780190906764"))["betterworldbooks"].out_of_stock
        assert not _stores()["betterworldbooks"].out_of_stock

    def test_amazon_offer_details(self):
        amz = {
            "price": "$6.12",
            "price_amt": 612,
            "list_price": "$17.00",
            "price_savings_pct": 64.4,
            "condition": "Used",
            "sub_condition": "LikeNew",
            "availability_message": "Usually ships within 2 to 3 days",
            "merchant": "Amazon.com",
            "deal_badge": "Limited time deal",
        }
        amazon = _stores(amz=amz)["amazon"]
        assert amazon.offers == (AffiliateOffer(price="$6.12", amount=6.12, condition="used", sub_condition="like_new", list_price="$17.00", savings_pct=64),)
        assert (amazon.availability, amazon.seller, amazon.deal) == ("Usually ships within 2 to 3 days", "Amazon.com", "Limited time deal")

    def test_no_metadata_has_no_offers(self):
        assert all(not store.offers for store in _stores().values())


class TestStoreLinks:
    def test_isbn_links_to_each_store_product_page(self):
        stores = _stores()
        assert stores["betterworldbooks"].link == "https://www.betterworldbooks.com/product/detail/9780190906764"
        assert "/dp/0190906766/" in stores["amazon"].link
        assert stores["bookshop-org"].link.endswith("/9780190906764")

    def test_no_isbn_searches_every_store_by_title_and_author(self):
        stores = _stores(isbn=None, asin=None, author="An Author")
        assert list(stores) == ["betterworldbooks", "amazon", "bookshop-org"]
        assert stores["betterworldbooks"].link.endswith("/search/results?q=A+Title+An+Author")
        assert "/s?k=A%20Title%20An%20Author&i=stripbooks" in stores["amazon"].link
        assert stores["bookshop-org"].link.startswith("https://bookshop.org/beta-search?keywords=A+Title+An+Author")

    def test_searches_by_title_alone_when_the_author_is_unknown(self):
        assert _stores(isbn=None, asin=None)["betterworldbooks"].link.endswith("?q=A+Title")

    def test_nothing_to_search_by_leaves_only_the_bwb_row(self):
        assert list(_stores(title="", isbn=None, asin=None)) == ["betterworldbooks"]
