# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pytest",
#     "requests",
# ]
# ///

"""Read-only checks against a running coverstore, for before/after a deploy.

Every request here is GET, HEAD or OPTIONS -- nothing uploads, touches or deletes.

Run against production before the deploy, then again after, and diff the two
snapshots:

    COVERS_SNAPSHOT=before.json uv run pytest -m integration tests/integration/test_coverstore_prod.py
    # ...deploy...
    COVERS_SNAPSHOT=after.json  uv run pytest -m integration tests/integration/test_coverstore_prod.py
    diff <(jq -S . before.json) <(jq -S . after.json)

Point it elsewhere with COVERS_BASE_URL (e.g. a staging host).

The assertions cover only behaviour that must be identical on either stack. The
web.py -> FastAPI migration changes a few things deliberately, so the snapshot
records them without asserting -- expect exactly these in the diff:

  * the placeholder image gains `Content-Type: image/gif` (web.py sent none at all)
  * 404 bodies become empty (web.py sent "not found")
  * /query gains `; charset=utf-8`
  * `Access-Control-Allow-Method` (singular, a web.py typo browsers ignored) becomes
    the correct plural `Access-Control-Allow-Methods`, and lists HEAD
  * 304 responses gain `Cache-Control: public`
  * responses gain `Content-Length` (web.py sent none at all)
  * a preflight that asks for a method or header we don't allow returns 400 rather
    than 200. web.py answered 200 but never sent Access-Control-Allow-Headers and
    advertised only its misspelled methods header, so a browser rejected the request
    either way -- only the status code moves.

`ETag`, `Last-Modified`, `Cache-Control` and `Expires` on cover responses are
unchanged, so caches stay valid across the deploy.

Anything else in the diff is a regression worth chasing.
"""

import email.utils
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import ClassVar

import pytest
import requests

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("COVERS_BASE_URL", "https://covers.openlibrary.org").rstrip("/")
SNAPSHOT_PATH = os.environ.get("COVERS_SNAPSHOT")
USER_AGENT = "openlibrary-coverstore-migration-check"
PACING_SECONDS = float(os.environ.get("COVERS_PACING", "0.15"))

# Stable fixtures, chosen to cover each branch of the cover lookup.
COVER_ID_TAR = 240727  # < 6M: served via the tar index
COVER_ID_MID = 5_000_000  # < 6M, different tarball
COVER_ID_LARGE = 12_000_000  # >= 8M: may redirect to the archive.org cluster
ISBN = "9780140328721"
OLID = "OL7353617M"

# Headers worth pinning; recorded for every request in the snapshot.
TRACKED_HEADERS = (
    "content-type",
    "content-length",
    "cache-control",
    "etag",
    "last-modified",
    "expires",
    "location",
    "access-control-allow-origin",
    "access-control-allow-method",  # web.py's singular typo
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-max-age",
    "vary",
)

_snapshot: dict[str, dict] = {}


@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    yield s
    s.close()


def bucket_expires(value):
    """`Expires` is now+delta, so the raw value differs on every run. Keep the
    distinction that matters -- cache-forever vs cache-briefly -- and drop the rest."""
    try:
        delta = email.utils.parsedate_to_datetime(value) - datetime.now(UTC)
    except TypeError, ValueError:
        return f"<unparsable: {value}>"
    days = delta.total_seconds() / 86400
    if days > 365:
        return "<many years>"
    if days > 1:
        return "<days>"
    return "<under a day>"


def body_shape(response):
    """/query returns whichever covers were most recently modified, so its body changes
    between any two runs. Record its shape instead of hashing live data."""
    text = response.text
    if text.startswith("cb("):
        return "jsonp"
    try:
        value = json.loads(text)
    except ValueError:
        return f"non-json, {len(response.content)}b"
    if isinstance(value, list):
        return f"list[{len(value)}] of {sorted({type(v).__name__ for v in value})}"
    if isinstance(value, dict):
        return f"dict[{len(value)}]"
    return type(value).__name__


def record(label, response, volatile_body=False):
    """Store a response's observable surface under `label` for the snapshot diff."""
    body = response.content
    headers = {h: response.headers.get(h) for h in TRACKED_HEADERS if response.headers.get(h)}
    if "expires" in headers:
        headers["expires"] = bucket_expires(headers["expires"])
    entry = {"status": response.status_code, "headers": headers}
    if volatile_body and body:
        entry["body"] = body_shape(response)
    else:
        entry["bytes"] = len(body)
        # a hash rather than the body, so image payloads stay comparable but small
        entry["sha256"] = hashlib.sha256(body).hexdigest()[:16] if body else None
    _snapshot[label] = entry
    return response


def fetch(http, path, method="GET", label=None, **kw):
    assert method in {"GET", "HEAD", "OPTIONS"}, f"{method} would not be read-only"
    kw.setdefault("allow_redirects", False)  # capture the redirect itself, not its target
    kw.setdefault("timeout", 30)
    for attempt in range(3):
        time.sleep(PACING_SECONDS)  # covers nginx rate-limits; see its @429 handler
        try:
            r = http.request(method, BASE_URL + path, **kw)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
            continue
        if r.status_code == 429 and attempt < 2:
            time.sleep(2 ** (attempt + 1))
            continue
        volatile = method == "GET" and path.startswith("/b/query")
        return record(label or f"{method} {path}", r, volatile_body=volatile)
    raise AssertionError("unreachable")


@pytest.fixture(scope="session", autouse=True)
def write_snapshot():
    yield
    if SNAPSHOT_PATH:
        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(_snapshot, f, indent=2, sort_keys=True)
        print(f"\nwrote {len(_snapshot)} observations to {SNAPSHOT_PATH}")


class TestCoverServing:
    @pytest.mark.parametrize("size", ["S", "M"])
    def test_cover_by_id(self, http, size):
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-{size}.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert len(r.content) > 500

    def test_thumbnail_is_smaller_than_medium(self, http):
        small = len(fetch(http, f"/b/id/{COVER_ID_TAR}-S.jpg").content)
        medium = len(fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg").content)
        assert small < medium, (small, medium)

    @pytest.mark.parametrize("suffix", ["-L", ""])
    def test_large_and_original_redirect_to_the_cluster(self, http, suffix):
        """Covers below max_coveritem_index * 10000 are served from archive.org zips.

        The redirect target is built by zipview_url_from_id, so the snapshot pins
        its exact shape.
        """
        r = fetch(http, f"/b/id/{COVER_ID_TAR}{suffix}.jpg")
        if r.status_code == 200:  # not (yet) archived: served inline
            assert r.headers["content-type"] == "image/jpeg"
            return
        assert r.status_code == 302
        item = COVER_ID_TAR // 10_000
        expected = f"archive.org/download/olcovers{item}/olcovers{item}{suffix}.zip/{COVER_ID_TAR}{suffix}.jpg"
        assert r.headers["location"].endswith(expected), r.headers["location"]
        assert r.headers["location"].startswith("https://"), "scheme must survive the nginx proxy"

    @pytest.mark.parametrize("cover_id", [COVER_ID_MID, COVER_ID_LARGE])
    def test_covers_in_other_id_ranges(self, http, cover_id):
        """Different id ranges take different code paths (tar index, db, cluster redirect)."""
        r = fetch(http, f"/b/id/{cover_id}-M.jpg")
        assert r.status_code in (200, 302), r.status_code
        if r.status_code == 302:
            assert "archive.org" in r.headers["location"]


class TestLookupKeys:
    def test_by_isbn(self, http):
        r = fetch(http, f"/b/isbn/{ISBN}-M.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_by_olid(self, http):
        r = fetch(http, f"/b/olid/{OLID}-M.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    @pytest.mark.parametrize("key", ["ISBN", "Isbn"])
    def test_keys_are_case_insensitive(self, http, key):
        """~95 req/min of production traffic uses an uppercase key."""
        r = fetch(http, f"/b/{key}/{ISBN}-M.jpg", label=f"GET /b/{key}/<isbn>-M.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_hyphenated_isbn_without_a_size(self, http):
        """The trailing -1 must not be read as a size. Production serves ~1/min of these."""
        hyphenated = "978-0-14-032872-1"
        r = fetch(http, f"/b/isbn/{hyphenated}.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_hyphenated_isbn_with_a_size(self, http):
        r = fetch(http, "/b/isbn/978-0-14-032872-1-M.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_unknown_size_suffix_is_part_of_the_value(self, http):
        """-X is not a size, so this is a lookup for the id "<id>-X", which won't resolve."""
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-X.jpg")
        assert r.status_code in (200, 404)
        if r.status_code == 200:  # the placeholder, not the real cover
            assert len(r.content) < 500


class TestNotFound:
    MISSING = "/b/id/99999999-M.jpg"

    def test_missing_cover_serves_the_placeholder(self, http):
        r = fetch(http, self.MISSING)
        assert r.status_code == 200
        assert len(r.content) < 500  # the 43-byte empty.gif, not a real cover

    def test_default_false_gives_404(self, http):
        r = fetch(http, self.MISSING + "?default=false")
        assert r.status_code == 404

    def test_default_url_redirects(self, http):
        r = fetch(http, self.MISSING + "?default=https://example.com/x.jpg")
        assert r.status_code in (302, 303)
        assert r.headers["location"] == "https://example.com/x.jpg"


class TestCaching:
    def test_by_id_sets_validators(self, http):
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg", label="GET cover (validators)")
        assert r.headers.get("etag")
        assert r.headers.get("last-modified")
        assert r.headers.get("cache-control") == "public"

    def test_etag_gives_304(self, http):
        etag = http.get(f"{BASE_URL}/b/id/{COVER_ID_TAR}-M.jpg", timeout=30).headers["etag"]
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg", headers={"If-None-Match": etag}, label="GET cover (If-None-Match)")
        assert r.status_code == 304
        assert r.content == b""

    def test_if_modified_since_gives_304(self, http):
        lm = http.get(f"{BASE_URL}/b/id/{COVER_ID_TAR}-M.jpg", timeout=30).headers["last-modified"]
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg", headers={"If-Modified-Since": lm}, label="GET cover (If-Modified-Since)")
        assert r.status_code == 304

    def test_head_honours_conditional_requests(self, http):
        etag = http.get(f"{BASE_URL}/b/id/{COVER_ID_TAR}-M.jpg", timeout=30).headers["etag"]
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg", "HEAD", headers={"If-None-Match": etag}, label="HEAD cover (If-None-Match)")
        assert r.status_code == 304

    def test_stale_validators_still_serve_the_image(self, http):
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg", headers={"If-None-Match": '"stale"'}, label="GET cover (stale etag)")
        assert r.status_code == 200


class TestJsonDetails:
    def test_details_by_id(self, http):
        r = fetch(http, f"/b/id/{COVER_ID_TAR}.json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        d = r.json()
        assert d["id"] == COVER_ID_TAR
        for field in ("olid", "created", "last_modified", "width", "height"):
            assert field in d, field

    def test_details_for_a_missing_cover(self, http):
        r = fetch(http, "/b/id/99999999.json")
        assert r.status_code == 404


class TestQuery:
    @pytest.mark.parametrize("qs", ["", "?limit=2", "?limit=2&details=true", "?cmd=ids&limit=2", "?callback=cb&limit=2"])
    def test_query_shapes(self, http, qs):
        r = fetch(http, f"/b/query{qs}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/javascript")
        if "callback" in qs:
            assert r.text.startswith("cb(")
        else:
            json.loads(r.text)  # must be valid JSON

    def test_limit_is_capped(self, http):
        r = fetch(http, "/b/query?limit=500")
        assert r.status_code == 200
        assert len(json.loads(r.text)) <= 100


class TestHead:
    """web.py mapped HEAD onto GET; FastAPI's APIRoute does not add it, so this regressed once."""

    PATHS: ClassVar = ["/", f"/b/id/{COVER_ID_TAR}-M.jpg", f"/b/id/{COVER_ID_TAR}.json", "/b/query?limit=2"]

    @pytest.mark.parametrize("path", PATHS)
    def test_head_matches_get_status(self, http, path):
        head = fetch(http, path, "HEAD")
        get = http.get(BASE_URL + path, allow_redirects=False, timeout=30)
        assert head.status_code == get.status_code

    @pytest.mark.parametrize("path", PATHS)
    def test_head_sends_no_body(self, http, path):
        assert fetch(http, path, "HEAD", label=f"HEAD {path} (body)").content == b""


class TestCors:
    """CORSProcessor(cors_everything=True) stamped every response, including Origin-less ones."""

    PATHS: ClassVar = ["/", f"/b/id/{COVER_ID_TAR}-M.jpg", f"/b/id/{COVER_ID_TAR}.json", "/b/query?limit=2"]

    @pytest.mark.parametrize("path", PATHS)
    def test_acao_without_an_origin(self, http, path):
        r = fetch(http, path, label=f"GET {path} (no Origin)")
        assert r.headers.get("access-control-allow-origin") == "*"

    @pytest.mark.parametrize("path", PATHS)
    def test_acao_with_an_origin(self, http, path):
        r = fetch(http, path, headers={"Origin": "https://example.com"}, label=f"GET {path} (Origin)")
        assert r.headers.get("access-control-allow-origin") == "*"

    def test_bare_options(self, http):
        r = fetch(http, f"/b/id/{COVER_ID_TAR}-M.jpg", "OPTIONS")
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "*"

    def test_preflight(self, http):
        r = fetch(
            http,
            f"/b/id/{COVER_ID_TAR}-M.jpg",
            "OPTIONS",
            headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
            label="OPTIONS cover (preflight)",
        )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "*"

    @pytest.mark.parametrize(
        ("case", "extra"),
        [
            ("disallowed method", {"Access-Control-Request-Method": "POST"}),
            (
                "disallowed header",
                {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-Custom"},
            ),
        ],
    )
    def test_preflight_that_should_fail(self, http, case, extra):
        """Recorded rather than pinned: web.py answers 200 and FastAPI 400, but a browser
        refuses the request either way, so only the status code moves."""
        r = fetch(
            http,
            f"/b/id/{COVER_ID_TAR}-M.jpg",
            "OPTIONS",
            headers={"Origin": "https://example.com", **extra},
            label=f"OPTIONS cover (preflight, {case})",
        )
        assert r.status_code in (200, 400), r.status_code

    def test_options_on_an_unrouted_path(self, http):
        """web.py's CORSProcessor ran before routing, so even bogus paths answered 200."""
        r = fetch(http, "/nonexistent/path/x.jpg", "OPTIONS")
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "*"


class TestMethods:
    """Only the safe methods are exercised; the write endpoints must still reject them."""

    @pytest.mark.parametrize("path", ["/", f"/b/id/{COVER_ID_TAR}-M.jpg", "/b/query"])
    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_safe_methods_are_allowed(self, http, path, method):
        assert fetch(http, path, method).status_code in (200, 302, 304, 404)

    @pytest.mark.parametrize("path", ["/b/upload2", "/b/touch", "/b/delete"])
    def test_write_endpoints_reject_get(self, http, path):
        """A GET can't mutate anything, and confirms the route still exists but is POST-only."""
        assert fetch(http, path, "GET").status_code == 405
