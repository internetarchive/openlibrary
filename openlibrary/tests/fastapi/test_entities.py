"""Tests for the FastAPI entities endpoint (openlibrary.fastapi.entities).

Verifies that the generic "view document as JSON" pattern works correctly
for all entity types (works, books, authors, people), including GET and
PUT operations, error handling, and query-parameter support.

.. important:: The endpoint routes are registered via ``router.add_api_route()``
   (using the factory pattern) for works/books/authors, and via the
   ``@router.get`` decorator for the ``/people/{username}.json`` route.
   Tests should exercise both registration styles.
"""

import json
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infogami.infobase.client import ClientException
from openlibrary.fastapi.auth import AuthenticatedUser, require_can_write
from openlibrary.fastapi.entities import router

# ---------------------------------------------------------------------------
# Fake entity data — mirrors the structure returned by thing.dict()
# ---------------------------------------------------------------------------

FAKE_WORK = {
    "key": "/works/OL123W",
    "title": "The Hitchhiker's Guide to the Galaxy",
    "type": {"key": "/type/work"},
    "authors": [{"author": {"key": "/authors/OL1A"}}],
    "subjects": ["Science fiction"],
    "revision": 5,
}

FAKE_EDITION = {
    "key": "/books/OL1M",
    "title": "The Hitchhiker's Guide to the Galaxy",
    "type": {"key": "/type/edition"},
    "works": [{"key": "/works/OL123W"}],
    "publishers": ["Pan Books"],
    "revision": 3,
}

FAKE_AUTHOR = {
    "key": "/authors/OL1A",
    "name": "Douglas Adams",
    "type": {"key": "/type/author"},
    "birth_date": "11 March 1952",
    "death_date": "11 May 2001",
    "revision": 2,
}

FAKE_USER = {
    "key": "/people/testuser",
    "displayname": "Test User",
    "type": {"key": "/type/user"},
    "revision": 1,
}

# Each tuple: (url_suffix, olid_suffix, expected_data)
ENTITY_TYPE_CASES = [
    ("works", "OL123W", FAKE_WORK),
    ("books", "OL1M", FAKE_EDITION),
    ("authors", "OL1A", FAKE_AUTHOR),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create a TestClient for just the entities router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _mock_site(site_get_return: object, site_save_return: object | None = None):
    """Build a fake ``site`` object that :func:`_entity_get` and
    :func:`_entity_put` can talk to.

    Parameters
    ----------
    site_get_return
        The value ``site.get(key, revision=...)`` should return.
        Pass ``None`` to simulate a non-existent document (the handler
        checks ``if thing is None: return 404``).
        For PUT-only tests this is unused (PUT doesn't fetch), so pass
        any value (e.g. ``{}``) when only ``site_save_return`` matters.
    site_save_return
        The value ``site.save(body, comment=...)`` should return
        (default ``None``).  Tests that exercise PUT should pass a
        real dict here.

    Returns
    -------
    MagicMock
        The fake-site instance, so callers can add extra assertions
        (e.g. ``fake_site.get.assert_called_with(...)``).
    """
    fake_site = MagicMock()

    # Set up GET behaviour
    if site_get_return is None:
        fake_site.get.return_value = None  # entity not found
    else:
        fake_thing = MagicMock()
        fake_thing.dict.return_value = site_get_return
        fake_site.get.return_value = fake_thing

    # Set up PUT behaviour (may be None for GET-only tests)
    if site_save_return is not None:
        fake_site.save.return_value = site_save_return

    return fake_site


def _stub_site(monkeypatch, fake_site: MagicMock):
    """Replace the module-level ``site`` ContextVar with a MagicMock
    whose ``.get()`` returns *fake_site*.

    ``monkeypatch.setattr`` can't directly replace ``.get`` on a
    ``contextvars.ContextVar`` because its ``get`` attribute is
    read-only, so we replace the entire module-level variable."""
    mock_cv = MagicMock()
    mock_cv.get.return_value = fake_site
    monkeypatch.setattr("openlibrary.fastapi.entities.site", mock_cv)


# ===================================================================
# GET tests
# ===================================================================


class TestEntityGet:
    """Tests for ``GET /{entity_type}/{id}.json`` routes."""

    # -- happy-path -------------------------------------------------------

    @pytest.mark.parametrize(("entity_type", "olid", "expected"), ENTITY_TYPE_CASES)
    def test_get_returns_entity(self, client, monkeypatch, entity_type, olid, expected):
        """Fetching an existing entity returns 200 with its full JSON."""
        _stub_site(monkeypatch, _mock_site(expected))
        resp = client.get(f"/{entity_type}/{olid}.json")

        assert resp.status_code == 200, f"Expected 200 for /{entity_type}/{olid}.json"
        assert resp.json() == expected

    def test_get_people_returns_entity(self, client, monkeypatch):
        """Fetching an existing user profile returns 200."""
        _stub_site(monkeypatch, _mock_site(FAKE_USER))
        resp = client.get("/people/testuser.json")

        assert resp.status_code == 200
        assert resp.json() == FAKE_USER

    # -- 404 --------------------------------------------------------------

    @pytest.mark.parametrize(
        ("path", "expected_key"),
        [
            ("/works/OL999W.json", "/works/OL999W"),
            ("/books/OL999M.json", "/books/OL999M"),
            ("/authors/OL999A.json", "/authors/OL999A"),
            ("/people/nobody.json", "/people/nobody"),
        ],
    )
    def test_get_not_found(self, client, monkeypatch, path, expected_key):
        """A non-existent entity returns 404 with ``notfound`` JSON."""
        _stub_site(monkeypatch, _mock_site(None))
        resp = client.get(path)

        assert resp.status_code == 404
        assert resp.json() == {"error": "notfound", "key": expected_key}

    # -- revision query-param ---------------------------------------------

    def test_get_with_revision(self, client, monkeypatch):
        """``?v=N`` should be forwarded to ``site.get(key, revision=N)``."""
        fake_site = _mock_site(FAKE_WORK)
        _stub_site(monkeypatch, fake_site)

        resp = client.get("/works/OL123W.json?v=3")
        assert resp.status_code == 200
        fake_site.get.assert_called_with("/works/OL123W", revision=3)

    def test_get_with_revision_for_people(self, client, monkeypatch):
        """``?v=N`` should also work for the people endpoint."""
        fake_site = _mock_site(FAKE_USER)
        _stub_site(monkeypatch, fake_site)

        resp = client.get("/people/testuser.json?v=1")
        assert resp.status_code == 200
        fake_site.get.assert_called_with("/people/testuser", revision=1)

    # -- text/plain -------------------------------------------------------

    @pytest.mark.parametrize("path", ["/works/OL123W.json", "/people/testuser.json"])
    def test_get_text_plain(self, client, monkeypatch, path):
        """``?text=true`` should return the raw JSON with ``text/plain`` content-type."""
        fake_data = FAKE_WORK if "works" in path else FAKE_USER
        _stub_site(monkeypatch, _mock_site(fake_data))

        resp = client.get(f"{path}?text=true")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        # Strip newlines from response text for comparison
        assert json.loads(resp.text) == fake_data

    # -- callback (JSONP) -------------------------------------------------

    @pytest.mark.parametrize(
        ("path", "expected_data"),
        [
            ("/works/OL123W.json?callback=myFunc", FAKE_WORK),
            ("/people/testuser.json?callback=cb", FAKE_USER),
        ],
    )
    def test_get_jsonp(self, client, monkeypatch, path, expected_data):
        """``?callback=functionName`` should wrap the response as JSONP."""
        _stub_site(monkeypatch, _mock_site(expected_data))

        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.text.startswith("myFunc(") or resp.text.startswith("cb(")
        # The JSONP body should contain the serialized entity
        assert json.dumps(expected_data) in resp.text

    # -- validation errors ------------------------------------------------

    @pytest.mark.parametrize(
        "bad_path",
        [
            "/works/OL0W.json",
            "/works/OL-1W.json",
            "/books/OL0M.json",
            "/books/OL-5M.json",
            "/authors/OL0A.json",
            "/authors/OL-3A.json",
        ],
    )
    def test_get_invalid_olid_rejected(self, client, bad_path):
        """OL IDs must be positive integers — 0 and negatives should be 422."""
        resp = client.get(bad_path)
        assert resp.status_code == 422, f"Expected 422 for {bad_path}"

    # -- ClientException --------------------------------------------------

    def test_get_client_exception_500(self, client, monkeypatch):
        """A ClientException with a 5xx status returns 500."""
        fake_site = MagicMock()
        exc = ClientException("500 Internal Server Error", "Internal error")
        exc.status = "500 Internal Server Error"
        fake_site.get.side_effect = exc
        _stub_site(monkeypatch, fake_site)

        resp = client.get("/works/OL123W.json")

        assert resp.status_code == 500
        assert resp.json()["error"] == "internal_error"

    def test_get_client_exception_404(self, client, monkeypatch):
        """A ClientException with a 404 status returns that status."""
        fake_site = MagicMock()
        exc = ClientException("404 Not Found", "Not found")
        exc.status = "404 Not Found"
        fake_site.get.side_effect = exc
        _stub_site(monkeypatch, fake_site)

        resp = client.get("/works/OL123W.json")

        assert resp.status_code == 404


# ===================================================================
# PUT tests
# ===================================================================


class TestEntityPut:
    """Tests for ``PUT /{entity_type}/{id}.json`` routes.

    All PUT routes require write access (admin, API usergroup, or bot);
    the autouse fixture overrides ``require_can_write`` to skip that check.
    """

    @pytest.fixture(autouse=True)
    def _write_override(self, client):
        """Override ``require_can_write`` so PUT tests don't need real auth.

        ``CanWriteDep`` is an ``Annotated[..., Depends(require_can_write)]``
        type alias.  ``dependency_overrides`` expects the actual function
        passed to ``Depends()`` as the key.
        """
        client.app.dependency_overrides[require_can_write] = lambda: AuthenticatedUser(
            username="testuser",
            user_key="/people/testuser",
            timestamp="2026-01-01T00:00:00",
        )
        yield
        client.app.dependency_overrides.clear()

    # -- happy-path -------------------------------------------------------

    @pytest.mark.parametrize(
        ("url", "body", "expected_key"),
        [
            ("/works/OL123W.json", {"key": "/works/OL123W", "title": "Updated"}, "/works/OL123W"),
            ("/books/OL1M.json", {"key": "/books/OL1M", "title": "Updated"}, "/books/OL1M"),
            ("/authors/OL1A.json", {"key": "/authors/OL1A", "name": "Updated"}, "/authors/OL1A"),
        ],
    )
    def test_put_updates_entity(self, client, monkeypatch, url, body, expected_key):
        """PUT with a valid body returns 200 and the save result."""
        # PUT handler doesn't use site.get() — pass a dummy value
        fake_site = _mock_site({}, site_save_return={"key": expected_key, "revision": 99})
        _stub_site(monkeypatch, fake_site)

        resp = client.put(url, json=body)

        assert resp.status_code == 200, f"Expected 200 for PUT {url}"
        assert resp.json() == {"key": expected_key, "revision": 99}

    # -- _comment extraction ----------------------------------------------

    def test_put_extracts_comment(self, client, monkeypatch):
        """``_comment`` should be stripped from the body and passed as the
        ``comment`` keyword argument to ``site.save()``."""
        fake_site = _mock_site({}, site_save_return={"key": "/works/OL123W", "revision": 6})
        _stub_site(monkeypatch, fake_site)

        resp = client.put(
            "/works/OL123W.json",
            json={"key": "/works/OL123W", "title": "Updated", "_comment": "my edit comment"},
        )

        assert resp.status_code == 200
        fake_site.save.assert_called_once_with(
            {"key": "/works/OL123W", "title": "Updated"},
            comment="my edit comment",
        )

    def test_put_adds_key_automatically(self, client, monkeypatch):
        """If the body omits ``key``, it should be added automatically before save."""
        fake_site = _mock_site({}, site_save_return={"key": "/works/OL123W", "revision": 6})
        _stub_site(monkeypatch, fake_site)

        resp = client.put("/works/OL123W.json", json={"title": "No Key Given"})

        assert resp.status_code == 200
        fake_site.save.assert_called_once_with(
            {"key": "/works/OL123W", "title": "No Key Given"},
            comment=None,
        )

    # -- key mismatch -----------------------------------------------------

    def test_put_key_mismatch(self, client, monkeypatch):
        """If the body contains a different key than the URL, return 400."""
        fake_site = _mock_site(None)
        _stub_site(monkeypatch, fake_site)

        resp = client.put(
            "/works/OL123W.json",
            json={"key": "/works/OL999W", "title": "Wrong key"},
        )

        assert resp.status_code == 400
        assert resp.json()["error"] == "key_mismatch"
        fake_site.save.assert_not_called()

    # -- ClientException --------------------------------------------------

    def test_put_client_exception(self, client, monkeypatch):
        """A ClientException during save returns the error with the
        appropriate status code."""
        fake_site = MagicMock()
        exc = ClientException("400 Bad Request", "Bad request")
        exc.status = "400 Bad Request"
        fake_site.save.side_effect = exc
        _stub_site(monkeypatch, fake_site)

        resp = client.put(
            "/works/OL123W.json",
            json={"key": "/works/OL123W", "title": "Bad"},
        )

        assert resp.status_code == 400
        assert resp.json()["error"] == "save_failed"

    # -- auth -------------------------------------------------------------

    def test_put_unauthenticated(self, client):
        """Without overriding ``CanWriteDep``, PUT should return 401."""
        # Ensure no override is active for this test
        client.app.dependency_overrides.clear()

        resp = client.put(
            "/works/OL123W.json",
            json={"key": "/works/OL123W", "title": "Test"},
        )

        assert resp.status_code == 401


# ===================================================================
# History mode (?m=history)
# ===================================================================


FAKE_VERSION_HISTORY = [
    {
        "key": "/works/OL123W",
        "revision": 2,
        "id": 42,
        "action": "update",
        "author_id": 524,
        "comment": "Updated title",
        "bot": False,
        "created": "2023-01-01 00:00:00",
        "changes": '[{"key": "/works/OL123W", "revision": 2}]',
        "data": "{}",
        "author": "/people/openlibrary",
        "ip": "127.0.0.1",  # should be stripped
    },
    {
        "key": "/works/OL123W",
        "revision": 1,
        "id": 41,
        "action": "new",
        "author_id": 524,
        "comment": "Created",
        "bot": False,
        "created": "2022-01-01 00:00:00",
        "changes": '[{"key": "/works/OL123W", "revision": 1}]',
        "data": "{}",
        "author": "/people/openlibrary",
        "ip": "127.0.0.1",  # should be stripped
    },
]


class TestEntityHistory:
    """Tests for ``?m=history`` mode on entity endpoints."""

    HISTORY_CASES: ClassVar[list[tuple[str, str, str, list[dict[str, object]]]]] = [
        ("works", "OL123W", "/works/OL123W", FAKE_VERSION_HISTORY),
        ("books", "OL1M", "/books/OL1M", [{**entry, "key": "/books/OL1M"} for entry in FAKE_VERSION_HISTORY]),
        ("authors", "OL1A", "/authors/OL1A", [{**entry, "key": "/authors/OL1A"} for entry in FAKE_VERSION_HISTORY]),
    ]

    @staticmethod
    def _mock_history_site(
        monkeypatch,
        history_data: list[dict[str, object]] | None = None,
    ) -> MagicMock:
        """Set up a fake site whose ``_conn.request`` returns *history_data*."""
        fake_site = MagicMock()
        fake_conn = MagicMock()
        fake_conn.request.return_value = json.dumps(history_data or FAKE_VERSION_HISTORY)
        fake_site._conn = fake_conn
        fake_site.name = "openlibrary"
        _stub_site(monkeypatch, fake_site)
        return fake_site

    # -- returns list (not entity dict) -----------------------------------

    @pytest.mark.parametrize(("entity_type", "olid", "expected_key", "history_data"), HISTORY_CASES)
    def test_history_returns_list(self, client, monkeypatch, entity_type, olid, expected_key, history_data):
        """``?m=history`` returns a list of version entries."""
        self._mock_history_site(monkeypatch, history_data)
        resp = client.get(f"/{entity_type}/{olid}.json?m=history")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Expected a list for history mode"
        assert len(data) == 2
        assert data[0]["key"] == expected_key

    def test_history_people(self, client, monkeypatch):
        """``?m=history`` works for the people endpoint."""
        fake_history = [{"key": "/people/testuser", "revision": 1, "id": 99}]
        self._mock_history_site(monkeypatch, fake_history)
        resp = client.get("/people/testuser.json?m=history")

        assert resp.status_code == 200
        assert resp.json() == fake_history

    # -- IP stripping -----------------------------------------------------

    def test_history_strips_ips(self, client, monkeypatch):
        """The ``ip`` field should be removed from each history entry."""
        self._mock_history_site(monkeypatch)
        resp = client.get("/works/OL123W.json?m=history")

        assert resp.status_code == 200
        for entry in resp.json():
            assert "ip" not in entry, "IP addresses must be stripped from history"

    # -- dispatch (history vs normal) -------------------------------------

    def test_history_dispatch(self, client, monkeypatch):
        """Without ``?m=history``, the normal entity document is returned."""
        _stub_site(monkeypatch, _mock_site(FAKE_WORK))
        resp = client.get("/works/OL123W.json")  # no ?m=history

        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)
        assert resp.json()["key"] == "/works/OL123W"
        assert resp.json()["title"] == FAKE_WORK["title"]

    # -- pagination params ------------------------------------------------

    def test_history_passes_pagination(self, client, monkeypatch):
        """``?offset=`` and ``?limit=`` should be forwarded as query constraints."""
        fake_site = self._mock_history_site(monkeypatch)

        client.get("/works/OL123W.json?m=history&offset=5&limit=10")

        # Check that the inner query dict passed to _conn.request includes offset/limit
        call_args = fake_site._conn.request.call_args
        assert call_args is not None, "_conn.request was not called"
        inner_query = json.loads(call_args[0][3]["query"])
        assert inner_query["offset"] == 5
        assert inner_query["limit"] == 10

    def test_history_passes_author_filter(self, client, monkeypatch):
        """``?author=`` should be forwarded as a query constraint."""
        fake_site = self._mock_history_site(monkeypatch)

        client.get("/works/OL123W.json?m=history&author=/people/admin")

        call_args = fake_site._conn.request.call_args
        assert call_args is not None
        inner_query = json.loads(call_args[0][3]["query"])
        assert inner_query["author"] == "/people/admin"

    # -- JSONP with history -----------------------------------------------

    def test_history_with_callback(self, client, monkeypatch):
        """``?callback=`` should wrap history response as JSONP."""
        self._mock_history_site(monkeypatch)
        resp = client.get("/works/OL123W.json?m=history&callback=myFunc")

        assert resp.status_code == 200
        assert resp.text.startswith("myFunc(")


# ===================================================================
# People-specific behavior
# ===================================================================


class TestPeopleEndpoint:
    """Additional tests specific to the ``/people/{username}.json`` route."""

    def test_people_empty_username_404(self, client):
        """An empty username segment matches no route and returns 404."""
        resp = client.get("/people/.json")
        assert resp.status_code == 404

    def test_people_username_with_dots(self, client, monkeypatch):
        """Usernames containing dots (like ``john.doe``) should be accepted."""
        fake_user = {
            "key": "/people/john.doe",
            "displayname": "John Doe",
            "type": {"key": "/type/user"},
        }
        _stub_site(monkeypatch, _mock_site(fake_user))

        resp = client.get("/people/john.doe.json")
        assert resp.status_code == 200
        assert resp.json()["key"] == "/people/john.doe"

    def test_people_no_put_endpoint(self, client):
        """PUT is not implemented for people — should return 405."""
        resp = client.put("/people/testuser.json", json={"key": "/people/testuser"})
        assert resp.status_code == 405
