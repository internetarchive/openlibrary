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
