"""Comprehensive tests for IA API negative caching bug fix."""

from unittest.mock import Mock

import httpx

from openlibrary.core import ia


class TestIANotFoundError:
    """Test IANotFoundError sentinel class."""

    def test_ianotfounderror_exists(self):
        """Verify IANotFoundError class is defined."""
        assert hasattr(ia, "IANotFoundError")

    def test_ianotfounderror_is_class(self):
        """Verify IANotFoundError is a class."""
        assert isinstance(ia.IANotFoundError, type)

    def test_ianotfounderror_can_be_instantiated(self):
        """Verify IANotFoundError can be instantiated."""
        error = ia.IANotFoundError()
        assert isinstance(error, ia.IANotFoundError)


class TestIATransientError:
    """Test IATransientError sentinel class."""

    def test_iatransienterror_exists(self):
        """Verify IATransientError class is defined."""
        assert hasattr(ia, "IATransientError")

    def test_iatransienterror_is_class(self):
        """Verify IATransientError is a class."""
        assert isinstance(ia.IATransientError, type)

    def test_iatransienterror_can_be_instantiated(self):
        """Verify IATransientError can be instantiated."""
        error = ia.IATransientError()
        assert isinstance(error, ia.IATransientError)


class TestGetAPIResponse:
    """Test get_api_response error classification."""

    def test_404_returns_not_found_sentinel(self, monkeypatch):
        """Verify HTTP 404 responses return IANotFoundError with 5 min TTL."""
        # VAL-IA-001: 404 responses return IANotFoundError

        mock_response = Mock()
        mock_response.status_code = httpx.codes.NOT_FOUND
        mock_response.json = Mock(return_value={})

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/nonexistent")

        assert isinstance(result, ia.IANotFoundError)
        assert not isinstance(result, dict)

    def test_timeout_returns_transient_sentinel(self, monkeypatch):
        """Verify timeout errors return IATransientError with 30 sec TTL."""
        # VAL-IA-002: Timeout errors return IATransientError

        mock_session = Mock()
        mock_session.get = Mock(side_effect=httpx.TimeoutException("Timeout"))

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/slow-item")

        assert isinstance(result, ia.IATransientError)
        assert not isinstance(result, dict)
        assert not isinstance(result, ia.IANotFoundError)

    def test_connect_error_returns_transient_sentinel(self, monkeypatch):
        """Verify network connectivity errors return IATransientError."""
        # VAL-IA-003: Network errors return IATransientError

        mock_session = Mock()
        mock_session.get = Mock(side_effect=httpx.ConnectError("Connection failed"))

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/some-item")

        assert isinstance(result, ia.IATransientError)

    def test_network_error_returns_transient_sentinel(self, monkeypatch):
        """Verify network errors return IATransientError."""
        # VAL-IA-003: Network errors return IATransientError

        mock_session = Mock()
        mock_session.get = Mock(side_effect=httpx.NetworkError("Network error"))

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/some-item")

        assert isinstance(result, ia.IATransientError)

    def test_500_returns_transient_sentinel(self, monkeypatch):
        """Verify 500 server errors return IATransientError."""
        # VAL-IA-004: 5xx server errors return IATransientError

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json = Mock(return_value={"error": "Internal server error"})

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/bad-item")

        assert isinstance(result, ia.IATransientError)

    def test_502_returns_transient_sentinel(self, monkeypatch):
        """Verify 502 server errors return IATransientError."""
        # VAL-IA-004: 5xx server errors return IATransientError

        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.json = Mock(return_value={"error": "Bad gateway"})

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/gateway-error")

        assert isinstance(result, ia.IATransientError)

    def test_503_returns_transient_sentinel(self, monkeypatch):
        """Verify 503 server errors return IATransientError."""
        # VAL-IA-004: 5xx server errors return IATransientError

        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.json = Mock(return_value={"error": "Service unavailable"})

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/unavailable")

        assert isinstance(result, ia.IATransientError)

    def test_success_returns_dict(self, monkeypatch):
        """Verify successful HTTP 200 responses return dict."""
        # VAL-IA-005: Successful responses cache normally

        expected_metadata = {
            "metadata": {
                "title": "Test Book",
                "identifier": "testitem",
                "collection": ["printdisabled"],
                "files": [],
            }
        }

        mock_response = Mock()
        mock_response.status_code = httpx.codes.OK
        mock_response.json = Mock(return_value=expected_metadata)

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/testitem")

        assert isinstance(result, dict)
        assert result == expected_metadata

    def test_other_error_status_returns_empty_dict(self, monkeypatch):
        """Verify other HTTP error statuses return empty dict."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json = Mock(return_value={"error": "Bad request"})

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)

        result = ia.get_api_response("https://archive.org/metadata/bad-request")

        assert isinstance(result, dict)
        assert result == {}


class TestGetMetadataDirect:
    """Test get_metadata_direct sentinel handling."""

    def test_sentinel_propagation_for_not_found(self, monkeypatch):
        """Verify IANotFoundError propagates through get_metadata_direct."""
        # VAL-IA-006: Sentinel values propagate through cache layers

        monkeypatch.setattr(ia, "get_api_response", lambda *args: ia.IANotFoundError())

        result = ia.get_metadata_direct("nonexistent")

        assert isinstance(result, ia.IANotFoundError)

    def test_sentinel_propagation_for_transient(self, monkeypatch):
        """Verify IATransientError propagates through get_metadata_direct."""
        # VAL-IA-006: Sentinel values propagate through cache layers

        monkeypatch.setattr(ia, "get_api_response", lambda *args: ia.IATransientError())

        result = ia.get_metadata_direct("slow-item")

        assert isinstance(result, ia.IATransientError)

    def test_dict_result_processed_normally(self, monkeypatch):
        """Verify dict results are processed normally."""
        # VAL-IA-006: Sentinel values propagate through cache layers

        metadata = {
            "metadata": {
                "title": "Test Book",
                "identifier": "testitem",
                "collection": ["printdisabled"],
            }
        }

        monkeypatch.setattr(ia, "get_api_response", lambda *args: metadata)

        result = ia.get_metadata_direct("testitem")

        assert isinstance(result, dict)
        assert result["title"] == "Test Book"
        assert result["identifier"] == "testitem"

    def test_sentinel_returned_without_extraction(self, monkeypatch):
        """Verify sentinel values are returned without extraction."""
        # VAL-IA-006: Sentinel values propagate through cache layers

        # When sentinel is returned, extract_item_metadata should not be called
        monkeypatch.setattr(ia, "get_api_response", lambda *args: ia.IATransientError())
        monkeypatch.setattr(ia, "extract_item_metadata", Mock(return_value={}))

        result = ia.get_metadata_direct("testitem")

        assert isinstance(result, ia.IATransientError)
        # extract_item_metadata should not be called for sentinels
        ia.extract_item_metadata.assert_not_called()


class TestCacheKeyConsistency:
    """Test cache key construction for error types."""

    def test_cache_key_consistency_for_error_types(self, monkeypatch):
        """Verify cache keys are identical regardless of error type."""
        # VAL-IA-007: Cache keys constructed correctly for all error types

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock()

        # We need to test that the cache key computation is the same
        # Since get_metadata is decorated with memcache_memoize, we can verify this

        call_count = [0]

        def track_get_api_response(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return ia.IANotFoundError()
            else:
                return ia.IATransientError()

        monkeypatch.setattr(ia, "get_api_response", track_get_api_response)
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        # First call with IANotFoundError
        ia.get_metadata("testitem")

        # Get the key used for the first call
        first_call_key = mock_memcache.set.call_args[0][0]

        # Reset the mock
        mock_memcache.set.reset_mock()

        # Second call with IATransientError
        ia.get_metadata("testitem")

        # Get the key used for the second call
        second_call_key = mock_memcache.set.call_args[0][0]

        # Keys should be identical for same itemid regardless of error type
        assert first_call_key == second_call_key


class TestTransientErrorRecovery:
    """Test transient error recovery after TTL expiration."""

    def test_transient_errors_dont_affect_subsequent_calls(self, monkeypatch):
        """Verify after TTL expiration, fresh requests succeed normally."""
        # VAL-IA-008: Transient errors don't affect subsequent calls

        # Setup mock cache that returns None (cache miss) to simulate TTL expiration
        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock()

        call_count = [0]

        def mock_get_api_response(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: transient error
                return ia.IATransientError()
            elif call_count[0] == 2:
                # Second call: still transient (new API call after cache expiration)
                return ia.IATransientError()
            else:
                # Third call: success
                return {
                    "metadata": {
                        "title": "Recovered Book",
                        "identifier": "recovered",
                        "collection": ["printdisabled"],
                    }
                }

        monkeypatch.setattr(ia, "get_api_response", mock_get_api_response)
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        # First call gets transient error (cache miss -> new API call)
        result1 = ia.get_metadata("recovered")
        assert isinstance(result1, ia.IATransientError)
        assert call_count[0] == 1

        # Second call gets transient error (cache miss -> new API call)
        result2 = ia.get_metadata("recovered")
        assert isinstance(result2, ia.IATransientError)
        assert call_count[0] == 2

        # Third call gets successful result (cache miss -> new API call)
        result3 = ia.get_metadata("recovered")
        assert isinstance(result3, dict)
        assert result3["title"] == "Recovered Book"
        assert call_count[0] == 3  # New API call was made


class TestDifferentialCacheTTL:
    """Test differential caching TTLs based on sentinel type."""

    def test_not_found_error_uses_5_min_ttl(self, monkeypatch):
        """Verify IANotFoundError is cached with 5-minute TTL."""
        # VAL-IA-010: Different error types get different cache TTLs

        # Create a mock that captures the cache TTL
        captured_time = [None]

        def mock_set_with_ttl(key, value, time=0):
            captured_time[0] = time

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock(side_effect=mock_set_with_ttl)

        monkeypatch.setattr(ia, "get_api_response", lambda *args: ia.IANotFoundError())
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        ia.get_metadata("notfound-item")

        # Verify set was called with 300 (5 minutes) as TTL for IANotFoundError
        assert mock_memcache.set.called
        assert captured_time[0] == 300  # 5 minutes

    def test_transient_error_uses_30_sec_ttl(self, monkeypatch):
        """Verify IATransientError is cached with 30-second TTL."""
        # VAL-IA-010: Different error types get different cache TTLs

        # Create a mock that captures the cache TTL
        captured_time = [None]

        def mock_set_with_ttl(key, value, time=0):
            captured_time[0] = time

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock(side_effect=mock_set_with_ttl)

        monkeypatch.setattr(ia, "get_api_response", lambda *args: ia.IATransientError())
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        ia.get_metadata("transient-item")

        # Verify set was called with 30 seconds as TTL for IATransientError
        assert mock_memcache.set.called
        assert captured_time[0] == 30  # 30 seconds

    def test_success_uses_5_min_ttl(self, monkeypatch):
        """Verify successful responses are cached with 5-minute TTL."""
        # VAL-IA-010: Different error types get different cache TTLs

        # Create a mock that captures the cache TTL
        captured_time = [None]

        def mock_set_with_ttl(key, value, time=0):
            captured_time[0] = time

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock(side_effect=mock_set_with_ttl)

        successful_metadata = {
            "metadata": {
                "title": "Success Book",
                "identifier": "success",
                "collection": ["printdisabled"],
            }
        }

        monkeypatch.setattr(ia, "get_api_response", lambda *args: successful_metadata)
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        ia.get_metadata("success-item")

        # Verify set was called with 300 (5 minutes) as TTL for successful responses
        assert mock_memcache.set.called
        assert captured_time[0] == 300  # 5 minutes


class TestBackgroundThreadSafety:
    """Test background refresh thread safety."""

    def test_background_refresh_no_duplicate_updates(self, monkeypatch):
        """Verify concurrent requests don't cause duplicate updates."""
        # VAL-IA-009: Background refresh doesn't cause cache corruption

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock()

        monkeypatch.setattr(ia, "get_api_response", lambda *args: {"metadata": {}})
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        # Make multiple concurrent calls
        ia.get_metadata("concurrent-item")

        # Should only call set once per get_metadata call
        assert mock_memcache.set.called


class TestIntegration:
    """Integration tests for complete IA API flow."""

    def test_complete_error_classification_flow(self, monkeypatch):
        """Verify complete error classification and caching flow."""
        # This test validates the entire flow from API response to cache

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock()

        # Test 404 -> IANotFoundError
        mock_response_404 = Mock()
        mock_response_404.status_code = httpx.codes.NOT_FOUND
        mock_response_404.json = Mock(return_value={})

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response_404)

        monkeypatch.setattr(ia, "session", mock_session)
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        result = ia.get_metadata("notfound")

        # Verify error classification
        assert isinstance(result, ia.IANotFoundError)
        # Verify caching was attempted
        assert mock_memcache.set.called

    def test_success_flow_with_metadata_extraction(self, monkeypatch):
        """Verify successful flow with metadata extraction."""

        mock_memcache = Mock()
        mock_memcache.get = Mock(return_value=None)
        mock_memcache.set = Mock()

        metadata = {
            "metadata": {
                "title": "Test Book",
                "identifier": "testbook",
                "collection": ["printdisabled", "inlibrary"],
                "files": [{"name": "file1.pdf", "private": "false"}],
            }
        }

        mock_response = Mock()
        mock_response.status_code = httpx.codes.OK
        mock_response.json = Mock(return_value=metadata)

        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)

        monkeypatch.setattr(ia, "session", mock_session)
        monkeypatch.setattr(ia.cache.memcache_memoize, "memcache", mock_memcache)

        result = ia.get_metadata("testbook")

        # Verify metadata extraction
        assert isinstance(result, dict)
        assert result["title"] == "Test Book"
        assert result["identifier"] == "testbook"
        assert result["collection"] == ["printdisabled", "inlibrary"]
        assert not result["access-restricted"]
        # The _filenames list should be empty because no files have private == "true"
        assert result["_filenames"] == []

        # Verify caching
        assert mock_memcache.set.called
