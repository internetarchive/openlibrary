"""Tests for the FastAPI QR code endpoint."""

import io
from unittest.mock import patch

import pytest
import web
from PIL import Image

from openlibrary.plugins.openlibrary.api import create_qrcode as legacy_create_qrcode


class FakeImage:
    def save(self, buf, format):
        Image.new("RGB", (1, 1), "white").save(buf, format=format)


def assert_valid_png(content: bytes) -> None:
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "PNG"
        assert image.width > 0
        assert image.height > 0


class TestQRCodeEndpoint:
    @pytest.mark.parametrize(
        ("request_path", "expected_qr_url"),
        [
            ("/qrcode", "http://testserver/"),
            ("/qrcode?path=/books/OL1M", "http://testserver/books/OL1M"),
            ("/qrcode?path=", "http://testserver"),
        ],
    )
    def test_generates_qrcode_for_expected_url(self, fastapi_client, request_path, expected_qr_url):
        with patch("openlibrary.fastapi.internal.api.qrcode.make", return_value=FakeImage()) as make_qrcode:
            response = fastapi_client.get(request_path)

        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]
        assert_valid_png(response.content)
        make_qrcode.assert_called_once_with(expected_qr_url)

    def test_returns_valid_png_with_real_qrcode(self, fastapi_client):
        response = fastapi_client.get("/qrcode?path=/books/OL1M")

        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]
        assert_valid_png(response.content)

    def test_only_get_is_registered(self, fastapi_client):
        response = fastapi_client.post("/qrcode", data={"path": "/books/OL1M"})

        assert response.status_code == 405


def test_qrcode_target_url_matches_legacy(fastapi_client):
    legacy_qr_urls = []
    fastapi_qr_urls = []

    with (
        patch("openlibrary.plugins.openlibrary.api.web.ctx", web.storage(home="http://testserver")),
        patch("openlibrary.plugins.openlibrary.api.web.input", return_value=web.storage(path="/books/OL1M")),
        patch("openlibrary.plugins.openlibrary.api.web.header"),
        patch("openlibrary.plugins.openlibrary.api.qrcode.make", side_effect=lambda url: legacy_qr_urls.append(url) or FakeImage()),
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        legacy_create_qrcode().GET()

    with patch("openlibrary.fastapi.internal.api.qrcode.make", side_effect=lambda url: fastapi_qr_urls.append(url) or FakeImage()):
        response = fastapi_client.get("/qrcode?path=/books/OL1M")

    assert response.status_code == 200
    assert legacy_qr_urls == fastapi_qr_urls == ["http://testserver/books/OL1M"]
