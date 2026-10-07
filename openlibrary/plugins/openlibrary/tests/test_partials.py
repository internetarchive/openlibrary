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
    AffiliateOffer,
    AffiliateStoreBuildContext,
    BookPageListsPartial,
    CarouselCardPartial,
    CarouselLoadMoreParams,
    CarouselPartial,
    LazyCarouselParams,
    NearbyBooksParams,
    NearbyBooksPartial,
    ReadingGoalProgressPartial,
    _solr_query_to_subject_key,
    build_carousel_placeholder_config,
    build_nearby_books_placeholder_config,
    build_stores,
    gather_list_carousel_data_async,
    gather_nearby_books_async,
    get_book_carousel_data,
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


# Bypass the memcache memoization so results don't leak between tests.
_gather_list_carousel_data = gather_list_carousel_data_async.__wrapped__

LIST_KEY = "/people/curator/lists/OL1L"


def _fake_list_carousel_env(seed_keys, solr_works):
    """Patch the list and Solr that gather_list_carousel_data_async talks to.

    ``solr_works`` maps a work key to ``{edition key: is_readable}``. The fake Solr
    answers like the real one: a work doc per matching work, carrying one edition.
    """
    lst = SimpleNamespace(get_seeds=lambda: [SimpleNamespace(key=key) for key in seed_keys])
    queries = []

    async def work_search(param, **kwargs):
        q = param["q"]
        queries.append(param)
        readable_only = param.get("has_fulltext") == "true"
        docs = []
        for work_key, editions in solr_works.items():
            candidates = {key: readable for key, readable in editions.items() if readable or not readable_only}
            if q.startswith("key:("):
                wanted = set(re.findall(r"/works/OL\d+W", q))
                matching = list(candidates) if work_key in wanted else []
            else:
                wanted = {f"/books/{olid}" for olid in re.findall(r"OL\d+M", q)}
                matching = [key for key in candidates if key in wanted]
            if matching:
                docs.append({"key": work_key, "title": work_key, "editions": {"docs": [{"key": matching[0]}]}})
        return {"docs": docs}

    patches = (
        patch("openlibrary.plugins.openlibrary.partials.site", Mock(get=Mock(return_value=Mock(get=Mock(return_value=lst))))),
        patch("openlibrary.plugins.openlibrary.partials.work_search_async", side_effect=work_search),
    )
    return patches, queries


async def _gather_list_pages(seed_keys, solr_works, *, has_fulltext_only, limit):
    """Walk a list the way the carousel does: start at 0, then resume from next_offset."""
    patches, _ = _fake_list_carousel_env(seed_keys, solr_works)
    shown = []
    offset: int | None = 0
    with patches[0], patches[1]:
        while offset is not None:
            page = await _gather_list_carousel_data(f"{LIST_KEY}", offset, limit, has_fulltext_only)
            shown += [doc["editions"]["docs"][0]["key"] for doc in page["docs"]]
            offset = page["next_offset"]
    return shown


class TestGatherListCarouselDataAsync:
    """Tests for the per-seed list carousel query."""

    @pytest.mark.asyncio
    async def test_editions_of_one_work_each_get_a_card_in_list_order(self):
        seeds = ["/books/OL3M", "/books/OL1M", "/books/OL2M"]
        solr_works = {"/works/OL1W": {"/books/OL1M": True, "/books/OL2M": True}, "/works/OL2W": {"/books/OL3M": True}}
        patches, _ = _fake_list_carousel_env(seeds, solr_works)

        with patches[0], patches[1]:
            data = await _gather_list_carousel_data(LIST_KEY, 0, 20, False)

        assert [doc["editions"]["docs"][0]["key"] for doc in data["docs"]] == seeds
        assert data["next_offset"] is None

    @pytest.mark.asyncio
    async def test_work_and_subject_seeds_are_handled_alongside_editions(self):
        seeds = ["/works/OL2W", "subject:history", "/books/OL1M"]
        solr_works = {"/works/OL1W": {"/books/OL1M": True}, "/works/OL2W": {"/books/OL2M": True}}
        patches, _ = _fake_list_carousel_env(seeds, solr_works)

        with patches[0], patches[1]:
            data = await _gather_list_carousel_data(LIST_KEY, 0, 20, False)

        assert [doc["key"] for doc in data["docs"]] == ["/works/OL2W", "/works/OL1W"]
        assert data["next_offset"] is None

    @pytest.mark.asyncio
    async def test_unreadable_seeds_are_kept_unless_readable_only_is_asked_for(self):
        seeds = ["/books/OL1M", "/books/OL2M"]
        solr_works = {"/works/OL1W": {"/books/OL1M": True}, "/works/OL2W": {"/books/OL2M": False}}
        patches, queries = _fake_list_carousel_env(seeds, solr_works)

        with patches[0], patches[1]:
            everything = await _gather_list_carousel_data(LIST_KEY, 0, 20, False)
            readable = await _gather_list_carousel_data(LIST_KEY, 0, 20, True)

        assert len(everything["docs"]) == 2
        assert [doc["key"] for doc in readable["docs"]] == ["/works/OL1W"]
        assert "has_fulltext" not in queries[0]
        assert queries[-1]["has_fulltext"] == "true"

    @pytest.mark.asyncio
    async def test_resumes_from_the_seed_offset_not_the_number_of_docs(self):
        """Seeds without a doc are still consumed, so the next page starts after them."""
        seeds = [f"/books/OL{n}M" for n in range(1, 7)]
        solr_works = {f"/works/OL{n}W": {f"/books/OL{n}M": n in (1, 5)} for n in range(1, 7)}
        patches, _ = _fake_list_carousel_env(seeds, solr_works)

        with patches[0], patches[1]:
            first = await _gather_list_carousel_data(LIST_KEY, 0, 4, True)
            second = await _gather_list_carousel_data(LIST_KEY, first["next_offset"], 4, True)

        assert [doc["key"] for doc in first["docs"]] == ["/works/OL1W"]
        assert first["next_offset"] == 4
        assert [doc["key"] for doc in second["docs"]] == ["/works/OL5W"]
        assert second["next_offset"] is None

    @pytest.mark.asyncio
    async def test_readable_only_list_with_unreadable_seeds_has_no_duplicates_and_reaches_the_end(self):
        seeds = [f"/books/OL{n}M" for n in range(1, 21)]
        readable = {n for n in range(1, 21) if n % 3 == 1}
        solr_works = {f"/works/OL{n}W": {f"/books/OL{n}M": n in readable} for n in range(1, 21)}

        shown = await _gather_list_pages(seeds, solr_works, has_fulltext_only=True, limit=5)

        assert shown == [f"/books/OL{n}M" for n in sorted(readable)]

    @pytest.mark.asyncio
    async def test_seed_missing_from_solr_does_not_cause_duplicates_on_the_next_page(self):
        seeds = ["/books/OL1M", "/books/OL2M", "/books/OL3M", "/books/OL4M"]
        solr_works = {"/works/OL1W": {"/books/OL1M": True}, "/works/OL3W": {"/books/OL3M": True}, "/works/OL4W": {"/books/OL4M": True}}

        shown = await _gather_list_pages(seeds, solr_works, has_fulltext_only=False, limit=2)

        assert shown == ["/books/OL1M", "/books/OL3M", "/books/OL4M"]

    @pytest.mark.asyncio
    async def test_text_after_the_list_key_filters_the_docs(self):
        patches, queries = _fake_list_carousel_env(["/books/OL1M"], {"/works/OL1W": {"/books/OL1M": True}})

        with patches[0], patches[1]:
            await _gather_list_carousel_data(f'{LIST_KEY} -subject:"content_warning:cover"', 0, 20, False)

        assert queries[0]["q"] == 'edition_key:(OL1M) -subject:"content_warning:cover"'

    @pytest.mark.asyncio
    async def test_query_that_is_not_a_list_key_has_no_docs(self):
        data = await _gather_list_carousel_data("subject:science", 0, 20, False)

        assert data == {"docs": [], "next_offset": None}

    @pytest.mark.asyncio
    async def test_solr_error_ends_the_carousel_and_is_not_cacheable(self):
        patches, _ = _fake_list_carousel_env(["/books/OL1M"], {})

        with patches[0], patch("openlibrary.plugins.openlibrary.partials.work_search_async", AsyncMock(return_value={"docs": [], "error": "boom"})):
            data = await _gather_list_carousel_data(LIST_KEY, 0, 20, False)

        assert data == {"docs": [], "next_offset": None, "error": True}


class TestCarouselCardPartialListQuery:
    @pytest.mark.asyncio
    async def test_load_more_reports_the_seed_to_resume_from(self):
        params = CarouselLoadMoreParams(queryType="LIST", q=LIST_KEY, limit=18, page=18, hasFulltextOnly=True)
        list_data = {"docs": [], "next_offset": 36}

        with patch("openlibrary.plugins.openlibrary.partials.gather_list_carousel_data_async", AsyncMock(return_value=list_data)) as gather:
            response = await CarouselCardPartial.generate_async(params, "/collections/test")

        gather.assert_awaited_once_with(LIST_KEY, 18, 18, True)
        assert response == {"partials": [], "nextOffset": 36}

    @pytest.mark.asyncio
    async def test_load_more_reports_the_end_of_the_list(self):
        params = CarouselLoadMoreParams(queryType="LIST", q=LIST_KEY, page=36)

        with patch("openlibrary.plugins.openlibrary.partials.gather_list_carousel_data_async", AsyncMock(return_value={"docs": [], "next_offset": None})):
            response = await CarouselCardPartial.generate_async(params, "/collections/test")

        assert response["nextOffset"] is None

    @pytest.mark.asyncio
    async def test_other_query_types_have_no_next_offset(self):
        params = CarouselLoadMoreParams(queryType="SEARCH", q="subject:science")

        with patch.object(CarouselCardPartial, "_make_book_query", AsyncMock(return_value=[])):
            response = await CarouselCardPartial.generate_async(params, "/")

        assert response == {"partials": []}


class TestGetBookCarouselDataLoadMore:
    def test_cursor_mode_starts_at_the_given_seed(self):
        load_more = {"queryType": "LIST", "q": LIST_KEY, "limit": 20, "mode": "cursor", "page": 20}

        data = get_book_carousel_data(books=[], test=True, load_more=load_more, full_path="/")

        config = json.loads(data["config_json"])
        assert config["loadMore"]["pageMode"] == "cursor"
        assert config["loadMore"]["page"] == 20


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
    async def test_list_carousel_hands_the_next_seed_to_load_more(self):
        gather = AsyncMock(return_value={"docs": [{"key": "/works/OL1W"}], "next_offset": 20})
        params = LazyCarouselParams(query=LIST_KEY, limit=20, has_fulltext_only=False, by_seed=True, safe_mode=False)

        kwargs = await self._generate(params, gather_list_carousel_data_async=gather)

        gather.assert_awaited_once_with(LIST_KEY, 0, 20, False)
        assert kwargs["load_more"] == {"queryType": "LIST", "q": LIST_KEY, "limit": 20, "hasFulltextOnly": False, "mode": "cursor", "page": 20}

    @pytest.mark.asyncio
    async def test_list_carousel_that_shows_every_seed_has_no_load_more(self):
        gather = AsyncMock(return_value={"docs": [{"key": "/works/OL1W"}], "next_offset": None})
        params = LazyCarouselParams(query=LIST_KEY, by_seed=True)

        kwargs = await self._generate(params, gather_list_carousel_data_async=gather)

        assert kwargs["load_more"] is None

    @pytest.mark.asyncio
    async def test_query_carousel_is_unchanged_even_when_the_query_is_a_list_key(self):
        gather = AsyncMock(return_value={"docs": [{"key": "/works/OL1W"}]})
        list_gather = AsyncMock()
        params = LazyCarouselParams(query=LIST_KEY, limit=20)

        kwargs = await self._generate(params, gather_lazy_carousel_data_async=gather, gather_list_carousel_data_async=list_gather)

        list_gather.assert_not_awaited()
        assert kwargs["load_more"]["queryType"] == "SEARCH"


class TestBuildCarouselPlaceholderConfig:
    @staticmethod
    def _config(**params):
        with patch("openlibrary.plugins.openlibrary.partials.render_macro", return_value={"__body__": ""}):
            return json.loads(build_carousel_placeholder_config(query=LIST_KEY, **params)["lazy_config_json"])

    def test_by_seed_is_only_sent_for_list_carousels(self):
        assert self._config(by_seed=True)["by_seed"] is True
        assert "by_seed" not in self._config()
