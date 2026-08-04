"""End-to-end retention scoring over real HTTP, with no container required.

``test_e2e.py`` next door covers the same ground but skips unless the
mockservices *container* is reachable -- and GitHub CI runs ``make test-py`` with
no containers at all, so those tests skip there and catch nothing. This module
closes that gap: it serves the *same* mock app in-process on an ephemeral
loopback port, so the real ``MatomoClient`` makes real HTTP requests and parses
real JSON on every CI run.

It lives here rather than under ``openlibrary/tests/`` deliberately.
``openlibrary/conftest.py`` has an autouse ``no_requests`` fixture that blocks
``requests`` outright, and overriding a repo-wide safety net to let one test
through is the wrong trade. This directory is already outside that guard,
already collected by ``make test-py``, and already the home for tests that speak
to a mock service over HTTP.

That matters because the bugs in this area live precisely in the seam between
Matomo's wire format and our parsing of it -- for instance ``dimension1``, which
this endpoint returns flat and which an earlier prototype read from a nested
structure the API never sends, silently mislabelling every visit. Unit tests with
a stubbed client cannot see that. This can.

The mock app is loaded from ``docker/mockservices/main.py`` by path rather than
copied, so there is one definition of the fake feed and it cannot drift from
what the container serves.
"""

import datetime
import importlib.util
import pathlib
import socket
import threading
import time

import pytest
import requests

from openlibrary.core.matomo import MatomoClient

MOCKSERVICES_MAIN = pathlib.Path(__file__).parents[1] / "main.py"

# The mock's default feed size, and the cohorts it cycles through. Asserted here
# so a change to the fake feed cannot quietly invalidate the tests that consume it.
EXPECTED_VISITS = 12
EXPECTED_COHORTS = {"visitor", "d0", "d1+", "d7+", "d14+", "d30+", "d90+"}


def _load_mock_app():
    """Import docker/mockservices/main.py by path; it is not an installed package."""
    spec = importlib.util.spec_from_file_location("ol_mockservices_main", MOCKSERVICES_MAIN)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.skip(f"could not load {MOCKSERVICES_MAIN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def matomo_url():
    """Serve the mockservices app on localhost for the duration of the module."""
    uvicorn = pytest.importorskip("uvicorn", reason="uvicorn is needed to serve the mock in-process")
    pytest.importorskip("fastapi", reason="fastapi is needed to build the mock app")

    port = _free_port()
    config = uvicorn.Config(_load_mock_app(), host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline:  # pragma: no cover - CI safety valve
            server.should_exit = True
            pytest.fail("mock Matomo server did not start within 30s")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}/matomo"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def client(matomo_url):
    return MatomoClient("mock-token", url=matomo_url)


class TestWireFormat:
    def test_dimension1_arrives_flat_on_the_visit(self, client):
        """Bug 1 lived here: `customDimensions` is never returned by this endpoint."""
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC))
        assert visits
        assert visits[0]["dimension1"] == "visitor"
        assert all("customDimensions" not in visit for visit in visits)

    def test_all_seven_cohorts_survive_the_round_trip(self, client):
        """The cohort labels are the contract between Matomo and any future scorer."""
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC))
        assert {visit["dimension1"] for visit in visits} == EXPECTED_COHORTS

    def test_action_details_carry_events_and_page_views(self, client):
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC))
        types = {action["type"] for visit in visits for action in visit["actionDetails"]}
        assert types == {"event", "action"}

    def test_a_caller_cannot_strip_the_token(self, client):
        """Fixed keys are applied after caller params, so the real token always wins."""
        assert client._post("Live.getLastVisitsDetails", token_auth="") != []

    def test_the_mock_rejects_an_unauthenticated_request(self, matomo_url):
        """Matomo answers 200 with an error body rather than an HTTP status code."""
        body = requests.post(f"{matomo_url}/index.php", data={"method": "Live.getLastVisitsDetails"}, timeout=10).json()
        assert body["result"] == "error"


class TestPaginationOverHttp:
    def test_a_short_page_size_still_returns_the_whole_feed_in_order(self, client):
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=5)
        assert [visit["idVisit"] for visit in visits] == [str(i) for i in range(EXPECTED_VISITS)]

    def test_page_size_larger_than_the_feed_is_a_single_request(self, client):
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=500)
        assert len(visits) == EXPECTED_VISITS
