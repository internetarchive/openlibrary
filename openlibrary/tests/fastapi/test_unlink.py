"""Tests for the FastAPI unlink (api/unlink) endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infogami.infobase.client import ClientException
from openlibrary.core.auth import ExpiredTokenError, MissingKeyError
from openlibrary.fastapi.unlink import DEFAULT_UNLINK_COMMENT, _make_dark
from openlibrary.utils.request_context import RequestContextVars, req_context, site


class FakeEdition:
    def __init__(self, data):
        self.key = data.get("key", "/books/OL1M")
        self._data = data

    def dict(self):
        return dict(self._data)


def _unlink_post(
    client,
    *,
    data=None,
    hmac_return_value=True,
    hmac_side_effect=None,
    things_results=None,
    save_side_effect=None,
):
    """POST to /api/unlink with standardized mocks.

    Sets up fake site, editions, and HMACToken mocks so tests only
    override what they need.
    """
    if data is None:
        data = {"digest": "d", "msg": "ocaid123|9999999999"}

    hmac_kw = {}
    if hmac_side_effect is not None:
        hmac_kw["side_effect"] = hmac_side_effect
    else:
        hmac_kw["return_value"] = hmac_return_value

    fake_edition = FakeEdition(
        {
            "key": "/books/OL1M",
            "ocaid": "ocaid123",
            "source_records": ["ia:ocaid123", "other:xyz"],
        }
    )
    fake_site = MagicMock()
    fake_site.things.side_effect = things_results or [
        ["/books/OL1M"],
        [],
    ]
    fake_site.get_many.return_value = [fake_edition]
    fake_site.save.return_value = None
    if save_side_effect:
        fake_site.save.side_effect = save_side_effect

    _site_token = site.set(fake_site)
    _req_token = req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )
    try:
        with (
            patch("openlibrary.fastapi.unlink.HMACToken.verify", **hmac_kw),
            patch("openlibrary.fastapi.unlink.accounts.RunAs"),
        ):
            response = client.post("/api/unlink", data=data)
    finally:
        site.reset(_site_token)
        req_context.reset(_req_token)

    return response, fake_site


class TestUnlinkIAOL:
    """Test the FastAPI /api/unlink endpoint."""

    def test_success(self, fastapi_client):
        resp, fake_site = _unlink_post(fastapi_client)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        fake_site.get_many.assert_called_once_with(["/books/OL1M"])
        saved_data = fake_site.save.call_args[0][0]
        assert "ocaid" not in saved_data
        assert saved_data["source_records"] == ["other:xyz"]
        assert fake_site.save.call_args[0][1] == DEFAULT_UNLINK_COMMENT

    def test_comment_passed_through(self, fastapi_client):
        resp, fake_site = _unlink_post(
            fastapi_client,
            data={"digest": "d", "msg": "ocaid123|9999999999", "comment": "Wrong item"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert fake_site.save.call_args[0][1] == "Wrong item"

    def test_empty_comment_uses_default(self, fastapi_client):
        resp, fake_site = _unlink_post(
            fastapi_client,
            data={"digest": "d", "msg": "ocaid123|9999999999", "comment": ""},
        )

        assert resp.status_code == 200
        assert fake_site.save.call_args[0][1] == DEFAULT_UNLINK_COMMENT

    def test_no_editions_found(self, fastapi_client):
        resp, _ = _unlink_post(
            fastapi_client,
            things_results=[[], []],
        )
        assert resp.status_code == 404
        assert resp.content == b""

    def test_hmac_failure(self, fastapi_client):
        resp, _ = _unlink_post(fastapi_client, hmac_return_value=False)
        assert resp.status_code == 401
        assert resp.content == b""

    def test_expired_token(self, fastapi_client):
        resp, _ = _unlink_post(fastapi_client, hmac_side_effect=ExpiredTokenError())
        assert resp.status_code == 401
        assert resp.content == b""

    def test_value_error(self, fastapi_client):
        resp, _ = _unlink_post(fastapi_client, hmac_side_effect=ValueError())
        assert resp.status_code == 401
        assert resp.content == b""

    def test_missing_key_error(self, fastapi_client):
        resp, _ = _unlink_post(fastapi_client, hmac_side_effect=MissingKeyError())
        assert resp.status_code == 503

    def test_malformed_msg_one_part(self, fastapi_client):
        resp, _ = _unlink_post(fastapi_client, data={"digest": "d", "msg": "onlyone"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Invalid inputs"

    def test_empty_msg(self, fastapi_client):
        resp, _ = _unlink_post(fastapi_client, data={"digest": "d", "msg": "|"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Invalid inputs"

    def test_save_failure(self, fastapi_client):
        resp, _ = _unlink_post(
            fastapi_client,
            save_side_effect=ClientException("500 Internal Server Error", "Save failed"),
        )
        assert resp.status_code == 500
        assert resp.json()["error"] == "Save failed"


class TestMakeDark:
    """Test the _make_dark helper function."""

    def test_make_dark_no_comment_uses_default(self):
        edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})
        fake_site = MagicMock()

        _site_token = site.set(fake_site)
        try:
            with patch("openlibrary.fastapi.unlink.accounts.RunAs"):
                _make_dark(edition, "foo123")
        finally:
            site.reset(_site_token)

        comment = fake_site.save.call_args[0][1]
        assert comment == DEFAULT_UNLINK_COMMENT

    def test_make_dark_empty_comment_uses_default(self):
        edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})
        fake_site = MagicMock()

        _site_token = site.set(fake_site)
        try:
            with patch("openlibrary.fastapi.unlink.accounts.RunAs"):
                _make_dark(edition, "foo123", comment="")
        finally:
            site.reset(_site_token)

        comment = fake_site.save.call_args[0][1]
        assert comment == DEFAULT_UNLINK_COMMENT

    def test_make_dark_uses_caller_supplied_comment_verbatim(self):
        edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})
        fake_site = MagicMock()

        _site_token = site.set(fake_site)
        try:
            with patch("openlibrary.fastapi.unlink.accounts.RunAs"):
                _make_dark(edition, "foo123", comment="Wrong item linked during digitization")
        finally:
            site.reset(_site_token)

        comment = fake_site.save.call_args[0][1]
        assert comment == "Wrong item linked during digitization"

    def test_make_dark_still_strips_ocaid_and_source_record(self):
        edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123", "other:xyz"]})
        fake_site = MagicMock()

        _site_token = site.set(fake_site)
        try:
            with patch("openlibrary.fastapi.unlink.accounts.RunAs"):
                _make_dark(edition, "foo123", comment="Wrong Item")
        finally:
            site.reset(_site_token)

        data = fake_site.save.call_args[0][0]
        assert "ocaid" not in data
        assert data["source_records"] == ["other:xyz"]
