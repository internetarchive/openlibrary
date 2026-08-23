from openlibrary.coverstore_fastapi import config


def test_index_exact_body_and_no_content_type(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.content == (
        b"<h1>Open Library Book Covers Repository</h1><div>See "
        b'<a href="https://openlibrary.org/dev/docs/api/covers">Open Library '
        b"Covers API</a> for details.</div>"
    )
    # Legacy plain responses carry no Content-Type at all.
    assert "content-type" not in resp.headers


def test_cors_headers_on_every_response(client):
    resp = client.get("/")
    assert resp.headers["access-control-allow-origin"] == "*"
    assert resp.headers["access-control-allow-method"] == "GET, OPTIONS"
    assert resp.headers["access-control-max-age"] == "86400"


def test_options_short_circuit(client):
    resp = client.options("/b/id/123.jpg")
    assert resp.status_code == 200
    assert resp.content == b""
    assert "content-type" not in resp.headers
    assert resp.headers["access-control-allow-origin"] == "*"

    resp = client.options("/anything/at/all")
    assert resp.status_code == 200


def test_unknown_path_404(client):
    resp = client.get("/zzz")
    assert resp.status_code == 404
    assert resp.text == "not found"
    assert resp.headers["content-type"] == "text/html; charset=utf-8"


def test_method_not_allowed(client):
    resp = client.post("/b/query")
    assert resp.status_code == 405
    assert resp.text == "method not allowed"
    assert resp.headers["content-type"] == "text/html"
    assert resp.headers["allow"] == "GET"

    resp = client.get("/b/upload2")
    assert resp.status_code == 405
    assert resp.headers["allow"] == "POST"


def test_head_served_like_get(client):
    resp = client.head("/")
    assert resp.status_code == 200
    # body suppressed by the server layer; headers identical to GET
    assert resp.headers["access-control-allow-origin"] == "*"


def test_default_image_served_on_miss(client, monkeypatch, tmp_path):
    gif = tmp_path / "empty.gif"
    gif.write_bytes(b"GIF89a-fake-placeholder-bytes")
    monkeypatch.setattr(config, "default_image", str(gif))

    resp = client.get("/b/id/abc.jpg")  # non-numeric id -> lookup fails
    assert resp.status_code == 200
    assert resp.content == gif.read_bytes()
    assert "content-type" not in resp.headers


def test_default_false_gives_404(client, monkeypatch):
    monkeypatch.setattr(config, "default_image", None)

    async def no_row(coverid, size=""):
        return None

    monkeypatch.setattr("openlibrary.coverstore_fastapi.app.get_details", no_row)
    resp = client.get("/b/id/999999999.jpg?default=false")
    assert resp.status_code == 404
    assert resp.text == "404 Not Found"
    assert resp.headers["content-type"] == "text/html; charset=utf-8"


def test_default_url_redirects(client, monkeypatch):
    monkeypatch.setattr(config, "default_image", None)

    async def no_row(coverid, size=""):
        return None

    monkeypatch.setattr("openlibrary.coverstore_fastapi.app.get_details", no_row)
    resp = client.get("/b/id/999999999.jpg?default=http://example.com/x.png")
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://example.com/x.png"
    assert resp.text == "303 See Other"
    assert resp.headers["content-type"] == "text/html"


def test_post_on_root_405(client):
    resp = client.post("/")
    assert resp.status_code == 405
    assert resp.headers["allow"] == "GET"
