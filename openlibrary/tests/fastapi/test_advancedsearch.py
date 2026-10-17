"""/advancedsearch on FastAPI, and proof that the site shell keeps requests isolated.

FastAPI never resets ``web.ctx``: async handlers share one on the event loop
thread. These tests poison it, run interleaved requests for different users on
that same thread, and check each page shows only its own request.
"""

import asyncio
import datetime as dt
import json
from urllib.parse import quote

import httpx
import pytest
import web
from fastapi import FastAPI, Request

from infogami.utils.context import context as infogami_context
from openlibrary.core.jinja import get_jinja_env
from openlibrary.fastapi.search import router
from openlibrary.utils.request_context import RequestContextVars, req_context, site

CANARY = "LEAKED"


class FakeUser:
    created = dt.datetime(2013, 3, 20)

    def __init__(self, name: str):
        self.key = f"/people/{name}"

    def is_librarian_or_higher(self):
        return False

    def is_super_librarian_or_higher(self):
        return False


class FakeSite:
    def __init__(self, username: str | None):
        self.username = username

    def get_user(self):
        return FakeUser(self.username) if self.username else None


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setitem(get_jinja_env().globals, "static_url", lambda p: f"/static/{p}")
    monkeypatch.setitem(get_jinja_env().globals, "icon", lambda *a, **kw: "")
    monkeypatch.setattr("openlibrary.core.shell.header.get_internet_archive_id", lambda key: "@ia")
    app = FastAPI()

    @app.middleware("http")
    async def set_context(request: Request, call_next):
        # What asgi_app's middleware does, minus infobase: per-request ContextVars.
        site.set(FakeSite(request.headers.get("x-user")))  # type: ignore[arg-type]
        req_context.set(RequestContextVars(None, "test", request.headers.get("x-lang", "en"), True, False))
        await asyncio.sleep(0)  # let other requests run between context setup and render
        return await call_next(request)

    app.include_router(router)
    return app


@pytest.fixture
def poisoned_web_ctx(monkeypatch):
    """Leave another request's state in web.ctx / infogami context on this thread."""
    leftovers = {
        "path": f"/{CANARY}-path",
        "readable_path": f"/{CANARY}-path",
        "host": f"{CANARY}.example",
        "homepath": f"/{CANARY}-home",
        "query": f"?q={CANARY}-q",
        "lang": "fr",
        "flash": [web.storage(type="info", message=f"{CANARY}-flash")],
        "env": {"HTTP_COOKIE": f"session={CANARY}-session", "QUERY_STRING": f"q={CANARY}-q&debug=1&dev_host={CANARY}"},
        "stats": [web.storage(name=CANARY, data={}, t_start=0.0, time=0.0)],
    }
    for key, value in leftovers.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)
    for key, value in {"bodyclass": [CANARY], "cssfile": CANARY, "experiments": {CANARY: 1}, "metatags": [CANARY]}.items():
        monkeypatch.setitem(infogami_context, key, value)


async def _get(client: httpx.AsyncClient, i: int) -> tuple[int, httpx.Response]:
    flash = quote(json.dumps([{"type": "info", "message": f"flash-{i}"}]))
    response = await client.get(
        f"/advancedsearch?q=query-{i}",
        headers={"x-user": f"user{i}", "cookie": f"flash={flash}"},
    )
    return i, response


def _run_concurrently(app: FastAPI, n: int) -> list[tuple[int, httpx.Response]]:
    async def main():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await asyncio.gather(*(_get(client, i) for i in range(n)))

    # asyncio.run uses this thread for the loop, so the handlers see the poisoned web.ctx.
    return asyncio.run(main())


def test_interleaved_requests_see_only_their_own_state(app, poisoned_web_ctx):
    n = 12
    for i, response in _run_concurrently(app, n):
        assert response.status_code == 200
        html = response.text
        assert CANARY not in html
        assert f'value="query-{i}"' in html
        assert f'data-user-key="/people/user{i}"' in html
        assert f"flash-{i}" in html
        # Joined date uses this request's lang (en), not web.ctx.lang (fr).
        assert "March 20, 2013" in html
        others = [j for j in range(n) if j != i]
        assert not any(f'query-{j}"' in html or f'/people/user{j}"' in html or f"flash-{j}<" in html for j in others)
        # Flash shown, so its cookie is expired, like web.py's flash_processor does.
        assert response.headers["set-cookie"].startswith('flash=""')


def test_advancedsearch_renders_form_and_escapes_input(app):
    payload = '"><script>alert(1)</script>'
    response = asyncio.run(_client_get(app, f"/advancedsearch?title={quote(payload)}&subject_facet=Fiction&subject="))
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "set-cookie" not in response.headers
    html = response.text
    assert "<script>alert(1)" not in html
    assert 'value="&#34;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"' in html
    assert 'value="Fiction"' in html  # facet is the fallback for an empty field
    assert "<title>advancedsearch | Open Library</title>" in html  # title defaults to the path, as on web.py


async def _client_get(app: FastAPI, url: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        return await client.get(url)
