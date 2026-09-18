import json
import urllib
from os import system
from os.path import abspath, dirname, join, pardir
from typing import ClassVar

import pytest
import web
from fastapi import FastAPI, Response
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

        async def fake_serve_cover(request, category, key, value, size, default):
            served.update(category=category, key=key, value=value, size=size, default=default)
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


class TestHeadAndOptions:
    """web.py's handle_class mapped HEAD onto GET, and CORSProcessor(cors_everything=True)
    answered every OPTIONS and stamped every response. FastAPI does neither by default."""

    @pytest.fixture
    def client(self, monkeypatch):
        from openlibrary.coverstore.asgi_app import create_app

        async def fake_serve_cover(*a):
            return Response(status_code=200, content=b"jpeg", media_type="image/jpeg")

        monkeypatch.setattr(code, "_serve_cover", fake_serve_cover)
        monkeypatch.setattr(code, "db", type("db", (), {"query": staticmethod(lambda *a, **kw: [])}))
        return TestClient(create_app())

    GET_ROUTES: ClassVar = ["/", "/b/id/1-M.jpg", "/b/id/1.jpg", "/b/query"]

    @pytest.mark.parametrize("path", GET_ROUTES)
    def test_head_matches_get_status(self, client, path):
        assert client.head(path).status_code == client.get(path).status_code == 200

    @pytest.mark.parametrize("path", GET_ROUTES)
    def test_head_sends_no_body(self, client, path):
        assert client.head(path).content == b""

    def test_head_on_a_post_only_route_is_405(self, client):
        assert client.head("/b/upload2").status_code == 405

    @pytest.mark.parametrize("path", ["/", "/b/id/1-M.jpg", "/b/query", "/b/upload2"])
    def test_bare_options_is_answered(self, client, path):
        # no Origin, so CORSMiddleware ignores it; web.py answered these with a 200
        r = client.options(path)
        assert (r.status_code, r.headers.get("access-control-allow-origin")) == (200, "*")

    def test_preflight_is_still_owned_by_cors_middleware(self, client):
        """The cors_everything middleware must sit *inside* CORSMiddleware. Registered the
        other way round it swallows every OPTIONS, and real preflights lose
        Access-Control-Allow-Headers, which makes a browser reject them."""
        r = client.options(
            "/b/id/1-M.jpg",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert "Content-Type" in r.headers.get("access-control-allow-headers", "")

    def test_options_preflight(self, client):
        r = client.options(
            "/b/id/1-M.jpg",
            headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "*"
        assert "GET" in r.headers["access-control-allow-methods"]

    @pytest.mark.parametrize("path", ["/", "/b/id/1-M.jpg", "/b/query"])
    @pytest.mark.parametrize("origin", [None, "https://example.com"])
    def test_acao_is_sent_whether_or_not_an_origin_is_present(self, client, path, origin):
        # unconditional, so a cache can't store an Origin-less response and replay it
        # to a cross-origin request without the header
        r = client.get(path, headers={"Origin": origin} if origin else None)
        assert r.headers.get("access-control-allow-origin") == "*"


class TestCoverCategory:
    """Only books/authors/works exist as categories; anything else must not route."""

    @pytest.fixture
    def client(self, monkeypatch):
        async def fake_serve_cover(*a):
            return Response(status_code=204)

        monkeypatch.setattr(code, "_serve_cover", fake_serve_cover)
        return TestClient(make_app())

    @pytest.mark.parametrize("category", ["a", "b", "w"])
    def test_real_categories_route(self, client, category):
        assert client.get(f"/{category}/id/1-M.jpg").status_code == 204

    @pytest.mark.parametrize("path", ["/x/id/1-M.jpg", "/bb/id/1-M.jpg", "/B/id/1-M.jpg", "/b2/id/1-M.jpg"])
    def test_unknown_categories_are_rejected(self, client, path):
        # 422 from the Literal; no real traffic reaches these, so the code needn't be a 404
        assert client.get(path).status_code == 422

    def test_unknown_category_cannot_reach_upload(self, monkeypatch):
        monkeypatch.setattr(code, "save_image", lambda *a, **kw: pytest.fail("must not reach save_image"))
        assert TestClient(make_app()).post("/x/upload2", files={"data": b"x"}).status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("category", ["a", "b", "w"])
    async def test_olid_lookup_uses_the_right_prefix(self, monkeypatch, category):
        seen = []

        async def fake_get_cover_id(olkeys):
            seen.extend(olkeys)

        monkeypatch.setattr(code, "get_cover_id", fake_get_cover_id)
        await code._query(category, "olid", "OL1X")
        assert seen == [{"a": "/authors/OL1X", "b": "/books/OL1X", "w": "/works/OL1X"}[category]]


class TestIaCovers:
    """archive.org only derives page images at a named size."""

    @pytest.fixture
    def client(self, monkeypatch):
        async def fake_ia_url(identifier, size):
            return f"https://ia/{identifier}-{size}"

        monkeypatch.setattr(code, "get_ia_cover_url", fake_ia_url)
        monkeypatch.setattr(code, "get_details", lambda coverid, size="": None)
        return TestClient(make_app())

    @pytest.mark.parametrize("size", ["S", "M", "L"])
    def test_sized_ia_request_redirects(self, client, size):
        r = client.get(f"/b/ia/someitem-{size}.jpg", follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (302, f"https://ia/someitem-{size}")

    def test_size_less_ia_request_falls_through(self, client):
        # there is no original-size page image; this used to raise KeyError -> 500
        assert client.get("/b/ia/someitem.jpg").status_code in (200, 404)


class TestIaCoverUrl:
    """Exercises the real get_ia_cover_url, stubbing only the HTTP transport --
    stubbing the function itself would miss anything wrong inside it."""

    @staticmethod
    def _patch_transport(monkeypatch, payload):
        import httpx

        from openlibrary.coverstore import utils as cutils

        def handler(request):
            return httpx.Response(200, json=payload)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(cutils, "get_async_session", lambda: client)
        monkeypatch.setattr(code, "get_async_session", lambda: client)

    SCANNED: ClassVar = {"result": {"mediatype": "texts", "repub_state": "4", "imagecount": "100"}}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("size", "expected"), [("S", "w116_h58"), ("M", "w180_h360"), ("L", "w500_h500")])
    async def test_scanned_text_item(self, monkeypatch, size, expected):
        self._patch_transport(monkeypatch, self.SCANNED)
        url = await code.get_ia_cover_url("someitem", size)
        assert url == f"https://archive.org/download/someitem/page/cover_{expected}.jpg"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            {"result": {"mediatype": "movies", "repub_state": "4", "imagecount": "1"}},
            {"result": {"mediatype": "texts", "repub_state": "2", "imagecount": "1"}},
            {"result": {"mediatype": "texts", "repub_state": "4"}},  # no imagecount: not scanned yet
            {},
        ],
    )
    async def test_items_without_a_usable_cover(self, monkeypatch, payload):
        self._patch_transport(monkeypatch, payload)
        assert await code.get_ia_cover_url("someitem", "M") is None

    @pytest.mark.asyncio
    async def test_network_failure_is_swallowed(self, monkeypatch):
        import httpx

        from openlibrary.coverstore import utils as cutils

        def boom(request):
            raise httpx.ConnectTimeout("archive.org is down")

        client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
        monkeypatch.setattr(cutils, "get_async_session", lambda: client)
        monkeypatch.setattr(code, "get_async_session", lambda: client)
        # httpx.RequestError is not an OSError, unlike requests' -- easy to miss when porting
        assert await code.get_ia_cover_url("someitem", "M") is None


class TestCoverKeyCasing:
    """Uppercase keys are a steady slice of production traffic (ISBN/ID/OLID)."""

    @pytest.mark.parametrize("key", ["isbn", "ISBN", "Isbn"])
    def test_key_is_lowercased_before_lookup(self, monkeypatch, key):
        seen = {}

        async def fake_query(category, key, value):
            seen.update(category=category, key=key, value=value)

        monkeypatch.setattr(code, "_query", fake_query)
        TestClient(make_app()).get(f"/b/{key}/978-0-14-118776-1-M.jpg")
        # hyphens stripped, and the key normalized so the isbn branch is reached
        assert seen == {"category": "b", "key": "isbn", "value": "9780141187761"}

    def test_uppercase_id_key_skips_lookup(self, monkeypatch):
        async def fail_query(*a):
            pytest.fail("id keys must not hit _query")

        monkeypatch.setattr(code, "_query", fail_query)
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
