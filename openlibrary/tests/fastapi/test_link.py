"""Tests for the FastAPI link (api/link) endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import web as web_mod

from infogami.infobase.client import ClientException
from openlibrary.core.auth import ExpiredTokenError, MissingKeyError
from openlibrary.plugins.openlibrary.api import link_ia_ol as legacy_link
from openlibrary.utils.request_context import RequestContextVars, req_context, site


def _link_post(
    client,
    *,
    data=None,
    hmac_return_value=True,
    hmac_side_effect=None,
    edition_exists=True,
    edition_data=None,
    save_side_effect=None,
):
    """POST to /api/link with standardized mocks.

    Sets up fake site, edition, and HMACToken mocks so tests only
    override what they need.
    """
    if data is None:
        data = {"digest": "d", "msg": "ocaid123|OL123M|9999999999"}

    hmac_kw = {}
    if hmac_side_effect is not None:
        hmac_kw["side_effect"] = hmac_side_effect
    else:
        hmac_kw["return_value"] = hmac_return_value

    fake_edition = MagicMock()
    fake_edition.dict.return_value = edition_data or {
        "key": "/books/OL123M",
        "title": "Test Edition",
    }
    fake_site = MagicMock()
    if edition_exists:
        fake_site.get.return_value = fake_edition
    else:
        fake_site.get.return_value = None
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
            patch("openlibrary.fastapi.link.HMACToken.verify", **hmac_kw),
            patch("openlibrary.fastapi.link.accounts.RunAs"),
        ):
            response = client.post("/api/link", data=data)
    finally:
        site.reset(_site_token)
        req_context.reset(_req_token)

    return response, fake_edition, fake_site


class TestLinkIAOL:
    """Test the FastAPI /api/link endpoint."""

    def test_success(self, fastapi_client):
        resp, edition, fake_site = _link_post(fastapi_client)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        edition.dict.assert_called_once_with()
        fake_site.save.assert_called_once_with(
            {
                "key": "/books/OL123M",
                "title": "Test Edition",
                "ocaid": "ocaid123",
            },
            "Associate OCAID with record",
            action="edit-edition-ocaid",
        )

    def test_success_with_custom_ocaid(self, fastapi_client):
        edition_data = {"key": "/books/OL456M", "title": "Another Book"}
        resp, _edition, fake_site = _link_post(
            fastapi_client,
            data={"digest": "d", "msg": "book.ocr456|OL456M|9999999999"},
            edition_data=edition_data,
        )

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        fake_site.save.assert_called_once_with(
            {**edition_data, "ocaid": "book.ocr456"},
            "Associate OCAID with record",
            action="edit-edition-ocaid",
        )

    def test_hmac_failure(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, hmac_return_value=False)
        assert resp.status_code == 401

    def test_expired_token(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, hmac_side_effect=ExpiredTokenError())
        assert resp.status_code == 401

    def test_missing_config_key(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, hmac_side_effect=ValueError())
        assert resp.status_code == 401

    def test_missing_key_error(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, hmac_side_effect=MissingKeyError())
        assert resp.status_code == 503

    def test_malformed_msg_one_part(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, data={"digest": "d", "msg": "onlyone"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid inputs"

    def test_malformed_msg_two_parts(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, data={"digest": "d", "msg": "part1|part2"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid inputs"

    def test_empty_parts(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, data={"digest": "d", "msg": "||"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid inputs"

    def test_edition_not_found(self, fastapi_client):
        resp, _, _ = _link_post(fastapi_client, edition_exists=False)
        assert resp.status_code == 404

    def test_save_failure(self, fastapi_client):
        resp, _, _ = _link_post(
            fastapi_client,
            save_side_effect=ClientException("500 Internal Server Error", "Save failed"),
        )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Save failed"

    def test_response_matches_legacy(self, fastapi_client):
        msg = "ocaid123|OL123M|9999999999"
        form_data = {"digest": "d", "msg": msg}

        legacy_edition = MagicMock()
        legacy_edition.dict.return_value = {
            "key": "/books/OL123M",
            "title": "Test Edition",
        }
        legacy_site = MagicMock()
        legacy_site.get.return_value = legacy_edition

        fastapi_edition = MagicMock()
        fastapi_edition.dict.return_value = {
            "key": "/books/OL123M",
            "title": "Test Edition",
        }
        fastapi_site = MagicMock()
        fastapi_site.get.return_value = fastapi_edition

        _site_token = site.set(MagicMock())
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
            # Minimal web.py request context for the legacy handler
            web_mod.ctx.site = legacy_site
            web_mod.ctx.ip = "127.0.0.1"
            web_mod.ctx.env = {
                "REQUEST_METHOD": "GET",
                "QUERY_STRING": f"digest={form_data['digest']}&msg={form_data['msg']}",
            }

            with (
                patch("openlibrary.plugins.openlibrary.api.HMACToken.verify", return_value=True),
                patch("openlibrary.plugins.openlibrary.api.accounts.RunAs"),
                patch("openlibrary.fastapi.link.HMACToken.verify", return_value=True),
                patch("openlibrary.fastapi.link.accounts.RunAs"),
                pytest.deprecated_call(match="migrated to fastapi"),
            ):
                legacy_resp = json.loads(legacy_link().POST()["rawtext"])

                site.set(fastapi_site)
                fastapi_resp = fastapi_client.post("/api/link", data=form_data)
        finally:
            site.reset(_site_token)
            req_context.reset(_req_token)

        assert fastapi_resp.status_code == 200
        assert fastapi_resp.json() == legacy_resp
        fastapi_site.save.assert_called_once_with(
            legacy_site.save.call_args[0][0],
            legacy_site.save.call_args[0][1],
            action=legacy_site.save.call_args[1]["action"],
        )
