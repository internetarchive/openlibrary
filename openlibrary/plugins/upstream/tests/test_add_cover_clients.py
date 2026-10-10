"""POST /books/OL…M/add-cover as scripted clients call it.

openlibrary-client (`Edition.add_bookcover`, `Edition.add_book_cover_from_file`) and
openlibrary-bots' BWBCoverBot post these exact forms, and BWBCoverBot treats an upload
as successful only when the reply contains "Saved!". Change this contract on purpose.
"""

import datetime
import io
from unittest.mock import MagicMock

import pytest
import requests
import web
from PIL import Image as PILImage

from openlibrary.core.models import Image
from openlibrary.plugins.upstream import covers

COVER_URL = "https://example.com/cover.jpg"


def png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (4, 6), "red").save(buf, format="PNG")
    return buf.getvalue()


class FakeEdition:
    key = "/books/OL1M"
    type = web.storage(key="/type/edition")

    def __init__(self):
        self.covers = [7]
        self.saves = []

    def url(self, suffix=""):
        return self.key + suffix

    def get_covers(self):
        return [Image(web.ctx.site, "b", i) for i in self.covers]

    def _save(self, comment=None, action=None, data=None):
        self.saves.append((comment, action, data))


def post_form(files: dict) -> None:
    """Put a multipart body on web.ctx, encoded the way `requests.post(files=...)` encodes it."""
    req = requests.Request("POST", "http://openlibrary.org/books/OL1M/-/add-cover", files=files).prepare()
    assert isinstance(req.body, bytes)
    web.ctx.env = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": req.headers["Content-Type"],
        "CONTENT_LENGTH": str(len(req.body)),
        "wsgi.input": io.BytesIO(req.body),
    }
    web.ctx.path, web.ctx.query = "/books/OL1M/-/add-cover", ""
    web.ctx.pop("_fieldstorage", None)
    web.ctx.pop("data", None)


@pytest.fixture
def setup(monkeypatch, render_template, request_context_fixture):
    request_context_fixture(lang="en")
    book = FakeEdition()
    web.ctx.site = MagicMock(get=lambda key: book if key == book.key else None)
    web.ctx.ip = "127.0.0.1"
    user = MagicMock(key="/people/bwbimportbot", is_read_only=lambda: False)
    monkeypatch.setattr(covers.accounts, "get_current_user", lambda: user)
    # The add form needs macros this fixture doesn't load; what matters is that it isn't the saved page.
    monkeypatch.setattr(covers, "render_template", lambda name, *a, **kw: render_template(name, *a, **kw) if name == "covers/saved" else name)
    monkeypatch.setattr(Image, "info", lambda self, fetch_author=True: web.storage(author=None, created=datetime.datetime(2026, 1, 1), source_url=None))

    uploads = []

    def fake_upload(category, olid, **kwargs):
        data = kwargs["data"]
        uploads.append(kwargs | {"data": data and data.read()})
        return web.storage(id=500)

    monkeypatch.setattr(covers, "upload_to_coverstore", fake_upload)
    return book, uploads


def test_upload_from_file_like_bwbcoverbot(setup):
    book, uploads = setup
    data = png_bytes()
    post_form({"file": ("9781483457550.png", data, "image/png"), "url": (None, "https://"), "upload": (None, "Submit")})

    html = str(covers.add_cover().POST("/books/OL1M"))

    assert "Saved!" in html
    assert uploads == [{"data": data, "source_url": "", "author_key": "/people/bwbimportbot", "ip": "127.0.0.1"}]
    assert book.covers == [500, 7]
    assert book.saves[0][1] == "add-cover"


def test_upload_from_url_like_add_bookcover(setup):
    book, uploads = setup
    post_form({"file": "", "url": COVER_URL, "upload": "submit"})

    html = str(covers.add_cover().POST("/books/OL1M"))

    assert "Saved!" in html
    assert uploads == [{"data": None, "source_url": COVER_URL, "author_key": "/people/bwbimportbot", "ip": "127.0.0.1"}]
    assert book.covers == [500, 7]
    assert book.saves[0][2] == {"url": COVER_URL}


def test_rejected_file_does_not_say_saved(setup):
    book, uploads = setup
    post_form({"file": ("cover.txt", b"not an image", "text/plain"), "url": (None, "https://"), "upload": (None, "Submit")})

    html = str(covers.add_cover().POST("/books/OL1M"))

    assert html == "covers/add"
    assert uploads == []
    assert book.saves == []
