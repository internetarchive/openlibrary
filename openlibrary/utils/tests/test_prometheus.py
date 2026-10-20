import pytest
import web
from prometheus_client import CollectorRegistry

from openlibrary.utils import prometheus
from openlibrary.utils.sentry import InfogamiRoute


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("/advancedsearch", "/advancedsearch", "/advancedsearch"),
        ("/", "/", "/"),
        (r"/works/OL(\d+)W/notes", "/works/OL1W/notes", "/works/OL{work_id}W/notes"),
        (r"(/works/OL\d+W|/books/OL\d+M)/widget", "/books/OL1M/widget", "/books/OL{edition_id}M/widget"),
        (r"((?:/people/[^/]+)?/(?:lists|series)/OL\d+L)/editions", "/people/foo/lists/OL1L/editions", "/people/{username}/lists/{list_id}/editions"),
        (r"((?:/people/[^/]+)?/(?:lists|series)/OL\d+L)/editions", "/series/OL1L/editions", "/series/{list_id}/editions"),
        (r"/people/([^/]+)/books/already-read/year/([0-9]+)", "/people/x/books/already-read/year/2024", "/people/{username}/books/already-read/year/{key}"),
        (r"/borrow/ia/(.*)", "/borrow/ia/foo00bar", "/borrow/ia/{key:path}"),
        (r"/(oclc|lccn|ia|OCLC|LCCN|IA)/([^/]*)(/.*)?", "/ia/foo/bar", "/ia/{key}/{key2:path}"),
        (r"/admin(?:/.*)?", "/admin", "/admin"),
        ("/sw.js", "/sw.js", "/sw.js"),  # an unescaped dot is not a parameter
        (r"((?:/people/[^/]+)?/(?:lists|series)/OL\d+L)/preview.png", "/people/foo/lists/OL1L/preview.png", "/people/{username}/lists/{list_id}/preview.png"),
        ("/data/ol_dump(_editions|_works)_latest.txt.gz", "/data/ol_dump_editions_latest.txt.gz", "/data/ol_dump_editions_latest.txt.gz"),
        (r"(?<=x)/lookbehind", "/lookbehind", r"(?<=x)/lookbehind"),  # unsupported: the pattern itself
    ],
)
def test_route_template(pattern, path, expected):
    assert prometheus.route_template(pattern, path) == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("/books/OL1M", "/books/OL{edition_id}M"),
        ("/works/OL1W", "/works/OL{work_id}W"),
        ("/authors/OL1A", "/authors/OL{author_id}A"),
        ("/lists/OL1L", "/lists/{list_id}"),
        ("/works/OL1W/Some_Title", "/works/OL{work_id}W/{title}"),
        ("/people/openlibrary", "/people/{username}"),
        ("/about/help", "/{key:path}"),
    ],
)
def test_key_template(key, expected):
    assert prometheus._key_template(key) == expected


def test_with_title_puts_back_the_readable_url_slug():
    assert prometheus._with_title("/books/OL{edition_id}M", "/books/OL1M", "/books/OL1M/Some_Title") == "/books/OL{edition_id}M/{title}"
    assert prometheus._with_title("/works/OL{work_id}W/edit", "/works/OL1W/edit", "/works/OL1W/Title/edit") == "/works/OL{work_id}W/{title}/edit"
    assert prometheus._with_title("/search", "/search", "/search") == "/search"


@pytest.mark.parametrize(
    ("route", "requested_path", "expected"),
    [
        (InfogamiRoute(r"/works/OL(\d+)W/notes", encoding="json", path="/works/OL1W/notes.json"), "/works/OL1W/notes.json", "/works/OL{work_id}W/notes.json"),
        # /addbook changes the path to the new book's; the route was found before it did
        (InfogamiRoute("/addbook", path="/addbook"), "/addbook", "/addbook"),
        (InfogamiRoute("^/books/[^/]*$", path="/books/OL1M"), "/books/OL1M/Some_Title", "/books/OL{edition_id}M/{title}"),
        (InfogamiRoute("^/books/[^/]*$", mode="edit", path="/books/OL1M"), "/books/OL1M/Some_Title", "/books/OL{edition_id}M/{title}?m=edit"),
        (InfogamiRoute("<other>", path="/people/openlibrary"), "/people/openlibrary", "/people/{username}"),
    ],
)
def test_infogami_route_name(monkeypatch, route, requested_path, expected):
    monkeypatch.setattr(prometheus.infogami_app, "pages", {r"/works/OL(\d+)W/notes": {}, "/addbook": {}})
    assert prometheus.infogami_route_name(route, requested_path) == expected


def test_fastapi_routes_name_webpy_requests():
    assert prometheus.fastapi_route_name("GET", "/works/OL1W/editions.json") == "/works/OL{work_id}W/editions.json"
    assert prometheus.fastapi_route_name("GET", "/people/foo/lists/OL1L.json") == "/people/{username}/lists/{list_id}.json"
    assert prometheus.fastapi_route_name("GET", "/not-a-fastapi-route") is None


@pytest.fixture
def registry():
    return CollectorRegistry()


@pytest.fixture
def app(registry, monkeypatch):
    monkeypatch.setattr(prometheus, "find_infogami_route", lambda: InfogamiRoute("<other>"))
    monkeypatch.setattr(prometheus, "infogami_route_name", lambda route, requested_path: "/things/{key}")

    class thing:
        def GET(self, name=""):
            if name == "missing":
                raise web.notfound()
            return "hello"

        def POST(self, name=""):
            web.ctx.path = "/authors/OL1A"  # as /addauthor does
            return "created"

    app = web.application(("/things/(.*)", "thing", "/works/OL1W/editions.json", "thing"), {"thing": thing})
    instrumentation = prometheus.request_metrics("webpy", registry=registry)
    assert instrumentation
    app.add_processor(prometheus.WebPyPrometheusProcessor(instrumentation))
    app.add_processor(web.loadhook(prometheus.capture_infogami_route))
    return app


def requests_total(registry, handler, status="200"):
    labels = {"method": "GET", "status": status, "handler": handler, "server": "webpy"}
    return registry.get_sample_value("http_requests_total", labels)


def test_webpy_records_fastapi_metrics(app, registry):
    app.request("/things/a")
    app.request("/things/b")
    app.request("/things/missing")

    assert requests_total(registry, "/things/{key}") == 2
    assert requests_total(registry, "/things/{key}", status="404") == 1
    labels = {"method": "GET", "handler": "/things/{key}", "server": "webpy"}
    assert registry.get_sample_value("http_request_duration_seconds_count", labels) == 3
    assert registry.get_sample_value("http_request_duration_seconds_bucket", labels | {"le": "60.0"}) == 3
    assert registry.get_sample_value("http_response_size_bytes_sum", {"handler": "/things/{key}", "server": "webpy"}) >= 2 * len("hello")


def test_webpy_uses_the_fastapi_route_name(app, registry):
    app.request("/works/OL1W/editions.json")
    assert requests_total(registry, "/works/OL{work_id}W/editions.json") == 1


def test_webpy_finds_the_route_before_the_handler_changes_the_path(app, registry, monkeypatch):
    monkeypatch.setattr(prometheus, "find_infogami_route", lambda: InfogamiRoute(web.ctx.path))
    monkeypatch.setattr(prometheus, "infogami_route_name", lambda route, requested_path: route.route)
    app.request("/things/new", method="POST")
    labels = {"method": "POST", "status": "200", "handler": "/things/new", "server": "webpy"}
    assert registry.get_sample_value("http_requests_total", labels) == 1


def test_webpy_skips_excluded_handlers(app, registry, monkeypatch):
    monkeypatch.setattr(prometheus, "infogami_route_name", lambda route, requested_path: "/metrics")
    app.request("/things/a")
    assert requests_total(registry, "/metrics") is None
