"""SitePageRoute wraps a returned SitePage in the site shell, with the user loaded off the event loop."""

import json
import threading
from urllib.parse import quote

import pytest
import web
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from markupsafe import Markup, escape

from infogami import config
from openlibrary.accounts import model as accounts_model
from openlibrary.core.shell import PageMeta, ShellUser
from openlibrary.fastapi.shared.site_page import CurrentUserDep, SitePage, SitePageRoute

pages = APIRouter(route_class=SitePageRoute)
loop_threads: list[threading.Thread] = []


@pages.get("/plain")
async def plain() -> SitePage:
    loop_threads.append(threading.current_thread())
    return SitePage("<p>plain body</p>")


@pages.get("/custom")
def custom() -> SitePage:
    return SitePage("<p>custom body</p>", page=PageMeta(title="Custom title"), status_code=404, headers={"x-extra": "1"})


@pages.get("/redirect")
async def redirect() -> RedirectResponse:
    return RedirectResponse("/plain")


@pages.get("/things/{name}")
async def thing(name: str) -> SitePage:
    return SitePage(f"<p>{escape(name)}</p>", page=PageMeta(cssfile="work"))


@pages.get("/echo")
async def echo(q: str = "") -> SitePage:
    return SitePage(f"<p>{escape(q)}</p>")


@pages.get("/missing")
async def missing() -> SitePage:
    raise HTTPException(404)


@pages.get("/whoami")
async def whoami(user: CurrentUserDep) -> SitePage:
    return SitePage(f"<p>you are {escape(user.key) if user else 'nobody'}</p>")


@pages.get("/titled")
async def titled(markup: bool = False) -> SitePage:
    title = Markup("<b>Tom</b> &amp; Jerry") if markup else "<b>Tom</b> & Jerry"
    return SitePage("<p>titled</p>", page=PageMeta(title=title, metatags=('<meta name="x">', Markup('<meta name="ok">'))))


def _set_a_cookie(response: Response) -> None:
    response.set_cookie("from-dependency", "1")


@pages.get("/with-headers", dependencies=[Depends(_set_a_cookie)])
async def with_headers(response: Response, redirect: bool = False) -> Response:
    response.headers["cache-control"] = "max-age=60"
    response.headers["x-extra"] = "from-injected-response"
    response.headers["vary"] = "Cookie, Accept-Language"
    if redirect:
        return RedirectResponse("/plain", status_code=303)
    page = SitePage("<p>with headers</p>", headers={"x-extra": "from-site-page", "vary": "Accept-Language"})
    page.headers.append("vary", "Accept-Encoding")  # a second Vary line
    return page


def _flash_cookie(message: str) -> str:
    return "flash=" + quote(json.dumps([{"type": "info", "message": message}]))


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


@pytest.fixture
def loads(monkeypatch) -> list[threading.Thread]:
    """Replace load_shell_user() with one that logs in bob; returns the thread of each call."""
    threads: list[threading.Thread] = []

    def fake_load_shell_user():
        threads.append(threading.current_thread())
        return ShellUser(key="/people/bob", created=None, ia_id=None, is_librarian=False, is_super_librarian=False, open_merges_count=0)

    monkeypatch.setattr("openlibrary.fastapi.shared.site_page.load_shell_user", fake_load_shell_user)
    return threads


def test_wraps_the_body_in_the_shell(client):
    response = client.get("/plain")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.text.startswith("<!DOCTYPE html>")
    assert "<p>plain body</p>" in response.text
    assert "<title>plain | Open Library</title>" in response.text  # title defaults to the path
    assert int(response.headers["content-length"]) == len(response.content)
    assert "set-cookie" not in response.headers


def test_keeps_the_page_meta_status_and_headers(client):
    response = client.get("/custom")
    assert response.status_code == 404
    assert response.headers["x-extra"] == "1"
    assert "<title>Custom title | Open Library</title>" in response.text
    assert int(response.headers["content-length"]) == len(response.content)


def test_loads_the_user_once_in_a_worker_thread(site_page_app, loads):
    # Including the router again copies its routes through SitePageRoute.__init__: still one load.
    outer = APIRouter()
    outer.include_router(pages)
    loop_threads.clear()
    response = TestClient(site_page_app(outer)).get("/plain")
    assert 'data-user-key="/people/bob"' in response.text
    assert len(loads) == 1
    assert loads[0] is not loop_threads[0]  # not on the event loop


def test_answers_head_like_get(client):
    get, head = client.get("/plain"), client.head("/plain")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == get.headers["content-length"]


def test_title_falls_back_to_the_escaped_path(client):
    """Also when a PageMeta sets other values but no title, as web.py does."""
    response = client.get("/things/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E")
    assert response.status_code == 200
    assert "<img src=x" not in response.text
    assert "<title>things/&lt;img src=x onerror=alert(1)&gt; | Open Library</title>" in response.text
    assert "page-work.css" in response.text


def test_other_responses_pass_through(client):
    response = client.get("/redirect", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/plain"


def test_expires_the_flash_cookie_once_shown(client):
    response = client.get("/plain", headers={"cookie": _flash_cookie("saved-it")})
    assert "saved-it" in response.text
    assert response.headers["set-cookie"].startswith('flash=""')


def test_page_routes_are_not_in_the_api_schema(client):
    assert client.get("/openapi.json").json()["paths"] == {}


def test_a_site_page_off_a_site_page_router_fails_loudly(site_page_app):
    plain_router = APIRouter()

    @plain_router.get("/bare")
    async def bare() -> SitePage:
        return SitePage("<p>no shell</p>")

    with pytest.raises(RuntimeError, match="route_class=SitePageRoute"):
        TestClient(site_page_app(plain_router)).get("/bare")


def test_concurrent_requests_each_get_only_their_own_shell(site_page_app, webpy_leftovers, fetch_concurrently):
    """Each page shows its own user, query, flash message and language: never another request's, or web.py's leftovers."""
    n = 12
    requests = [(f"/echo?q=query-{i}", {"x-user": f"user{i}", "cookie": _flash_cookie(f"flash-{i}")}) for i in range(n)]
    for i, response in enumerate(fetch_concurrently(site_page_app(pages), requests)):
        html = response.text
        assert webpy_leftovers not in html
        assert f"<p>query-{i}</p>" in html
        assert f'data-user-key="/people/user{i}"' in html
        assert f"flash-{i}<" in html
        assert "Joined March 20, 2013" in html  # this request's language (en), not the leftover fr
        others = [j for j in range(n) if j != i]
        assert not any(f"query-{j}<" in html or f'/people/user{j}"' in html or f"flash-{j}<" in html for j in others)
        assert response.headers["set-cookie"].startswith('flash=""')


@pytest.fixture
def secret_key(monkeypatch):
    monkeypatch.setattr(config, "infobase", web.storage(secret_key="test-secret-key"), raising=False)
    monkeypatch.setattr(config, "login_cookie_name", "session", raising=False)


def test_genuine_cookies_get_the_page(client, secret_key):
    vf = accounts_model.create_verification_cookie_value()
    session = accounts_model.generate_login_code_for_user("bob")
    # Encoded as web.setcookie() writes them.
    for cookie in (f"vf={quote(vf)}", f"session={quote(session)}", "session=not-an-ol-session"):
        assert client.get("/plain", headers={"cookie": cookie}).status_code == 200, cookie


@pytest.mark.parametrize("name", ["vf", "session"])
def test_forged_cookies_are_rejected_and_cleared(client, secret_key, name):
    """nginx lets requests with cookies skip its challenge, so a forged one must not get the page."""
    forged = "vf/abc,12345$forged" if name == "vf" else "/people/bob,2026-01-01T00:00:00,12345$forged"
    response = client.get("/plain", headers={"cookie": f'{name}="{forged}"'})
    assert response.status_code == 403
    assert response.headers["x-abuse"] == "spoofed-cookie"
    assert response.headers["set-cookie"].startswith(f'{name}=""')
    assert "plain body" not in response.text


def test_recognized_crawlers_skip_the_cookie_check(client, secret_key):
    response = client.get("/plain", headers={"cookie": "vf=junk", "x-recognized-bot": "1"})
    assert response.status_code == 200


def test_requests_nginx_flags_are_sent_to_the_challenge(client, secret_key):
    response = client.get("/plain?a=1", headers={"x-ol-verify-human": "1"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/verify_human?next=/plain%3Fa%3D1"
    # A genuine cookie means they passed it already.
    vf = accounts_model.create_verification_cookie_value()
    assert client.get("/plain", headers={"x-ol-verify-human": "1", "cookie": f"vf={quote(vf)}"}).status_code == 200


def test_loads_the_user_only_when_rendering_the_shell(client, loads):
    """A redirect or an error renders no shell, so it pays for no user lookup."""
    assert client.get("/redirect", follow_redirects=False).status_code == 307
    assert client.get("/missing").status_code == 404
    assert loads == []
    client.get("/plain")
    assert len(loads) == 1


def test_current_user_dep_is_shared_with_the_shell(client, loads):
    response = client.get("/whoami")
    assert "you are /people/bob" in response.text
    assert 'data-user-key="/people/bob"' in response.text
    assert len(loads) == 1  # one lookup for the route and the shell


def test_page_values_are_escaped_unless_markup(client):
    html = client.get("/titled").text
    assert "<title>&lt;b&gt;Tom&lt;/b&gt; &amp; Jerry | Open Library</title>" in html
    assert "&lt;meta name=&#34;x&#34;&gt;" in html
    assert '<meta name="ok">' in html
    assert "<title><b>Tom</b> &amp; Jerry | Open Library</title>" in client.get("/titled?markup=true").text


def test_headers_set_on_the_injected_response_apply(client):
    """FastAPI drops them when a route returns a Response itself; the route class keeps them."""
    response = client.get("/with-headers")
    assert "with headers" in response.text
    assert response.headers["cache-control"] == "max-age=60"
    assert response.headers["x-extra"] == "from-site-page"  # the returned response's own header wins
    # But Vary values are merged, from every Vary line, so caches vary on all of them.
    assert response.headers.get_list("vary") == ["Accept-Language, Accept-Encoding, Cookie"]
    assert response.cookies["from-dependency"] == "1"
    assert int(response.headers["content-length"]) == len(response.content)

    redirect = client.get("/with-headers?redirect=true", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["cache-control"] == "max-age=60"
    assert redirect.cookies["from-dependency"] == "1"


def test_cookie_check_responses_are_plain(client, secret_key):
    """Not FastAPI's JSON error bodies: a bot gets a plain 403, a flagged visitor a plain redirect."""
    forbidden = client.get("/plain", headers={"cookie": "vf=junk"})
    assert (forbidden.status_code, forbidden.text) == (403, "Forbidden")
    challenged = client.get("/plain", headers={"x-ol-verify-human": "1"}, follow_redirects=False)
    assert challenged.status_code == 303
    assert "detail" not in challenged.text
