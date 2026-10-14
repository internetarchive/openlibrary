import asyncio
import pathlib
import re

import httpx
import pytest
import web

from infogami.utils import stats
from openlibrary.core.jinja import get_jinja_env
from openlibrary.utils import server_timing
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.solr import Solr

# https://www.w3.org/TR/server-timing/#the-server-timing-header-field
TOKEN = r"[A-Za-z0-9!#$%&'*+\-.^_`|~]+"
METRIC = re.compile(rf'^{TOKEN}(?:;{TOKEN}=(?:{TOKEN}|"(?:[^"\\]|\\.)*"))*$')


def parse(header: str) -> dict[str, dict[str, str]]:
    """Strictly parse a Server-Timing value into {name: {param: value}}."""
    metrics = {}
    for metric in header.split(", "):
        assert METRIC.match(metric), metric
        name, *params = metric.split(";")
        metrics[name] = dict(p.split("=", 1) for p in params)
    return metrics


@pytest.fixture
def timings():
    timings, token = server_timing.start_request()
    yield timings
    server_timing.end_request(token)


def test_timed_counts_calls_and_failures(timings):
    with server_timing.timed("solr"):
        pass
    with server_timing.timed("solr") as call:
        call.failed = True
    with pytest.raises(TimeoutError), server_timing.timed("solr"):
        raise TimeoutError
    with pytest.raises(asyncio.CancelledError), server_timing.timed("solr"):
        raise asyncio.CancelledError  # client went away; not a backend failure
    assert timings.snapshot()["solr"][::2] == (4, 2)
    assert parse(server_timing.format_header(timings))["solr"]["desc"] == '"4 calls (2 failed)"'


@pytest.mark.asyncio
async def test_solr_5xx_counts_as_failed(timings, httpx_mock):
    httpx_mock.add_response(status_code=503)
    await Solr("http://solr:8983/solr/openlibrary").raw_request("select", "q=*:*")
    assert timings.snapshot()["solr"][::2] == (1, 1)


class SlowBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        await asyncio.sleep(0.05)
        yield b"body"


class SyncBody(httpx.SyncByteStream):
    def __iter__(self):
        yield b"body"


def timed_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=server_timing.TimedTransport("svc", httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_timed_transport_counts_5xx_and_errors_as_failed(timings):
    def handler(request):
        if request.url.path == "/down":
            raise httpx.ConnectError("refused")
        return httpx.Response(503 if request.url.path == "/5xx" else 200)

    async with timed_client(handler) as client:
        await client.get("http://svc/ok")
        await client.get("http://svc/5xx")
        with pytest.raises(httpx.ConnectError):
            await client.get("http://svc/down")
    assert timings.snapshot()["svc"][::2] == (3, 2)


@pytest.mark.asyncio
async def test_timed_transport_includes_body_download(timings):
    async with timed_client(lambda request: httpx.Response(200, stream=SlowBody())) as client:
        await client.get("http://svc/")
    count, seconds, _ = timings.snapshot()["svc"]
    assert count == 1
    assert seconds >= 0.05


def test_timed_sync_transport_with_per_call_names(timings):
    def handler(request):
        return httpx.Response(503 if request.url.path == "/5xx" else 200, stream=SyncBody())

    with httpx.Client(transport=server_timing.TimedSyncTransport("svc", httpx.MockTransport(handler))) as client:
        with client.stream("GET", "http://svc/ok") as response:
            assert timings.snapshot() == {}  # still timing until the body is closed
            response.read()
        client.get("http://svc/5xx", extensions={"server_timing": "svc-other"})
    assert {name: (count, failures) for name, (count, _, failures) in timings.snapshot().items()} == {"svc": (1, 0), "svc-other": (1, 1)}


def test_nested_renders_count_once(timings):
    with server_timing.timed_render("render-jinja"), server_timing.timed_render("render-jinja"):
        pass
    with server_timing.timed_render("render-jinja"):
        pass
    assert timings.snapshot()["render-jinja"][0] == 2


def test_async_bridge_records_into_the_request(timings):
    async def query():
        with server_timing.timed("solr"):
            await asyncio.sleep(0)

    async_bridge.run(query())  # runs on async_bridge's own loop thread
    assert timings.snapshot()["solr"][0] == 1


def test_jinja_renders_are_timed(timings):
    get_jinja_env().from_string("{{ x }}").render(x=1)
    assert timings.snapshot()["render-jinja"][0] == 1


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def perf_counter(self) -> float:
        return self.now

    def tick(self, seconds: float) -> str:
        self.now += seconds
        return ""


class TestInfogamiBridge:
    @pytest.fixture(autouse=True)
    def bridge(self):
        server_timing.install_legacy_bridge()
        web.ctx.pop("stats", None)

    def test_records_during_request_without_touching_web_ctx(self, timings):
        stats.begin("memcache.get", key="k")
        stats.end(error=True)  # infogami errors (e.g. not-founds) aren't failures
        stats.end()  # unbalanced; ignored
        web.database(dbn="sqlite", db=":memory:").query("SELECT 1")
        assert {name: (count, failures) for name, (count, _, failures) in timings.snapshot().items()} == {"memcache": (1, 0), "db-legacy": (1, 0)}
        assert "stats" not in web.ctx

    def test_templetor_and_jinja_record_their_own_time(self, timings, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr(server_timing, "time", clock)
        templetor = web.template.Template("$def with (seconds, inner)\n$clock.tick(seconds)$:inner()\n", globals={"clock": clock})
        jinja = get_jinja_env().from_string("{{ clock.tick(5) }}{{ inner() }}")

        # Templetor (1s) -> Jinja (5s) -> Templetor (3s)
        templetor(1, lambda: jinja.render(clock=clock, inner=lambda: templetor(3, str)))

        snapshot = timings.snapshot()
        assert snapshot["render-templetor"] == (2, 4.0, 0)  # the nested one is a second call
        assert snapshot["render-jinja"] == (1, 5.0, 0)  # without the Templetor inside it

    def test_unchanged_outside_request(self):
        stats.begin("infobase")
        stats.end()
        assert stats.stats_summary()["infobase"].count == 1
        web.ctx.pop("stats")


def test_all_metric_names_are_valid():
    root = pathlib.Path(__file__).parents[2]
    named = re.compile(r'server_timing\.(?:timed|timed_render|Timed\w*Transport)\("([^"]*)"|"server_timing": "([^"]*)"')
    names = {a or b for path in root.rglob("*.py") if "tests" not in path.parts for a, b in named.findall(path.read_text())}
    names |= {"render-templetor", "db-legacy"} | {server_timing._infogami_metric_name(n) for n in ["infobase", "memcache.get"]}
    assert {
        "solr",
        "db",
        "db-checkout",
        "db-legacy",
        "render-jinja",
        "render-templetor",
        "webpy-proxy",
        "memcache",
        "ia",
        "ia-loans",
        "ia-fts",
        "ia-metadata",
    } <= names
    for name in names:
        assert re.fullmatch(TOKEN, name), name
        assert name not in {"total", "sentry-trace", "baggage"}, name
