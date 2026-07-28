"""Tests for human verification challenge functionality."""

import web

from infogami import config
from openlibrary.plugins.openlibrary.processors import CookieValidationProcessor
from openlibrary.utils.request_context import RequestContextVars, req_context


class TestCookieValidationProcessor:
    """Tests for the CookieValidationProcessor global processor."""

    def setup_method(self):
        ctx = web.storage()
        ctx.env = {"REQUEST_URI": "/books/OL1M"}
        ctx.path = "/books/OL1M"
        ctx.home = "http://localhost"
        web.ctx = ctx
        web.webapi.ctx = web.ctx
        config.infobase = web.storage(secret_key="test-secret-key")
        config.login_cookie_name = "session"
        self._req_context_token = req_context.set(
            RequestContextVars(
                x_forwarded_for=None,
                user_agent="pytest-agent",
                lang="en",
                solr_editions=True,
                print_disabled=False,
                sfw=False,
                is_recognized_bot=False,
                is_bot=False,
            )
        )
        self.processor = CookieValidationProcessor()

    def teardown_method(self):
        req_context.reset(self._req_context_token)

    def _make_handler(self):
        called = []

        def handler():
            called.append(True)
            return "ok"

        return handler, called

    def test_no_cookies_calls_handler(self, monkeypatch):
        monkeypatch.setattr(web, "cookies", dict)
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called

    def test_valid_vf_cookie_calls_handler(self, monkeypatch):
        from openlibrary.accounts import model

        valid_cookie = model.create_verification_cookie_value()
        monkeypatch.setattr(web, "cookies", lambda: {"vf": valid_cookie})
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called

    def test_invalid_vf_cookie_returns_403(self, monkeypatch):
        import pytest

        headers = {}
        cleared = []
        monkeypatch.setattr(web, "cookies", lambda: {"vf": "spoofed_value"})
        monkeypatch.setattr(web, "setcookie", lambda *a, **kw: cleared.append((a, kw)))
        monkeypatch.setattr(web, "header", lambda k, v: headers.update({k: v}))
        handler, called = self._make_handler()
        with pytest.raises(web.HTTPError) as exc_info:
            self.processor(handler)
        assert not called
        assert cleared  # cookie was purged
        assert exc_info.value.args[0] == "403 Forbidden"
        assert headers.get("X-Abuse") == "spoofed-cookie"

    def test_invalid_vf_cookie_on_verify_human_passes_through(self, monkeypatch):
        web.ctx.path = "/verify_human"
        monkeypatch.setattr(web, "cookies", lambda: {"vf": "spoofed_value"})
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called

    def test_nginx_header_redirects(self, monkeypatch):
        import pytest

        class FakeSeeOther(Exception):
            def __init__(self, url):
                self.url = url

        web.ctx.env["HTTP_X_OL_VERIFY_HUMAN"] = "1"
        monkeypatch.setattr(web, "cookies", dict)
        monkeypatch.setattr(web, "seeother", FakeSeeOther)
        handler, called = self._make_handler()
        with pytest.raises(FakeSeeOther) as exc_info:
            self.processor(handler)
        assert not called
        assert "/verify_human" in exc_info.value.url

    def test_nginx_header_on_verify_human_passes_through(self, monkeypatch):
        web.ctx.path = "/verify_human"
        web.ctx.env["HTTP_X_OL_VERIFY_HUMAN"] = "1"
        monkeypatch.setattr(web, "cookies", dict)
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called

    def test_valid_session_cookie_calls_handler(self, monkeypatch):
        from openlibrary.accounts.model import generate_login_code_for_user

        valid_session = generate_login_code_for_user("testuser")
        monkeypatch.setattr(web, "cookies", lambda: {"session": valid_session})
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called

    def test_invalid_session_cookie_returns_403(self, monkeypatch):
        import pytest

        headers = {}
        cleared = []
        monkeypatch.setattr(
            web,
            "cookies",
            lambda: {"session": "/people/hacker,2024-01-01T00:00:00,forgedsig"},
        )
        monkeypatch.setattr(web, "setcookie", lambda *a, **kw: cleared.append((a, kw)))
        monkeypatch.setattr(web, "header", lambda k, v: headers.update({k: v}))
        handler, called = self._make_handler()
        with pytest.raises(web.HTTPError) as exc_info:
            self.processor(handler)
        assert not called
        assert cleared
        assert exc_info.value.args[0] == "403 Forbidden"
        assert headers.get("X-Abuse") == "spoofed-cookie"

    def test_cookies_on_verify_human_always_pass_through(self, monkeypatch):
        web.ctx.path = "/verify_human"
        monkeypatch.setattr(
            web,
            "cookies",
            lambda: {
                "vf": "spoofed_value",
                "session": "/people/hacker,2024-01-01T00:00:00,forgedsig",
            },
        )
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called

    def test_unknown_format_session_cookie_passes_through(self, monkeypatch):
        """Non-OL session cookies (unknown format) should not invalidate the session."""
        monkeypatch.setattr(web, "cookies", lambda: {"session": "some-other-format-token"})
        handler, called = self._make_handler()
        result = self.processor(handler)
        assert result == "ok"
        assert called
