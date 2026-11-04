"""Tests for the human verification challenge page (/verify_human).

The route and its POST live in ``openlibrary/fastapi/account.py`` on the
``pages`` router. Which ``next`` values are safe is tested in
``test_is_safe_redirect``; here we only check that the page uses it.
"""

from http.cookies import SimpleCookie
from urllib.parse import urlencode

import pytest
import web
from fastapi.testclient import TestClient

from infogami import config
from infogami.utils.context import context
from openlibrary.accounts.model import check_human_cookies
from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.account import pages
from openlibrary.plugins.upstream import account as legacy_account


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def test_renders_with_same_origin_next(client, webpy_leftovers):
    """Isolation: the page shows only its own request's ``next``, never web.py leftovers."""
    response = client.get("/verify_human", params={"next": "/search?q=x"})
    assert response.status_code == 200
    assert 'data-next="/search?q=x"' in response.text
    assert webpy_leftovers not in response.text


def test_next_outside_site_falls_back_to_home(client):
    response = client.get("/verify_human", params={"next": "/\\evil.example"})
    assert 'data-next="/"' in response.text


@pytest.mark.parametrize("cookie", [None, "vf=garbage"])
def test_post_sets_signed_vf_cookie(client, monkeypatch, cookie):
    """The cookie verifies, and a forged ``vf`` gets a fresh one instead of a 403."""
    # site_page_app has no infobase; get_secret_key() reads this.
    monkeypatch.setattr(config, "infobase", web.storage(secret_key="test-secret-key"), raising=False)

    response = client.post("/verify_human", headers={"Cookie": cookie} if cookie else {})
    assert response.json() == {"success": True}

    set_cookie = response.headers["set-cookie"]
    for attribute in ("HttpOnly", "Max-Age=2592000", "Path=/", "SameSite=lax"):
        assert attribute in set_cookie
    # Parse the header: response.cookies keeps the quoted, \054-escaped value.
    morsel = SimpleCookie()
    morsel.load(set_cookie)
    assert check_human_cookies({"vf": morsel["vf"].value}).verified


@pytest.mark.parametrize(("next", "next_url"), [("/search?q=x", "/search?q=x"), ("/\\evil.example", "/")])
def test_webpy_handler_renders_the_fastapi_body(monkeypatch, request_context_fixture, next, next_url):
    """Until web.py's handler is retired, both servers render the same page."""
    request_context_fixture(lang="en")
    monkeypatch.setattr(web.ctx, "env", {"QUERY_STRING": urlencode({"next": next}), "REQUEST_METHOD": "GET"}, raising=False)
    monkeypatch.setattr(web.ctx, "path", "/verify_human", raising=False)
    monkeypatch.setattr(context, "disable_analytics", False, raising=False)

    result = legacy_account.account_verify_human().GET()

    assert result.title == "Human Verification"  # web.py's layout reads the title from here
    assert context.disable_analytics is True
    assert str(result) == render_jinja_template("verify_human.html.jinja", next_url=next_url)
