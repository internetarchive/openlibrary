from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import web

from openlibrary.core import lending
from openlibrary.utils import dateutil
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


class TestGetLoansOfUser:
    """Tests for get_loans_of_user and get_cached_loans_of_user."""

    @pytest.fixture(autouse=True)
    def _web_ctx(self, monkeypatch):
        """Provide a minimal web.ctx so fakeload() is skipped.

        web.storage is a dict subclass, so `"env" in ctx` works correctly via
        the standard __contains__ lookup — unlike MagicMock where setting
        __contains__ on the instance is ignored by the `in` operator (Python
        resolves special methods on the type, not the instance).
        """
        ctx = web.storage(env={}, site=web.storage(store=MagicMock()))
        monkeypatch.setattr(web, "ctx", ctx)

    def test_returns_ia_loans(self, monkeypatch):
        ia_loan = lending.Loan(
            {
                "_key": "loan-test-item",
                "type": "/type/loan",
                "user": "/people/testuser",
                "book": "/books/OL1M",
                "ocaid": "test-item",
                "resource_type": "bookreader",
                "stored_at": "ia",
            }
        )
        mock_account = Mock()
        mock_account.itemname = "@testuser"
        monkeypatch.setattr(lending.OpenLibraryAccount, "get_by_username", lambda u: mock_account)
        monkeypatch.setattr(lending, "_get_ia_loans_of_user", lambda userid: [ia_loan])
        monkeypatch.setattr(lending.get_cached_loans_of_user, "memcache_set", lambda *a, **kw: None)

        result = lending.get_loans_of_user("/people/testuser")

        assert result == [ia_loan]

    def test_returns_empty_list_when_no_account(self, monkeypatch):
        monkeypatch.setattr(lending.OpenLibraryAccount, "get_by_username", lambda u: None)
        monkeypatch.setattr(lending.get_cached_loans_of_user, "memcache_set", lambda *a, **kw: None)

        result = lending.get_loans_of_user("/people/unknown")

        assert result == []

    def test_returns_empty_list_when_no_itemname(self, monkeypatch):
        mock_account = Mock()
        mock_account.itemname = None
        monkeypatch.setattr(lending.OpenLibraryAccount, "get_by_username", lambda u: mock_account)
        monkeypatch.setattr(lending.get_cached_loans_of_user, "memcache_set", lambda *a, **kw: None)

        result = lending.get_loans_of_user("/people/testuser")

        assert result == []

    def test_does_not_query_local_store(self, monkeypatch):
        """Local OL store must not be consulted — loans are authoritative at IA."""
        mock_account = Mock()
        mock_account.itemname = "@testuser"
        monkeypatch.setattr(lending.OpenLibraryAccount, "get_by_username", lambda u: mock_account)
        monkeypatch.setattr(lending, "_get_ia_loans_of_user", lambda userid: [])
        monkeypatch.setattr(lending.get_cached_loans_of_user, "memcache_set", lambda *a, **kw: None)

        lending.get_loans_of_user("/people/testuser")

        web.ctx.site.store.values.assert_not_called()

    def test_cache_ttl_is_ten_minutes(self):
        assert lending.get_cached_loans_of_user.timeout == 10 * dateutil.MINUTE_SECS
