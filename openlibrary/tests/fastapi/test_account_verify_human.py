"""Tests for the human verification challenge page (/verify_human).

The route and its POST live in ``openlibrary/fastapi/account.py`` on the
``pages`` router; ``SitePageRoute`` checks the ``vf``/session cookies before
both, adds HEAD, and wraps the GET body in the site shell.
"""

from http.cookies import SimpleCookie

import pytest
import web
from fastapi.testclient import TestClient

from infogami import config
from openlibrary.accounts.model import check_human_cookies
from openlibrary.fastapi.account import pages


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def test_renders_with_same_origin_next(client, webpy_leftovers):
    """Isolation: the page shows only its own request's ``next``, never web.py leftovers."""
    response = client.get("/verify_human", params={"next": "/search?q=x"})
    assert response.status_code == 200
    assert 'data-next="/search?q=x"' in response.text
    assert "Verify you are human" in response.text
    assert webpy_leftovers not in response.text


@pytest.mark.parametrize(
    ("next", "reason"),
    [
        ("//evil.example", "protocol-relative url"),
        ("/\\evil.example", "backslash:scheme-relative url"),
        ("\\evil.example", "schemeless backslash url"),
        ("http://evil.example", "absolute url"),
    ],
)
def test_next_outside_site_falls_back_to_home(client, next, reason):
    """Only same-origin paths are honored as the ``next`` redirect target.

    The shell echoes the raw query string elsewhere, so only the button's
    ``data-next`` must show the fallback, never the unsafe value.
    """
    response = client.get("/verify_human", params={"next": next})
    assert response.status_code == 200, reason
    assert 'data-next="/"' in response.text, reason
    assert 'data-next="..' not in response.text.split('data-next="')[1], reason


def test_head_answered(client):
    assert client.head("/verify_human").status_code == 200


def test_post_sets_signed_vf_cookie(client, monkeypatch):
    """The POST confirms as JSON and the cookie it set verifies on the next request."""
    # site_page_app has no infobase; get_secret_key() reads this.
    monkeypatch.setattr(config, "infobase", web.storage(secret_key="test-secret-key"), raising=False)

    response = client.post("/verify_human")
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # response.cookies gives the morsel-encoded value (".." quoted, \054 for ",");
    # the site shell reads the plain value, so parse the Set-Cookie header directly.
    morsel = SimpleCookie()
    morsel.load(response.headers["set-cookie"])
    vf = morsel["vf"].value
    assert vf.startswith("vf/")
    assert check_human_cookies({"vf": vf}).verified


def test_post_with_spoofed_vf_sets_fresh_vf_cookie(client, monkeypatch):
    """A forged ``vf`` is replaced with a fresh one, not rejected.

    The challenge page is exempt from the spoofed-cookie check
    (``HUMAN_CHECK_EXEMPT_PATHS``), as web.py's ``CookieValidationProcessor``
    is: otherwise a visitor whose ``vf`` went stale could never earn a new one.
    """
    # site_page_app has no infobase; get_secret_key() reads this.
    monkeypatch.setattr(config, "infobase", web.storage(secret_key="test-secret-key"), raising=False)

    response = client.post("/verify_human", headers={"Cookie": "vf=garbage"})
    assert response.status_code == 200
    assert response.json() == {"success": True}

    morsel = SimpleCookie()
    morsel.load(response.headers["set-cookie"])
    vf = morsel["vf"].value
    assert vf.startswith("vf/")
    assert check_human_cookies({"vf": vf}).verified
