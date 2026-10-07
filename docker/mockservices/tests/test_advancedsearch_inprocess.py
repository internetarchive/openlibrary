"""The mock AdvancedSearch endpoint over real HTTP, with no container required.

This endpoint is the entire input to the loan availability updater's v3
poll-and-reconcile design: the daemon asks it "which identifiers are checked
out right now" and reconciles Solr to the answer. So the fixture's own contract
deserves checking rather than hand-verifying, and it has to be checkable where
CI runs -- ``make test-py`` starts no containers, so the container-gated tests
in ``test_e2e.py`` catch nothing there.

The set is served from ``_unavailable`` and replaced wholesale through
``PUT /_test/unavailable``. It used to be derived from the loan-changes window
instead. That coupling was right while the daemon followed events and is wrong
now the index IS the source: a fixture that computes the answer from events
cannot express an index that disagrees with them, and an index disagreeing with
reality is the entire class of failure the poll design has to survive -- a
mid-reindex read that honestly reports a near-empty set is what the daemon's
clear-direction breaker exists for.

Served with ``lifespan="off"``, so the startup seeder (and its Solr calls) stay
out of it and every test states its own set.
"""

import importlib.util
import pathlib
import threading
import time
import urllib.parse

import pytest
import requests

MOCKSERVICES_MAIN = pathlib.Path(__file__).parents[1] / "main.py"

CHECKED_OUT_QUERY = "lending___is_lendable:true AND lending___available_to_borrow:false AND lending___available_to_browse:false"


def _load_mock_app_module():
    spec = importlib.util.spec_from_file_location("ol_mockservices_main_advancedsearch", MOCKSERVICES_MAIN)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"could not load {MOCKSERVICES_MAIN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def base_url():
    mock_module = _load_mock_app_module()
    uvicorn = pytest.importorskip("uvicorn", reason="uvicorn is needed to serve the mock in-process")
    pytest.importorskip("fastapi", reason="fastapi is needed to build the mock app")

    config = uvicorn.Config(mock_module.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive():  # pragma: no cover
            pytest.fail("mock advancedsearch server thread died during startup")
        if time.monotonic() > deadline:  # pragma: no cover
            server.should_exit = True
            pytest.fail("mock advancedsearch server did not start within 30s")
        time.sleep(0.05)

    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def _set_unavailable(base_url: str, identifiers: list[str]) -> None:
    response = requests.put(f"{base_url}/_test/unavailable", json={"identifiers": identifiers}, timeout=10)
    response.raise_for_status()


def _search(base_url: str, **params) -> dict:
    query = urllib.parse.urlencode({"q": CHECKED_OUT_QUERY, "output": "json", **params})
    response = requests.get(f"{base_url}/advancedsearch.php?{query}", timeout=10)
    response.raise_for_status()
    return response.json()


def test_the_set_a_test_puts_is_the_set_the_search_returns(base_url):
    _set_unavailable(base_url, ["bookccc", "bookaaa", "bookbbb"])
    body = _search(base_url, rows=100, page=1)
    assert body["response"]["numFound"] == 3
    assert [doc["identifier"] for doc in body["response"]["docs"]] == ["bookaaa", "bookbbb", "bookccc"]


def test_the_set_can_change_between_two_reads(base_url):
    """The property the whole poll design is tested against: a book returned
    between polls leaves the set, and a book borrowed joins it."""
    _set_unavailable(base_url, ["bookaaa", "bookbbb"])
    first = {doc["identifier"] for doc in _search(base_url, rows=100, page=1)["response"]["docs"]}
    _set_unavailable(base_url, ["bookbbb", "bookccc"])
    second = {doc["identifier"] for doc in _search(base_url, rows=100, page=1)["response"]["docs"]}
    assert first == {"bookaaa", "bookbbb"}
    assert second == {"bookbbb", "bookccc"}


def test_an_empty_set_is_reported_as_empty_rather_than_withheld(base_url):
    """The case the daemon's clear-direction breaker exists for. If the mock
    could not express "the index says nobody is checked out", the breaker could
    not be exercised against the shape that motivates it."""
    _set_unavailable(base_url, [])
    body = _search(base_url, rows=100, page=1)
    assert body["response"]["numFound"] == 0
    assert body["response"]["docs"] == []


def test_paging_walks_the_set_without_repeating_or_skipping(base_url):
    _set_unavailable(base_url, [f"book{i:03d}" for i in range(25)])
    seen: list[str] = []
    for page in range(1, 4):
        body = _search(base_url, rows=10, page=page)
        assert body["response"]["start"] == (page - 1) * 10
        seen += [doc["identifier"] for doc in body["response"]["docs"]]
    assert seen == sorted(f"book{i:03d}" for i in range(25))


def test_numfound_describes_the_set_not_the_page(base_url):
    """A count matched to a truncated page is the one nobody can catch, because
    everything on screen agrees. The daemon's completeness guard reads this."""
    _set_unavailable(base_url, [f"book{i:03d}" for i in range(25)])
    body = _search(base_url, rows=10, page=1)
    assert body["response"]["numFound"] == 25
    assert len(body["response"]["docs"]) == 10


def test_a_request_past_the_window_omits_the_response_envelope(base_url):
    """What the real endpoint does past `start + rows <= 10000`: HTTP 200 with
    no `response` key at all. Read as an empty result it would clear the whole
    seed, so the daemon treats it as an incomplete read -- a branch only
    reachable if the mock fails the same shape."""
    _set_unavailable(base_url, ["bookaaa"])
    body = _search(base_url, rows=1000, page=11)
    assert "response" not in body


def test_a_query_the_mock_does_not_understand_answers_nothing(base_url):
    """A mock that answers queries it does not understand teaches a caller the
    wrong contract. Controlled: the same request with the real query returns
    the set."""
    _set_unavailable(base_url, ["bookaaa"])
    query = urllib.parse.urlencode({"q": "collection:inlibrary", "output": "json", "rows": 100})
    body = requests.get(f"{base_url}/advancedsearch.php?{query}", timeout=10).json()
    assert body["response"]["numFound"] == 0
    assert _search(base_url, rows=100, page=1)["response"]["numFound"] == 1, "control: the real query still answers"


def test_a_malformed_control_request_is_rejected(base_url):
    response = requests.put(f"{base_url}/_test/unavailable", json={"identifiers": "not-a-list"}, timeout=10)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# The changes feed, and specifically the DEFAULT behaviour a cursor bootstrap
# depends on. Both mocks are driven from this module because the hybrid's whole
# premise is that they DISAGREE -- the feed ahead, the index behind -- and a
# test can only stage that if it can set each independently.
# ---------------------------------------------------------------------------


def _set_rows(base_url: str, rows: list[dict]) -> None:
    response = requests.put(f"{base_url}/_test/loan_changes", json={"rows": rows}, timeout=10)
    response.raise_for_status()


def _feed(base_url: str, **params) -> dict:
    query = urllib.parse.urlencode({"action": "changes", **params})
    response = requests.get(f"{base_url}/services/loans/loan/?{query}", timeout=10)
    return response.json() if response.ok else {"_status_code": response.status_code, **response.json()}


def _rows(n: int, start_uid: int = 1) -> list[dict]:
    return [
        {
            "identifier": f"feedbook{i:03d}",
            "uid": start_uid + i,
            "event_type": "borrow",
            "extra": "{}",
            "time": f"2026-10-06 0{i // 10}:{i % 60:02d}:00",
        }
        for i in range(n)
    ]


def test_no_after_uid_returns_the_tail_rather_than_an_error(base_url):
    """The behaviour a cursor bootstrap rests on. Without it there is no way to
    place a cursor at the index's currency without already having one, and the
    daemon falls back to the feed head -- leaving the lag gap uncovered until
    the next borrow."""
    _set_rows(base_url, _rows(50))
    body = _feed(base_url, limit=10)
    assert body["status"] == "OK"
    assert len(body["rows"]) == 10
    assert [r["uid"] for r in body["rows"]] == list(range(41, 51)), "the TAIL, not the head"


def test_after_uid_zero_is_still_an_error(base_url):
    """0 and absent are the same to IA, but a caller passing a literal 0 has
    almost certainly failed to read its own state rather than asked for the
    tail. Answering those two identically would hide that."""
    _set_rows(base_url, _rows(5))
    body = _feed(base_url, after_uid=0)
    assert body.get("_status_code") == 400
    assert body["status"] == "ERROR"


def test_after_uid_returns_only_what_follows_it(base_url):
    _set_rows(base_url, _rows(20))
    body = _feed(base_url, after_uid=15, limit=100)
    assert [r["uid"] for r in body["rows"]] == [16, 17, 18, 19, 20]


def test_the_feed_and_the_index_can_be_set_to_disagree(base_url):
    """The property the hybrid exists for, and the one a fixture deriving one
    from the other could not express: the feed knows about a borrow the index
    has not caught up with."""
    _set_rows(base_url, [{"identifier": "freshborrow", "uid": 99, "event_type": "borrow", "extra": "{}", "time": "2026-10-06 09:00:00"}])
    _set_unavailable(base_url, ["somethingelse"])

    feed_ids = {r["identifier"] for r in _feed(base_url, limit=100)["rows"]}
    index_ids = {d["identifier"] for d in _search(base_url, rows=100, page=1)["response"]["docs"]}
    assert feed_ids == {"freshborrow"}
    assert index_ids == {"somethingelse"}
    assert not (feed_ids & index_ids), "the two mocks must be independently settable"


def test_rows_keep_the_timestamps_a_test_gives_them(base_url):
    """A mark is stamped from the event's own time, so a test has to be able to
    choose it -- otherwise the gate can only be exercised against the wall
    clock, which means waiting."""
    _set_rows(base_url, [{"identifier": "timed", "uid": 7, "event_type": "borrow", "extra": "{}", "time": "2001-09-09 01:46:40"}])
    assert _feed(base_url, limit=10)["rows"][0]["time"] == "2001-09-09 01:46:40"
