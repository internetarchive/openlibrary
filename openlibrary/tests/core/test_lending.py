import asyncio
import json
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from openlibrary.core import lending
from openlibrary.utils.request_context import RequestContextVars, req_context


@pytest.mark.usefixtures("request_context_fixture")
class TestAddAvailability:
    def test_reads_ocaids(self, monkeypatch):
        async def mock_get_availability_async(id_type, ocaids):
            return {"foo": {"status": "available"}}

        monkeypatch.setattr(lending, "get_availability_async", mock_get_availability_async)

        f = lending.add_availability
        assert f([{"ocaid": "foo"}]) == [{"ocaid": "foo", "availability": {"status": "available"}}]
        assert f([{"identifier": "foo"}]) == [{"identifier": "foo", "availability": {"status": "available"}}]
        assert f([{"ia": "foo"}]) == [{"ia": "foo", "availability": {"status": "available"}}]
        assert f([{"ia": ["foo"]}]) == [{"ia": ["foo"], "availability": {"status": "available"}}]

    def test_handles_ocaid_none(self):
        f = lending.add_availability
        assert f([{}]) == [{}]

    def test_handles_availability_none(self, monkeypatch):
        async def mock_get_availability_async(id_type, ocaids):
            return {"foo": {"status": "error"}}

        monkeypatch.setattr(lending, "get_availability_async", mock_get_availability_async)

        f = lending.add_availability
        r = f([{"ocaid": "foo"}])
        print(r)
        assert r[0]["availability"]["status"] == "error"


class TestGetAvailability:
    @pytest.fixture(autouse=True)
    def setup_context(self):
        """Set up RequestContextVars with specific values for this test class."""
        token = req_context.set(
            RequestContextVars(
                x_forwarded_for="ol-internal",
                user_agent="test-user-agent",
                lang=None,
                solr_editions=True,
                print_disabled=False,
                is_bot=False,
            )
        )
        yield
        # Cleanup
        req_context.reset(token)

    def test_cache(self):
        mock_get = AsyncMock()
        with patch(
            "openlibrary.core.ia.get_async_session",
            return_value=SimpleNamespace(get=mock_get),
        ):
            mock_response = AsyncMock()
            mock_response.json = Mock(
                return_value={
                    "success": True,
                    "responses": {"foo": {"status": "open"}},
                }
            )
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            foo_expected = {
                "status": "open",
                "identifier": "foo",
                "is_restricted": False,
                "is_browseable": False,
                "__src__": "core.models.lending.get_availability",
            }
            bar_expected = {
                "status": "error",
                "identifier": "bar",
                "is_restricted": True,
                "is_browseable": False,
                "__src__": "core.models.lending.get_availability",
            }

            r = lending.get_availability("identifier", ["foo"])
            assert mock_get.call_count == 1
            assert r == {"foo": foo_expected}

            # Should not make a call to the API again
            r2 = lending.get_availability("identifier", ["foo"])
            assert mock_get.call_count == 1
            assert r2 == {"foo": foo_expected}

            # Now should make a call for just the new identifier
            mock_response.json = Mock(
                return_value={
                    "success": True,
                    "responses": {"bar": {"status": "error"}},
                }
            )
            r3 = lending.get_availability("identifier", ["foo", "bar"])
            assert mock_get.call_count == 2
            assert mock_get.call_args[1]["params"]["identifier"] == "bar"
            assert r3 == {"foo": foo_expected, "bar": bar_expected}

    @staticmethod
    def _session(responses_per_call):
        """Patch the shared async session; each GET answers with the next dict of `responses`."""
        mock_get = AsyncMock()
        replies = []
        for responses in responses_per_call:
            reply = Mock()
            reply.json = Mock(return_value={"success": True, "responses": responses})
            reply.raise_for_status = Mock()
            replies.append(reply)
        mock_get.side_effect = replies
        return patch("openlibrary.core.ia.get_async_session", return_value=SimpleNamespace(get=mock_get)), mock_get

    @pytest.mark.asyncio
    async def test_use_cache_false_always_asks_and_leaves_the_cache_alone(self):
        session, mock_get = self._session([{"nocache1": {"status": "open"}}] * 2)
        with session, patch("openlibrary.core.lending.cache.get_memcache", side_effect=AssertionError("cache touched")):
            await lending.get_availability_async("identifier", ["nocache1"], use_cache=False)
            await lending.get_availability_async("identifier", ["nocache1"], use_cache=False)
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_batches_requests(self):
        ids = [f"batched{i}" for i in range(5)]
        session, mock_get = self._session([{}, {}, {}])
        with session:
            await lending.get_availability_async("identifier", ids, use_cache=False, batch_size=2)
        sent = [call.kwargs["params"]["identifier"].split(",") for call in mock_get.call_args_list]
        assert sent == [ids[0:2], ids[2:4], ids[4:5]]

    @pytest.mark.asyncio
    async def test_a_failed_batch_only_errors_its_own_ids(self):
        session, mock_get = self._session([{"failbatch2": {"status": "open"}}])
        mock_get.side_effect = [httpx.ConnectError("boom"), *mock_get.side_effect]
        with session:
            r = await lending.get_availability_async("identifier", ["failbatch1", "failbatch2"], use_cache=False, batch_size=1)
        assert r["failbatch1"]["status"] == "error"
        assert r["failbatch2"]["status"] == "open"
        assert r["error"] == "request_timeout"

    @pytest.mark.asyncio
    async def test_drop_errors_leaves_errors_out_of_the_response(self):
        """A caller deciding availability from this must not mistake a failed
        lookup for an answer: no placeholder, no top-level error keys."""
        session, mock_get = self._session([{"dropok": {"status": "open"}, "droperr": {"status": "error"}}])
        mock_get.side_effect = [*mock_get.side_effect, httpx.ReadTimeout("boom")]
        with session:
            r = await lending.get_availability_async("identifier", ["dropok", "droperr", "dropfailed"], use_cache=False, batch_size=2, drop_errors=True)
        assert list(r) == ["dropok"]

    @pytest.mark.asyncio
    async def test_a_service_level_failure_only_loses_its_own_batch(self):
        """A `success: false` batch used to make the whole call return {},
        discarding the other batches' answers and even the cached ones."""
        session, mock_get = self._session([])
        busy = Mock(raise_for_status=Mock(), json=Mock(return_value={"success": False, "error": "busy"}))
        ok = Mock(raise_for_status=Mock(), json=Mock(return_value={"success": True, "responses": {"svcok": {"status": "open"}}}))
        mock_get.side_effect = [busy, ok]
        with session:
            r = await lending.get_availability_async("identifier", ["svcfail", "svcok"], use_cache=False, batch_size=1)
        assert list(r) == ["svcok"]

    @pytest.mark.asyncio
    async def test_a_non_json_body_is_a_failed_batch(self):
        session, mock_get = self._session([])
        bad = Mock(raise_for_status=Mock(), json=Mock(side_effect=json.JSONDecodeError("Expecting value", "<html>", 0)))
        mock_get.side_effect = [bad]
        with session:
            r = await lending.get_availability_async("identifier", ["htmlbody"], use_cache=False)
        assert r["htmlbody"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_a_missing_request_context_raises_rather_than_reading_as_no_answer(self):
        """Under drop_errors a swallowed LookupError is indistinguishable from the
        service answering nothing -- a daemon would free nothing, forever."""
        session, _ = self._session([{"noctx": {"status": "open"}}])
        with session, patch("openlibrary.core.lending.req_context", ContextVar("unset")), pytest.raises(LookupError):
            await lending.get_availability_async("identifier", ["noctx"], use_cache=False, drop_errors=True)

    @pytest.mark.asyncio
    async def test_drop_errors_leaves_out_a_cached_error_without_refetching(self):
        session, mock_get = self._session([{"cachederr": {"status": "error"}}])
        with session:
            assert (await lending.get_availability_async("identifier", ["cachederr"]))["cachederr"]["status"] == "error"
            assert await lending.get_availability_async("identifier", ["cachederr"], drop_errors=True) == {}
        assert mock_get.call_count == 1


@pytest.mark.usefixtures("request_context_fixture")
class TestGetLendingState:
    def test_get_lending_state_borrowed(self, mock_site):
        doc = {"key": "/books/OL1M", "loan": {"expiry": "tomorrow"}}
        assert lending.get_lending_state(doc) == "borrowed"

    def test_get_lending_state_partner(self, mock_site):
        mock_provider = Mock()
        mock_provider.short_name = "betterworldbooks"
        with patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider):
            doc = {}
            assert lending.get_lending_state(doc) == "partner"

    def test_get_lending_state_open(self, mock_site):
        mock_provider = Mock()
        mock_provider.short_name = "ia"
        with patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider):
            doc = {"availability": {"is_readable": True}}
            assert lending.get_lending_state(doc) == "open"

            doc = {"availability": {"status": "open"}}
            assert lending.get_lending_state(doc) == "open"

    def test_get_lending_state_printdisabled(self, mock_site):
        mock_provider = Mock()
        mock_provider.short_name = "ia"
        mock_user = Mock()
        mock_user.is_printdisabled.return_value = True
        mock_user.get_user_waiting_loans.return_value = None
        mock_user.get_loan_for.return_value = None

        with patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider):
            doc = {"ocaid": "foo"}
            assert lending.get_lending_state(doc, user=mock_user) == "printdisabled"

    def test_get_lending_state_lendable(self, mock_site):
        mock_provider = Mock()
        mock_provider.short_name = "ia"
        with patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider):
            doc = {"availability": {"is_lendable": True, "available_to_borrow": True}}
            assert lending.get_lending_state(doc) == "borrowable"

            doc = {"availability": {"is_lendable": True, "available_to_waitlist": True}}
            assert lending.get_lending_state(doc) == "waitlist"

            doc = {"availability": {"is_lendable": True}}
            assert lending.get_lending_state(doc) == "checkedout"

    def test_get_lending_state_preview(self, mock_site):
        mock_provider = Mock()
        mock_provider.short_name = "ia"
        with patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider):
            doc = {"ocaid": "foo", "availability": {"is_previewable": True}}
            assert lending.get_lending_state(doc) == "preview_only"

    def test_get_lending_state_locate(self, mock_site):
        mock_provider = Mock()
        mock_provider.short_name = "ia"
        with patch("openlibrary.book_providers.get_book_provider", return_value=mock_provider):
            doc = {}
            assert lending.get_lending_state(doc) == "locate"

    def test_get_lending_state_waiting_loan(self, mock_site):
        # Case A: User is on waitlist, but it is not their turn yet (position > 1 or status != available)
        mock_user = Mock()
        mock_user.is_printdisabled.return_value = False
        mock_user.get_user_waiting_loans.return_value = {"status": "waiting", "position": 2}
        mock_user.get_loan_for.return_value = None

        mock_ia_provider = Mock()
        mock_ia_provider.short_name = "ia"

        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_ia_provider):
            # General availability says waitlist is closed (i.e. 'checkedout')
            doc = {"key": "/books/OL1M", "ocaid": "foo", "availability": {"is_lendable": True, "available_to_waitlist": False}}
            # Proves that without check_loan_status=True, we ignore the waitlist and return "checkedout"
            assert lending.get_lending_state(doc, user=mock_user, check_loan_status=False) == "checkedout"
            # Proves that enabling check_loan_status=True successfully resolves to "waitlist"
            assert lending.get_lending_state(doc, user=mock_user, check_loan_status=True) == "waitlist"

        # Case B: It is the user's turn to borrow (position 1, status available)
        mock_user.get_user_waiting_loans.return_value = {"status": "available", "position": 1}
        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_ia_provider):
            # General availability has the book as borrowable now that it's their turn
            doc = {"key": "/books/OL1M", "ocaid": "foo", "availability": {"is_lendable": True, "available_to_borrow": True}}
            assert lending.get_lending_state(doc, user=mock_user, check_loan_status=True) == "borrowable"

        # Case C: User is on waitlist, but they are printdisabled (or book is readable/borrowable)
        mock_user.get_user_waiting_loans.return_value = {"status": "waiting", "position": 2}
        mock_user.is_printdisabled.return_value = True
        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_ia_provider):
            doc = {"key": "/books/OL1M", "ocaid": "foo", "availability": {"is_lendable": True, "available_to_waitlist": False}}
            assert lending.get_lending_state(doc, user=mock_user, check_loan_status=True) == "printdisabled"

        mock_user.is_printdisabled.return_value = False
        with patch("openlibrary.book_providers.get_book_provider_by_name", return_value=mock_ia_provider):
            doc = {"key": "/books/OL1M", "ocaid": "foo", "availability": {"is_readable": True, "is_lendable": True}}
            assert lending.get_lending_state(doc, user=mock_user, check_loan_status=True) == "open"


@pytest.mark.asyncio
async def test_get_checked_out_async(monkeypatch):
    availabilities = {
        "out00": {"status": "borrow_unavailable"},
        "in00": {"status": "borrow_available"},
        "open00": {"status": "open"},
        "error": "request_timeout",
    }
    monkeypatch.setattr(lending, "get_availability_async", AsyncMock(return_value=availabilities))

    assert await lending.get_checked_out_async(["out00", "in00", "open00"]) == {"out00"}


def test_get_loan_queries_ia_once(monkeypatch):
    mock_api = Mock()
    mock_api.get_loan.return_value = {"identifier": "foo00bar"}
    monkeypatch.setattr(lending, "ia_lending_api", mock_api)
    monkeypatch.setattr(lending.Loan, "from_ia_loan", staticmethod(lambda d: ("loan", d)))

    assert lending.get_loan("foo00bar") == ("loan", {"identifier": "foo00bar"})
    mock_api.get_loan.assert_called_once_with("foo00bar")


@pytest.mark.usefixtures("request_context_fixture")
class TestGetLoanHistoryData:
    """parse_s3_cookie() is annotated `dict | None` and legitimately returns
    None for a patron with no `s3` cookie. s3_loan_api() then does
    `s3_keys | kwargs`, which raises
    TypeError: unsupported operand type(s) for |: 'NoneType' and 'dict'.

    This matters because /account/loans calls get_loan_history_data() directly
    and is not wrapped in a try/except, so the whole page 500s -- a page that
    rendered fine before loan history was folded into it.
    """

    def test_returns_empty_history_when_patron_has_no_s3_keys(self):
        response = Mock()
        response.json.return_value = {"history": {"items": []}}
        with (
            patch.object(lending.OpenLibraryAccount, "get_by_username", return_value=Mock()),
            patch("openlibrary.core.lending.web.cookies", return_value={"s3": "irrelevant"}),
            patch("openlibrary.core.lending.parse_s3_cookie", return_value=None),
            patch("openlibrary.core.lending.s3_loan_api", return_value=response) as mock_api,
            patch("openlibrary.core.lending.get_items_and_add_availability", return_value={}),
        ):
            result = lending.get_loan_history_data("someuser", page=1)

        # Must short-circuit: calling the real s3_loan_api with None keys raises
        # TypeError on `s3_keys | kwargs`, which 500s /account/loans.
        mock_api.assert_not_called()
        assert result["docs"] == []
        assert result["show_next"] is False
        assert result["page"] == 1

    def test_real_s3_loan_api_cannot_take_none_keys(self):
        """Documents why the guard above is needed, at the boundary itself."""
        with pytest.raises(TypeError):
            lending.s3_loan_api(s3_keys=None, action="user_borrow_history", limit=1)

    def test_still_queries_ia_when_s3_keys_are_present(self):
        """Guard against 'fixing' the above by disabling history for everyone."""
        response = Mock()
        response.json.return_value = {"history": {"items": []}}
        with (
            patch.object(lending.OpenLibraryAccount, "get_by_username", return_value=Mock()),
            patch("openlibrary.core.lending.web.cookies", return_value={"s3": "irrelevant"}),
            patch("openlibrary.core.lending.parse_s3_cookie", return_value={"access": "a", "secret": "s"}),
            patch("openlibrary.core.lending.s3_loan_api", return_value=response) as mock_api,
            patch("openlibrary.core.lending.get_items_and_add_availability", return_value={}),
        ):
            result = lending.get_loan_history_data("someuser", page=1)

        mock_api.assert_called_once()
        assert result["docs"] == []


class TestIsAvailableForLoan:
    def test_browsable_or_borrowable_is_available(self):
        assert lending.is_available_for_loan({"available_to_browse": True, "available_to_borrow": False})
        assert lending.is_available_for_loan({"available_to_browse": False, "available_to_borrow": True})

    def test_neither_is_unavailable(self):
        assert not lending.is_available_for_loan({"available_to_browse": False, "available_to_borrow": False})

    def test_waitlistable_is_still_unavailable(self):
        """A book you may queue for is not a book you may read: available_to_waitlist
        must not be mistaken for availability."""
        assert not lending.is_available_for_loan({"available_to_browse": False, "available_to_borrow": False, "available_to_waitlist": True})

    def test_missing_keys_are_unavailable(self):
        assert not lending.is_available_for_loan({})


class TestGetCheckedOutCandidates:
    """The cold-start seed. Its failure direction is asymmetric: a seed that is
    short publishes checked-out books as borrowable, and nothing downstream
    revisits them -- so every test here is about refusing to return a partial
    set rather than about returning a set."""

    @staticmethod
    def _session(bodies):
        """Patch the shared async session; each GET answers with the next body."""
        mock_get = AsyncMock()
        replies = []
        for body in bodies:
            reply = Mock()
            reply.json = Mock(return_value=body)
            reply.raise_for_status = Mock()
            replies.append(reply)
        mock_get.side_effect = replies
        return patch("openlibrary.core.ia.get_async_session", return_value=SimpleNamespace(get=mock_get)), mock_get

    @staticmethod
    def _page(num_found, identifiers):
        return {"response": {"numFound": num_found, "start": 0, "docs": [{"identifier": i} for i in identifiers]}}

    def test_one_page_is_one_request(self):
        """Today's set is ~600, so the loop must not page past the end of it."""
        session, mock_get = self._session([self._page(600, [f"book{i}" for i in range(600)])])
        with session:
            got = asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))
        assert len(got) == 600
        assert mock_get.call_count == 1

    def test_it_pages_until_it_has_every_identifier(self):
        pages = [
            self._page(2500, [f"book{i}" for i in range(1000)]),
            self._page(2500, [f"book{i}" for i in range(1000, 2000)]),
            self._page(2500, [f"book{i}" for i in range(2000, 2500)]),
        ]
        session, mock_get = self._session(pages)
        with session:
            got = asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))
        assert len(got) == 2500
        assert got[0] == "book0"
        assert got[-1] == "book2499"
        assert mock_get.call_count == 3
        assert [dict(call.kwargs["params"])["page"] for call in mock_get.call_args_list] == ["1", "2", "3"]

    def test_a_set_beyond_the_paging_window_raises_and_names_the_way_out(self):
        """advancedsearch cannot answer past 10k at any page size, so no retry
        fixes this; it is the trigger for the authenticated Scrape path."""
        session, mock_get = self._session([self._page(12_000, [f"book{i}" for i in range(1000)])])
        with session, pytest.raises(lending.CheckedOutSeedIncomplete) as excinfo:
            asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))
        assert "12000" in str(excinfo.value)
        assert "Scrape" in str(excinfo.value)
        assert mock_get.call_count == 1, "should refuse on the first page rather than paging a set it cannot finish"

    def test_a_short_read_raises_rather_than_returning_what_arrived(self):
        pages = [
            self._page(2500, [f"book{i}" for i in range(1000)]),
            self._page(2500, [f"book{i}" for i in range(1000, 1400)]),
        ]
        session, _ = self._session(pages)
        with session, pytest.raises(lending.CheckedOutSeedIncomplete) as excinfo:
            asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))
        assert "2500" in str(excinfo.value)
        assert "1400" in str(excinfo.value)

    def test_a_missing_envelope_is_an_incomplete_read_not_an_empty_one(self):
        """How the endpoint answers past its window: HTTP 200, no `response`.
        Read as "no books are checked out" it would clear the whole seed."""
        session, _ = self._session([{"responseHeader": {"status": 0}}])
        with session, pytest.raises(lending.CheckedOutSeedIncomplete) as excinfo:
            asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))
        # The downstream guards would also refuse this, so assert on the
        # message: "no envelope" and "no numFound" send an operator to
        # different places, and only this branch can say which happened.
        assert "envelope" in str(excinfo.value)

    def test_an_absent_numfound_raises_because_completeness_is_unknowable(self):
        session, _ = self._session([{"response": {"docs": [{"identifier": "book0"}]}}])
        with session, pytest.raises(lending.CheckedOutSeedIncomplete):
            asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))

    def test_identifiers_repeated_across_pages_do_not_count_toward_completeness(self):
        """A paging window that slides under churn re-serves rows. Counting
        those twice is how a short set passes the completeness check."""
        pages = [
            self._page(2000, [f"book{i}" for i in range(1000)]),
            self._page(2000, [f"book{i}" for i in range(500, 1500)]),
            self._page(2000, []),
        ]
        session, _ = self._session(pages)
        with session, pytest.raises(lending.CheckedOutSeedIncomplete) as excinfo:
            asyncio.run(lending.get_checked_out_candidates_async(page_rows=1000))
        assert "1500" in str(excinfo.value)
