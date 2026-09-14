import json
import urllib
from os import system
from os.path import abspath, dirname, join, pardir

import pytest
import web
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.coverstore import archive, code, config, coverlib, schema, utils

static_dir = abspath(join(dirname(__file__), pardir, pardir, pardir, "static"))


@pytest.fixture(scope="module")
def setup_db():
    """These tests have to run as the openlibrary user."""
    system("dropdb coverstore_test")
    system("createdb coverstore_test")
    config.db_parameters = {
        "dbn": "postgres",
        "db": "coverstore_test",
        "user": "openlibrary",
        "pw": "",
    }
    db_schema = schema.get_schema("postgres")
    db = web.database(**config.db_parameters)
    db.query(db_schema)
    db.insert("category", name="b")


@pytest.fixture
def image_dir(tmpdir):
    tmpdir.mkdir("localdisk")
    tmpdir.mkdir("items")
    config.data_root = str(tmpdir)


class Mock:
    def __init__(self):
        self.calls = []
        self.default = None

    def __call__(self, *a, **kw):
        for a2, kw2, _return in self.calls:
            if (a, kw) == (a2, kw2):
                return _return
        return self.default

    def setup_call(self, *a, **kw):
        _return = kw.pop("_return", None)
        call = a, kw, _return
        self.calls.append(call)


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(code.router)
    return app


class WebTestCase:
    def setup_method(self, method):
        self.browser = TestClient(make_app())

    def jsonget(self, path):
        return self.browser.get(path).json()

    def upload(self, olid, path):
        """Uploads an image in static dir"""
        with open(join(static_dir, path), "rb") as file:
            resp = self.browser.post("/b/upload2", data={"olid": olid}, files={"data": file.read()})
        return resp.json()["id"]

    def delete(self, id, redirect_url=None):
        params = {"id": id}
        if redirect_url:
            params["redirect_url"] = redirect_url
        return self.browser.post("/b/delete", data=params).text

    def static_path(self, path):
        return join(static_dir, path)


@pytest.mark.skip(reason="Currently needs running db and openlibrary user. TODO: Make this more flexible.")
class TestDB:
    def test_write(self, setup_db, image_dir):
        path = static_dir + "/logos/logo-en.png"
        with open(path) as file:
            data = file.read()
        d = coverlib.save_image(data, category="b", olid="OL1M")

        assert "OL1M" in d.filename
        path = config.data_root + "/localdisk/" + d.filename
        with open(path) as file:
            assert file.read() == data


class TestWebapp(WebTestCase):
    def test_get(self):
        assert self.browser.get("/").status_code == 200


class TestCoverRouting:
    """The cover filename patterns are the part of the web.py -> FastAPI port that
    can silently change meaning, so pin the parsing down."""

    @pytest.fixture
    def client(self, monkeypatch):
        served = {}

        def fake_serve_cover(request, category, key, value, size, default):
            served.update(category=category, key=key, value=value, size=size, default=default)
            from fastapi import Response

            return Response(status_code=204)

        monkeypatch.setattr(code, "_serve_cover", fake_serve_cover)
        client = TestClient(make_app())
        client.served = served
        return client

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/b/id/12345-M.jpg", ("b", "id", "12345", "M")),
            ("/b/id/12345.jpg", ("b", "id", "12345", "")),
            # a greedy value must not eat the size out of a hyphenated ISBN
            ("/b/isbn/978-0-14-118776-1-M.jpg", ("b", "isbn", "978-0-14-118776-1", "M")),
            # ...nor treat its last segment as a size when no size was asked for
            ("/b/isbn/978-0-14-118776-1.jpg", ("b", "isbn", "978-0-14-118776-1", "")),
            # an unknown size is part of the value, not a size
            ("/b/id/123-X.jpg", ("b", "id", "123-X", "")),
            ("/a/olid/OL1A-S.jpg", ("a", "olid", "OL1A", "S")),
        ],
    )
    def test_cover_path_parsing(self, client, path, expected):
        assert client.get(path).status_code == 204
        served = client.served
        assert (served["category"], served["key"], served["value"], served["size"]) == expected

    def test_default_param(self, client):
        client.get("/b/id/1-M.jpg?default=false")
        assert client.served["default"] == "false"


class TestCoverKeyCasing:
    """Uppercase keys are a steady slice of production traffic (ISBN/ID/OLID)."""

    @pytest.mark.parametrize("key", ["isbn", "ISBN", "Isbn"])
    def test_key_is_lowercased_before_lookup(self, monkeypatch, key):
        seen = {}

        def fake_query(category, key, value):
            seen.update(category=category, key=key, value=value)

        monkeypatch.setattr(code, "_query", fake_query)
        TestClient(make_app()).get(f"/b/{key}/978-0-14-118776-1-M.jpg")
        # hyphens stripped, and the key normalized so the isbn branch is reached
        assert seen == {"category": "b", "key": "isbn", "value": "9780141187761"}

    def test_uppercase_id_key_skips_lookup(self, monkeypatch):
        monkeypatch.setattr(code, "_query", lambda *a: pytest.fail("id keys must not hit _query"))
        monkeypatch.setattr(code, "get_details", lambda coverid, size="": None)
        assert TestClient(make_app()).get("/b/ID/123-M.jpg").status_code in (200, 404)


@pytest.mark.skip(reason="Currently needs running db and openlibrary user. TODO: Make this more flexible.")
class TestWebappWithDB(WebTestCase):
    def test_touch(self):
        pytest.skip("TODO: touch is no more used. Remove or fix this test later.")

        b = self.browser

        id1 = self.upload("OL1M", "logos/logo-en.png")
        id2 = self.upload("OL1M", "logos/logo-it.png")

        assert id1 < id2
        with open(static_dir + "/logos/logo-it.png") as file:
            assert b.open("/b/olid/OL1M.jpg").read() == file.read()

        b.open("/b/touch", urllib.parse.urlencode({"id": id1}))
        with open(static_dir + "/logos/logo-en.png") as file:
            assert b.open("/b/olid/OL1M.jpg").read() == file.read()

    def test_delete(self, setup_db):
        id1 = self.upload("OL1M", "logos/logo-en.png")
        data = self.delete(id1)

        assert data == "cover has been deleted successfully."

    def test_upload(self):
        b = self.browser

        path = join(static_dir, "logos/logo-en.png")
        with open(path) as file:
            filedata = file.read()
        content_type, data = utils.urlencode({"olid": "OL1234M", "data": filedata})
        b.open("/b/upload2", data, {"Content-Type": content_type})
        assert b.status == 200
        id = json.loads(b.data)["id"]

        self.verify_upload(id, filedata, {"olid": "OL1234M"})

    def test_upload_with_url(self, monkeypatch):
        b = self.browser
        with open(join(static_dir, "logos/logo-en.png")) as file:
            filedata = file.read()
        source_url = "http://example.com/bookcovers/1.jpg"

        mock = Mock()
        mock.setup_call(source_url, _return=filedata)
        monkeypatch.setattr(code, "download", mock)

        content_type, data = utils.urlencode({"olid": "OL1234M", "source_url": source_url})
        b.open("/b/upload2", data, {"Content-Type": content_type})
        assert b.status == 200
        id = json.loads(b.data)["id"]

        self.verify_upload(id, filedata, {"source_url": source_url, "olid": "OL1234M"})

    def verify_upload(self, id, data, expected_info=None):
        expected_info = expected_info or {}
        b = self.browser
        b.open("/b/id/%d.json" % id)
        info = json.loads(b.data)
        for k, v in expected_info.items():
            assert info[k] == v

        response = b.open("/b/id/%d.jpg" % id)
        assert b.status == 200
        assert response.info().getheader("Content-Type") == "image/jpeg"
        assert b.data == data

        b.open("/b/id/%d-S.jpg" % id)
        assert b.status == 200

        b.open("/b/id/%d-M.jpg" % id)
        assert b.status == 200

        b.open("/b/id/%d-L.jpg" % id)
        assert b.status == 200

    def test_archive_status(self):
        id = self.upload("OL1M", "logos/logo-en.png")
        d = self.jsonget("/b/id/%d.json" % id)
        assert d["archived"] is False
        assert d["deleted"] is False

    def test_archive(self):
        b = self.browser

        f1 = web.storage(olid="OL1M", filename="logos/logo-en.png")
        f2 = web.storage(olid="OL2M", filename="logos/logo-it.png")
        files = [f1, f2]

        for f in files:
            f.id = self.upload(f.olid, f.filename)
            f.path = join(static_dir, f.filename)
            with open(f.path) as file:
                assert b.open("/b/id/%d.jpg" % f.id).read() == file.read()

        archive.archive()

        for f in files:
            d = self.jsonget("/b/id/%d.json" % f.id)
            assert "tar:" in d["filename"]
            with open(f.path) as file:
                assert b.open("/b/id/%d.jpg" % f.id).read() == file.read()
