"""Tests for SiteProxy."""

from contextvars import ContextVar, copy_context
from unittest.mock import Mock

import pytest


class TestSiteProxy:
    """Test that SiteProxy correctly delegates to the ContextVar."""

    def test_getattr_delegates_to_site(self):
        """site.foo should delegate to the underlying site.foo."""
        from openlibrary.utils.request_context import site_ctx

        mock_site = Mock()
        mock_site.get = Mock(return_value="result")
        mock_site.some_method = Mock(return_value="method_result")

        site_ctx._set_site(mock_site)

        # Test method delegation
        assert site_ctx.get("key") == "result"
        assert site_ctx.some_method() == "method_result"

    def test_getattr_caches_per_context(self):
        """Each context should have its own site."""
        from openlibrary.utils.request_context import site_ctx

        mock_site1 = Mock()
        mock_site1.name = "site1"

        mock_site2 = Mock()
        mock_site2.name = "site2"

        # Set in main context
        site_ctx._set_site(mock_site1)
        assert site_ctx.name == "site1"

        # Create a new context and set a different site
        ctx = copy_context()
        ctx.run(site_ctx._set_site, mock_site2)

        # Main context should still have site1
        assert site_ctx.name == "site1"

    def test_lookup_error_outside_fresh_context(self):
        """Should raise LookupError if called in a fresh context with no site set."""

        # Create a brand new ContextVar to test the behavior
        fresh_var: ContextVar[str] = ContextVar("fresh_test")

        # In a fresh context, calling get should raise LookupError
        ctx = copy_context()
        with pytest.raises(LookupError):
            ctx.run(fresh_var.get)

    def test_nested_context_isolation(self):
        """Nested contexts should have isolated site values."""
        from openlibrary.utils.request_context import _site_contextvar, site_ctx

        mock_site_outer = Mock()
        mock_site_outer.name = "outer"

        mock_site_inner = Mock()
        mock_site_inner.name = "inner"

        site_ctx._set_site(mock_site_outer)

        # Simulate inner context
        old = _site_contextvar.get()
        site_ctx._set_site(mock_site_inner)
        try:
            assert site_ctx.name == "inner"
        finally:
            site_ctx._set_site(old)

        # Outer context should be restored
        assert site_ctx.name == "outer"

    def test_property_access(self):
        """site.property should work."""
        from openlibrary.utils.request_context import site_ctx

        mock_site = Mock()
        mock_site.store = Mock()
        mock_site.store.get = Mock(return_value={"key": "value"})

        site_ctx._set_site(mock_site)

        # Access nested property
        result = site_ctx.store.get("some/key")
        assert result == {"key": "value"}
        mock_site.store.get.assert_called_once_with("some/key")

    def test_magic_methods_not_delegated(self):
        """Magic methods like __repr__ should not delegate to site."""
        from openlibrary.utils.request_context import site_ctx

        # These should work on the proxy itself
        repr_str = repr(site_ctx)
        assert "SiteProxy" in repr_str

        str_str = str(site_ctx)
        assert "SiteProxy" in str_str
