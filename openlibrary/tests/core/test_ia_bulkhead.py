from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import memcache
import pytest

from infogami import config
from openlibrary.core import ia_bulkhead, lending
from openlibrary.utils.request_context import RequestContextVars, req_context

NOW = 1_800_000_000.0  # the start of a window


@pytest.fixture
def mc(mock_memcache, monkeypatch):
    """A real memcache.Client whose network calls go to the mock_memcache dict."""
    client = memcache.Client(["mock:11211"])
    monkeypatch.setattr(ia_bulkhead, "_enabled", True)
    monkeypatch.setattr(ia_bulkhead, "_memcache", lambda: client)
    monkeypatch.setattr(ia_bulkhead, "time", SimpleNamespace(time=lambda: NOW))
    return mock_memcache


@pytest.fixture
def skipped(monkeypatch):
    calls = []
    monkeypatch.setattr(ia_bulkhead.stats, "increment", lambda key, *a, **kw: calls.append(key))
    return calls


def set_limit(monkeypatch, limit):
    monkeypatch.setattr(config, "ia_max_concurrent_requests", limit, raising=False)


def in_flight(mc) -> int:
    return sum(int(v) for k, v in mc.cache.items() if k.startswith("ia_bulkhead:"))


class TestIARequestSlot:
    def test_allows_up_to_the_limit_then_skips(self, mc, skipped, monkeypatch):
        set_limit(monkeypatch, 2)
        with ia_bulkhead.ia_request_slot("availability"), ia_bulkhead.ia_request_slot("availability"):
            assert in_flight(mc) == 2
            ran = False
            with pytest.raises(ia_bulkhead.IABulkheadFull), ia_bulkhead.ia_request_slot("availability"):
                ran = True
            assert not ran
            assert skipped == ["ol.ia_bulkhead.skipped.availability"]
            assert in_flight(mc) == 2  # the skipped request gave its slot back

        assert in_flight(mc) == 0
        with ia_bulkhead.ia_request_slot("groundtruth"):
            pass
        assert skipped == ["ol.ia_bulkhead.skipped.availability"]

    def test_releases_the_slot_when_the_request_fails(self, mc, monkeypatch):
        set_limit(monkeypatch, 1)
        with pytest.raises(TimeoutError), ia_bulkhead.ia_request_slot("availability"):
            raise TimeoutError
        assert in_flight(mc) == 0

    def test_counts_requests_still_in_flight_from_the_previous_window(self, mc, skipped, monkeypatch):
        set_limit(monkeypatch, 1)
        with ia_bulkhead.ia_request_slot("availability"):
            monkeypatch.setattr(ia_bulkhead, "time", SimpleNamespace(time=lambda: NOW + ia_bulkhead.WINDOW_SECONDS))
            with pytest.raises(ia_bulkhead.IABulkheadFull), ia_bulkhead.ia_request_slot("availability"):
                pass
        # Released from the window it was taken in, so the new window is free again
        assert in_flight(mc) == 0
        with ia_bulkhead.ia_request_slot("availability"):
            pass
        assert skipped == ["ol.ia_bulkhead.skipped.availability"]

    def test_does_nothing_unless_enabled(self, mc, skipped, monkeypatch):
        """FastAPI never calls enable_concurrency_limit(), so its requests aren't limited or counted."""
        monkeypatch.setattr(ia_bulkhead, "_enabled", False)
        set_limit(monkeypatch, 0)
        ran = False
        with ia_bulkhead.ia_request_slot("availability"):
            ran = True
            assert in_flight(mc) == 0
        assert ran
        assert skipped == []

    @pytest.mark.parametrize(
        "broken_client",
        [
            None,  # memcache_servers not configured
            Mock(add=Mock(return_value=0), incr=Mock(return_value=None)),  # python-memcached with the server down
            Mock(add=Mock(side_effect=OSError)),
        ],
    )
    def test_fails_open_without_memcache(self, broken_client, skipped, monkeypatch):
        set_limit(monkeypatch, 0)
        monkeypatch.setattr(ia_bulkhead, "_enabled", True)
        monkeypatch.setattr(ia_bulkhead, "_memcache", lambda: broken_client)
        ran = False
        with ia_bulkhead.ia_request_slot("availability"):
            ran = True
        assert ran
        assert skipped == []


@pytest.fixture
def request_context():
    token = req_context.set(
        RequestContextVars(x_forwarded_for="ol-internal", user_agent="test", lang=None, solr_editions=True, print_disabled=False, is_bot=False)
    )
    yield
    req_context.reset(token)


@pytest.mark.usefixtures("request_context")
class TestLendingWhenFull:
    def test_get_availability_returns_errors_without_calling_ia(self, mc, skipped, monkeypatch):
        response = Mock(json=Mock(return_value={"success": True, "responses": {"bulkhead-test-item": {"status": "open"}}}))
        mock_get = AsyncMock(return_value=response)
        monkeypatch.setattr(lending.ia, "get_async_session", lambda: SimpleNamespace(get=mock_get))

        set_limit(monkeypatch, 0)
        result = lending.get_availability("identifier", ["bulkhead-test-item"])
        mock_get.assert_not_called()
        assert result["bulkhead-test-item"]["status"] == "error"
        assert skipped == ["ol.ia_bulkhead.skipped.availability"]

        # The skipped answer wasn't cached: once there's room, IA is asked
        set_limit(monkeypatch, 15)
        assert lending.get_availability("identifier", ["bulkhead-test-item"])["bulkhead-test-item"]["status"] == "open"
        mock_get.assert_called_once()
        assert in_flight(mc) == 0

    def test_groundtruth_returns_empty_without_calling_ia(self, mc, skipped, monkeypatch):
        mock_gt = Mock(return_value={"status": "borrow_available"})
        monkeypatch.setattr(lending, "get_groundtruth_availability", mock_gt)

        set_limit(monkeypatch, 0)
        assert lending.get_cached_groundtruth_availability("bulkhead-test-gt-item") == {}
        mock_gt.assert_not_called()
        assert skipped == ["ol.ia_bulkhead.skipped.groundtruth"]

        set_limit(monkeypatch, 15)
        assert lending.get_cached_groundtruth_availability("bulkhead-test-gt-item") == {"status": "borrow_available"}
        assert lending.get_cached_groundtruth_availability("bulkhead-test-gt-item") == {"status": "borrow_available"}
        mock_gt.assert_called_once()  # a real answer is still cached
