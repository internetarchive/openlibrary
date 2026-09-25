"""The mock IA availability endpoint over real HTTP, with no container required.

``test_e2e.py`` next door covers this endpoint too, but skips unless the
mockservices *container* is reachable -- and GitHub CI runs ``make test-py`` with
no containers, so those tests catch nothing there. This module closes that gap
the same way ``test_matomo_inprocess.py`` does: it serves the *same* mock app
in-process on an ephemeral loopback port and makes real HTTP requests against it.

That matters for this endpoint specifically. The previous stub accepted only
POST while ``lending.get_availability_async()`` issues a GET, so in dev the route
405'd, ``get_availability()`` swallowed the error, and every book resolved to
status="error" -- an endpoint that was silently answering nothing rather than
failing in a way anyone would notice. A test that calls the handler function
directly cannot see a verb mismatch. This can.

The app is served with ``lifespan="off"``, so the loan-changes window starts
empty and nothing calls Solr. The endpoint has two answer sources and which one
applies depends on the identifier, so the tests below seed events explicitly
when they mean to exercise the event-derived path:

* an identifier the loan-changes window knows about gets an event-derived
  answer, which is the one the loan availability updater is built against;
* any other identifier falls through to the variant matrix, which sweeps the
  full CTA state space for dev (``test_every_variant_is_reachable`` in
  ``test_e2e.py`` pins that, and an event-derived answer cannot satisfy it --
  it only ever produces three shapes).
"""

import importlib.util
import pathlib
import threading
import time
from datetime import UTC, datetime

import pytest
import requests

MOCKSERVICES_MAIN = pathlib.Path(__file__).parents[1] / "main.py"

# The fields OL reads off an availability response. Spelled out here rather than
# read from the mock: they are the contract with the real service, and a mock
# that quietly stopped sending one should fail this.
REQUIRED_FIELDS = {
    "status",
    "available_to_browse",
    "available_to_borrow",
    "available_to_waitlist",
    "is_printdisabled",
    "is_readable",
    "is_lendable",
    "is_previewable",
    "identifier",
    "last_loan_date",
    "num_waitlist",
    "last_waitlist_date",
}


def _load_mock_app_module():
    """Import docker/mockservices/main.py by path; it is not an installed package."""
    spec = importlib.util.spec_from_file_location("ol_mockservices_main_availability", MOCKSERVICES_MAIN)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"could not load {MOCKSERVICES_MAIN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mock_module():
    return _load_mock_app_module()


@pytest.fixture(scope="module")
def availability_url(mock_module):
    """Serve the mockservices app on localhost for the duration of the module."""
    uvicorn = pytest.importorskip("uvicorn", reason="uvicorn is needed to serve the mock in-process")
    pytest.importorskip("fastapi", reason="fastapi is needed to build the mock app")

    # port=0 lets the kernel choose and uvicorn bind it, rather than picking a
    # free port and binding it later -- which races under a parallel runner.
    # lifespan="off" keeps the loan-changes seeder (and its Solr calls) out of it.
    config = uvicorn.Config(mock_module.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive():  # pragma: no cover - fail fast with the real cause
            pytest.fail("mock availability server thread died during startup")
        if time.monotonic() > deadline:  # pragma: no cover - CI safety valve
            server.should_exit = True
            pytest.fail("mock availability server did not start within 30s")
        time.sleep(0.05)

    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/services/availability/"

    server.should_exit = True
    thread.join(timeout=10)


def _seed(mock_module, identifier, event_type="borrow"):
    """Put `identifier` into the loan-changes window so the endpoint answers
    from events rather than from the variant matrix."""
    event = mock_module._make_loan_event(identifier, datetime.now(UTC), event_type)
    mock_module._loan_changes.append(event)
    return event


def _ids_in_bucket(mock_module, bucket, count):
    """Find identifiers that hash into a given bucket, so the tests can name a
    multi-copy or waitlisted book without hardcoding crc32 outputs."""
    found = []
    for i in range(10_000):
        candidate = f"mockbook_{i}"
        if mock_module._availability_bucket(candidate) == bucket:
            found.append(candidate)
            if len(found) == count:
                return found
    pytest.fail(f"could not find {count} identifiers in bucket {bucket}")


class TestVerbs:
    def test_get_is_answered(self, availability_url):
        """The bug this endpoint had: OL calls GET, the stub only allowed POST."""
        resp = requests.get(availability_url, params={"identifier": "mockbook_0"}, timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "mockbook_0" in body["responses"]

    def test_post_is_answered(self, availability_url):
        resp = requests.post(availability_url, params={"identifier": "mockbook_0"}, timeout=10)
        assert resp.status_code == 200
        assert "mockbook_0" in resp.json()["responses"]

    def test_no_identifier_returns_an_empty_map_not_an_error(self, availability_url):
        resp = requests.get(availability_url, timeout=10)
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "responses": {}}


class TestResponseShape:
    def test_every_field_ol_reads_is_present(self, availability_url):
        body = requests.get(availability_url, params={"identifier": "mockbook_0"}, timeout=10).json()
        assert set(body["responses"]["mockbook_0"]) >= REQUIRED_FIELDS

    def test_identifier_is_echoed_back(self, availability_url):
        body = requests.get(availability_url, params={"identifier": "mockbook_7"}, timeout=10).json()
        assert body["responses"]["mockbook_7"]["identifier"] == "mockbook_7"

    def test_num_waitlist_is_a_string(self, availability_url):
        """The real service returns it as a string; consumers int() it themselves."""
        body = requests.get(availability_url, params={"identifier": "mockbook_0"}, timeout=10).json()
        assert isinstance(body["responses"]["mockbook_0"]["num_waitlist"], str)

    def test_all_requested_identifiers_are_answered(self, availability_url):
        ids = [f"mockbook_{i}" for i in range(25)]
        body = requests.get(availability_url, params={"identifier": ",".join(ids)}, timeout=10).json()
        assert set(body["responses"]) == set(ids)

    def test_status_agrees_with_the_availability_booleans(self, mock_module, availability_url):
        """Event-derived answers only. The variant matrix also carries `open`
        (open access is readable without a loan) and `error`, so this two-state
        invariant is not true of it and must not be asserted there."""
        ids = [f"statusbook_{i}" for i in range(25)]
        for identifier in ids:
            _seed(mock_module, identifier)
        body = requests.get(availability_url, params={"identifier": ",".join(ids)}, timeout=10).json()
        for identifier, availability in body["responses"].items():
            borrowable = availability["available_to_browse"] or availability["available_to_borrow"]
            expected = "borrow_available" if borrowable else "borrow_unavailable"
            assert availability["status"] == expected, identifier


class TestTwoAnswerSources:
    """Which source answers is decided per identifier, and both must survive.

    Collapsing them either way breaks something real: event-derived everywhere
    makes most CTA states unreachable in dev (only three shapes exist), and
    variant-matrix everywhere makes the endpoint disagree with the changes feed,
    which is the agreement the loan availability updater is tested against.
    """

    def test_an_identifier_with_no_events_gets_a_variant_answer(self, mock_module, availability_url):
        identifier = "no_events_here_0"
        body = requests.get(availability_url, params={"identifier": identifier}, timeout=10).json()
        assert body["responses"][identifier] == mock_module._deterministic_availability(identifier)

    def test_seeding_an_event_switches_that_identifier_to_the_event_source(self, mock_module, availability_url):
        """Same identifier, before and after. The variant matrix is static, so
        any change at all can only have come from the event path."""
        identifier = "switches_source_0"
        before = requests.get(availability_url, params={"identifier": identifier}, timeout=10).json()["responses"][identifier]
        assert before == mock_module._deterministic_availability(identifier)

        _seed(mock_module, identifier, "borrow")
        after = requests.get(availability_url, params={"identifier": identifier}, timeout=10).json()["responses"][identifier]
        assert after != before, "seeding an event did not change the answer; the sources are collapsed"
        assert after["last_loan_date"] is not None, "an event-derived answer carries the event's timestamp"

    def test_one_request_can_mix_both_sources(self, mock_module, availability_url):
        """The dispatch is per identifier, not per request."""
        seeded, unseeded = "mixed_seeded_0", "mixed_unseeded_0"
        _seed(mock_module, seeded, "borrow")
        body = requests.get(availability_url, params={"identifier": f"{seeded},{unseeded}"}, timeout=10).json()["responses"]
        assert body[seeded]["last_loan_date"] is not None
        assert body[unseeded] == mock_module._deterministic_availability(unseeded)


class TestBuckets:
    """The buckets exist so dev has a book in each interesting lending state."""

    def test_answers_are_stable_across_requests(self, availability_url):
        """crc32, not hash(): a salted hash would change these on every restart."""
        first = requests.get(availability_url, params={"identifier": "mockbook_3"}, timeout=10).json()
        second = requests.get(availability_url, params={"identifier": "mockbook_3"}, timeout=10).json()
        assert first == second

    def test_a_spread_of_identifiers_covers_both_states(self, mock_module, availability_url):
        ids = [f"spreadbook_{i}" for i in range(25)]
        for identifier in ids:
            _seed(mock_module, identifier)
        body = requests.get(availability_url, params={"identifier": ",".join(ids)}, timeout=10).json()
        states = {a["status"] for a in body["responses"].values()}
        assert states == {"borrow_available", "borrow_unavailable"}

    def test_multi_copy_ids_are_available(self, mock_module, availability_url):
        """The whole point of the bucket: a borrow is active and the item is
        still available, because it owns more than one copy. Asserting this
        without an active borrow would pass for a book nobody had borrowed."""
        ids = _ids_in_bucket(mock_module, mock_module._MULTI_COPY_BUCKET, 3)
        for identifier in ids:
            _seed(mock_module, identifier, "borrow")
        body = requests.get(availability_url, params={"identifier": ",".join(ids)}, timeout=10).json()
        for identifier in ids:
            assert body["responses"][identifier]["available_to_borrow"] is True, identifier

    def test_waitlisted_ids_are_unavailable_and_have_a_queue(self, mock_module, availability_url):
        """Unavailable even after a RETURN -- the freed copy goes to the head of
        the queue rather than back on the shelf. Seeding a return is what makes
        this distinguishable from a book that is merely on loan."""
        ids = _ids_in_bucket(mock_module, mock_module._WAITLISTED_BUCKET, 3)
        for identifier in ids:
            _seed(mock_module, identifier, "return")
        body = requests.get(availability_url, params={"identifier": ",".join(ids)}, timeout=10).json()
        for identifier in ids:
            availability = body["responses"][identifier]
            assert availability["available_to_borrow"] is False, identifier
            assert int(availability["num_waitlist"]) > 0, identifier
            assert availability["available_to_waitlist"] is True, identifier

    def test_available_books_have_no_waitlist(self, availability_url):
        ids = [f"mockbook_{i}" for i in range(25)]
        body = requests.get(availability_url, params={"identifier": ",".join(ids)}, timeout=10).json()
        for identifier, availability in body["responses"].items():
            if availability["available_to_borrow"]:
                assert int(availability["num_waitlist"]) == 0, identifier
                assert availability["available_to_waitlist"] is False, identifier


class TestEventWindowJoin:
    """With events present, an active loan makes a normal-bucket book unavailable."""

    def _borrow_event(self, identifier, until):
        return {
            "time": "2026-01-01 00:00:00",
            "identifier": identifier,
            "username": "@dummy",
            "loan_id": "a1000001-0001-4000-8000-000000000001",
            "event_type": "borrow",
            "extra": f'{{"until": "{until}"}}',
            "uid": 1,
        }

    def _normal_bucket_id(self, mock_module):
        for i in range(10_000):
            candidate = f"mockbook_{i}"
            bucket = mock_module._availability_bucket(candidate)
            if bucket not in (mock_module._MULTI_COPY_BUCKET, mock_module._WAITLISTED_BUCKET):
                return candidate
        pytest.fail("could not find an identifier outside the special buckets")

    def test_an_unexpired_borrow_makes_a_normal_book_unavailable(self, mock_module, availability_url):
        identifier = self._normal_bucket_id(mock_module)
        mock_module._loan_changes.append(self._borrow_event(identifier, "2099-01-01 00:00:00"))
        try:
            body = requests.get(availability_url, params={"identifier": identifier}, timeout=10).json()
        finally:
            mock_module._loan_changes.clear()
        assert body["responses"][identifier]["available_to_borrow"] is False

    def test_an_expired_borrow_does_not(self, mock_module, availability_url):
        identifier = self._normal_bucket_id(mock_module)
        mock_module._loan_changes.append(self._borrow_event(identifier, "2000-01-01 00:00:00"))
        try:
            body = requests.get(availability_url, params={"identifier": identifier}, timeout=10).json()
        finally:
            mock_module._loan_changes.clear()
        assert body["responses"][identifier]["available_to_borrow"] is True

    def test_a_multi_copy_book_stays_available_under_an_active_borrow(self, mock_module, availability_url):
        """The whole reason this bucket exists: an event stream cannot predict it."""
        identifier = _ids_in_bucket(mock_module, mock_module._MULTI_COPY_BUCKET, 1)[0]
        mock_module._loan_changes.append(self._borrow_event(identifier, "2099-01-01 00:00:00"))
        try:
            body = requests.get(availability_url, params={"identifier": identifier}, timeout=10).json()
        finally:
            mock_module._loan_changes.clear()
        assert body["responses"][identifier]["available_to_borrow"] is True
