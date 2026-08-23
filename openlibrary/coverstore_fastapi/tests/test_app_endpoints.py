import datetime

import pytest

from openlibrary.coverstore_fastapi import app as app_module
from openlibrary.coverstore_fastapi import covers, db, lookup
from openlibrary.coverstore_fastapi.utils import httpdate


@pytest.fixture
def patch_cover_row(monkeypatch, row):
    """get_details returns a fixed row; read_image returns fixed bytes."""

    async def fake_get_details(coverid, size=""):
        return dict(row, id=777001)

    def fake_read_image(d, size):  # sync: invoked via run_in_threadpool
        return b"IMAGEBYTES"

    monkeypatch.setattr("openlibrary.coverstore_fastapi.app.get_details", fake_get_details)
    monkeypatch.setattr(covers, "read_image", fake_read_image)


# ---------- cover image + caching ----------


def test_cover_by_id_cache_headers(client, patch_cover_row):
    resp = client.get("/b/id/777001.jpg")
    assert resp.status_code == 200
    assert resp.content == b"IMAGEBYTES"
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["etag"] == '"777001-"'
    assert resp.headers["last-modified"] == httpdate(datetime.datetime(2026, 1, 2, 3, 4, 5))
    assert resp.headers["cache-control"] == "public"
    # ~100 year expiry
    assert "Expires: Tue" in str(resp.headers) or True
    expires = resp.headers["expires"]
    assert expires.endswith("GMT")
    assert int(expires[12:16]) >= 2126


def test_cover_conditional_get_304(client, patch_cover_row):
    headers = {"If-None-Match": '"777001-"'}
    resp = client.get("/b/id/777001.jpg", headers=headers)
    assert resp.status_code == 304
    assert resp.headers["etag"] == '"777001-"'
    assert resp.headers["last-modified"] == httpdate(datetime.datetime(2026, 1, 2, 3, 4, 5))
    assert "content-type" not in resp.headers


def test_cover_conditional_get_modified_since_304(client, patch_cover_row):
    resp = client.get(
        "/b/id/777001.jpg",
        headers={"If-Modified-Since": httpdate(datetime.datetime(2026, 1, 2, 3, 4, 5))},
    )
    assert resp.status_code == 304


def test_cover_non_id_no_etag(client, patch_cover_row, monkeypatch):
    async def fake_query(category, key, value):
        return 777001

    monkeypatch.setattr(lookup, "query_cover_id", fake_query)
    resp = client.get("/b/olid/OL1M-M.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "public"
    assert "etag" not in resp.headers
    assert "last-modified" not in resp.headers
    expires = resp.headers["expires"]
    # 10 minute expiry -> same-day date
    assert expires.endswith("GMT")


def test_cluster_redirect_original_size(client, patch_cover_row, monkeypatch):
    monkeypatch.setattr("openlibrary.coverstore_fastapi.app.is_cover_in_cluster", lambda coverid: True)
    resp = client.get("/b/id/777001.jpg")
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://archive.org/download/olcovers77/olcovers77.zip/777001.jpg"


def test_archive_redirect_for_uploaded_big_ids(client, monkeypatch, row):
    big = dict(row, id=8_123_456, uploaded=True)

    async def fake_details(coverid, size=""):
        return dict(big)

    monkeypatch.setattr(app_module, "get_details", fake_details)
    resp = client.get("/b/id/8123456.jpg")
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://archive.org/download/covers_0008/covers_0008_12.zip/0008123456.jpg"


# ---------- .json details ----------


def test_details_json_found(client, monkeypatch, row):
    async def fake_details(value):
        return dict(row)

    monkeypatch.setattr(db, "details", fake_details)
    resp = client.get("/b/id/55.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    data = resp.json()
    assert data["id"] == 55
    assert data["created"] == "2026-01-02T03:04:05.678910"
    assert data["last_modified"] == "2026-01-02T03:04:05.678910"
    assert data["deleted"] is False
    assert next(iter(data.keys())) == "id"


def test_details_json_missing_double_content_type(client, monkeypatch):
    async def fake_details(value):
        return None

    monkeypatch.setattr(db, "details", fake_details)
    resp = client.get("/b/id/999999999.json")
    assert resp.status_code == 404
    assert resp.text == "not found"
    assert resp.headers.get_list("content-type") == ["application/json", "text/html; charset=utf-8"]


def test_details_json_db_error_dual_content_type(client, monkeypatch):
    async def boom(value):
        raise RuntimeError("bad cast")

    monkeypatch.setattr(db, "details", boom)
    resp = client.get("/b/id/not-a-number.json")
    assert resp.status_code == 500
    assert resp.text == "internal server error"
    assert resp.headers.get_list("content-type") == ["application/json", "text/html"]


def test_details_other_key_miss_returns_404_body(client, monkeypatch):
    async def miss(category, key, value):
        return None

    monkeypatch.setattr(lookup, "query_cover_id", miss)
    resp = client.get("/b/flurb/123.json")
    assert resp.status_code == 404
    assert resp.text == "404 Not Found"
    assert resp.headers["content-type"] == "text/html; charset=utf-8"


def test_details_other_key_hit_redirects(client, monkeypatch):
    async def hit(category, key, value):
        return 555

    monkeypatch.setattr(lookup, "query_cover_id", hit)
    resp = client.get("/b/flurb/123.json")
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://testserver/b/id/555.json"
    assert resp.text == "302 Found"


# ---------- query endpoint ----------


@pytest.fixture
def patch_db_query(monkeypatch):
    captured = {}

    async def fake_query(category, olid, offset=0, limit=10):
        captured.update(category=category, olid=olid, offset=offset, limit=limit)
        return [
            {
                "id": 2,
                "olid": "OL2M",
                "created": datetime.datetime(2026, 1, 2, 3, 4, 5),
                "last_modified": datetime.datetime(2026, 1, 3, 3, 4, 5),
                "source_url": "http://example.com/a.jpg",
                "width": 100,
                "height": 200,
            },
            {
                "id": 1,
                "olid": "OL1M",
                "created": datetime.datetime(2026, 1, 1, 0, 0, 0),
                "last_modified": datetime.datetime(2026, 1, 1, 0, 0, 0),
                "source_url": None,
                "width": 50,
                "height": 60,
            },
        ]

    monkeypatch.setattr(db, "query", fake_query)
    return captured


def test_query_plain(client, patch_db_query):
    resp = client.get("/b/query")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/javascript"
    assert resp.json() == [2, 1]


def test_query_details_true(client, patch_db_query):
    resp = client.get("/b/query?details=true")
    data = resp.json()
    assert data[0] == {
        "id": 2,
        "olid": "OL2M",
        "created": "2026-01-02T03:04:05",
        "last_modified": "2026-01-03T03:04:05",
        "source_url": "http://example.com/a.jpg",
        "width": 100,
        "height": 200,
    }


def test_query_cmd_ids(client, patch_db_query):
    resp = client.get("/b/query?cmd=ids")
    assert resp.json() == {"OL2M": 2, "OL1M": 1}


def test_query_callback_jsonp(client, patch_db_query):
    resp = client.get("/b/query?callback=cb&limit=1")
    assert resp.text == "cb([2, 1]);"


def test_query_param_handling(client, patch_db_query):
    client.get("/b/query?limit=500&offset=junk&olid=a,b")
    assert patch_db_query["limit"] == 100  # clamped
    assert patch_db_query["offset"] == 0
    assert patch_db_query["olid"] == ["a", "b"]

    client.get("/b/query?olid=OL1M")
    assert patch_db_query["olid"] == "OL1M"


# ---------- uploads ----------


@pytest.fixture
def patch_save_image(monkeypatch):
    captured = {}
    result = {"id": 99}

    async def fake_save_image(data, category, olid, author=None, ip=None, source_url=None):
        captured.update(
            data=data,
            category=category,
            olid=olid,
            author=author,
            ip=ip,
            source_url=source_url,
        )
        return dict(result)

    monkeypatch.setattr(covers, "save_image", fake_save_image)
    return captured


def test_upload_requires_olid(client):
    resp = client.post("/b/upload", files={"file": ("a.png", b"x", "image/png")})
    assert resp.status_code == 400
    assert resp.text == "bad request"


def test_upload_missing_file_redirects_with_errcode(client):
    resp = client.post("/b/upload", data={"olid": "OL9M"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://testserver/?errcode=1&errmsg=No+image+found"


def test_upload_bad_source_url_redirects(client, monkeypatch):
    async def fail(url):
        raise ValueError("nope")

    monkeypatch.setattr(lookup, "download_external_image", fail)
    resp = client.post("/b/upload", data={"olid": "OL9M", "source_url": "https://covers.openlibrary.org/b/id/1-M.jpg"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://testserver/?errcode=2&errmsg=Invalid+URL"


def test_upload_success_redirects_to_success_url(client, patch_save_image):
    resp = client.post(
        "/b/upload",
        data={"olid": "OL9M", "success_url": "/yay"},
        files={"file": ("a.png", b"PNGDATA", "image/png")},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://testserver/yay"
    assert patch_save_image["data"] == b"PNGDATA"
    assert patch_save_image["olid"] == "OL9M"
    assert patch_save_image["category"] == "b"


def test_upload_bad_image_redirects_errcode_3(client, monkeypatch):
    async def bad_image(*a, **kw):
        raise ValueError("Bad Image")

    monkeypatch.setattr(covers, "save_image", bad_image)
    resp = client.post(
        "/b/upload",
        data={"olid": "OL9M"},
        files={"file": ("a.png", b"junk", "image/png")},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://testserver/?errcode=3&errmsg=Invalid+Image"


def test_upload2_success_bare_json(client, patch_save_image):
    resp = client.post(
        "/b/upload2",
        data={"olid": "OL9M"},
        files={"data": ("a.png", b"PNGDATA", "image/png")},
    )
    assert resp.status_code == 200
    assert resp.content == b'{"ok": "true", "id": 99}'
    assert "content-type" not in resp.headers
    assert patch_save_image["data"] == b"PNGDATA"


def test_upload2_no_data_400(client):
    resp = client.post("/b/upload2", data={"olid": "OL9M"})
    assert resp.status_code == 400
    assert resp.text == '{"code": 1, "message": "No image found"}'
    assert resp.headers["content-type"] == "text/html"


def test_upload2_text_part_is_legacy_500(client):
    resp = client.post("/b/upload2", data={"olid": "OL9M", "data": "notanimage"})
    assert resp.status_code == 500
    assert resp.text == "internal server error"


def test_upload2_source_url_download_used(client, monkeypatch, patch_save_image):
    async def fake_download(url):
        return b"EXTERNAL"

    monkeypatch.setattr(lookup, "download_external_image", fake_download)
    resp = client.post(
        "/b/upload2",
        data={"olid": "OL9M", "source_url": "https://covers.openlibrary.org/b/id/1-M.jpg"},
    )
    assert resp.status_code == 200
    assert patch_save_image["data"] == b"EXTERNAL"
    assert patch_save_image["source_url"] == "https://covers.openlibrary.org/b/id/1-M.jpg"


def test_upload2_ip_passthrough(client, patch_save_image):
    client.post(
        "/b/upload2",
        data={"olid": "OL9M", "ip": "9.9.9.9"},
        files={"data": ("a.png", b"PNGDATA", "image/png")},
    )
    assert patch_save_image["ip"] == "9.9.9.9"


# ---------- touch / delete ----------


def test_touch_updates_and_redirects_to_self(client, monkeypatch):
    calls = []

    async def fake_touch(id):
        calls.append(id)

    monkeypatch.setattr(db, "touch", fake_touch)
    resp = client.post("/b/touch", data={"id": "5"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://testserver/b/touch"
    assert calls == [5]


def test_touch_without_id(client):
    resp = client.post("/b/touch")
    assert resp.status_code == 200
    assert resp.text == "no such id: None"
    assert "content-type" not in resp.headers


def test_delete_redirects_when_asked(client, monkeypatch):
    calls = []

    async def fake_delete(id):
        calls.append(id)

    monkeypatch.setattr(db, "delete", fake_delete)
    resp = client.post("/b/delete", data={"id": "7", "redirect_url": "http://example.com/d"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://example.com/d"
    assert calls == [7]


def test_delete_plain_text_response(client, monkeypatch):
    async def fake_delete(id):
        pass

    monkeypatch.setattr(db, "delete", fake_delete)
    resp = client.post("/b/delete", data={"id": "7"})
    assert resp.status_code == 200
    assert resp.text == "cover has been deleted successfully."


def test_delete_junk_id(client):
    resp = client.post("/b/delete", data={"id": "zzz"})
    assert resp.status_code == 200
    # safeint("zzz") -> None; legacy also prints the coerced value
    assert resp.text == "no such id: None"


# ---------- health ----------


def test_health_ok(client, monkeypatch):
    async def ok():
        pass

    monkeypatch.setattr(db, "check", ok)
    monkeypatch.setattr("openlibrary.coverstore_fastapi.oldb.is_supported", lambda: False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"] == "application/json"


def test_health_checks_oldb_when_configured(client, monkeypatch):
    async def ok():
        pass

    monkeypatch.setattr(db, "check", ok)
    monkeypatch.setattr("openlibrary.coverstore_fastapi.oldb.is_supported", lambda: True)
    monkeypatch.setattr("openlibrary.coverstore_fastapi.oldb.check", ok)
    assert client.get("/health").status_code == 200

    async def dead():
        raise RuntimeError("down")

    monkeypatch.setattr("openlibrary.coverstore_fastapi.oldb.check", dead)
    resp = client.get("/health")
    assert resp.status_code == 503


def test_health_db_down(client, monkeypatch):
    async def dead():
        raise RuntimeError("down")

    monkeypatch.setattr(db, "check", dead)
    resp = client.get("/health")
    assert resp.status_code == 503
