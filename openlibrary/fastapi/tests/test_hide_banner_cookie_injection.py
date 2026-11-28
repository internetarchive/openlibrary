"""CodeQL #61 (py/cookie-injection): /hide_banner sets a cookie whose name is
caller-supplied. The name is now constrained to a safe cookie-token character
set, so CRLF/control characters or header-smuggling payloads are rejected
before set_cookie. Legitimate banner names (letters, digits, '-', '_') still
work -- that behaviour is covered by tests/fastapi/test_hide_banner.py. The
rejection path runs before auth, so it is testable without a logged-in user."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.fastapi.internal.api import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_rejects_crlf_injection_payload():
    r = client.post("/hide_banner", json={"cookie-name": "banner\r\nSet-Cookie: evil=1"})
    assert r.status_code == 400


def test_rejects_cookie_attribute_smuggling():
    r = client.post("/hide_banner", json={"cookie-name": "x=1; Domain=evil.example"})
    assert r.status_code == 400


def test_rejects_overlong_cookie_name():
    r = client.post("/hide_banner", json={"cookie-name": "a" * 100})
    assert r.status_code == 400
