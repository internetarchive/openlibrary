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
        with patch("openlibrary.core.ia.async_session.get") as mock_get:
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


class TestGetLoan:
    """get_loan should make at most the necessary IA loan-API calls."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self, monkeypatch):
        mock_site = Mock()
        mock_site.get.return_value.store.get.return_value = None
        monkeypatch.setattr(lending, "site", mock_site)
        self.mock_get_ia_loan = Mock(return_value=None)
        monkeypatch.setattr(lending, "_get_ia_loan", self.mock_get_ia_loan)

    def make_account(self, monkeypatch, username="mek", itemname="@mek"):
        account = Mock()
        account.username = username
        account.itemname = itemname
        monkeypatch.setattr(lending.OpenLibraryAccount, "get_by_key", Mock(return_value=account))
        return account

    def test_anonymous_lookup_calls_api_once(self):
        loan = Mock()
        self.mock_get_ia_loan.return_value = loan

        assert lending.get_loan("foo00bar") is loan
        self.mock_get_ia_loan.assert_called_once_with("foo00bar", None)

    def test_loan_found_by_username_is_not_clobbered(self, monkeypatch):
        self.make_account(monkeypatch)
        loan = Mock()
        self.mock_get_ia_loan.return_value = loan

        assert lending.get_loan("foo00bar", user_key="/people/mek") is loan
        self.mock_get_ia_loan.assert_called_once_with("foo00bar", "ol:mek")

    def test_falls_back_to_itemname_when_username_finds_nothing(self, monkeypatch):
        self.make_account(monkeypatch)
        loan = Mock()
        self.mock_get_ia_loan.side_effect = [None, loan]

        assert lending.get_loan("foo00bar", user_key="/people/mek") is loan
        assert self.mock_get_ia_loan.call_args_list == [
            (("foo00bar", "ol:mek"),),
            (("foo00bar", "@mek"),),
        ]

    def test_account_without_itemname_calls_api_once(self, monkeypatch):
        self.make_account(monkeypatch, itemname=None)

        assert lending.get_loan("foo00bar", user_key="/people/mek") is None
        self.mock_get_ia_loan.assert_called_once_with("foo00bar", "ol:mek")
