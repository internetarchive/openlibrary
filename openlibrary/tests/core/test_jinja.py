"""Tests for openlibrary.core.jinja — Jinja2 environment setup."""

import jinja2
import jinja2.exceptions
import pytest

from openlibrary.core.jinja import get_jinja_env


class TestGetJinjaEnv:
    """Tests for get_jinja_env()."""

    def test_returns_jinja2_environment(self):
        """Should return a Jinja2 Environment instance."""
        env = get_jinja_env()
        assert isinstance(env, jinja2.Environment)

    def test_is_cached(self):
        """Should return the same object on repeated calls (functools.cache)."""
        env1 = get_jinja_env()
        env2 = get_jinja_env()
        assert env1 is env2

    def test_has_strict_undefined(self):
        """Should use StrictUndefined so undefined variables raise errors."""
        env = get_jinja_env()
        assert isinstance(env.undefined, type(jinja2.StrictUndefined))
        # Verify that accessing an undefined variable raises
        tpl = env.from_string("{{ nonexistent }}")

        with pytest.raises(jinja2.exceptions.UndefinedError):
            tpl.render()

    def test_has_gettext_global(self):
        """Should have the _ (gettext) function in globals."""
        env = get_jinja_env()
        assert "_" in env.globals
        assert callable(env.globals["_"])

    def test_has_autoescape_enabled(self):
        """Should have autoescaping enabled."""
        env = get_jinja_env()
        assert env.autoescape is True

    def test_has_trim_blocks_enabled(self):
        """Should have trim_blocks enabled."""
        env = get_jinja_env()
        assert env.trim_blocks is True

    def test_has_lstrip_blocks_enabled(self):
        """Should have lstrip_blocks enabled."""
        env = get_jinja_env()
        assert env.lstrip_blocks is True

    def test_can_load_and_render_affiliate_links_template(self, request_context_fixture):
        """Should be able to load the AffiliateLinks.html.jinja template
        from the macros/ directory and render it with store data."""
        request_context_fixture(lang="en")
        env = get_jinja_env()
        tpl = env.get_template("AffiliateLinks.html.jinja")
        output = tpl.render(
            primary_stores=[
                {
                    "key": "teststore",
                    "analytics_key": "TestStore",
                    "name": "Test Store",
                    "link": "https://example.com/book",
                    "price": None,  # StrictUndefined - must include all accessed attrs
                    "price_note": "",
                }
            ],
            more_stores=[],
        )
        # Should contain the store link
        assert "https://example.com/book" in output
        assert "Test Store" in output
        assert "affiliate-links-section" in output
        # Should not have HTML injection from store name
        assert "&gt;" not in output  # no encoded angle brackets from simple names
