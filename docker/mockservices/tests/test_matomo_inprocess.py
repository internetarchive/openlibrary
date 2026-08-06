"""End-to-end retention scoring over real HTTP, with no container required.

``test_e2e.py`` next door covers the same ground but skips unless the
mockservices *container* is reachable -- and GitHub CI runs ``make test-py`` with
no containers at all, so those tests skip there and catch nothing. This module
closes that gap: it serves the *same* mock app in-process on an ephemeral
loopback port, so the real ``MatomoClient`` makes real HTTP requests and the real
scorer consumes real JSON, on every CI run.

It lives here rather than under ``openlibrary/tests/`` deliberately.
``openlibrary/conftest.py`` has an autouse ``no_requests`` fixture that blocks
``requests`` outright, and overriding a repo-wide safety net to let one test
through is the wrong trade. This directory is already outside that guard,
already collected by ``make test-py``, and already the home for tests that speak
to a mock service over HTTP.

That matters because every bug this pipeline has shipped lived precisely in the
seam between Matomo's wire format and our parsing of it -- reading ``dimension1``
from a nested structure the API never returns, and mapping ``read`` to an event
category that does not exist. Unit tests with a stubbed client cannot see either
of those. This can.

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

from openlibrary.core import retention
from openlibrary.core.matomo import MatomoClient

MOCKSERVICES_MAIN = pathlib.Path(__file__).parents[1] / "main.py"

# The 12-visit default feed, worked out by hand. See TestMatomoMock in
# docker/mockservices/tests/test_e2e.py for the per-visit derivation.
#   visitor    210 x 0.01 =   2.10  (2 patrons)
#   registrant 210 x 0.20 =  42.00  (2 patrons)
#   returning  315 x 0.50 = 157.50  (7 patrons)
#   retained     5 x 1.00 =   5.00  (1 patron)
EXPECTED_R_TOTAL = 206.60
EXPECTED_CONTRIBUTIONS = {"visitor": 2.10, "registrant": 42.00, "returning": 157.50, "retained": 5.00}
EXPECTED_PATRONS = 12


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
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC))
        assert {visit["dimension1"] for visit in visits} == set(retention.COHORTS)

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
        assert [visit["idVisit"] for visit in visits] == [str(i) for i in range(12)]

    def test_page_size_larger_than_the_feed_is_a_single_request(self, client):
        visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=500)
        assert len(visits) == 12


class TestScoringOverHttp:
    def test_r_total_matches_the_hand_computed_value(self, client):
        scores = retention.gather_retention_scores(client=client)
        assert scores["visits"] == 12
        assert scores["r_total"] == pytest.approx(EXPECTED_R_TOTAL)

    def test_every_class_contribution_matches_by_hand(self, client):
        classes = retention.gather_retention_scores(client=client)["classes"]
        for name, expected in EXPECTED_CONTRIBUTIONS.items():
            assert classes[name]["contribution"] == pytest.approx(expected), name

    def test_patron_total_matches(self, client):
        scores = retention.gather_retention_scores(client=client)
        assert sum(c["patrons"] for c in scores["classes"].values()) == EXPECTED_PATRONS

    def test_read_is_actually_scored(self, client):
        """`read` silently scored zero for the prototype's whole life; pin it over the wire."""
        events = retention.gather_retention_scores(client=client)["events"]
        assert events["read"]["points"] == 100
        assert events["read"]["count"] == 4  # CTAClick|Read and CTAClick|Borrow, twice each

    def test_only_schema_events_are_ever_reported(self, client):
        events = retention.gather_retention_scores(client=client)["events"]
        assert set(events) <= set(retention.EVENT_POINTS)

    def test_unmapped_traffic_is_ignored_rather_than_fatal(self, client):
        """The feed includes SearchModal|Open, which the schema has no row for."""
        scores = retention.gather_retention_scores(client=client)
        assert "SearchModal" not in str(scores["events"])
        assert scores["r_total"] > 0

    def test_by_hour_scoring_works_over_the_wire(self, client):
        hourly = retention.gather_retention_scores_by_hour(client=client, hours=2)
        assert len(hourly) == 2
        assert hourly[0]["partial"] is True
        assert hourly[1]["partial"] is False

    def test_gauges_are_emittable_from_a_wire_scored_result(self, client):
        gauges = retention.retention_gauges(retention.gather_retention_scores(client=client))
        assert gauges["stats.ol.retention.total_score.hourly"] == pytest.approx(EXPECTED_R_TOTAL)
        assert not any("+" in key for key in gauges)
