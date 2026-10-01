from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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
        mock_get.side_effect = [RuntimeError("boom"), *mock_get.side_effect]
        with session:
            r = await lending.get_availability_async("identifier", ["failbatch1", "failbatch2"], use_cache=False, batch_size=1)
        assert r["failbatch1"]["status"] == "error"
        assert r["failbatch2"]["status"] == "open"
        assert r["error"] == "request_timeout"


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


class TestGetAvailabilityBatch:
    """lending.get_availability_batch — the daemon-side, uncached, chunked lookup."""

    @staticmethod
    @contextmanager
    def _session(**get_kwargs):
        """Patch the shared async session, yielding its `get` mock."""
        mock_get = AsyncMock(**get_kwargs)
        with patch("openlibrary.core.ia.get_async_session", return_value=SimpleNamespace(get=mock_get)):
            yield mock_get

    def _response(self, responses, success=True):
        response = Mock()
        response.json.return_value = {"success": success, "responses": responses}
        response.raise_for_status = Mock()
        return response

    @pytest.mark.asyncio
    async def test_empty_input_makes_no_request(self):
        with self._session() as mock_get:
            assert await lending.get_availability_batch([]) == {}
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_keyed_availability(self):
        payload = {"a": {"status": "borrow_available", "available_to_borrow": True}}
        with self._session(return_value=self._response(payload)):
            assert await lending.get_availability_batch(["a"]) == payload

    @pytest.mark.asyncio
    async def test_chunks_requests(self):
        """The shared get_availability() comma-joins every id into one request; this one
        must not, or a hydration pass would build a multi-megabyte URL."""
        ids = [f"id{i}" for i in range(250)]
        with self._session(return_value=self._response({})) as mock_get:
            await lending.get_availability_batch(ids, batch_size=100)
        assert mock_get.call_count == 3
        sent = [call.kwargs["params"]["identifier"].split(",") for call in mock_get.call_args_list]
        assert [len(batch) for batch in sent] == [100, 100, 50]
        assert [id_ for batch in sent for id_ in batch] == ids

    @pytest.mark.asyncio
    async def test_a_failed_batch_is_skipped_not_fatal(self):
        """One bad batch must not lose the batches that did succeed -- and must not
        produce a fabricated answer for the ids it covered."""
        good = self._response({"b": {"status": "borrow_available", "available_to_borrow": True}})
        with self._session(side_effect=[RuntimeError("boom"), good]):
            result = await lending.get_availability_batch(["a", "b"], batch_size=1)
        assert list(result) == ["b"]

    @pytest.mark.asyncio
    async def test_service_level_failure_yields_nothing(self):
        with self._session(return_value=self._response({"a": {}}, success=False)):
            assert await lending.get_availability_batch(["a"]) == {}

    @pytest.mark.asyncio
    async def test_error_status_entries_are_dropped(self):
        """The service reports per-identifier errors inline; those must not be written
        to Solr as if they were real answers."""
        payload = {
            "a": {"status": "error"},
            "b": {"status": "borrow_unavailable", "available_to_borrow": False},
        }
        with self._session(return_value=self._response(payload)):
            assert list(await lending.get_availability_batch(["a", "b"])) == ["b"]

    @pytest.mark.asyncio
    async def test_non_dict_responses_are_ignored(self):
        response = Mock()
        response.json.return_value = {"success": True, "responses": ["not", "a", "dict"]}
        response.raise_for_status = Mock()
        with self._session(return_value=response):
            assert await lending.get_availability_batch(["a"]) == {}

    @pytest.mark.asyncio
    async def test_sends_auth_and_static_headers(self):
        """No req_context here: this runs in a daemon with no web request."""
        with (
            patch("openlibrary.core.lending.config_ia_ol_metadata_write_s3", {"s3_key": "k", "s3_secret": "s"}),
            self._session(return_value=self._response({})) as mock_get,
        ):
            await lending.get_availability_batch(["a"])
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["authorization"] == "LOW k:s"
        assert headers["x-application-id"] == "openlibrary"

    @pytest.mark.asyncio
    async def test_explicit_s3_keys_override_config(self):
        with (
            patch("openlibrary.core.lending.config_ia_ol_metadata_write_s3", {"s3_key": "k", "s3_secret": "s"}),
            self._session(return_value=self._response({})) as mock_get,
        ):
            await lending.get_availability_batch(["a"], s3_keys={"access": "A", "secret": "S"})
        assert mock_get.call_args.kwargs["headers"]["authorization"] == "LOW A:S"
