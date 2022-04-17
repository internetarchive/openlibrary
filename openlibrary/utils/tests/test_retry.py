from unittest.mock import Mock
import pytest
from openlibrary.utils.retry import MaxRetriesExceeded, RetryStrategy


class TestRetryStrategy:
    def test_exception_filter(self, monkeytime):
        foo = Mock(side_effect=ZeroDivisionError)
        retry = RetryStrategy([ZeroDivisionError], max_retries=3)
        with pytest.raises(MaxRetriesExceeded):
            retry(foo)
        assert foo.call_count == 4

    def test_no_retry(self):
        foo = Mock(return_value=1)
        retry = RetryStrategy([ZeroDivisionError], max_retries=3)
        assert retry(foo) == 1
        assert foo.call_count == 1

    def test_retry(self, monkeytime):
        foo = Mock(side_effect=[ZeroDivisionError, 1])
        retry = RetryStrategy([ZeroDivisionError], max_retries=3)
        assert retry(foo) == 1
        assert foo.call_count == 2

    def test_unhandled_error(self):
        foo = Mock(side_effect=ZeroDivisionError)
        retry = RetryStrategy([ValueError], max_retries=3)
        with pytest.raises(ZeroDivisionError):
            retry(foo)
        assert foo.call_count == 1

    def test_last_exception(self, monkeytime):
        retry = RetryStrategy([ZeroDivisionError], max_retries=3)
        with pytest.raises(MaxRetriesExceeded):
            try:
                retry(lambda: 1 / 0)
            except MaxRetriesExceeded as e:
                assert isinstance(e.last_exception, ZeroDivisionError)
                raise
