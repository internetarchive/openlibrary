"""Tests for the FastAPI QR code endpoint."""

import io
from unittest.mock import patch

import pytest
from PIL import Image


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

        # A non-GET request has no FastAPI handler and falls through to the
        # web.py proxy, which is stubbed to 404 in tests.
        assert response.status_code == 404
