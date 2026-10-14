import asyncio
import contextvars
import pathlib
import re
import threading

import pytest
import web

from infogami.utils import stats
from openlibrary.utils import server_timing
from openlibrary.utils.async_utils import async_bridge

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


def test_noop_outside_request():
    with server_timing.timed("solr"), server_timing.timed_render():
        pass
    assert server_timing._current.get() is None


def test_timed_counts_calls_and_failures(timings):
    with server_timing.timed("solr"):
        pass
    with server_timing.timed("solr") as call:
        call.failed = True
    with pytest.raises(TimeoutError), server_timing.timed("solr"):
        raise TimeoutError
    assert timings.snapshot()["solr"][::2] == (3, 2)
    assert parse(server_timing.format_header(timings))["solr"]["desc"] == '"3 calls (2 failed)"'


def test_nested_renders_count_once(timings):
    with server_timing.timed_render(), server_timing.timed_render():
        pass
    with server_timing.timed_render():
        pass
    assert timings.snapshot()["render"][0] == 2


def test_records_from_threads_and_async_bridge(timings):
    def work():
        for _ in range(500):
            with server_timing.timed("solr"):
                pass

    threads = [threading.Thread(target=contextvars.copy_context().run, args=(work,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    async def query():
        with server_timing.timed("solr"):
            await asyncio.sleep(0)

    async_bridge.run(query())
    assert timings.snapshot()["solr"][0] == 2001


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("http://mockservices:8090/services/loans/loan/", "ia-loans"),
        ("https://archive.org/metadata/someitem", "ia-metadata"),
        ("https://archive.org/advancedsearch.php?q=x", "ia-advancedsearch"),
        ("https://be-api.us.archive.org/fts/v1/search", "ia-fts"),
        ("https://archive.org/someitem", "ia-other"),  # never an identifier
        (None, "ia-other"),
    ],
)
def test_ia_metric_name(url, name):
    assert server_timing.ia_metric_name(url) == name


class TestInfogamiBridge:
    @pytest.fixture(autouse=True)
    def bridge(self):
        server_timing.install_infogami_bridge()
        web.ctx.pop("stats", None)

    def test_records_during_request_without_touching_web_ctx(self, timings):
        stats.begin("memcache.get", key="k")
        stats.end(hit=True)
        stats.begin("archive.org", url="https://archive.org/metadata/x")
        stats.end(error=True)
        stats.end()  # unbalanced; ignored
        assert {name: (count, failures) for name, (count, _, failures) in timings.snapshot().items()} == {"memcache": (1, 0), "ia-metadata": (1, 1)}
        assert "stats" not in web.ctx

    def test_unchanged_outside_request(self):
        stats.begin("infobase")
        stats.end()
        assert stats.stats_summary()["infobase"].count == 1
        web.ctx.pop("stats")


def test_all_metric_names_are_valid():
    root = pathlib.Path(__file__).parents[2]
    names = {name for path in root.rglob("*.py") if "tests" not in path.parts for name in re.findall(r'server_timing\.timed\("([^"]*)"', path.read_text())}
    names |= {"render", "ia-other"} | {f"ia-{s}" for s in server_timing._IA_SERVICES}
    names |= {server_timing._infogami_metric_name(n, {}) for n in ["infobase", "db", "memcache.get"]}
    assert {"solr", "db", "webpy-proxy", "memcache"} <= names
    for name in names:
        assert re.fullmatch(TOKEN, name), name
        assert name not in {"total", "sentry-trace", "baggage"}, name
