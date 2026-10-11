"""Tests for partials.py functionality."""

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import web
from pydantic import ValidationError

from openlibrary.core.vendors import betterworldbooks_fmt
from openlibrary.plugins.openlibrary import code  # noqa: F401  # code.setup() imports partials; import it first
from openlibrary.plugins.openlibrary.partials import (
    LIST_CAROUSEL_MAX,
    AffiliateOffer,
    AffiliateStoreBuildContext,
    BookPageListsPartial,
    CarouselPartial,
    LazyCarouselParams,
    NearbyBooksParams,
    NearbyBooksPartial,
    ReadingGoalProgressPartial,
    _solr_query_to_subject_key,
    build_carousel_placeholder_config,
    build_nearby_books_placeholder_config,
    build_stores,
    gather_list_carousel_docs_async,
    gather_nearby_books_async,
)
from openlibrary.plugins.upstream.yearly_reading_goals import YearlyGoal
from openlibrary.utils.solr import Solr


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
    with patch("openlibrary.plugins.openlibrary.partials.render_macro", return_value={"__body__": "<div>loading</div>"}):
        config = build_nearby_books_placeholder_config("/works/OL1W", "eng")
    assert json.loads(config["lazy_config_json"]) == {"partial": "NearbyBooks", "work_key": "/works/OL1W", "language": "eng"}
    assert config["fallback"] is None


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


LIST_KEY = "/people/curator/lists/OL1L"


def _thing(key, type_, **data):
    thing = SimpleNamespace(key=key, type=SimpleNamespace(key=f"/type/{type_}"), **data)
    thing.get = lambda name, default=None: getattr(thing, name, default)
    return thing


def _fake_list_env(seed_keys, things, solr_works, solr_editions=None, years=None):
    """Patch the list, infobase and Solr that gather_list_carousel_docs_async reads.

    ``things`` are the infobase records by key; ``solr_works`` maps an indexed work key
    to whether it is readable; ``solr_editions`` maps an indexed edition key to its ebook_access;
    ``years`` maps a work key to its first publish year.
    """
    lst = SimpleNamespace(get_seeds=lambda: [SimpleNamespace(key=key) for key in seed_keys])
    infobase = Mock(get=Mock(return_value=lst), get_many=Mock(side_effect=lambda keys: [things[key] for key in keys if key in things]))
    solr_editions = solr_editions or {}
    years = years or {}

    async def work_search(param, **kwargs):
        wanted = set(re.findall(r"/works/OL\d+W", param["q"]))
        readable_only = param.get("has_fulltext") == "true"
        docs = [{"key": key, "first_publish_year": years.get(key)} for key, readable in solr_works.items() if key in wanted and (readable or not readable_only)]
        return {"docs": docs}

    async def get_many_async(keys, **kwargs):
        return [{"key": key, "ebook_access": solr_editions[key]} for key in keys if key in solr_editions]

    work_search_mock = AsyncMock(side_effect=work_search)
    patches = (
        patch("openlibrary.plugins.openlibrary.partials.site", Mock(get=Mock(return_value=infobase))),
        patch("openlibrary.plugins.openlibrary.partials.work_search_async", work_search_mock),
        patch("openlibrary.plugins.worksearch.search.get_solr", Mock(return_value=Mock(get_many_async=get_many_async))),
        patch("openlibrary.plugins.openlibrary.partials.add_availability_async", AsyncMock()),
    )
    return patches, work_search_mock, infobase


async def _gather(seed_keys, things, solr_works, solr_editions=None, *, years=None, has_fulltext_only=False, sort=""):
    patches, _, _ = _fake_list_env(seed_keys, things, solr_works, solr_editions, years)
    with patches[0], patches[1], patches[2], patches[3]:
        return await gather_list_carousel_docs_async(LIST_KEY, "", has_fulltext_only, sort)


def _shown(docs):
    """What each card shows: its edition if it has one, else its work."""
    return [doc["editions"]["docs"][0]["key"] if "editions" in doc else doc["key"] for doc in docs]


class TestGatherListCarouselDocsAsync:
    @pytest.mark.asyncio
    async def test_cards_follow_list_order_and_keep_edition_picks(self):
        """Solr returns works in its own order, and one edition per work; neither may leak into the carousel."""
        things = {
            "/books/OL2M": _thing("/books/OL2M", "edition", works=[SimpleNamespace(key="/works/OL1W")]),
            "/works/OL2W": _thing("/works/OL2W", "work"),
            "/books/OL1M": _thing("/books/OL1M", "edition", works=[SimpleNamespace(key="/works/OL1W")]),
            "/books/OL9M": _thing("/books/OL9M", "edition", works=[SimpleNamespace(key="/works/OL1W")]),  # not indexed yet
        }
        solr_editions = {"/books/OL1M": "public", "/books/OL2M": "public"}
        seeds = ["/books/OL2M", "/works/OL2W", "subject:history", "/books/OL9M", "/books/OL1M"]

        docs = await _gather(seeds, things, {"/works/OL2W": True, "/works/OL1W": True}, solr_editions)

        assert _shown(docs) == ["/books/OL2M", "/works/OL2W", "/books/OL1M"]
        assert [doc["key"] for doc in docs] == ["/works/OL1W", "/works/OL2W", "/works/OL1W"]

    @pytest.mark.asyncio
    async def test_makes_one_work_query_however_many_editions_share_a_work(self):
        """Querying by edition_key yields one edition per work, which forces a query per edition."""
        seeds = [f"/books/OL{n}M" for n in range(1, 21)]
        things = {key: _thing(key, "edition", works=[SimpleNamespace(key="/works/OL1W")]) for key in seeds}
        patches, work_search, _ = _fake_list_env(seeds, things, {"/works/OL1W": True}, dict.fromkeys(seeds, "borrowable"))

        with patches[0], patches[1], patches[2], patches[3]:
            docs = await gather_list_carousel_docs_async(LIST_KEY, "", False)

        assert _shown(docs) == seeds
        work_search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_readable_only_drops_unreadable_works_and_editions(self):
        """A readable work can have an unreadable edition; filtering the work alone isn't enough."""
        things = {
            "/works/OL1W": _thing("/works/OL1W", "work"),
            "/works/OL2W": _thing("/works/OL2W", "work"),
            "/books/OL3M": _thing("/books/OL3M", "edition", works=[SimpleNamespace(key="/works/OL1W")]),
            "/books/OL4M": _thing("/books/OL4M", "edition", works=[SimpleNamespace(key="/works/OL1W")]),
        }
        solr_editions = {"/books/OL3M": "no_ebook", "/books/OL4M": "borrowable"}
        seeds = list(things)

        everything = await _gather(seeds, things, {"/works/OL1W": True, "/works/OL2W": False}, solr_editions)
        readable = await _gather(seeds, things, {"/works/OL1W": True, "/works/OL2W": False}, solr_editions, has_fulltext_only=True)

        assert _shown(everything) == seeds
        assert _shown(readable) == ["/works/OL1W", "/books/OL4M"]

    @pytest.mark.asyncio
    async def test_redirected_seeds_show_where_they_were_merged_once(self):
        """Lists keep the keys of merged records, and a merge can chain or land on another seed."""
        things = {
            "/works/OL1W": _thing("/works/OL1W", "redirect", location="/works/OL2W"),
            "/works/OL2W": _thing("/works/OL2W", "redirect", location="/works/OL3W"),
            "/works/OL3W": _thing("/works/OL3W", "work"),
            "/works/OL4W": _thing("/works/OL4W", "work"),
        }

        docs = await _gather(["/works/OL1W", "/works/OL4W", "/works/OL3W"], things, {"/works/OL3W": True, "/works/OL4W": True})

        assert _shown(docs) == ["/works/OL3W", "/works/OL4W"]

    @pytest.mark.asyncio
    async def test_shows_the_whole_list_up_to_the_cap(self):
        """Collection lists of 20-60 books must show in full, but a 754-book list must not cost 754 lookups."""
        seeds = [f"/works/OL{n}W" for n in range(1, 121)]
        things = {key: _thing(key, "work") for key in seeds}

        docs = await _gather(seeds, things, dict.fromkeys(seeds, True))

        assert _shown(docs) == seeds[:LIST_CAROUSEL_MAX]

    @pytest.mark.asyncio
    async def test_old_and_new_sort_by_first_publish_year(self):
        """The Haunted Library's series grids pass sort='old' to show each series in publication order."""
        seeds = ["/works/OL1W", "/works/OL2W", "/works/OL3W", "/works/OL4W"]
        things = {key: _thing(key, "work") for key in seeds}
        years = {"/works/OL1W": 1995, "/works/OL2W": None, "/works/OL3W": 1990, "/works/OL4W": 2001}
        solr_works = dict.fromkeys(seeds, True)

        assert _shown(await _gather(seeds, things, solr_works, years=years)) == seeds
        assert _shown(await _gather(seeds, things, solr_works, years=years, sort="old")) == ["/works/OL3W", "/works/OL1W", "/works/OL4W", "/works/OL2W"]
        assert _shown(await _gather(seeds, things, solr_works, years=years, sort="new")) == ["/works/OL4W", "/works/OL1W", "/works/OL3W", "/works/OL2W"]

    @pytest.mark.asyncio
    async def test_text_after_the_list_key_filters_the_works(self):
        """This is how safe mode keeps content-warning books off collection pages."""
        patches, work_search, _ = _fake_list_env(["/works/OL1W"], {"/works/OL1W": _thing("/works/OL1W", "work")}, {"/works/OL1W": True})

        with patches[0], patches[1], patches[2], patches[3]:
            await gather_list_carousel_docs_async(LIST_KEY, ' -subject:"content_warning:cover"', False)

        assert work_search.call_args.args[0]["q"].endswith(' -subject:"content_warning:cover"')


class TestCarouselPartialBySeed:
    @staticmethod
    async def _generate(params, **patches):
        book_data = dict.fromkeys(("show", "title", "url", "key", "grid", "compact", "loadjs", "config_json", "cards", "count", "shelf"))
        with (
            patch("openlibrary.plugins.openlibrary.partials.get_book_carousel_data", Mock(return_value=book_data)) as get_data,
            patch("openlibrary.plugins.openlibrary.partials.render_jinja_template", Mock(return_value="")),
            patch.multiple("openlibrary.plugins.openlibrary.partials", **patches),
        ):
            await CarouselPartial.generate_async(params)
        return get_data.call_args.kwargs

    @pytest.mark.asyncio
    async def test_list_carousel_loads_once_with_no_load_more(self):
        """The default SEARCH load-more would append Solr-ordered, edition-collapsed cards to a list carousel,
        and collection pages pass limit as a page size (6, 10, 20), so honouring it would cut lists short."""
        gather = AsyncMock(return_value=[{"key": "/works/OL1W"}])
        params = LazyCarouselParams(query=LIST_KEY, limit=6, sort="old", has_fulltext_only=False, by_seed=True, safe_mode=True)

        kwargs = await self._generate(params, gather_list_carousel_docs_async=gather)

        gather.assert_awaited_once_with(LIST_KEY, ' -subject:"content_warning:cover"', False, "old")
        assert kwargs["load_more"] is None


class TestBuildCarouselPlaceholderConfig:
    @staticmethod
    def _config(**params):
        with patch("openlibrary.plugins.openlibrary.partials.render_macro", return_value={"__body__": ""}):
            return json.loads(build_carousel_placeholder_config(query=LIST_KEY, **params)["lazy_config_json"])

    def test_by_seed_reaches_the_lazy_partial(self):
        """Without it the lazy carousel silently falls back to the search path and loses edition picks."""
        assert self._config(by_seed=True)["by_seed"] is True
