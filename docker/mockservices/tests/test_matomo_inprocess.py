"""The Matomo client against a real HTTP server, with no container required.

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

Note this shares source with the container but not its pinned runtime: the
container installs its own fastapi/uvicorn (``docker/mockservices/requirements.txt``)
while this runs them from the root requirements. Code fidelity, not runtime fidelity.

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
import threading
import time

import pytest
import requests

from openlibrary.core.matomo import MatomoClient

MOCKSERVICES_MAIN = pathlib.Path(__file__).parents[1] / "main.py"

# The cohort labels are the contract between Matomo and any consumer, so they
# are spelled out here independently of the mock. The feed *size* is a property
# of the fixture rather than the contract, so it is read from the mock instead of
# duplicated -- see expected_visits in the fixture below.
EXPECTED_COHORTS = {"visitor", "d0", "d1+", "d7+", "d14+", "d30+", "d90+"}


def _load_mock_app_module():
    """Import docker/mockservices/main.py by path; it is not an installed package."""
    spec = importlib.util.spec_from_file_location("ol_mockservices_main", MOCKSERVICES_MAIN)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        # A breakage, not an unmet precondition: skipping here would silently
        # reopen the CI gap this module exists to close.
        pytest.fail(f"could not load {MOCKSERVICES_MAIN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_mock_app():
    return _load_mock_app_module().app


@pytest.fixture(scope="module")
def expected_visits():
    """The mock's feed size, read from the mock rather than restated here."""
    return _load_mock_app_module().MATOMO_MOCK_VISITS


@pytest.fixture(scope="module")
def matomo_url():
    """Serve the mockservices app on localhost for the duration of the module."""
    uvicorn = pytest.importorskip("uvicorn", reason="uvicorn is needed to serve the mock in-process")
    pytest.importorskip("fastapi", reason="fastapi is needed to build the mock app")

    # port=0 lets the kernel choose and uvicorn bind it, rather than picking a
    # free port and binding it later -- which races under a parallel runner.
    config = uvicorn.Config(_load_mock_app(), host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive():  # pragma: no cover - fail fast with the real cause
            pytest.fail("mock Matomo server thread died during startup")
        if time.monotonic() > deadline:  # pragma: no cover - CI safety valve
            server.should_exit = True
            pytest.fail("mock Matomo server did not start within 30s")
        time.sleep(0.05)

    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/matomo"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def client(matomo_url):
    return MatomoClient("mock-token", url=matomo_url)


def _recent() -> datetime.datetime:
    """A `since` early enough to include the mock's whole fixed-epoch feed."""
    return datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=6)


class TestWireFormat:
    def test_dimension1_arrives_flat_on_the_visit(self, client):
        """This endpoint never returns the nested `customDimensions` it looks like it should."""
        fetch = client.get_visits_since(_recent())
        assert fetch.visits
        assert all(visit["dimension1"] in EXPECTED_COHORTS for visit in fetch.visits)
        assert all("customDimensions" not in visit for visit in fetch.visits)

    def test_every_cohort_label_survives_the_round_trip(self, client):
        """The cohort labels are the contract between Matomo and any consumer."""
        fetch = client.get_visits_since(_recent())
        assert {visit["dimension1"] for visit in fetch.visits} == EXPECTED_COHORTS

    def test_action_details_carry_events_and_page_views(self, client):
        fetch = client.get_visits_since(_recent())
        types = {action["type"] for visit in fetch.visits for action in visit["actionDetails"]}
        assert types == {"event", "action"}

    def test_a_caller_cannot_strip_the_token(self, client, expected_visits):
        """Fixed keys are applied after caller params, so the real token always wins."""
        rows = client._post("Live.getLastVisitsDetails", token_auth="", minTimestamp=0)
        assert len(rows) == expected_visits

    def test_the_mock_rejects_an_unauthenticated_request(self, matomo_url):
        """Matomo answers 200 with an error body rather than an HTTP status code."""
        body = requests.post(f"{matomo_url}/index.php", data={"method": "Live.getLastVisitsDetails"}, timeout=10).json()
        assert body["result"] == "error"


class TestPaginationOverHttp:
    def test_a_short_page_size_still_returns_the_whole_feed(self, client, expected_visits):
        fetch = client.get_visits_since(_recent(), page_size=5)
        assert len(fetch.visits) == expected_visits
        # Newest first, which is the order the real endpoint uses.
        ids = [int(visit["idVisit"]) for visit in fetch.visits]
        assert ids == sorted(ids, reverse=True)

    def test_no_visit_is_returned_twice_across_pages(self, client, expected_visits):
        fetch = client.get_visits_since(_recent(), page_size=5)
        ids = [visit["idVisit"] for visit in fetch.visits]
        assert len(ids) == len(set(ids)) == expected_visits

    def test_a_page_size_over_the_feed_size_returns_everything(self, client, expected_visits):
        fetch = client.get_visits_since(_recent(), page_size=500)
        assert len(fetch.visits) == expected_visits

    def test_a_clean_fetch_is_not_flagged_truncated(self, client):
        fetch = client.get_visits_since(_recent())
        assert fetch.truncated is False
        assert fetch.truncated_reason is None


class TestWindowFiltering:
    """`minTimestamp` is honoured by the mock, so window behaviour is testable.

    The fake feed is stamped from a fixed epoch rather than from the caller's
    filter; deriving it from the filter would make every visit pass by
    construction and this whole class vacuous.
    """

    def test_a_window_after_the_whole_feed_returns_nothing(self, client):
        fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1))
        assert fetch.visits == []
        assert fetch.truncated is False

    def test_a_narrower_window_returns_fewer_visits(self, client, expected_visits):
        module = _load_mock_app_module()
        epoch, interval = module.MATOMO_MOCK_EPOCH, module.MATOMO_MOCK_INTERVAL
        # Halfway through the feed, so roughly half the visits are excluded.
        midpoint = datetime.datetime.fromtimestamp(epoch + (expected_visits // 2) * interval, datetime.UTC)
        assert 0 < len(client.get_visits_since(midpoint).visits) < expected_visits
