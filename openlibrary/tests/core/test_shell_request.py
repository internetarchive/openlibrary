"""ShellRequest: the shell's only view of the HTTP request, built the same way on web.py and FastAPI."""

import json
from urllib.parse import quote

import pytest
import web
from starlette.requests import Request

from openlibrary.core.shell import ShellRequest
from openlibrary.plugins.openlibrary.code import changequery as templetor_changequery


def _starlette_request(path: str = "/advancedsearch", query: str = "", cookie: str = "") -> Request:
    headers = [(b"host", b"localhost:8080")] + ([(b"cookie", cookie.encode())] if cookie else [])
    return Request({"type": "http", "method": "GET", "path": path, "query_string": query.encode(), "headers": headers, "root_path": ""})


def test_from_starlette_reads_flash_like_web_py_and_keeps_no_cookies():
    flash = [{"type": "info", "message": "Saved, really"}, {"type": "missing-message"}, "junk"]
    req = ShellRequest.from_starlette(_starlette_request(cookie=f"session=SECRET-TOKEN; flash={quote(json.dumps(flash))}"))
    assert req.flash_messages == ({"type": "info", "message": "Saved, really"},)
    assert "SECRET-TOKEN" not in repr(req)
    assert req.host == "localhost:8080"


@pytest.mark.parametrize("cookie", ["flash=not-json", 'flash={"type": "info"}', "", "flash=" + "[" * 100_000])
def test_from_starlette_ignores_bad_flash(cookie):
    assert ShellRequest.from_starlette(_starlette_request(cookie=cookie)).flash_messages == ()


def test_params_keep_last_value_like_web_input():
    req = ShellRequest(path="/", readable_path="/", query_string="q=one&q=two&empty=", host="")
    assert req.params == {"q": "two", "empty": ""}


@pytest.mark.parametrize(
    ("query", "kw"),
    [
        ("", {"_path": "/advancedsearch", "page": None}),
        ("q=a+b&page=3&q=c", {"_path": "/advancedsearch", "page": None}),
        ("q=%C3%B1and%C3%BA&x=", {"page": 2}),
        ("a=1", {"a": None}),
    ],
)
def test_changequery_matches_templetor(monkeypatch, query, kw):
    for key, value in {"path": "/search", "env": {"QUERY_STRING": query, "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)
    req = ShellRequest(path="/search", readable_path="/search", query_string=query, host="")
    assert req.changequery(**kw) == templetor_changequery(**kw)
