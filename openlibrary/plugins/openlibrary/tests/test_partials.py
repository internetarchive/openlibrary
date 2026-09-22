"""Tests for partials.py functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
import web

from openlibrary.core.vendors import betterworldbooks_fmt
from openlibrary.plugins.openlibrary.partials import (
    AffiliateOffer,
    AffiliateStoreBuildContext,
    BookPageListsPartial,
    NearbyBooksPartial,
    _solr_query_to_subject_key,
    build_stores,
    gather_nearby_books_async,
)


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


class TestGatherNearbyBooksAsync:
    """Tests for the "Nearby Books" (DDC shelf-adjacency) Solr queries."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_work_has_no_ddc_sort(self):
        mock_solr = Mock()
        mock_solr.get_async = AsyncMock(return_value=None)

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await gather_nearby_books_async("/works/OL1W", language=None, limit=20)

        assert docs == []
        mock_solr.get_async.assert_awaited_once_with("/works/OL1W", fields=["ddc_sort"])

    @pytest.mark.asyncio
    async def test_returns_empty_for_non_numeric_ddc_sort(self):
        """[Fic]/[E] etc. sort after every number and aren't a real shelf position."""
        mock_solr = Mock()
        mock_solr.get_async = AsyncMock(return_value={"ddc_sort": "[Fic]"})

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await gather_nearby_books_async("/works/OL1W", language=None, limit=20)

        assert docs == []

    @pytest.mark.asyncio
    async def test_anchors_on_the_works_indexed_ddc_sort_with_strict_bounds(self):
        """The anchor is the work's own ddc_sort (fetched from Solr), not a
        value recomputed from whichever edition happens to be viewed."""
        mock_solr = Mock()
        mock_solr.get_async = AsyncMock(return_value={"ddc_sort": "813.54"})
        mock_solr.select_async = AsyncMock(
            side_effect=[
                _solr_result([{"key": "/works/OL2W"}]),  # exact
                _solr_result([{"key": "/works/OL3W"}]),  # before
                _solr_result([{"key": "/works/OL4W"}]),  # after
            ]
        )

        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=mock_solr):
            docs = await gather_nearby_books_async("/works/OL1W", language="eng", limit=20)

        assert [d["key"] for d in docs] == ["/works/OL3W", "/works/OL2W", "/works/OL4W"]

        queries = [c.args[0] for c in mock_solr.select_async.call_args_list]
        assert 'ddc_sort:"813.54"' in queries[0]
        assert 'ddc_sort:["000" TO "813.54"}' in queries[1]
        assert 'ddc_sort:{"813.54" TO "999.99999"]' in queries[2]
        assert all('-key:"/works/OL1W"' in q for q in queries)
        assert all('language:"eng"' in q for q in queries)
        assert all("content_warning:cover" in q for q in queries)
        assert all("type:work" in q for q in queries)


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
